import calendar
import json
import requests
import secrets
import uuid
from datetime import date, datetime, timedelta

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import check_password
from django.http import HttpResponseNotAllowed, JsonResponse
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db import transaction
from django.db.models import Count
from django.db.models import F
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.db import IntegrityError, OperationalError, ProgrammingError

from .decorators import login_required
from .decorators import role_required
from .forms import (
    AppUserForm,
    DoctorAccountLinkForm,
    DoctorInvitationDecisionForm,
    EtablissementForm,
    HealthProfessionalSessionCreateForm,
    MedecinPresenceForm,
    MedecinEtablissementInvitationForm,
    MedecinIndisponibiliteForm,
    MedecinForm,
    PatientForm,
    PersonnelEtablissementPermissionForm,
    RoleForm,
    StaffAppointmentForm,
    UserPasswordResetForm,
)
from .models import AppUser
from .models import ETABLISSEMENT_TYPE_LABELS
from .models import Appointment, Etablissement, ExamSession, ExamSessionActivationPin, Medecin, MedecinEtablissement, MedecinEtablissementInvitation, MedecinHoraireIntervalle, MedecinHoraireSemaine, MedecinIndisponibilite, MedecinPresence, Patient, PatientVitalSign, PersonnelEtablissement, PersonnelEtablissementPermission, Role
from .services import SupabaseAdminError, SupabaseAdminService

ADMIN_ETABLISSEMENT_STAFF_ROLE_CODES = (
    "secretary",
    "secretaire",
    "infirmier",
    "assistant",
    "receptionniste",
    "technicien",
    "staff_frontdesk",
)
STAFF_PERMISSION_LABELS = {
    "manage_patients": "Gerer les patients",
    "manage_appointments": "Gerer les rendez-vous",
    "declare_presences": "Declarer les presences",
    "view_documents": "Voir les documents",
}
STAFF_ROLE_PERMISSION_MAP = {
    "secretary": {"manage_patients", "manage_appointments"},
    "secretaire": {"manage_patients", "manage_appointments"},
    "infirmier": {"manage_patients", "manage_appointments", "declare_presences", "view_documents"},
    "assistant": {"manage_patients", "view_documents"},
    "receptionniste": {"manage_patients", "manage_appointments"},
    "technicien": {"view_documents"},
    "staff_frontdesk": {"manage_patients", "manage_appointments", "view_documents"},
}
WEEKDAY_ROWS = [
    {"index": 0, "code": "monday", "short": "LUN", "label": "Lundi"},
    {"index": 1, "code": "tuesday", "short": "MAR", "label": "Mardi"},
    {"index": 2, "code": "wednesday", "short": "MER", "label": "Mercredi"},
    {"index": 3, "code": "thursday", "short": "JEU", "label": "Jeudi"},
    {"index": 4, "code": "friday", "short": "VEN", "label": "Vendredi"},
    {"index": 5, "code": "saturday", "short": "SAM", "label": "Samedi"},
    {"index": 6, "code": "sunday", "short": "DIM", "label": "Dimanche"},
]
SCHEDULE_INTERVAL_SLOTS = 3
MONTH_LABELS = {
    1: "Janvier",
    2: "Fevrier",
    3: "Mars",
    4: "Avril",
    5: "Mai",
    6: "Juin",
    7: "Juillet",
    8: "Aout",
    9: "Septembre",
    10: "Octobre",
    11: "Novembre",
    12: "Decembre",
}


def home_view(request):
    return render(request, "home/index.html")


def _start_authenticated_session(request, *, access_token, user):
    request.session.cycle_key()
    request.session["access_token"] = access_token
    request.session["user_id"] = str(user.id)
    request.session["role"] = user.role.code if user.role else None
    request.session.pop("pending_access_token", None)
    request.session.pop("pending_user_id", None)
    request.session.pop("pending_role", None)


def _handle_password_entry_flow(request, *, template_name, page_mode):
    if request.session.get("user_id"):
        return redirect("dashboard")

    context = {
        "page_mode": page_mode,
        "submitted_email": "",
    }

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        password = request.POST.get("password") or ""
        context["submitted_email"] = email

        response = requests.post(
            f"{settings.SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={
                "apikey": settings.SUPABASE_ANON_KEY,
                "Content-Type": "application/json",
            },
            json={
                "email": email,
                "password": password,
            },
        )

        data = response.json()

        if response.status_code != 200:
            messages.error(request, "Email ou mot de passe incorrect.")
            return render(request, template_name, context)

        access_token = data["access_token"]
        user_id = data["user"]["id"]

        try:
            user = AppUser.objects.select_related("role").get(id=user_id)
        except AppUser.DoesNotExist:
            messages.error(request, "Utilisateur introuvable.")
            return render(request, template_name, context)

        _start_authenticated_session(request, access_token=access_token, user=user)
        return redirect("dashboard")

    return render(request, template_name, context)


def login_view(request):
    return _handle_password_entry_flow(
        request,
        template_name="auth/login.html",
        page_mode="login",
    )


def activate_account_view(request):
    if request.session.get("user_id"):
        return redirect("dashboard")
    return redirect("login")


def setup_password_view(request):
    if request.session.get("user_id"):
        return redirect("dashboard")
    return redirect("login")


def logout_view(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    request.session.flush()
    messages.success(request, "Session closed successfully.")
    return redirect("login")


def _build_exam_session_patient_context(exam_session):
    patient = exam_session.patient
    full_name = patient.full_name if patient else ""

    return {
        "full_name": full_name or "-",
        "patient_code": getattr(patient, "patient_code", None) or "-",
        "barcode_value": getattr(patient, "barcode_value", None) or "-",
        "date_of_birth": getattr(patient, "date_of_birth", None),
        "gender": getattr(patient, "gender", None) or "-",
        "phone": getattr(patient, "phone", None) or "-",
    }


def _build_patient_context_from_patient(patient):
    return {
        "full_name": patient.full_name or "-",
        "patient_code": patient.patient_code or "-",
        "barcode_value": patient.barcode_value or "-",
        "date_of_birth": patient.date_of_birth,
        "gender": patient.gender or "-",
        "phone": patient.phone or "-",
    }


def _build_exam_session_measurement_rows(latest_vital_sign):
    systolic_bp = getattr(latest_vital_sign, "systolic_bp", None)
    diastolic_bp = getattr(latest_vital_sign, "diastolic_bp", None)
    blood_pressure = None
    if systolic_bp is not None or diastolic_bp is not None:
        blood_pressure = f"{systolic_bp or '-'} / {diastolic_bp or '-'} mmHg"

    rows = [
        {"label": "Temperature", "value": getattr(latest_vital_sign, "temperature_c", None), "unit": "degC"},
        {"label": "Frequence cardiaque", "value": getattr(latest_vital_sign, "heart_rate_bpm", None), "unit": "bpm"},
        {"label": "SpO2", "value": getattr(latest_vital_sign, "spo2_percent", None), "unit": "%"},
        {"label": "Tension arterielle", "value": blood_pressure, "unit": ""},
        {"label": "Frequence respiratoire", "value": getattr(latest_vital_sign, "respiratory_rate_bpm", None), "unit": "rpm"},
        {"label": "Poids", "value": getattr(latest_vital_sign, "weight_kg", None), "unit": "kg"},
        {"label": "Taille", "value": getattr(latest_vital_sign, "height_cm", None), "unit": "cm"},
        {"label": "Glycemie", "value": getattr(latest_vital_sign, "blood_glucose_mg_dl", None), "unit": "mg/dL"},
    ]

    for row in rows:
        if row["value"] in (None, ""):
            row["display_value"] = "En attente"
        elif row["unit"]:
            row["display_value"] = f"{row['value']} {row['unit']}"
        else:
            row["display_value"] = str(row["value"])
    return rows


def _generate_unique_activation_pin():
    for _ in range(20):
        candidate = f"{secrets.randbelow(1000000):06d}"
        if not ExamSessionActivationPin.objects.filter(session_pin=candidate).exists():
            return candidate
    raise RuntimeError("Impossible de generer un PIN unique.")


def _db_table_exists(table_name):
    try:
        with connection.cursor() as cursor:
            return table_name in connection.introspection.table_names(cursor)
    except (ProgrammingError, OperationalError):
        return False


def health_professional_session_lookup(request):
    form = HealthProfessionalSessionCreateForm(request.POST or None)
    generated_activation = None
    patient_context = None

    if request.method == "POST" and form.is_valid():
        if not _db_table_exists(ExamSessionActivationPin._meta.db_table):
            form.add_error(
                None,
                "La table des PIN de session n'existe pas encore. Appliquez le script SQL `create_exam_session_activation_pins.sql`.",
            )
            return render(
                request,
                "kiosk/session_lookup.html",
                {
                    "session_create_form": form,
                    "generated_activation": generated_activation,
                    "patient_context": patient_context,
                },
            )

        patient_code = form.cleaned_data["patient_code"]
        patient = (
            Patient.objects.select_related("etablissement")
            .filter(Q(patient_code__iexact=patient_code) | Q(barcode_value__iexact=patient_code))
            .order_by("-created_at")
            .first()
        )
        if not patient:
            form.add_error("patient_code", "Aucun patient ne correspond a ce code.")
        else:
            try:
                now = timezone.now()
                ExamSessionActivationPin.objects.filter(patient=patient, status="pending").update(
                    status="expired",
                    updated_at=now,
                )
                created_by_user_id = request.session.get("user_id") or None
                generated_activation = ExamSessionActivationPin.objects.create(
                    patient=patient,
                    created_by_user_id=created_by_user_id,
                    session_pin=_generate_unique_activation_pin(),
                    status="pending",
                    expires_at=now + timedelta(minutes=30),
                    created_at=now,
                    updated_at=now,
                )
                patient_context = _build_patient_context_from_patient(patient)
            except (ProgrammingError, OperationalError):
                form.add_error(
                    None,
                    "La table des PIN de session n'existe pas encore. Appliquez le script SQL `create_exam_session_activation_pins.sql`.",
                )

    return render(
        request,
        "kiosk/session_lookup.html",
        {
            "session_create_form": form,
            "generated_activation": generated_activation,
            "patient_context": patient_context,
        },
    )


def health_professional_session_detail(request, session_pin):
    normalized_pin = "".join(char for char in (session_pin or "") if char.isdigit())
    if len(normalized_pin) != 6:
        messages.error(request, "Le PIN session doit contenir exactement 6 chiffres.")
        return redirect("health_professional_session_lookup")

    exam_session = None
    candidate_sessions = (
        ExamSession.objects.select_related("patient", "patient__etablissement")
        .filter(status__in=["active", "completed", "cancelled", "expired"])
        .order_by("-created_at")[:250]
    )
    for candidate in candidate_sessions:
        if candidate.session_pin == normalized_pin:
            exam_session = candidate
            break

    if not exam_session:
        messages.error(request, "Aucune session active ou recente ne correspond a ce PIN.")
        return redirect("health_professional_session_lookup")

    latest_vital_sign = (
        PatientVitalSign.objects.filter(exam_session_id=exam_session.id).order_by("-measured_at", "-created_at").first()
    )
    result_summary = getattr(latest_vital_sign, "notes", None)
    if not result_summary:
        result_summary = "La session est disponible. Les mesures ci-dessous correspondent aux captures deja enregistrees pour cette session."

    return render(
        request,
        "kiosk/session_detail.html",
        {
            "kiosk_session": exam_session,
            "patient_context": _build_exam_session_patient_context(exam_session),
            "measurement_rows": _build_exam_session_measurement_rows(latest_vital_sign),
            "latest_vital_sign": latest_vital_sign,
            "result_summary": result_summary,
            "result_recommendations": [],
            "session_create_form": HealthProfessionalSessionCreateForm(),
        },
    )


@login_required
def dashboard(request):
    role = request.session.get("role")
    current_user_id = request.session.get("user_id")

    if role == "super_admin":
        facilities_qs = Etablissement.objects.order_by("-created_at")
        doctors_qs = Medecin.objects.select_related("user").order_by("-user__created_at", "-id")
        users_qs = AppUser.objects.select_related("role").order_by("-created_at")

        facility_type_stats = list(
            Etablissement.objects.values("type_etablissement")
            .annotate(total=Count("id"))
            .order_by("-total", "type_etablissement")[:4]
        )
        max_facility_type_total = facility_type_stats[0]["total"] if facility_type_stats else 0

        for item in facility_type_stats:
            item["label"] = ETABLISSEMENT_TYPE_LABELS.get(
                item["type_etablissement"], item["type_etablissement"]
            )
            item["percent"] = int((item["total"] / max_facility_type_total) * 100) if max_facility_type_total else 0

        context = {
            "stats": {
                "facilities_total": facilities_qs.count(),
                "facilities_active": facilities_qs.filter(actif=True).count(),
                "doctors_total": doctors_qs.count(),
                "doctors_active": doctors_qs.filter(user__is_active=True).count(),
                "users_total": users_qs.count(),
                "users_active": users_qs.filter(is_active=True).count(),
            },
            "recent_facilities": facilities_qs[:5],
            "recent_doctors": doctors_qs[:5],
            "recent_users": users_qs[:6],
            "facility_type_stats": facility_type_stats,
        }
        return render(request, "dashboard/super_admin.html", context)

    if role == "admin_etablissement":
        managed_facilities = Etablissement.objects.select_related("admin").filter(admin_id=current_user_id).order_by("-created_at")
        primary_facility = managed_facilities.first()
        doctor_links_qs = MedecinEtablissement.objects.select_related("medecin__user", "medecin__user__role")
        invitation_qs = MedecinEtablissementInvitation.objects.none()
        patients_qs = Patient.objects.none()
        appointments_qs = Appointment.objects.none()
        doctors_present = 0
        if primary_facility:
            doctor_links_qs = doctor_links_qs.filter(etablissement=primary_facility, actif=True)
            invitation_qs = MedecinEtablissementInvitation.objects.filter(etablissement=primary_facility)
            patients_qs = Patient.objects.filter(etablissement=primary_facility).order_by("-created_at")
            appointments_qs = Appointment.objects.filter(etablissement=primary_facility).order_by("scheduled_at")
            doctors_present = MedecinPresence.objects.filter(
                etablissement=primary_facility,
                presence_date=timezone.localdate(),
                check_in_time__isnull=False,
            ).filter(
                Q(check_out_time__isnull=True) | Q(check_out_time__lt=F("check_in_time"))
            ).values("medecin_id").distinct().count()
        else:
            doctor_links_qs = doctor_links_qs.none()
        doctors_qs = Medecin.objects.select_related("user", "user__role").filter(
            id__in=doctor_links_qs.values_list("medecin_id", flat=True)
        ).order_by("-user__created_at", "-id")

        context = {
            "stats": {
                "managed_facilities_total": 1 if primary_facility else 0,
                "managed_facilities_active": 1 if primary_facility and primary_facility.actif else 0,
                "doctors_total": doctors_qs.count(),
                "doctors_active": doctors_qs.filter(user__is_active=True).count(),
                "doctors_present_today": doctors_present,
                "doctors_absent_today": max(doctors_qs.count() - doctors_present, 0),
                "pending_invitations": invitation_qs.filter(status="pending").count(),
                "security_alerts": 0,
                "appointments_today": appointments_qs.filter(scheduled_at__date=timezone.localdate()).count() if primary_facility else 0,
                "patients_total": patients_qs.count() if primary_facility else 0,
            },
            "primary_facility": primary_facility,
            "recent_doctors": doctors_qs[:5],
            "recent_patients": patients_qs[:5],
        }
        return render(request, "dashboard/admin_etablissement.html", context)

    if role in ["medecin", "doctor"]:
        doctor = (
            Medecin.objects.select_related("user", "user__role")
            .filter(user_id=current_user_id)
            .first()
        )
        doctor_facility_links = MedecinEtablissement.objects.select_related("etablissement").filter(
            medecin=doctor,
            actif=True,
        ).order_by("-est_principal", "etablissement__nom") if doctor else MedecinEtablissement.objects.none()
        doctor_invitations = MedecinEtablissementInvitation.objects.select_related("etablissement").filter(
            Q(medecin=doctor) | Q(medecin_email__iexact=doctor.email if doctor and doctor.email else ""),
        ).order_by("-created_at") if doctor else MedecinEtablissementInvitation.objects.none()

        context = {
            "doctor_profile": doctor,
            "doctor_facility_links": doctor_facility_links[:6],
            "doctor_invitations": doctor_invitations[:5],
            "doctor_stats": {
                "facilities_total": doctor_facility_links.count() if doctor else 0,
                "facilities_active": doctor_facility_links.filter(etablissement__actif=True).count() if doctor else 0,
                "pending_invitations": doctor_invitations.filter(status="pending").count() if doctor else 0,
                "accepted_invitations": doctor_invitations.filter(status="accepted").count() if doctor else 0,
                "expired_invitations": doctor_invitations.filter(status="expired").count() if doctor else 0,
            },
            "now": timezone.now(),
        }
        return render(request, "dashboard/doctor.html", context)

    if role in ["secretaire", "secretary", "infirmier", "assistant", "receptionniste", "technicien", "staff_frontdesk"]:
        current_user = get_object_or_404(AppUser.objects.select_related("role"), pk=current_user_id)
        staff_link = _get_current_staff_facility_link(current_user_id)
        facility = staff_link.etablissement if staff_link else None
        quick_appointment_form = StaffAppointmentForm(
            request.POST or None,
            etablissement=facility,
        ) if facility else None
        doctor_links = (
            MedecinEtablissement.objects.select_related("medecin__user", "etablissement")
            .filter(etablissement=facility, actif=True)
            .order_by("medecin__user__first_name", "medecin__user__last_name")
            if facility else MedecinEtablissement.objects.none()
        )
        doctor_invitations = (
            MedecinEtablissementInvitation.objects.filter(etablissement=facility).order_by("-created_at")
            if facility else MedecinEtablissementInvitation.objects.none()
        )
        staff_colleagues = (
            PersonnelEtablissement.objects.select_related("personnel_user", "personnel_user__role")
            .filter(etablissement=facility, est_actif=True)
            .exclude(personnel_user_id=current_user_id)
            .order_by("personnel_user__first_name", "personnel_user__last_name")
            if facility else PersonnelEtablissement.objects.none()
        )
        today = timezone.localdate()
        today_presences = (
            MedecinPresence.objects.select_related("medecin__user")
            .filter(etablissement=facility, presence_date=today)
            .order_by("-created_at", "-updated_at")
            if facility else MedecinPresence.objects.none()
        )
        latest_presence_by_doctor_id = {}
        open_presence_by_doctor_id = {}
        completed_presence_by_doctor_id = {}
        for presence in today_presences:
            if presence.medecin_id not in latest_presence_by_doctor_id:
                latest_presence_by_doctor_id[presence.medecin_id] = presence
            if (
                presence.medecin_id not in open_presence_by_doctor_id
                and presence.check_in_time
                and (not presence.check_out_time or presence.check_out_time < presence.check_in_time)
            ):
                open_presence_by_doctor_id[presence.medecin_id] = presence
            if (
                presence.medecin_id not in completed_presence_by_doctor_id
                and presence.check_in_time
                and presence.check_out_time
                and presence.check_out_time >= presence.check_in_time
            ):
                completed_presence_by_doctor_id[presence.medecin_id] = presence

        doctors_total = doctor_links.count() if facility else 0
        doctors_present = len(open_presence_by_doctor_id)
        doctors_checked_out = len(completed_presence_by_doctor_id)
        pending_checkins = max(doctors_total - doctors_present - doctors_checked_out, 0)
        pending_invitations = doctor_invitations.filter(status="pending").count() if facility else 0
        staff_doctor_rows = []
        for doctor_link in doctor_links[:6]:
            open_presence = open_presence_by_doctor_id.get(doctor_link.medecin_id)
            latest_presence = latest_presence_by_doctor_id.get(doctor_link.medecin_id)
            if open_presence:
                presence_label = "ON-SITE"
                presence_tone = "onsite"
                action_label = "CLAIM EXIT"
                action_enabled = False
            elif latest_presence:
                presence_label = "CHECKED OUT"
                presence_tone = "checked_out"
                action_label = "SESSION CLOSED"
                action_enabled = False
            else:
                presence_label = "EXPECTED"
                presence_tone = "expected"
                action_label = "CLAIM ENTRY"
                action_enabled = True
            staff_doctor_rows.append(
                {
                    "doctor_link": doctor_link,
                    "presence": latest_presence,
                    "presence_label": presence_label,
                    "presence_tone": presence_tone,
                    "action_label": action_label,
                    "action_enabled": action_enabled,
                }
        )
        staff_schedule = list(today_presences[:4])
        today_appointments = (
            Appointment.objects.select_related("patient", "medecin__user")
            .filter(etablissement=facility)
            .filter(
                scheduled_at__date=today,
                status__in=["pending", "confirmed", "follow_up_planned"],
            )
            .order_by("scheduled_at")[:5]
            if facility else Appointment.objects.none()
        )

        if request.method == "POST" and request.POST.get("dashboard_action") == "quick_appointment":
            if not facility:
                messages.error(request, "Aucun etablissement actif n'est associe a ce compte.")
                return redirect("dashboard")
            if quick_appointment_form and quick_appointment_form.is_valid():
                current_timestamp = timezone.now()
                scheduled_at = quick_appointment_form.cleaned_data["scheduled_at"]
                if timezone.is_naive(scheduled_at):
                    scheduled_at = timezone.make_aware(scheduled_at, timezone.get_current_timezone())
                duration_minutes = quick_appointment_form.cleaned_data["duration_minutes"]

                appointment = quick_appointment_form.save(commit=False)
                appointment.patient = quick_appointment_form.patient_instance
                appointment.etablissement = facility
                appointment.created_by_user = current_user
                appointment.requested_by_id = current_user.id
                appointment.requested_by_type = "nurse" if (current_user.role and current_user.role.code == "infirmier") else "secretary"
                appointment.source = "hospital_desk"
                appointment.status = "pending"
                appointment.scheduled_at = scheduled_at
                appointment.scheduled_end_at = scheduled_at + timedelta(minutes=duration_minutes)
                appointment.created_at = current_timestamp
                appointment.updated_at = current_timestamp
                appointment.save()
                messages.success(
                    request,
                    f"Rendez-vous cree avec succes pour le patient {appointment.patient.patient_code or appointment.patient.barcode_value}.",
                )
                return redirect("dashboard")

        context = {
            "staff_profile": current_user,
            "staff_link": staff_link,
            "staff_facility": facility,
            "staff_doctor_rows": staff_doctor_rows,
            "staff_colleagues": staff_colleagues[:5],
            "staff_stats": {
                "doctors_present": doctors_present,
                "doctors_total": doctors_total,
                "checked_out_today": doctors_checked_out,
                "pending_checkins": pending_checkins,
                "pending_invitations": pending_invitations,
                "average_wait_minutes": 12,
            },
            "staff_schedule": staff_schedule,
            "quick_appointment_form": quick_appointment_form,
            "today_appointments": today_appointments,
            "today_label": today.strftime("%A %d %B %Y"),
        }
        return render(request, "dashboard/staff_frontdesk.html", context)

    if role == "patient":
        return render(request, "dashboard/patient.html")

    return render(request, "dashboard/default.html")


def _generate_invitation_pin():
    return f"{secrets.randbelow(10000):04d}"


def _get_current_doctor(current_user_id):
    return (
        Medecin.objects.select_related("user", "user__role")
        .filter(user_id=current_user_id)
        .first()
    )


def _get_doctor_facility_links(doctor, *, active_only=True):
    if not doctor:
        return MedecinEtablissement.objects.none()
    queryset = MedecinEtablissement.objects.select_related("etablissement", "medecin__user").filter(medecin=doctor)
    if active_only:
        queryset = queryset.filter(actif=True)
    return queryset.order_by("-est_principal", "etablissement__nom")


def _get_selected_doctor_facility_link(request, doctor, *, source_keys=("facility",), active_only=True):
    doctor_links = _get_doctor_facility_links(doctor, active_only=active_only)
    selected_facility_id = ""
    for key in source_keys:
        selected_facility_id = (request.GET.get(key) or request.POST.get(key) or "").strip()
        if selected_facility_id:
            break
    selected_link = None
    if selected_facility_id:
        selected_link = doctor_links.filter(etablissement_id=selected_facility_id).first()
    if not selected_link:
        selected_link = doctor_links.first()
    normalized_facility_id = selected_link.etablissement_id if selected_link else selected_facility_id
    return selected_link, doctor_links, normalized_facility_id


def _parse_time_value(value):
    raw_value = (value or "").strip()
    if not raw_value:
        return None
    return datetime.strptime(raw_value, "%H:%M").time()


def _get_admin_doctor_link(etablissement, doctor_id):
    return get_object_or_404(
        MedecinEtablissement.objects.select_related("medecin__user", "etablissement"),
        etablissement=etablissement,
        medecin_id=doctor_id,
    )


def _build_doctor_schedule_rows(doctor_link):
    schedule_entries = {
        item.weekday: item
        for item in MedecinHoraireSemaine.objects.filter(
            etablissement=doctor_link.etablissement,
            medecin=doctor_link.medecin,
        ).prefetch_related("intervals")
    }

    rows = []
    for weekday in WEEKDAY_ROWS:
        schedule_entry = schedule_entries.get(weekday["index"])
        intervals = list(schedule_entry.intervals.all()) if schedule_entry else []
        interval_rows = []
        for slot_index in range(SCHEDULE_INTERVAL_SLOTS):
            interval = intervals[slot_index] if slot_index < len(intervals) else None
            interval_rows.append(
                {
                    "slot": slot_index + 1,
                    "start": interval.heure_debut.strftime("%H:%M") if interval and interval.heure_debut else "",
                    "end": interval.heure_fin.strftime("%H:%M") if interval and interval.heure_fin else "",
                }
            )
        rows.append(
            {
                **weekday,
                "schedule_entry": schedule_entry,
                "is_active": bool(schedule_entry and schedule_entry.is_active),
                "notes": schedule_entry.notes if schedule_entry else "",
                "intervals": interval_rows,
            }
        )
    return rows


def _build_month_calendar(selected_month):
    year = selected_month.year
    month = selected_month.month
    month_matrix = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    weekday_labels = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    weeks = []
    for week in month_matrix:
        weeks.append(
            [
                {
                    "date": day,
                    "iso": day.isoformat(),
                    "day_number": day.day,
                    "is_current_month": day.month == month,
                    "is_today": day == timezone.localdate(),
                }
                for day in week
            ]
        )
    return {
        "label": f"{MONTH_LABELS.get(month, month)} {year}",
        "value": selected_month.strftime("%Y-%m"),
        "weekday_labels": weekday_labels,
        "weeks": weeks,
    }


def _build_unavailability_calendar(*, doctor_link, selected_month):
    month_start = selected_month
    month_end = (selected_month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    entries = list(
        MedecinIndisponibilite.objects.filter(
            etablissement=doctor_link.etablissement,
            medecin=doctor_link.medecin,
            date_debut__lte=month_end,
            date_fin__gte=month_start,
        ).order_by("date_debut", "heure_debut", "created_at")
    )

    type_colors = {
        "conge": "red",
        "absence": "amber",
        "formation": "blue",
        "indisponible": "slate",
    }
    day_map = {}
    for entry in entries:
        current_day = max(entry.date_debut, month_start)
        last_day = min(entry.date_fin, month_end)
        while current_day <= last_day:
            day_map.setdefault(current_day.isoformat(), []).append(entry)
            current_day += timedelta(days=1)

    calendar_data = _build_month_calendar(selected_month)
    for week in calendar_data["weeks"]:
        for day in week:
            entries_for_day = day_map.get(day["iso"], [])
            day["entries"] = entries_for_day
            day["is_blocked"] = bool(entries_for_day)
            day["tone"] = type_colors.get(entries_for_day[0].type_indisponibilite, "slate") if entries_for_day else None

    return calendar_data, entries


def _build_doctor_global_unavailability_calendar(*, doctor_links, selected_month):
    month_start = selected_month
    month_end = (selected_month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    facility_map = {str(link.etablissement_id): link.etablissement for link in doctor_links}
    entries = list(
        MedecinIndisponibilite.objects.select_related("etablissement")
        .filter(
            etablissement_id__in=list(facility_map.keys()),
            medecin=doctor_links[0].medecin if doctor_links else None,
            date_debut__lte=month_end,
            date_fin__gte=month_start,
        )
        .order_by("date_debut", "heure_debut", "created_at")
    ) if doctor_links else []

    type_colors = {
        "conge": "red",
        "absence": "amber",
        "formation": "blue",
        "indisponible": "slate",
    }
    day_map = {}
    for entry in entries:
        entry.facility_name = entry.etablissement.nom if entry.etablissement else "-"
        current_day = max(entry.date_debut, month_start)
        last_day = min(entry.date_fin, month_end)
        while current_day <= last_day:
            day_map.setdefault(current_day.isoformat(), []).append(entry)
            current_day += timedelta(days=1)

    calendar_data = _build_month_calendar(selected_month)
    for week in calendar_data["weeks"]:
        for day in week:
            entries_for_day = day_map.get(day["iso"], [])
            day["entries"] = entries_for_day
            day["is_blocked"] = bool(entries_for_day)
            day["tone"] = type_colors.get(entries_for_day[0].type_indisponibilite, "slate") if entries_for_day else None

    return calendar_data, entries


def _serialize_unavailability_payload(*, doctor_link):
    today = timezone.localdate()
    current_year = today.year
    schedule_entries = list(
        MedecinHoraireSemaine.objects.filter(
            etablissement=doctor_link.etablissement,
            medecin=doctor_link.medecin,
            is_active=True,
        ).prefetch_related("intervals")
    )
    schedule_by_weekday = {entry.weekday: entry for entry in schedule_entries}

    year_entries = list(
        MedecinIndisponibilite.objects.filter(
            etablissement=doctor_link.etablissement,
            medecin=doctor_link.medecin,
            date_debut__year__lte=current_year,
            date_fin__year__gte=current_year,
        ).order_by("date_debut", "heure_debut", "created_at")
    )
    type_colors = {
        "conge": "red",
        "absence": "amber",
        "formation": "blue",
        "indisponible": "slate",
    }

    day_entries_map = {}
    for entry in year_entries:
        start_day = max(entry.date_debut, date(current_year, 1, 1))
        end_day = min(entry.date_fin, date(current_year, 12, 31))
        current_day = start_day
        while current_day <= end_day:
            day_entries_map.setdefault(current_day.isoformat(), []).append(entry)
            current_day += timedelta(days=1)

    day_details = {}
    current_day = date(current_year, 1, 1)
    last_day = date(current_year, 12, 31)
    while current_day <= last_day:
        schedule = schedule_by_weekday.get(current_day.weekday())
        intervals = []
        if schedule:
            intervals = [
                {
                    "start": interval.heure_debut.strftime("%H:%M"),
                    "end": interval.heure_fin.strftime("%H:%M"),
                }
                for interval in schedule.intervals.all()
            ]
        entries_for_day = day_entries_map.get(current_day.isoformat(), [])
        tone = type_colors.get(entries_for_day[0].type_indisponibilite, "slate") if entries_for_day else None
        is_available = bool(intervals) and not entries_for_day
        day_details[current_day.isoformat()] = {
            "weekday_label": dict(MedecinHoraireSemaine.WEEKDAY_CHOICES).get(current_day.weekday(), ""),
            "intervals": intervals,
            "entries": [
                {
                    "type": entry.type_display_name,
                    "motif": entry.motif,
                    "date_start": entry.date_debut.strftime("%d/%m/%Y"),
                    "date_end": entry.date_fin.strftime("%d/%m/%Y"),
                }
                for entry in entries_for_day
            ],
            "is_available": is_available,
            "is_blocked": bool(entries_for_day),
            "tone": tone,
        }
        current_day += timedelta(days=1)

    months = {}
    year_summary = []
    for month_number in range(1, 13):
        month_start = date(current_year, month_number, 1)
        calendar_data = _build_month_calendar(month_start)
        month_weeks = []
        month_items = []
        blocked_days = 0
        available_days = 0

        for week in calendar_data["weeks"]:
            serialized_week = []
            for day in week:
                details = day_details.get(day["iso"], {})
                if day["is_current_month"] and details.get("is_blocked"):
                    blocked_days += 1
                if day["is_current_month"] and details.get("is_available"):
                    available_days += 1
                serialized_day = {
                    "iso": day["iso"],
                    "day_number": day["day_number"],
                    "is_current_month": day["is_current_month"],
                    "is_today": day["is_today"],
                    "is_blocked": details.get("is_blocked", False),
                    "is_available": details.get("is_available", False),
                    "tone": details.get("tone"),
                    "entries": details.get("entries", [])[:2],
                }
                if day["is_current_month"] and details.get("entries"):
                    for entry in details["entries"]:
                        month_items.append(entry)
                serialized_week.append(serialized_day)
            month_weeks.append(serialized_week)

        month_key = f"{current_year}-{month_number:02d}"
        months[month_key] = {
            "label": calendar_data["label"],
            "weekday_labels": calendar_data["weekday_labels"],
            "weeks": month_weeks,
            "items": month_items,
            "month": month_number,
            "year": current_year,
        }
        year_summary.append(
            {
                "key": month_key,
                "month": MONTH_LABELS[month_number],
                "count": blocked_days,
                "available_days": available_days,
                "has_blocked": blocked_days > 0,
            }
        )

    return {
        "doctor_name": doctor_link.medecin.full_name or "Medecin",
        "specialite": doctor_link.medecin.specialite or "Sans specialite",
        "selected_month": today.strftime("%Y-%m"),
        "selected_date": today.isoformat(),
        "months": months,
        "day_details": day_details,
        "year": {
            "label": str(current_year),
            "summary": year_summary,
        },
    }


def _get_next_presence_periods(*, etablissement, doctor, limit=3):
    today = timezone.localdate()
    now_time = timezone.localtime().time()
    schedules = list(
        MedecinHoraireSemaine.objects.filter(
            etablissement=etablissement,
            medecin=doctor,
            is_active=True,
        ).prefetch_related("intervals")
    )
    schedule_by_weekday = {item.weekday: item for item in schedules}
    leave_dates = set(
        MedecinIndisponibilite.objects.filter(
            etablissement=etablissement,
            medecin=doctor,
            type_indisponibilite="conge",
            date_fin__gte=today,
            date_debut__lte=today + timedelta(days=30),
        ).values_list("date_debut", flat=True)
    )

    periods = []
    for day_offset in range(0, 21):
        current_date = today + timedelta(days=day_offset)
        schedule = schedule_by_weekday.get(current_date.weekday())
        if not schedule or current_date in leave_dates:
            continue

        intervals = list(schedule.intervals.all())
        for interval in intervals:
            if day_offset == 0 and interval.heure_fin <= now_time:
                continue
            periods.append(
                {
                    "date": current_date,
                    "weekday_label": dict(MedecinHoraireSemaine.WEEKDAY_CHOICES).get(schedule.weekday, ""),
                    "start": interval.heure_debut,
                    "end": interval.heure_fin,
                }
            )
            if len(periods) >= limit:
                return periods
    return periods


def _admin_etablissement_staff_role_filter():
    role_filter = Q()
    for role_code in ADMIN_ETABLISSEMENT_STAFF_ROLE_CODES:
        role_filter |= Q(role__code__iexact=role_code) | Q(role__nom__iexact=role_code)
    return role_filter


def _admin_etablissement_staff_link_role_filter():
    role_filter = Q()
    for role_code in ADMIN_ETABLISSEMENT_STAFF_ROLE_CODES:
        role_filter |= Q(personnel_user__role__code__iexact=role_code) | Q(personnel_user__role__nom__iexact=role_code)
    return role_filter


def _admin_etablissement_role_option_filter():
    role_filter = Q()
    for role_code in ADMIN_ETABLISSEMENT_STAFF_ROLE_CODES:
        role_filter |= Q(code__iexact=role_code) | Q(nom__iexact=role_code)
    return role_filter


def _get_managed_facility_for_admin(current_user_id):
    return (
        Etablissement.objects.select_related("admin")
        .filter(admin_id=current_user_id)
        .order_by("-created_at")
        .first()
    )


def _map_app_role_to_personnel_role(role_obj):
    role_code = ((getattr(role_obj, "code", None) or getattr(role_obj, "nom", None) or "")).strip().lower()
    if role_code in {"secretary", "secretaire"}:
        return "secretaire"
    if role_code == "infirmier":
        return "infirmier"
    if role_code == "assistant":
        return "assistant"
    if role_code == "receptionniste":
        return "receptionniste"
    if role_code == "technicien":
        return "technicien"
    if role_code in {"admin", "admin_etablissement"}:
        return "admin"
    if role_code in {"medecin", "doctor"}:
        return "medecin"
    return "assistant"


def _get_staff_links_queryset(etablissement):
    return PersonnelEtablissement.objects.select_related("personnel_user", "personnel_user__role", "permissions").filter(
        etablissement=etablissement
    )


def _get_current_staff_facility_link(current_user_id):
    return (
        PersonnelEtablissement.objects.select_related("etablissement", "personnel_user", "personnel_user__role", "permissions")
        .filter(personnel_user_id=current_user_id, est_actif=True)
        .order_by("-created_at")
        .first()
    )


def _normalize_staff_role_code(role_code):
    normalized = (role_code or "").strip().lower()
    if normalized == "secretary":
        return "secretaire"
    return normalized


def _get_staff_permissions_for_role(role_code):
    normalized = _normalize_staff_role_code(role_code)
    return STAFF_ROLE_PERMISSION_MAP.get(normalized, set())


def _resolve_staff_role_code(role_value):
    normalized = _normalize_staff_role_code(role_value)
    if normalized in STAFF_ROLE_PERMISSION_MAP:
        return normalized

    role_obj = Role.objects.filter(pk=role_value).only("code").first()
    if role_obj:
        return _normalize_staff_role_code(role_obj.code)
    return ""


def _get_staff_permission_rows(role_code):
    granted_permissions = _get_staff_permissions_for_role(role_code)
    return [
        {
            "code": permission_code,
            "label": permission_label,
            "enabled": permission_code in granted_permissions,
        }
        for permission_code, permission_label in STAFF_PERMISSION_LABELS.items()
    ]


def _build_staff_permission_initial(role_code):
    granted_permissions = _get_staff_permissions_for_role(role_code)
    return {
        "can_manage_patients": "manage_patients" in granted_permissions,
        "can_manage_appointments": "manage_appointments" in granted_permissions,
        "can_declare_presences": "declare_presences" in granted_permissions,
        "can_view_documents": "view_documents" in granted_permissions,
    }


def _get_staff_permission_form(role_code, *args, instance=None, **kwargs):
    if instance is not None:
        return PersonnelEtablissementPermissionForm(*args, instance=instance, **kwargs)
    return PersonnelEtablissementPermissionForm(*args, initial=_build_staff_permission_initial(role_code), **kwargs)


def _get_staff_permission_rows_from_instance(permission_obj):
    return [
        {
            "code": "manage_patients",
            "label": STAFF_PERMISSION_LABELS["manage_patients"],
            "enabled": bool(getattr(permission_obj, "can_manage_patients", False)),
        },
        {
            "code": "manage_appointments",
            "label": STAFF_PERMISSION_LABELS["manage_appointments"],
            "enabled": bool(getattr(permission_obj, "can_manage_appointments", False)),
        },
        {
            "code": "declare_presences",
            "label": STAFF_PERMISSION_LABELS["declare_presences"],
            "enabled": bool(getattr(permission_obj, "can_declare_presences", False)),
        },
        {
            "code": "view_documents",
            "label": STAFF_PERMISSION_LABELS["view_documents"],
            "enabled": bool(getattr(permission_obj, "can_view_documents", False)),
        },
    ]


def _get_or_build_staff_permission_rows(staff_link):
    permission_obj = getattr(staff_link, "permissions", None)
    if permission_obj:
        return _get_staff_permission_rows_from_instance(permission_obj)
    return _get_staff_permission_rows(staff_link.role)


def _staff_has_permission(staff_link, permission_code):
    if not staff_link:
        return False
    permission_obj = getattr(staff_link, "permissions", None)
    if permission_obj:
        return {
            "manage_patients": bool(permission_obj.can_manage_patients),
            "manage_appointments": bool(permission_obj.can_manage_appointments),
            "declare_presences": bool(permission_obj.can_declare_presences),
            "view_documents": bool(permission_obj.can_view_documents),
        }.get(permission_code, False)
    return permission_code in _get_staff_permissions_for_role(staff_link.role)


def _reject_staff_permission(request, permission_code):
    permission_label = STAFF_PERMISSION_LABELS.get(permission_code, permission_code)
    messages.error(request, f"Acces refuse. Permission requise: {permission_label}.")
    return redirect("forbidden")


def _format_presence_duration(check_in_time, check_out_time):
    if not check_in_time or not check_out_time or check_out_time <= check_in_time:
        return None

    total_seconds = int((check_out_time - check_in_time).total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def _build_patient_preview_code(etablissement):
    city = getattr(etablissement, "ville", "") or ""
    normalized = city[:3].upper() if city else "PAT"
    return f"PAT-{normalized}-0001"


def _escpos_qr_bytes(value):
    data = (value or "").encode("utf-8")
    store_len = len(data) + 3
    pL = store_len % 256
    pH = store_len // 256
    return b"".join(
        [
            b"\x1d\x28\x6b\x04\x00\x31\x41\x32\x00",
            b"\x1d\x28\x6b\x03\x00\x31\x43\x04",
            b"\x1d\x28\x6b\x03\x00\x31\x45\x31",
            bytes([0x1D, 0x28, 0x6B, pL, pH, 0x31, 0x50, 0x30]) + data,
            b"\x1d\x28\x6b\x03\x00\x31\x51\x30",
        ]
    )


def _build_patient_receipt_raw(*, patient, facility, printer_name, printed_at):
    line_width = 32

    def line(value=""):
        return f"{value}\n".encode("cp1252", errors="replace")

    def divider(char="-"):
        return line(char * line_width)

    def wrap_text(value, width=line_width):
        text = str(value or "-").strip() or "-"
        return [text[index:index + width] for index in range(0, len(text), width)] or ["-"]

    def center_lines(value):
        return b"".join(line(chunk.center(line_width)) for chunk in wrap_text(value, line_width))

    def left_right(label, value):
        label_text = str(label or "").strip()
        value_text = str(value or "-").strip() or "-"
        available = max(line_width - len(label_text) - 1, 8)
        value_text = value_text[:available]
        spaces = " " * max(line_width - len(label_text) - len(value_text), 1)
        return line(f"{label_text}{spaces}{value_text}")

    gender_display = {
        "male": "Homme",
        "female": "Femme",
        "other": "Autre",
    }.get((patient.gender or "").strip().lower(), patient.gender or "-")

    facility_subtitle = facility.type_display_name or "Etablissement"
    if facility.ville:
        facility_subtitle = f"{facility_subtitle} - {facility.ville}"

    payload = {
        "patient_code": patient.patient_code,
        "barcode_value": patient.barcode_value,
        "patient_name": patient.full_name,
        "facility": facility.nom,
    }

    chunks = [
        b"\x1b\x40",
        b"\x1b\x61\x01",
        b"\x1b\x45\x01",
        center_lines(facility.nom or "Facility"),
        b"\x1b\x45\x00",
        center_lines(facility_subtitle),
        center_lines(f"PRINTER {printer_name}"),
        center_lines(printed_at.strftime("%d/%m/%Y %H:%M")),
        divider("="),
        b"\x1b\x61\x00",
        left_right("PATIENT", ""),
        b"".join(line(chunk) for chunk in wrap_text(patient.full_name or "-", line_width)),
        divider(),
        left_right("DOB", patient.date_of_birth.strftime('%d/%m/%Y') if patient.date_of_birth else "-"),
        left_right("PHONE", patient.phone or "-"),
        left_right("SEX", gender_display),
        left_right("BLOOD", patient.blood_group or "-"),
        divider(),
        b"\x1b\x45\x01",
        left_right("CIN / CODE", patient.patient_code or "-"),
        left_right("BARCODE ID", patient.barcode_value),
        b"\x1b\x45\x00",
        b"\n",
        b"\x1b\x61\x01",
        _escpos_qr_bytes(str(payload)),
        b"\n\n",
        center_lines("KEEP THIS TICKET"),
        center_lines("FOR FAST IDENTIFICATION"),
        b"\n\n\n",
        b"\x1d\x56\x00",
    ]
    return b"".join(chunks)


def _send_raw_receipt_to_printer(*, printer_name, raw_bytes, doc_name):
    import win32print

    printer_handle = win32print.OpenPrinter(printer_name)
    try:
        job = ("HealthSync Receipt", None, "RAW")
        win32print.StartDocPrinter(printer_handle, 1, job)
        try:
            win32print.StartPagePrinter(printer_handle)
            win32print.WritePrinter(printer_handle, raw_bytes)
            win32print.EndPagePrinter(printer_handle)
        finally:
            win32print.EndDocPrinter(printer_handle)
    finally:
        win32print.ClosePrinter(printer_handle)


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_invitations(request):
    current_user_id = request.session.get("user_id")
    current_user = get_object_or_404(AppUser.objects.select_related("role"), pk=current_user_id)
    etablissement = (
        Etablissement.objects.select_related("admin")
        .filter(admin_id=current_user_id)
        .order_by("-created_at")
        .first()
    )

    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    form = MedecinEtablissementInvitationForm(request.POST or None, etablissement=etablissement)
    generated_pin = request.session.pop("latest_invitation_pin", None)

    if request.method == "POST" and form.is_valid():
        invitation = form.save(commit=False)
        invitation.etablissement = etablissement
        invitation.invited_by_user = current_user
        invitation.invitation_token = secrets.token_urlsafe(32)
        raw_pin = _generate_invitation_pin()
        invitation.pin_hash = make_password(raw_pin)
        invitation.pin_expires_at = timezone.now() + timedelta(hours=24)
        invitation.status = "pending"
        invitation.created_at = timezone.now()
        invitation.updated_at = timezone.now()

        linked_doctor = (
            Medecin.objects.select_related("user")
            .filter(user__email__iexact=form.cleaned_data["medecin_email"])
            .first()
        )
        if linked_doctor:
            invitation.medecin = linked_doctor

        invitation.save()
        request.session["latest_invitation_pin"] = raw_pin
        messages.success(request, "Invitation creee avec succes.")
        return redirect("admin_etablissement_invitations")

    invitations = (
        MedecinEtablissementInvitation.objects.select_related("medecin__user", "etablissement")
        .filter(etablissement=etablissement)
        .order_by("-created_at")
    )

    context = {
        "form": form,
        "etablissement": etablissement,
        "invitations": invitations,
        "pending_invitations_count": invitations.filter(status="pending").count(),
        "generated_pin": generated_pin,
    }
    return render(request, "admin_etablissement/invitations.html", context)


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_invitation_cancel(request, invitation_id):
    current_user_id = request.session.get("user_id")
    etablissement = _get_managed_facility_for_admin(current_user_id)

    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    invitation = get_object_or_404(
        MedecinEtablissementInvitation,
        pk=invitation_id,
        etablissement=etablissement,
    )

    if request.method != "POST":
        return redirect("admin_etablissement_invitations")

    if invitation.status != "pending":
        messages.warning(request, "Seules les invitations en attente peuvent etre annulees.")
        return redirect("admin_etablissement_invitations")

    invitation.status = "cancelled"
    invitation.updated_at = timezone.now()
    invitation.save(update_fields=["status", "updated_at"])
    messages.success(request, "Invitation annulee avec succes.")
    return redirect("admin_etablissement_invitations")


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_availability(request):
    current_user_id = request.session.get("user_id")
    current_user = get_object_or_404(AppUser.objects.select_related("role"), pk=current_user_id)
    etablissement = _get_managed_facility_for_admin(current_user_id)

    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    doctor_links = (
        MedecinEtablissement.objects.select_related("medecin__user", "etablissement")
        .filter(etablissement=etablissement)
        .order_by("-actif", "medecin__user__first_name", "medecin__user__last_name", "medecin__specialite")
    )
    doctors_qs = Medecin.objects.select_related("user").filter(
        id__in=doctor_links.values_list("medecin_id", flat=True)
    ).order_by("user__first_name", "user__last_name", "specialite")

    doctor_filter = (request.GET.get("doctor") or "").strip()
    type_filter = (request.GET.get("type") or "").strip()

    if request.method == "POST":
        form = MedecinIndisponibiliteForm(request.POST, doctor_queryset=doctors_qs)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.etablissement = etablissement
            entry.declared_by_user = current_user
            entry.created_at = timezone.now()
            entry.updated_at = timezone.now()
            if entry.toute_la_journee:
                entry.heure_debut = None
                entry.heure_fin = None
            entry.save()
            messages.success(request, "Indisponibilite enregistree avec succes.")
            return redirect("admin_etablissement_availability")
    else:
        form = MedecinIndisponibiliteForm(doctor_queryset=doctors_qs)

    unavailability_qs = (
        MedecinIndisponibilite.objects.select_related("medecin__user", "etablissement")
        .filter(etablissement=etablissement)
        .order_by("date_debut", "heure_debut", "created_at")
    )
    if doctor_filter:
        unavailability_qs = unavailability_qs.filter(medecin_id=doctor_filter)
    if type_filter:
        unavailability_qs = unavailability_qs.filter(type_indisponibilite=type_filter)

    entries_by_doctor_id = {}
    for entry in unavailability_qs:
        entries_by_doctor_id.setdefault(entry.medecin_id, []).append(entry)

    doctor_rows = []
    today = timezone.localdate()
    for doctor_link in doctor_links:
        doctor = doctor_link.medecin
        upcoming_entries = entries_by_doctor_id.get(doctor.id, [])
        calendar_payload = _serialize_unavailability_payload(doctor_link=doctor_link)
        current_entry = next(
            (
                item for item in upcoming_entries
                if item.date_debut <= today <= item.date_fin
            ),
            None,
        )
        doctor_rows.append(
            {
                "doctor_link": doctor_link,
                "doctor": doctor,
                "current_entry": current_entry,
                "entries": upcoming_entries[:4],
                "entries_count": len(upcoming_entries),
                "next_periods": _get_next_presence_periods(
                    etablissement=etablissement,
                    doctor=doctor,
                    limit=1,
                ),
                "calendar_payload": calendar_payload,
                "calendar_payload_json": json.dumps(
                    calendar_payload,
                    ensure_ascii=True,
                ),
            }
        )

    context = {
        "etablissement": etablissement,
        "doctor_rows": doctor_rows,
        "form": form,
        "type_choices": MedecinIndisponibilite.TYPE_CHOICES,
        "filters": {
            "doctor": doctor_filter,
            "type": type_filter,
        },
        "entries_count": unavailability_qs.count(),
        "doctors_count": doctors_qs.count(),
    }
    return render(request, "admin_etablissement/availability/list.html", context)


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_doctor_schedule(request, doctor_id):
    current_user_id = request.session.get("user_id")
    etablissement = _get_managed_facility_for_admin(current_user_id)

    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    doctor_link = _get_admin_doctor_link(etablissement, doctor_id)

    if request.method == "POST":
        now = timezone.now()
        errors = []
        day_payloads = []
        for weekday in WEEKDAY_ROWS:
            day_code = weekday["code"]
            is_active = request.POST.get(f"{day_code}_enabled") == "on"
            notes = (request.POST.get(f"{day_code}_notes") or "").strip()
            interval_payloads = []

            for slot in range(1, SCHEDULE_INTERVAL_SLOTS + 1):
                start_value = _parse_time_value(request.POST.get(f"{day_code}_start_{slot}"))
                end_value = _parse_time_value(request.POST.get(f"{day_code}_end_{slot}"))
                if start_value and end_value:
                    if end_value <= start_value:
                        errors.append(f"{weekday['label']} - le creneau {slot} doit se terminer apres son debut.")
                    else:
                        interval_payloads.append((slot, start_value, end_value))
                elif start_value or end_value:
                    errors.append(f"{weekday['label']} - le creneau {slot} est incomplet.")

            if is_active and not interval_payloads:
                errors.append(f"{weekday['label']} est active mais aucun intervalle complet n'a ete saisi.")

            day_payloads.append(
                {
                    "weekday_index": weekday["index"],
                    "is_active": is_active,
                    "notes": notes,
                    "intervals": interval_payloads,
                }
            )

        if not errors:
            with transaction.atomic():
                for payload in day_payloads:
                    schedule_entry, created = MedecinHoraireSemaine.objects.get_or_create(
                        etablissement=etablissement,
                        medecin=doctor_link.medecin,
                        weekday=payload["weekday_index"],
                        defaults={
                            "is_active": payload["is_active"],
                            "notes": payload["notes"],
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    if not created:
                        schedule_entry.is_active = payload["is_active"]
                        schedule_entry.notes = payload["notes"]
                        schedule_entry.updated_at = now
                        schedule_entry.save(update_fields=["is_active", "notes", "updated_at"])

                    MedecinHoraireIntervalle.objects.filter(horaire=schedule_entry).delete()
                    for slot, start_value, end_value in payload["intervals"]:
                        MedecinHoraireIntervalle.objects.create(
                            horaire=schedule_entry,
                            ordre=slot,
                            heure_debut=start_value,
                            heure_fin=end_value,
                            created_at=now,
                            updated_at=now,
                        )

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            messages.success(request, "Horaire hebdomadaire mis a jour avec succes.")
            return redirect("admin_etablissement_doctor_schedule", doctor_id=doctor_link.medecin_id)

    context = {
        "etablissement": etablissement,
        "doctor_link": doctor_link,
        "weekday_rows": _build_doctor_schedule_rows(doctor_link),
        "interval_slots": range(1, SCHEDULE_INTERVAL_SLOTS + 1),
    }
    return render(request, "admin_etablissement/availability/schedule.html", context)


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_doctor_calendar(request, doctor_id):
    current_user_id = request.session.get("user_id")
    etablissement = _get_managed_facility_for_admin(current_user_id)

    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    doctor_link = _get_admin_doctor_link(etablissement, doctor_id)
    selected_month_raw = (request.GET.get("month") or "").strip()
    try:
        selected_month = datetime.strptime(selected_month_raw, "%Y-%m").date().replace(day=1) if selected_month_raw else timezone.localdate().replace(day=1)
    except ValueError:
        selected_month = timezone.localdate().replace(day=1)

    calendar_data, month_entries = _build_unavailability_calendar(
        doctor_link=doctor_link,
        selected_month=selected_month,
    )
    previous_month = (selected_month.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (selected_month.replace(day=28) + timedelta(days=4)).replace(day=1)

    return render(
        request,
        "admin_etablissement/availability/calendar.html",
        {
            "etablissement": etablissement,
            "doctor_link": doctor_link,
            "calendar_data": calendar_data,
            "month_entries": month_entries,
            "selected_month": selected_month.strftime("%Y-%m"),
            "previous_month": previous_month.strftime("%Y-%m"),
            "next_month": next_month.strftime("%Y-%m"),
        },
    )


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_doctor_leaves(request, doctor_id):
    current_user_id = request.session.get("user_id")
    current_user = get_object_or_404(AppUser.objects.select_related("role"), pk=current_user_id)
    etablissement = _get_managed_facility_for_admin(current_user_id)

    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    doctor_link = _get_admin_doctor_link(etablissement, doctor_id)

    selected_month_raw = (request.GET.get("month") or request.POST.get("selected_month") or "").strip()
    try:
        selected_month = datetime.strptime(selected_month_raw, "%Y-%m").date().replace(day=1) if selected_month_raw else timezone.localdate().replace(day=1)
    except ValueError:
        selected_month = timezone.localdate().replace(day=1)

    if request.method == "POST":
        selected_days = request.POST.getlist("selected_days")
        motif = (request.POST.get("motif") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        if not selected_days:
            messages.error(request, "Selectionne au moins un jour de conge.")
        elif not motif:
            messages.error(request, "Le motif du conge est requis.")
        else:
            now = timezone.now()
            created_count = 0
            with transaction.atomic():
                for raw_day in selected_days:
                    try:
                        leave_day = datetime.strptime(raw_day, "%Y-%m-%d").date()
                    except ValueError:
                        continue

                    if MedecinIndisponibilite.objects.filter(
                        medecin=doctor_link.medecin,
                        etablissement=etablissement,
                        type_indisponibilite="conge",
                        date_debut=leave_day,
                        date_fin=leave_day,
                    ).exists():
                        continue

                    MedecinIndisponibilite.objects.create(
                        medecin=doctor_link.medecin,
                        etablissement=etablissement,
                        declared_by_user=current_user,
                        type_indisponibilite="conge",
                        motif=motif,
                        date_debut=leave_day,
                        date_fin=leave_day,
                        heure_debut=None,
                        heure_fin=None,
                        toute_la_journee=True,
                        notes=notes,
                        created_at=now,
                        updated_at=now,
                    )
                    created_count += 1

            if created_count:
                messages.success(request, f"{created_count} jour(s) de conge enregistre(s) avec succes.")
                return redirect(f"{reverse('admin_etablissement_doctor_leaves', kwargs={'doctor_id': doctor_link.medecin_id})}?month={selected_month.strftime('%Y-%m')}")
            messages.error(request, "Aucun jour valide n'a ete enregistre.")

    leaves = (
        MedecinIndisponibilite.objects.select_related("medecin__user")
        .filter(
            etablissement=etablissement,
            medecin=doctor_link.medecin,
            type_indisponibilite="conge",
        )
        .order_by("date_debut", "heure_debut", "created_at")
    )

    leave_days = {leave.date_debut.isoformat() for leave in leaves if leave.date_debut == leave.date_fin}
    previous_month = (selected_month.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (selected_month.replace(day=28) + timedelta(days=4)).replace(day=1)

    return render(
        request,
        "admin_etablissement/availability/leaves.html",
        {
            "etablissement": etablissement,
            "doctor_link": doctor_link,
            "leaves": leaves,
            "calendar_data": _build_month_calendar(selected_month),
            "leave_days": leave_days,
            "selected_month": selected_month.strftime("%Y-%m"),
            "previous_month": previous_month.strftime("%Y-%m"),
            "next_month": next_month.strftime("%Y-%m"),
        },
    )


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_doctor_toggle_access(request, doctor_id):
    current_user_id = request.session.get("user_id")
    etablissement = _get_managed_facility_for_admin(current_user_id)

    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    doctor_link = _get_admin_doctor_link(etablissement, doctor_id)
    if request.method != "POST":
        return redirect("admin_etablissement_availability")

    doctor_link.actif = not doctor_link.actif
    doctor_link.updated_at = timezone.now()
    doctor_link.save(update_fields=["actif", "updated_at"])

    if doctor_link.actif:
        messages.success(request, "Acces du medecin reactive pour cet etablissement.")
    else:
        messages.success(request, "Acces du medecin desactive pour cet etablissement.")
    return redirect("admin_etablissement_availability")


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_detail(request):
    current_user_id = request.session.get("user_id")
    etablissement = _get_managed_facility_for_admin(current_user_id)

    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    doctors_count = MedecinEtablissement.objects.filter(etablissement=etablissement).count()
    active_staff_count = PersonnelEtablissement.objects.filter(etablissement=etablissement, est_actif=True).count()
    patients_count = Patient.objects.filter(etablissement=etablissement).count()
    appointments_today = Appointment.objects.filter(
        etablissement=etablissement,
        scheduled_at__date=timezone.localdate(),
    ).count()

    return render(
        request,
        "admin_etablissement/detail.html",
        {
            "etablissement": etablissement,
            "stats": {
                "doctors_count": doctors_count,
                "active_staff_count": active_staff_count,
                "patients_count": patients_count,
                "appointments_today": appointments_today,
            },
        },
    )


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_attendance(request):
    current_user_id = request.session.get("user_id")
    current_user = get_object_or_404(AppUser.objects.select_related("role"), pk=current_user_id)
    etablissement = _get_managed_facility_for_admin(current_user_id)

    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    doctor_links = MedecinEtablissement.objects.select_related("medecin__user", "etablissement").filter(
        etablissement=etablissement,
        actif=True,
    ).order_by("medecin__user__first_name", "medecin__user__last_name")
    search_query = (request.GET.get("q") or "").strip()
    if search_query:
        doctor_links = doctor_links.filter(
            Q(medecin__user__first_name__icontains=search_query)
            | Q(medecin__user__last_name__icontains=search_query)
            | Q(medecin__specialite__icontains=search_query)
            | Q(medecin__id__icontains=search_query)
        )

    today = timezone.localdate()
    today_presences = MedecinPresence.objects.select_related("medecin__user").filter(
        etablissement=etablissement,
        presence_date=today,
    ).order_by("-created_at", "-updated_at")
    latest_presence_by_doctor_id = {}
    open_presence_by_doctor_id = {}
    for presence in today_presences:
        if presence.medecin_id not in latest_presence_by_doctor_id:
            latest_presence_by_doctor_id[presence.medecin_id] = presence
        if (
            presence.medecin_id not in open_presence_by_doctor_id
            and presence.check_in_time
            and (not presence.check_out_time or presence.check_out_time < presence.check_in_time)
        ):
            open_presence_by_doctor_id[presence.medecin_id] = presence

    attendance_rows = []
    for doctor_link in doctor_links:
        open_presence = open_presence_by_doctor_id.get(doctor_link.medecin_id)
        latest_presence = latest_presence_by_doctor_id.get(doctor_link.medecin_id)
        presence = open_presence or latest_presence
        attendance_rows.append(
            {
                "doctor_link": doctor_link,
                "presence": presence,
                "is_checked_in": bool(open_presence),
            }
        )

    recent_logs = MedecinPresence.objects.select_related(
        "medecin__user",
        "declared_by_user",
        "etablissement",
    ).filter(etablissement=etablissement).order_by("-presence_date", "-updated_at")[:10]
    for log in recent_logs:
        log.duration_display = _format_presence_duration(log.check_in_time, log.check_out_time)

    doctors_present = sum(1 for row in attendance_rows if row["is_checked_in"])
    doctors_absent = max(len(attendance_rows) - doctors_present, 0)

    return render(
        request,
        "admin_etablissement/attendance.html",
        {
            "admin_profile": current_user,
            "etablissement": etablissement,
            "attendance_rows": attendance_rows,
            "recent_logs": recent_logs,
            "today": today,
            "current_timestamp": timezone.now(),
            "search_query": search_query,
            "attendance_stats": {
                "doctors_present": doctors_present,
                "doctors_absent": doctors_absent,
                "doctors_total": len(attendance_rows),
            },
        },
    )


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_patient_list(request):
    current_user_id = request.session.get("user_id")
    current_user = get_object_or_404(AppUser.objects.select_related("role"), pk=current_user_id)
    etablissement = _get_managed_facility_for_admin(current_user_id)

    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    patients = Patient.objects.filter(etablissement=etablissement).order_by("-created_at")
    if query:
        patients = patients.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(patient_code__icontains=query)
            | Q(barcode_value__icontains=query)
            | Q(phone__icontains=query)
            | Q(email__icontains=query)
        )
    if status == "active":
        patients = patients.filter(is_active=True)
    elif status == "inactive":
        patients = patients.filter(is_active=False)

    recent_patients = patients[:6]

    return render(
        request,
        "admin_etablissement/patients/list.html",
        {
            "admin_profile": current_user,
            "etablissement": etablissement,
            "patients": patients,
            "patients_count": patients.count(),
            "recent_patients": recent_patients,
            "filters": {
                "q": query,
                "status": status,
            },
        },
    )


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_appointment_list(request):
    current_user_id = request.session.get("user_id")
    current_user = get_object_or_404(AppUser.objects.select_related("role"), pk=current_user_id)
    etablissement = _get_managed_facility_for_admin(current_user_id)

    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    search_code = (request.GET.get("patient_code") or "").strip().upper()
    status = (request.GET.get("status") or "").strip()
    week_param = (request.GET.get("week") or "").strip()
    try:
        selected_anchor = datetime.strptime(week_param, "%Y-%m-%d").date() if week_param else timezone.localdate()
    except ValueError:
        selected_anchor = timezone.localdate()
    week_start = selected_anchor - timedelta(days=selected_anchor.weekday())
    week_end = week_start + timedelta(days=6)

    appointments = Appointment.objects.select_related(
        "patient",
        "medecin__user",
        "created_by_user",
    ).filter(etablissement=etablissement)
    if search_code:
        appointments = appointments.filter(patient__patient_code__icontains=search_code)
    if status:
        appointments = appointments.filter(status=status)
    appointments = appointments.order_by("scheduled_at")

    week_appointments = list(
        appointments.filter(
            scheduled_at__date__gte=week_start,
            scheduled_at__date__lte=week_end,
        )
    )
    appointments_today = appointments.filter(scheduled_at__date=timezone.localdate()).count()
    recent_appointments = appointments[:20]

    return render(
        request,
        "admin_etablissement/appointments/list.html",
        {
            "admin_profile": current_user,
            "etablissement": etablissement,
            "appointments": recent_appointments,
            "appointments_count": appointments.count(),
            "appointments_today": appointments_today,
            "week_appointments": week_appointments,
            "week_start": week_start,
            "week_end": week_end,
            "filters": {
                "patient_code": search_code,
                "status": status,
            },
            "status_choices": Appointment.STATUS_CHOICES,
        },
    )


@login_required
@role_required(["secretary", "secretaire", "infirmier", "assistant", "receptionniste", "technicien", "staff_frontdesk"])
def staff_attendance(request):
    current_user_id = request.session.get("user_id")
    current_user = get_object_or_404(AppUser.objects.select_related("role"), pk=current_user_id)
    staff_link = _get_current_staff_facility_link(current_user_id)

    if not staff_link or not staff_link.etablissement:
        messages.error(request, "Aucun etablissement actif n'est associe a ce compte.")
        return redirect("dashboard")
    if not _staff_has_permission(staff_link, "declare_presences"):
        return _reject_staff_permission(request, "declare_presences")

    facility = staff_link.etablissement
    doctor_links = MedecinEtablissement.objects.select_related("medecin__user", "etablissement").filter(
        etablissement=facility,
        actif=True,
    ).order_by("medecin__user__first_name", "medecin__user__last_name")
    search_query = (request.GET.get("q") or "").strip()
    if search_query:
        doctor_links = doctor_links.filter(
            Q(medecin__user__first_name__icontains=search_query)
            | Q(medecin__user__last_name__icontains=search_query)
            | Q(medecin__specialite__icontains=search_query)
            | Q(medecin__id__icontains=search_query)
        )
    today = timezone.localdate()
    today_presences = MedecinPresence.objects.select_related("medecin__user").filter(
        etablissement=facility,
        presence_date=today,
    ).order_by("-created_at", "-updated_at")
    latest_presence_by_doctor_id = {}
    open_presence_by_doctor_id = {}
    for presence in today_presences:
        if presence.medecin_id not in latest_presence_by_doctor_id:
            latest_presence_by_doctor_id[presence.medecin_id] = presence
        if (
            presence.medecin_id not in open_presence_by_doctor_id
            and presence.check_in_time
            and (not presence.check_out_time or presence.check_out_time < presence.check_in_time)
        ):
            open_presence_by_doctor_id[presence.medecin_id] = presence

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        medecin_id = (request.POST.get("medecin_id") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        selected_doctor_link = doctor_links.filter(medecin_id=medecin_id).first() if medecin_id else None
        if action not in {"check_in", "check_out", "absent", "delayed", "replaced"}:
            messages.error(request, "Action de presence invalide.")
        elif not selected_doctor_link:
            messages.error(request, "Aucun medecin selectionne.")
        else:
            current_timestamp = timezone.now()
            open_presence = open_presence_by_doctor_id.get(selected_doctor_link.medecin_id)
            latest_presence = latest_presence_by_doctor_id.get(selected_doctor_link.medecin_id)
            with transaction.atomic():
                if action == "check_in":
                    if open_presence:
                        messages.warning(request, "Ce medecin est deja en session. Utilise Check-out d'abord.")
                        return redirect(f"{request.path}?q={search_query}" if search_query else "staff_attendance")

                    MedecinPresence.objects.create(
                        medecin=selected_doctor_link.medecin,
                        etablissement=facility,
                        declared_by_user=current_user,
                        presence_date=today,
                        check_in_time=current_timestamp,
                        check_out_time=None,
                        status="present",
                        notes=notes,
                        created_at=current_timestamp,
                        updated_at=current_timestamp,
                    )
                elif action == "check_out":
                    if not open_presence:
                        messages.warning(request, "Aucune session ouverte a cloturer pour ce medecin.")
                        return redirect(f"{request.path}?q={search_query}" if search_query else "staff_attendance")

                    open_presence.declared_by_user = current_user
                    open_presence.check_out_time = current_timestamp
                    open_presence.status = open_presence.status or "present"
                    open_presence.notes = notes
                    open_presence.updated_at = current_timestamp
                    open_presence.save(
                        update_fields=[
                            "declared_by_user",
                            "check_out_time",
                            "status",
                            "notes",
                            "updated_at",
                        ]
                    )
                elif action == "delayed":
                    if open_presence:
                        open_presence.status = "delayed"
                        open_presence.notes = notes
                        open_presence.updated_at = current_timestamp
                        open_presence.save(update_fields=["status", "notes", "updated_at"])
                    else:
                        MedecinPresence.objects.create(
                            medecin=selected_doctor_link.medecin,
                            etablissement=facility,
                            declared_by_user=current_user,
                            presence_date=today,
                            check_in_time=current_timestamp,
                            check_out_time=None,
                            status="delayed",
                            notes=notes,
                            created_at=current_timestamp,
                            updated_at=current_timestamp,
                        )
                else:
                    target_presence = latest_presence
                    if target_presence and target_presence.presence_date == today:
                        target_presence.declared_by_user = current_user
                        target_presence.check_in_time = None
                        target_presence.check_out_time = None
                        target_presence.status = "absent" if action == "absent" else "replaced"
                        target_presence.notes = notes
                        target_presence.updated_at = current_timestamp
                        target_presence.save(
                            update_fields=[
                                "declared_by_user",
                                "check_in_time",
                                "check_out_time",
                                "status",
                                "notes",
                                "updated_at",
                            ]
                        )
                    else:
                        MedecinPresence.objects.create(
                            medecin=selected_doctor_link.medecin,
                            etablissement=facility,
                            declared_by_user=current_user,
                            presence_date=today,
                            check_in_time=None,
                            check_out_time=None,
                            status="absent" if action == "absent" else "replaced",
                            notes=notes,
                            created_at=current_timestamp,
                            updated_at=current_timestamp,
                        )
            messages.success(
                request,
                {
                    "check_in": "Check-in enregistre avec succes.",
                    "check_out": "Check-out enregistre avec succes.",
                    "absent": "Absence enregistree avec succes.",
                    "delayed": "Retard enregistre avec succes.",
                    "replaced": "Remplacement enregistre avec succes.",
                }[action],
            )
            return redirect(f"{request.path}?q={search_query}" if search_query else "staff_attendance")

    attendance_rows = []
    for doctor_link in doctor_links:
        open_presence = open_presence_by_doctor_id.get(doctor_link.medecin_id)
        latest_presence = latest_presence_by_doctor_id.get(doctor_link.medecin_id)
        presence = open_presence or latest_presence
        is_checked_in = bool(open_presence)
        attendance_rows.append(
            {
                "doctor_link": doctor_link,
                "presence": presence,
                "is_checked_in": is_checked_in,
                "next_action": "check_out" if is_checked_in else "check_in",
            }
        )

    recent_logs = MedecinPresence.objects.select_related(
        "medecin__user",
        "declared_by_user",
        "etablissement",
    ).filter(etablissement=facility).order_by("-presence_date", "-updated_at")[:10]
    for log in recent_logs:
        log.duration_display = _format_presence_duration(log.check_in_time, log.check_out_time)

    return render(
        request,
        "staff/attendance.html",
        {
            "staff_profile": current_user,
            "staff_link": staff_link,
            "staff_facility": facility,
            "attendance_rows": attendance_rows,
            "recent_logs": recent_logs,
            "today": today,
            "current_timestamp": timezone.now(),
            "search_query": search_query,
        },
    )


@login_required
@role_required(["secretary", "secretaire", "infirmier", "assistant", "receptionniste", "technicien", "staff_frontdesk"])
def staff_patient_list(request):
    current_user_id = request.session.get("user_id")
    current_user = get_object_or_404(AppUser.objects.select_related("role"), pk=current_user_id)
    staff_link = _get_current_staff_facility_link(current_user_id)

    if not staff_link or not staff_link.etablissement:
        messages.error(request, "Aucun etablissement actif n'est associe a ce compte.")
        return redirect("dashboard")
    if not _staff_has_permission(staff_link, "manage_patients"):
        return _reject_staff_permission(request, "manage_patients")

    facility = staff_link.etablissement
    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    patients = Patient.objects.filter(etablissement=facility).order_by("-created_at")
    if query:
        patients = patients.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(patient_code__icontains=query)
            | Q(barcode_value__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )
    if status == "active":
        patients = patients.filter(is_active=True)
    elif status == "inactive":
        patients = patients.filter(is_active=False)

    return render(
        request,
        "staff/patients/list.html",
        {
            "staff_profile": current_user,
            "staff_link": staff_link,
            "staff_facility": facility,
            "patients": patients[:50],
            "patients_count": patients.count(),
            "filters": {"q": query, "status": status},
        },
    )


@login_required
@role_required(["secretary", "secretaire", "infirmier", "assistant", "receptionniste", "technicien", "staff_frontdesk"])
def staff_patient_detail(request, patient_id):
    current_user_id = request.session.get("user_id")
    current_user = get_object_or_404(AppUser.objects.select_related("role"), pk=current_user_id)
    staff_link = _get_current_staff_facility_link(current_user_id)

    if not staff_link or not staff_link.etablissement:
        messages.error(request, "Aucun etablissement actif n'est associe a ce compte.")
        return redirect("dashboard")
    if not _staff_has_permission(staff_link, "manage_patients"):
        return _reject_staff_permission(request, "manage_patients")

    facility = staff_link.etablissement
    patient = get_object_or_404(Patient.objects.select_related("etablissement"), pk=patient_id, etablissement=facility)
    patient_appointments = Appointment.objects.select_related("medecin__user").filter(
        etablissement=facility,
        patient=patient,
    ).order_by("-scheduled_at")[:12]
    patient_vital_signs = PatientVitalSign.objects.select_related("etablissement").filter(
        patient=patient
    ).order_by("-measured_at", "-created_at")[:10]
    return render(
        request,
        "staff/patients/detail.html",
        {
            "staff_profile": current_user,
            "staff_link": staff_link,
            "staff_facility": facility,
            "patient": patient,
            "patient_appointments": patient_appointments,
            "patient_vital_signs": patient_vital_signs,
        },
    )


@login_required
@role_required(["secretary", "secretaire", "infirmier", "assistant", "receptionniste", "technicien", "staff_frontdesk"])
def staff_patient_create(request):
    current_user_id = request.session.get("user_id")
    current_user = get_object_or_404(AppUser.objects.select_related("role"), pk=current_user_id)
    staff_link = _get_current_staff_facility_link(current_user_id)

    if not staff_link or not staff_link.etablissement:
        messages.error(request, "Aucun etablissement actif n'est associe a ce compte.")
        return redirect("dashboard")
    if not _staff_has_permission(staff_link, "manage_patients"):
        return _reject_staff_permission(request, "manage_patients")

    facility = staff_link.etablissement
    created_patient_id = (request.GET.get("created") or "").strip()
    last_created_patient = None
    if created_patient_id:
        last_created_patient = Patient.objects.filter(
            pk=created_patient_id,
            etablissement=facility,
        ).first()
    form = PatientForm(request.POST or None, etablissement=facility)

    if request.method == "POST" and form.is_valid():
        current_timestamp = timezone.now()
        patient = form.save(commit=False)
        patient.etablissement = facility
        patient.patient_code = form.cleaned_data.get("patient_code")
        patient.barcode_value = form.cleaned_data["generated_barcode_value"]
        patient.is_active = form.cleaned_data.get("is_active", True)
        patient.created_at = current_timestamp
        patient.updated_at = current_timestamp
        patient.save()
        messages.success(
            request,
            f"Patient cree avec succes. Barcode: {patient.barcode_value}.",
        )
        return redirect(f"{reverse('staff_patient_create')}?created={patient.id}")

    return render(
        request,
        "staff/patients/create.html",
        {
            "form": form,
            "staff_profile": current_user,
            "staff_link": staff_link,
            "staff_facility": facility,
            "last_created_patient": last_created_patient,
        },
    )


@login_required
@role_required(["secretary", "secretaire", "infirmier", "assistant", "receptionniste", "technicien", "staff_frontdesk"])
def staff_patient_receipt(request, patient_id):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required."}, status=405)

    current_user_id = request.session.get("user_id")
    staff_link = _get_current_staff_facility_link(current_user_id)

    if not staff_link or not staff_link.etablissement:
        return JsonResponse({"ok": False, "error": "Aucun etablissement actif n'est associe a ce compte."}, status=400)
    if not _staff_has_permission(staff_link, "view_documents"):
        return JsonResponse(
            {"ok": False, "error": f"Permission requise: {STAFF_PERMISSION_LABELS['view_documents']}."},
            status=403,
        )

    facility = staff_link.etablissement
    patient = get_object_or_404(
        Patient.objects.select_related("etablissement"),
        pk=patient_id,
        etablissement=facility,
    )
    printer_name = (request.POST.get("printer") or "").strip() or "printer"
    printed_at = timezone.now()

    try:
        raw_bytes = _build_patient_receipt_raw(
            patient=patient,
            facility=facility,
            printer_name=printer_name,
            printed_at=printed_at,
        )
        _send_raw_receipt_to_printer(
            printer_name=printer_name,
            raw_bytes=raw_bytes,
            doc_name=patient.patient_code or str(patient.id),
        )
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)

    return JsonResponse(
        {
            "ok": True,
            "message": "Ticket envoye a l'imprimante.",
            "printer": printer_name,
            "patient_code": patient.patient_code,
        }
    )


@login_required
@role_required(["secretary", "secretaire", "infirmier", "assistant", "receptionniste", "technicien", "staff_frontdesk"])
def staff_appointments(request):
    current_user_id = request.session.get("user_id")
    current_user = get_object_or_404(AppUser.objects.select_related("role"), pk=current_user_id)
    staff_link = _get_current_staff_facility_link(current_user_id)

    if not staff_link or not staff_link.etablissement:
        messages.error(request, "Aucun etablissement actif n'est associe a ce compte.")
        return redirect("dashboard")
    if not _staff_has_permission(staff_link, "manage_appointments"):
        return _reject_staff_permission(request, "manage_appointments")

    facility = staff_link.etablissement
    form = StaffAppointmentForm(request.POST or None, etablissement=facility)
    search_code = (request.GET.get("patient_code") or "").strip().upper()
    week_param = (request.GET.get("week") or "").strip()
    try:
        selected_anchor = datetime.strptime(week_param, "%Y-%m-%d").date() if week_param else timezone.localdate()
    except ValueError:
        selected_anchor = timezone.localdate()
    week_start = selected_anchor - timedelta(days=selected_anchor.weekday())
    week_end = week_start + timedelta(days=6)

    if request.method == "POST" and form.is_valid():
        current_timestamp = timezone.now()
        scheduled_at = form.cleaned_data["scheduled_at"]
        if timezone.is_naive(scheduled_at):
            scheduled_at = timezone.make_aware(scheduled_at, timezone.get_current_timezone())
        duration_minutes = form.cleaned_data["duration_minutes"]

        appointment = form.save(commit=False)
        appointment.patient = form.patient_instance
        appointment.etablissement = facility
        appointment.created_by_user = current_user
        appointment.requested_by_id = current_user.id
        appointment.requested_by_type = "nurse" if (current_user.role and current_user.role.code == "infirmier") else "secretary"
        appointment.source = "hospital_desk"
        appointment.status = form.cleaned_data.get("status") or "pending"
        appointment.scheduled_at = scheduled_at
        appointment.scheduled_end_at = scheduled_at + timedelta(minutes=duration_minutes)
        appointment.created_at = current_timestamp
        appointment.updated_at = current_timestamp
        appointment.save()
        messages.success(
            request,
            f"Rendez-vous cree avec succes pour le patient {appointment.patient.patient_code or appointment.patient.barcode_value}.",
        )
        return redirect("staff_appointments")

    appointments = Appointment.objects.select_related(
        "patient",
        "medecin__user",
        "created_by_user",
    ).filter(
        etablissement=facility,
    )
    if search_code:
        appointments = appointments.filter(
            Q(patient__patient_code__icontains=search_code)
            | Q(patient__barcode_value__icontains=search_code)
        )
    appointments = appointments.order_by("scheduled_at")[:20]

    week_appointments_qs = Appointment.objects.select_related(
        "patient",
        "medecin__user",
    ).filter(
        etablissement=facility,
        scheduled_at__date__gte=week_start,
        scheduled_at__date__lte=week_end,
    )
    if search_code:
        week_appointments_qs = week_appointments_qs.filter(
            Q(patient__patient_code__icontains=search_code)
            | Q(patient__barcode_value__icontains=search_code)
        )
    week_appointments = list(week_appointments_qs.order_by("scheduled_at"))

    selected_month = selected_anchor.replace(day=1)
    month_calendar = _build_month_calendar(selected_month)
    appointment_dates = set(timezone.localtime(item.scheduled_at).date().isoformat() for item in week_appointments)
    for week in month_calendar["weeks"]:
        for day in week:
            day["has_appointment"] = day["iso"] in appointment_dates
            day["is_selected_week"] = week_start <= day["date"] <= week_end

    week_days = []
    week_day_appointments = []
    hour_start = 8 * 60
    hour_end = 18 * 60
    total_minutes = hour_end - hour_start
    status_palette = {
        "pending": {"card": "bg-blue-50 border-blue-600", "text": "text-blue-800", "meta": "text-blue-600"},
        "confirmed": {"card": "bg-emerald-50 border-emerald-600", "text": "text-emerald-800", "meta": "text-emerald-600"},
        "cancelled": {"card": "bg-red-50 border-red-600", "text": "text-red-800", "meta": "text-red-600"},
        "completed": {"card": "bg-slate-100 border-slate-500", "text": "text-slate-800", "meta": "text-slate-500"},
        "no_show": {"card": "bg-amber-50 border-amber-500", "text": "text-amber-800", "meta": "text-amber-600"},
        "follow_up_planned": {"card": "bg-violet-50 border-violet-600", "text": "text-violet-800", "meta": "text-violet-600"},
    }
    appointments_by_day = {index: [] for index in range(7)}

    for index in range(7):
        current_day = week_start + timedelta(days=index)
        week_days.append(
            {
                "date": current_day,
                "weekday_short": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][index],
                "day_number": current_day.day,
                "is_today": current_day == timezone.localdate(),
            }
        )

    doctor_filter_rows = []
    doctor_color_map = {}
    for idx, doctor_link in enumerate(
        MedecinEtablissement.objects.select_related("medecin__user").filter(
            etablissement=facility,
            actif=True,
        ).order_by("medecin__user__first_name", "medecin__user__last_name")[:6]
    ):
        color_class = ["bg-blue-500", "bg-orange-500", "bg-emerald-500", "bg-violet-500", "bg-rose-500", "bg-cyan-500"][idx % 6]
        doctor_color_map[str(doctor_link.medecin_id)] = color_class
        doctor_filter_rows.append(
            {
                "doctor": doctor_link.medecin,
                "color_class": color_class,
                "weekly_count": len([item for item in week_appointments if item.medecin_id == doctor_link.medecin_id]),
            }
        )

    for appointment in week_appointments:
        local_start = timezone.localtime(appointment.scheduled_at)
        local_end = timezone.localtime(appointment.scheduled_end_at)
        day_index = (local_start.date() - week_start).days
        if day_index < 0 or day_index > 6:
            continue
        start_minutes = (local_start.hour * 60) + local_start.minute
        end_minutes = (local_end.hour * 60) + local_end.minute
        clipped_start = max(start_minutes, hour_start)
        clipped_end = min(end_minutes, hour_end)
        if clipped_end <= hour_start or clipped_start >= hour_end:
            continue
        top_percent = ((clipped_start - hour_start) / total_minutes) * 100
        height_percent = max(((clipped_end - clipped_start) / total_minutes) * 100, 9)
        palette = status_palette.get(appointment.status, status_palette["pending"])
        appointments_by_day[day_index].append(
            {
                "patient_code": appointment.patient.patient_code,
                "patient_name": appointment.patient.full_name,
                "doctor_id": str(appointment.medecin_id),
                "doctor_name": appointment.medecin.full_name or appointment.medecin.email,
                "reason": appointment.reason or "Consultation",
                "start_label": local_start.strftime("%H:%M"),
                "end_label": local_end.strftime("%H:%M"),
                "top_percent": round(top_percent, 2),
                "height_percent": round(height_percent, 2),
                "card_class": palette["card"],
                "text_class": palette["text"],
                "meta_class": palette["meta"],
                "dot_class": doctor_color_map.get(str(appointment.medecin_id), "bg-blue-500"),
            }
        )

    for index in range(7):
        week_day_appointments.append({"day": week_days[index], "appointments": appointments_by_day[index]})

    appointments_today_count = Appointment.objects.filter(
        etablissement=facility,
        scheduled_at__date=timezone.localdate(),
    ).count()

    return render(
        request,
        "staff/appointments/index.html",
        {
            "form": form,
            "staff_profile": current_user,
            "staff_link": staff_link,
            "staff_facility": facility,
            "appointments": appointments,
            "search_code": search_code,
            "month_calendar": month_calendar,
            "week_start": week_start,
            "week_end": week_end,
            "week_days": week_days,
            "week_day_appointments": week_day_appointments,
            "time_labels": [f"{hour:02d}:00" for hour in range(8, 18)],
            "today_week": timezone.localdate().isoformat(),
            "previous_week": (week_start - timedelta(days=7)).isoformat(),
            "next_week": (week_start + timedelta(days=7)).isoformat(),
            "doctor_filter_rows": doctor_filter_rows,
            "staff_calendar_stats": {
                "appointments_today": appointments_today_count,
                "staff_on_duty": PersonnelEtablissement.objects.filter(etablissement=facility, est_actif=True).count(),
                "doctors_total": MedecinEtablissement.objects.filter(etablissement=facility, actif=True).count(),
                "capacity_percent": min(max(appointments_today_count * 5, 0), 100),
            },
        },
    )


@login_required
@role_required(["medecin", "doctor"])
def doctor_invitations(request):
    current_user_id = request.session.get("user_id")
    doctor = _get_current_doctor(current_user_id)
    doctor_facility_links = _get_doctor_facility_links(doctor)

    invitations = (
        MedecinEtablissementInvitation.objects.select_related("etablissement", "medecin")
        .filter(
            Q(medecin=doctor) | Q(medecin_email__iexact=doctor.email if doctor and doctor.email else ""),
        )
        .order_by("-created_at")
    ) if doctor else MedecinEtablissementInvitation.objects.none()

    context = {
        "doctor_profile": doctor,
        "doctor_facility_links": doctor_facility_links,
        "invitations": invitations[:20],
        "invitation_stats": {
            "total_sent": invitations.count() if doctor else 0,
            "pending": invitations.filter(status="pending").count() if doctor else 0,
            "accepted": invitations.filter(status="accepted").count() if doctor else 0,
            "expired": invitations.filter(status="expired").count() if doctor else 0,
        },
    }
    return render(request, "doctor/invitations.html", context)


@login_required
@role_required(["medecin", "doctor"])
def doctor_invitation_open(request, token):
    current_user_id = request.session.get("user_id")
    doctor = _get_current_doctor(current_user_id)
    if not doctor:
        messages.error(request, "Profil medecin introuvable.")
        return redirect("doctor_invitations")

    invitation = get_object_or_404(
        MedecinEtablissementInvitation.objects.select_related("etablissement", "medecin"),
        invitation_token=token,
    )
    owns_invitation = invitation.medecin_id == doctor.id or (
        doctor.email and invitation.medecin_email and invitation.medecin_email.lower() == doctor.email.lower()
    )
    if not owns_invitation:
        messages.error(request, "Cette invitation ne vous appartient pas.")
        return redirect("doctor_invitations")

    if invitation.status == "pending" and invitation.pin_expires_at and invitation.pin_expires_at <= timezone.now():
        invitation.status = "expired"
        invitation.updated_at = timezone.now()
        invitation.save(update_fields=["status", "updated_at"])

    return render(
        request,
        "doctor/invitation_open.html",
        {
            "doctor_profile": doctor,
            "doctor_facility_links": _get_doctor_facility_links(doctor),
            "invitation": invitation,
            "decision_form": DoctorInvitationDecisionForm(),
        },
    )


@login_required
@role_required(["medecin", "doctor"])
def doctor_invitation_decision(request, invitation_id):
    if request.method != "POST":
        return redirect("doctor_invitations")

    current_user_id = request.session.get("user_id")
    doctor = (
        Medecin.objects.select_related("user", "user__role")
        .filter(user_id=current_user_id)
        .first()
    )
    if not doctor:
        messages.error(request, "Profil medecin introuvable.")
        return redirect("doctor_invitations")

    invitation = get_object_or_404(
        MedecinEtablissementInvitation.objects.select_related("etablissement", "medecin"),
        pk=invitation_id,
    )

    owns_invitation = invitation.medecin_id == doctor.id or (
        doctor.email and invitation.medecin_email and invitation.medecin_email.lower() == doctor.email.lower()
    )
    if not owns_invitation:
        messages.error(request, "Cette invitation ne vous appartient pas.")
        return redirect("doctor_invitations")

    if invitation.status != "pending":
        messages.warning(request, "Cette invitation n'est plus en attente.")
        return redirect("doctor_invitations")

    form = DoctorInvitationDecisionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Le code PIN et l'action sont obligatoires.")
        return redirect("doctor_invitations")

    pin_code = form.cleaned_data["pin_code"]
    action = form.cleaned_data["action"]

    if not check_password(pin_code, invitation.pin_hash):
        messages.error(request, "Code PIN invalide.")
        return redirect("doctor_invitations")

    if invitation.pin_expires_at and invitation.pin_expires_at <= timezone.now():
        invitation.status = "expired"
        invitation.updated_at = timezone.now()
        invitation.save(update_fields=["status", "updated_at"])
        messages.error(request, "Cette invitation a expire.")
        return redirect("doctor_invitations")

    if action == "accept":
        with transaction.atomic():
            link, created = MedecinEtablissement.objects.get_or_create(
                medecin=doctor,
                etablissement=invitation.etablissement,
                defaults={
                    "role": invitation.role,
                    "est_principal": False,
                    "created_at": timezone.now(),
                    "pin_hash": invitation.pin_hash,
                    "pin_updated_at": timezone.now(),
                    "actif": True,
                    "can_issue_prescriptions": invitation.can_issue_prescriptions,
                    "can_sign_documents": invitation.can_sign_documents,
                    "updated_at": timezone.now(),
                },
            )
            if not created:
                link.role = invitation.role
                link.pin_hash = invitation.pin_hash
                link.pin_updated_at = timezone.now()
                link.actif = True
                link.can_issue_prescriptions = invitation.can_issue_prescriptions
                link.can_sign_documents = invitation.can_sign_documents
                link.updated_at = timezone.now()
                link.save(
                    update_fields=[
                        "role",
                        "pin_hash",
                        "pin_updated_at",
                        "actif",
                        "can_issue_prescriptions",
                        "can_sign_documents",
                        "updated_at",
                    ]
                )

            invitation.medecin = doctor
            invitation.status = "accepted"
            invitation.accepted_at = timezone.now()
            invitation.updated_at = timezone.now()
            invitation.save(
                update_fields=[
                    "medecin",
                    "status",
                    "accepted_at",
                    "updated_at",
                ]
            )

        messages.success(request, "Invitation acceptee avec succes.")
        return redirect("doctor_invitations")

    invitation.medecin = doctor
    invitation.status = "rejected"
    invitation.rejected_at = timezone.now()
    invitation.updated_at = timezone.now()
    invitation.save(
        update_fields=[
            "medecin",
            "status",
            "rejected_at",
            "updated_at",
        ]
    )
    messages.success(request, "Invitation refusee avec succes.")
    return redirect("doctor_invitations")


@login_required
@role_required(["medecin", "doctor"])
def doctor_availability(request):
    current_user_id = request.session.get("user_id")
    doctor = _get_current_doctor(current_user_id)
    if not doctor:
        messages.error(request, "Profil medecin introuvable.")
        return redirect("dashboard")

    selected_link, doctor_facility_links, selected_facility_id = _get_selected_doctor_facility_link(request, doctor)
    if not selected_link:
        messages.error(request, "Aucun etablissement actif n'est lie a ce medecin.")
        return redirect("dashboard")

    form_data = request.POST.copy() if request.method == "POST" else None
    if form_data is not None:
        form_data["medecin"] = str(doctor.id)
    form = (
        MedecinIndisponibiliteForm(form_data, doctor_queryset=Medecin.objects.filter(pk=doctor.id))
        if request.method == "POST"
        else MedecinIndisponibiliteForm(doctor_queryset=Medecin.objects.filter(pk=doctor.id), initial={"medecin": doctor.id})
    )
    form.fields["medecin"].widget = forms.HiddenInput()

    if request.method == "POST" and form.is_valid():
        entry = form.save(commit=False)
        entry.medecin = doctor
        entry.etablissement = selected_link.etablissement
        entry.declared_by_user = doctor.user
        entry.created_at = timezone.now()
        entry.updated_at = timezone.now()
        if entry.toute_la_journee:
            entry.heure_debut = None
            entry.heure_fin = None
        entry.save()
        messages.success(request, "Indisponibilite enregistree avec succes.")
        return redirect(f"{reverse('doctor_availability')}?facility={selected_link.etablissement_id}")

    entries_qs = (
        MedecinIndisponibilite.objects.filter(
            etablissement=selected_link.etablissement,
            medecin=doctor,
        )
        .order_by("date_debut", "heure_debut", "created_at")
    )
    today = timezone.localdate()
    current_entry = next((item for item in entries_qs if item.date_debut <= today <= item.date_fin), None)
    calendar_payload = _serialize_unavailability_payload(doctor_link=selected_link)

    return render(
        request,
        "doctor/availability/list.html",
        {
            "doctor_profile": doctor,
            "doctor_facility_links": doctor_facility_links,
            "selected_link": selected_link,
            "selected_facility_id": selected_link.etablissement_id,
            "entries": entries_qs[:8],
            "entries_count": entries_qs.count(),
            "current_entry": current_entry,
            "next_periods": _get_next_presence_periods(
                etablissement=selected_link.etablissement,
                doctor=doctor,
                limit=3,
            ),
            "form": form,
            "type_choices": MedecinIndisponibilite.TYPE_CHOICES,
            "calendar_payload_json": json.dumps(calendar_payload, ensure_ascii=True),
        },
    )


@login_required
@role_required(["medecin", "doctor"])
def doctor_schedule(request):
    current_user_id = request.session.get("user_id")
    doctor = _get_current_doctor(current_user_id)
    if not doctor:
        messages.error(request, "Profil medecin introuvable.")
        return redirect("dashboard")

    selected_link, doctor_facility_links, _ = _get_selected_doctor_facility_link(request, doctor)
    if not selected_link:
        messages.error(request, "Aucun etablissement actif n'est lie a ce medecin.")
        return redirect("dashboard")

    if request.method == "POST":
        now = timezone.now()
        errors = []
        day_payloads = []
        for weekday in WEEKDAY_ROWS:
            day_code = weekday["code"]
            is_active = request.POST.get(f"{day_code}_enabled") == "on"
            notes = (request.POST.get(f"{day_code}_notes") or "").strip()
            interval_payloads = []
            for slot in range(1, SCHEDULE_INTERVAL_SLOTS + 1):
                start_value = _parse_time_value(request.POST.get(f"{day_code}_start_{slot}"))
                end_value = _parse_time_value(request.POST.get(f"{day_code}_end_{slot}"))
                if start_value and end_value:
                    if end_value <= start_value:
                        errors.append(f"{weekday['label']} - le creneau {slot} doit se terminer apres son debut.")
                    else:
                        interval_payloads.append((slot, start_value, end_value))
                elif start_value or end_value:
                    errors.append(f"{weekday['label']} - le creneau {slot} est incomplet.")
            if is_active and not interval_payloads:
                errors.append(f"{weekday['label']} est active mais aucun intervalle complet n'a ete saisi.")
            day_payloads.append(
                {
                    "weekday_index": weekday["index"],
                    "is_active": is_active,
                    "notes": notes,
                    "intervals": interval_payloads,
                }
            )

        if not errors:
            with transaction.atomic():
                for payload in day_payloads:
                    schedule_entry, created = MedecinHoraireSemaine.objects.get_or_create(
                        etablissement=selected_link.etablissement,
                        medecin=doctor,
                        weekday=payload["weekday_index"],
                        defaults={
                            "is_active": payload["is_active"],
                            "notes": payload["notes"],
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    if not created:
                        schedule_entry.is_active = payload["is_active"]
                        schedule_entry.notes = payload["notes"]
                        schedule_entry.updated_at = now
                        schedule_entry.save(update_fields=["is_active", "notes", "updated_at"])
                    MedecinHoraireIntervalle.objects.filter(horaire=schedule_entry).delete()
                    for slot, start_value, end_value in payload["intervals"]:
                        MedecinHoraireIntervalle.objects.create(
                            horaire=schedule_entry,
                            ordre=slot,
                            heure_debut=start_value,
                            heure_fin=end_value,
                            created_at=now,
                            updated_at=now,
                        )
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            messages.success(request, "Horaire hebdomadaire mis a jour avec succes.")
            return redirect(f"{reverse('doctor_schedule')}?facility={selected_link.etablissement_id}")

    return render(
        request,
        "doctor/availability/schedule.html",
        {
            "doctor_profile": doctor,
            "doctor_facility_links": doctor_facility_links,
            "doctor_link": selected_link,
            "selected_facility_id": selected_link.etablissement_id,
            "weekday_rows": _build_doctor_schedule_rows(selected_link),
            "interval_slots": range(1, SCHEDULE_INTERVAL_SLOTS + 1),
        },
    )


@login_required
@role_required(["medecin", "doctor"])
def doctor_calendar(request):
    current_user_id = request.session.get("user_id")
    doctor = _get_current_doctor(current_user_id)
    if not doctor:
        messages.error(request, "Profil medecin introuvable.")
        return redirect("dashboard")

    doctor_facility_links = list(_get_doctor_facility_links(doctor))
    if not doctor_facility_links:
        messages.error(request, "Aucun etablissement actif n'est lie a ce medecin.")
        return redirect("dashboard")

    selected_month_raw = (request.GET.get("month") or "").strip()
    try:
        selected_month = datetime.strptime(selected_month_raw, "%Y-%m").date().replace(day=1) if selected_month_raw else timezone.localdate().replace(day=1)
    except ValueError:
        selected_month = timezone.localdate().replace(day=1)

    calendar_data, month_entries = _build_doctor_global_unavailability_calendar(
        doctor_links=doctor_facility_links,
        selected_month=selected_month,
    )
    previous_month = (selected_month.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (selected_month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return render(
        request,
        "doctor/availability/calendar.html",
        {
            "doctor_profile": doctor,
            "doctor_facility_links": doctor_facility_links,
            "calendar_data": calendar_data,
            "month_entries": month_entries,
            "selected_month": selected_month.strftime("%Y-%m"),
            "previous_month": previous_month.strftime("%Y-%m"),
            "next_month": next_month.strftime("%Y-%m"),
        },
    )


@login_required
@role_required(["medecin", "doctor"])
def doctor_leaves(request):
    current_user_id = request.session.get("user_id")
    doctor = _get_current_doctor(current_user_id)
    if not doctor:
        messages.error(request, "Profil medecin introuvable.")
        return redirect("dashboard")

    selected_link, doctor_facility_links, _ = _get_selected_doctor_facility_link(request, doctor)
    if not selected_link:
        messages.error(request, "Aucun etablissement actif n'est lie a ce medecin.")
        return redirect("dashboard")

    selected_month_raw = (request.GET.get("month") or request.POST.get("selected_month") or "").strip()
    try:
        selected_month = datetime.strptime(selected_month_raw, "%Y-%m").date().replace(day=1) if selected_month_raw else timezone.localdate().replace(day=1)
    except ValueError:
        selected_month = timezone.localdate().replace(day=1)

    if request.method == "POST":
        selected_days = request.POST.getlist("selected_days")
        motif = (request.POST.get("motif") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        if not selected_days:
            messages.error(request, "Selectionne au moins un jour de conge.")
        elif not motif:
            messages.error(request, "Le motif du conge est requis.")
        else:
            now = timezone.now()
            created_count = 0
            with transaction.atomic():
                for raw_day in selected_days:
                    try:
                        leave_day = datetime.strptime(raw_day, "%Y-%m-%d").date()
                    except ValueError:
                        continue
                    if MedecinIndisponibilite.objects.filter(
                        medecin=doctor,
                        etablissement=selected_link.etablissement,
                        type_indisponibilite="conge",
                        date_debut=leave_day,
                        date_fin=leave_day,
                    ).exists():
                        continue
                    MedecinIndisponibilite.objects.create(
                        medecin=doctor,
                        etablissement=selected_link.etablissement,
                        declared_by_user=doctor.user,
                        type_indisponibilite="conge",
                        motif=motif,
                        date_debut=leave_day,
                        date_fin=leave_day,
                        heure_debut=None,
                        heure_fin=None,
                        toute_la_journee=True,
                        notes=notes,
                        created_at=now,
                        updated_at=now,
                    )
                    created_count += 1
            if created_count:
                messages.success(request, f"{created_count} jour(s) de conge enregistre(s) avec succes.")
                return redirect(f"{reverse('doctor_leaves')}?facility={selected_link.etablissement_id}&month={selected_month.strftime('%Y-%m')}")
            messages.error(request, "Aucun jour valide n'a ete enregistre.")

    leaves = (
        MedecinIndisponibilite.objects.select_related("medecin__user")
        .filter(etablissement=selected_link.etablissement, medecin=doctor, type_indisponibilite="conge")
        .order_by("date_debut", "heure_debut", "created_at")
    )
    leave_days = {leave.date_debut.isoformat() for leave in leaves if leave.date_debut == leave.date_fin}
    previous_month = (selected_month.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (selected_month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return render(
        request,
        "doctor/availability/leaves.html",
        {
            "doctor_profile": doctor,
            "doctor_facility_links": doctor_facility_links,
            "doctor_link": selected_link,
            "selected_facility_id": selected_link.etablissement_id,
            "leaves": leaves,
            "calendar_data": _build_month_calendar(selected_month),
            "leave_days": leave_days,
            "selected_month": selected_month.strftime("%Y-%m"),
            "previous_month": previous_month.strftime("%Y-%m"),
            "next_month": next_month.strftime("%Y-%m"),
        },
    )


@login_required
@role_required(["medecin", "doctor"])
def doctor_appointments(request):
    current_user_id = request.session.get("user_id")
    doctor = _get_current_doctor(current_user_id)
    if not doctor:
        messages.error(request, "Profil medecin introuvable.")
        return redirect("dashboard")

    selected_link, doctor_facility_links, selected_facility_id = _get_selected_doctor_facility_link(request, doctor)
    active_links = list(doctor_facility_links)
    if not active_links:
        messages.error(request, "Aucun etablissement actif n'est lie a ce medecin.")
        return redirect("dashboard")

    facility_ids = [link.etablissement_id for link in active_links]
    appointments = Appointment.objects.select_related("patient", "medecin__user", "etablissement").filter(
        medecin=doctor,
        etablissement_id__in=facility_ids,
    )
    if selected_facility_id and selected_link:
        appointments = appointments.filter(etablissement=selected_link.etablissement)
    patient_code = (request.GET.get("patient_code") or "").strip().upper()
    status = (request.GET.get("status") or "").strip()
    if patient_code:
        appointments = appointments.filter(patient__patient_code__icontains=patient_code)
    if status:
        appointments = appointments.filter(status=status)
    appointments = appointments.order_by("scheduled_at")

    today = timezone.localdate()
    appointments_today = appointments.filter(scheduled_at__date=today).count()
    upcoming_appointments = appointments.filter(scheduled_at__date__gte=today).count()
    return render(
        request,
        "doctor/appointments/list.html",
        {
            "doctor_profile": doctor,
            "doctor_facility_links": doctor_facility_links,
            "selected_link": selected_link,
            "selected_facility_id": selected_facility_id,
            "appointments": appointments[:30],
            "appointments_count": appointments.count(),
            "appointments_today": appointments_today,
            "upcoming_appointments": upcoming_appointments,
            "status_choices": Appointment.STATUS_CHOICES,
            "filters": {
                "patient_code": patient_code,
                "status": status,
            },
        },
    )


@login_required
@role_required(["medecin", "doctor"])
def doctor_appointment_detail(request, appointment_id):
    current_user_id = request.session.get("user_id")
    doctor = _get_current_doctor(current_user_id)
    if not doctor:
        messages.error(request, "Profil medecin introuvable.")
        return redirect("dashboard")

    doctor_facility_links = _get_doctor_facility_links(doctor)
    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "etablissement", "created_by_user", "medecin__user"),
        pk=appointment_id,
        medecin=doctor,
    )
    doctor_link = doctor_facility_links.filter(etablissement=appointment.etablissement).first()
    if not doctor_link:
        messages.error(request, "Ce rendez-vous n'est pas accessible.")
        return redirect("doctor_appointments")

    allowed_statuses = {"confirmed", "completed", "no_show"}
    if request.method == "POST":
        new_status = (request.POST.get("status") or "").strip()
        if new_status not in allowed_statuses:
            messages.error(request, "Statut invalide.")
        else:
            appointment.status = new_status
            appointment.updated_at = timezone.now()
            appointment.save(update_fields=["status", "updated_at"])
            messages.success(request, "Statut du rendez-vous mis a jour avec succes.")
            return redirect("doctor_appointment_detail", appointment_id=appointment.id)

    return render(
        request,
        "doctor/appointments/detail.html",
        {
            "doctor_profile": doctor,
            "doctor_facility_links": doctor_facility_links,
            "doctor_link": doctor_link,
            "appointment": appointment,
            "allowed_statuses": [item for item in Appointment.STATUS_CHOICES if item[0] in allowed_statuses],
        },
    )


@login_required
@role_required(["medecin", "doctor"])
def doctor_patient_list(request):
    current_user_id = request.session.get("user_id")
    doctor = _get_current_doctor(current_user_id)
    if not doctor:
        messages.error(request, "Profil medecin introuvable.")
        return redirect("dashboard")

    selected_link, doctor_facility_links, selected_facility_id = _get_selected_doctor_facility_link(request, doctor)
    active_links = list(doctor_facility_links)
    if not active_links:
        messages.error(request, "Aucun etablissement actif n'est lie a ce medecin.")
        return redirect("dashboard")

    facility_ids = [link.etablissement_id for link in active_links]
    patients = Patient.objects.filter(
        appointments__medecin=doctor,
        appointments__etablissement_id__in=facility_ids,
    ).distinct().order_by("-created_at")
    if selected_facility_id and selected_link:
        patients = patients.filter(appointments__etablissement=selected_link.etablissement)
    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    if query:
        patients = patients.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(patient_code__icontains=query)
            | Q(barcode_value__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )
    if status == "active":
        patients = patients.filter(is_active=True)
    elif status == "inactive":
        patients = patients.filter(is_active=False)

    return render(
        request,
        "doctor/patients/list.html",
        {
            "doctor_profile": doctor,
            "doctor_facility_links": doctor_facility_links,
            "selected_link": selected_link,
            "selected_facility_id": selected_facility_id,
            "patients": patients[:50],
            "patients_count": patients.count(),
            "filters": {
                "q": query,
                "status": status,
            },
        },
    )


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_staff_list(request):
    current_user_id = request.session.get("user_id")
    etablissement = _get_managed_facility_for_admin(current_user_id)
    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    query = (request.GET.get("q") or "").strip()
    role_code = (request.GET.get("role") or "").strip()
    status = (request.GET.get("status") or "").strip()

    staff_links = _get_staff_links_queryset(etablissement).filter(
        personnel_user__role__isnull=False
    ).filter(_admin_etablissement_staff_link_role_filter()).order_by("-created_at")
    roles = Role.objects.filter(_admin_etablissement_role_option_filter()).order_by("nom")

    if query:
        staff_links = staff_links.filter(
            Q(personnel_user__first_name__icontains=query)
            | Q(personnel_user__last_name__icontains=query)
            | Q(personnel_user__email__icontains=query)
            | Q(personnel_user__phone__icontains=query)
        )

    if role_code and role_code.lower() in ADMIN_ETABLISSEMENT_STAFF_ROLE_CODES:
        staff_links = staff_links.filter(
            Q(personnel_user__role__code__iexact=role_code) | Q(personnel_user__role__nom__iexact=role_code)
        )

    if status == "active":
        staff_links = staff_links.filter(personnel_user__is_active=True, est_actif=True)
    elif status == "inactive":
        staff_links = staff_links.filter(Q(personnel_user__is_active=False) | Q(est_actif=False))

    user_rows = []
    for staff_link in staff_links:
        user_obj = staff_link.personnel_user
        user_rows.append(
            {
                "user": user_obj,
                "staff_link": staff_link,
                "permission_rows": _get_or_build_staff_permission_rows(staff_link),
            }
        )

    return render(
        request,
        "admin_etablissement/staff/list.html",
        {
            "user_rows": user_rows,
            "roles": roles,
            "filters": {
                "q": query,
                "role": role_code,
                "status": status,
            },
            "users_count": len(user_rows),
            "etablissement": etablissement,
        },
    )


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_staff_detail(request, user_id):
    current_user_id = request.session.get("user_id")
    etablissement = _get_managed_facility_for_admin(current_user_id)
    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    staff_link = get_object_or_404(
        _get_staff_links_queryset(etablissement).filter(_admin_etablissement_staff_link_role_filter()),
        personnel_user_id=user_id,
    )
    user_obj = staff_link.personnel_user
    return render(
        request,
        "admin_etablissement/staff/detail.html",
        {
            "user_obj": user_obj,
            "etablissement": etablissement,
            "staff_link": staff_link,
            "permission_rows": _get_or_build_staff_permission_rows(staff_link),
        },
    )


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_staff_create(request):
    current_user_id = request.session.get("user_id")
    etablissement = _get_managed_facility_for_admin(current_user_id)
    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    form = AppUserForm(
        request.POST or None,
        require_password=True,
        allowed_role_codes=ADMIN_ETABLISSEMENT_STAFF_ROLE_CODES,
    )
    selected_role_code = ""
    permission_form = None
    if request.method == "POST":
        selected_role_code = _resolve_staff_role_code((request.POST.get("role") or "").strip())
        permission_form = _get_staff_permission_form(selected_role_code, request.POST)
    else:
        permission_form = _get_staff_permission_form(selected_role_code)

    if request.method == "POST" and form.is_valid() and permission_form.is_valid():
        service = SupabaseAdminService()
        role = form.cleaned_data["role"]
        password = form.cleaned_data["password"]

        try:
            with transaction.atomic():
                auth_user = service.create_auth_user(
                    email=form.cleaned_data["email"],
                    password=password,
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    phone=form.cleaned_data.get("phone") or "",
                    role_code=role.code if role else "",
                    require_password_change=True,
                )

                auth_user_id = auth_user["id"]
                existing_user = AppUser.objects.filter(pk=auth_user_id).first()
                if existing_user:
                    existing_user.role = role
                    existing_user.first_name = form.cleaned_data["first_name"]
                    existing_user.last_name = form.cleaned_data["last_name"]
                    existing_user.phone = form.cleaned_data.get("phone") or ""
                    existing_user.email = form.cleaned_data["email"]
                    existing_user.is_active = form.cleaned_data["is_active"]
                    existing_user.updated_at = timezone.now()
                    existing_user.save(
                        update_fields=[
                            "role",
                            "first_name",
                            "last_name",
                            "phone",
                            "email",
                            "is_active",
                            "updated_at",
                        ]
                    )
                    user_obj = existing_user
                else:
                    user_obj = AppUser.objects.create(
                        id=auth_user_id,
                        role=role,
                        first_name=form.cleaned_data["first_name"],
                        last_name=form.cleaned_data["last_name"],
                        phone=form.cleaned_data.get("phone") or "",
                        email=form.cleaned_data["email"],
                        is_active=form.cleaned_data["is_active"],
                        created_at=timezone.now(),
                        updated_at=timezone.now(),
                    )

                staff_link, _ = PersonnelEtablissement.objects.update_or_create(
                    etablissement=etablissement,
                    personnel_user=user_obj,
                    defaults={
                        "role": _map_app_role_to_personnel_role(role),
                        "est_actif": form.cleaned_data["is_active"],
                        "created_at": timezone.now(),
                        "date_fin": None,
                        "updated_at": timezone.now(),
                        "date_debut": timezone.now().date(),
                    },
                )
                PersonnelEtablissementPermission.objects.update_or_create(
                    personnel_etablissement=staff_link,
                    defaults={
                        "can_manage_patients": permission_form.cleaned_data["can_manage_patients"],
                        "can_manage_appointments": permission_form.cleaned_data["can_manage_appointments"],
                        "can_declare_presences": permission_form.cleaned_data["can_declare_presences"],
                        "can_view_documents": permission_form.cleaned_data["can_view_documents"],
                        "created_at": timezone.now(),
                        "updated_at": timezone.now(),
                    },
                )
        except SupabaseAdminError as exc:
            form.add_error(None, str(exc))
        except Exception as exc:
            try:
                if "auth_user_id" in locals():
                    service.delete_auth_user(user_id=auth_user_id)
            except SupabaseAdminError:
                pass
            form.add_error(None, f"Unable to create user: {exc}")
        else:
            messages.success(request, "Membre du personnel cree avec succes.")
            return redirect("admin_etablissement_staff_list")

    return render(
        request,
        "admin_etablissement/staff/create.html",
        {
            "form": form,
            "page_mode": "create",
            "page_title": "Create Staff",
            "page_heading": "New Facility Staff",
            "submit_label": "Create Account",
            "etablissement": etablissement,
            "permission_form": permission_form,
        },
    )


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_staff_edit(request, user_id):
    current_user_id = request.session.get("user_id")
    etablissement = _get_managed_facility_for_admin(current_user_id)
    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    staff_link = get_object_or_404(
        _get_staff_links_queryset(etablissement).filter(_admin_etablissement_staff_link_role_filter()),
        personnel_user_id=user_id,
    )
    user_obj = staff_link.personnel_user
    form = AppUserForm(
        request.POST or None,
        instance=user_obj,
        require_password=False,
        allowed_role_codes=ADMIN_ETABLISSEMENT_STAFF_ROLE_CODES,
    )
    existing_permission = getattr(staff_link, "permissions", None)
    selected_role_code = (
        _resolve_staff_role_code((request.POST.get("role") or "").strip())
        if request.method == "POST"
        else staff_link.role
    )
    if request.method == "POST":
        permission_form = _get_staff_permission_form(selected_role_code, request.POST, instance=existing_permission)
    else:
        permission_form = _get_staff_permission_form(selected_role_code, instance=existing_permission)

    if request.method == "POST" and form.is_valid() and permission_form.is_valid():
        service = SupabaseAdminService()
        role = form.cleaned_data["role"]
        original_email = user_obj.email

        try:
            with transaction.atomic():
                service.update_auth_user(
                    user_id=str(user_obj.id),
                    email=form.cleaned_data["email"],
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    phone=form.cleaned_data.get("phone") or "",
                    role_code=role.code if role else "",
                    is_active=form.cleaned_data["is_active"],
                )

                user_obj.role = role
                user_obj.first_name = form.cleaned_data["first_name"]
                user_obj.last_name = form.cleaned_data["last_name"]
                user_obj.phone = form.cleaned_data.get("phone") or ""
                user_obj.email = form.cleaned_data["email"]
                user_obj.is_active = form.cleaned_data["is_active"]
                user_obj.updated_at = timezone.now()
                user_obj.save(
                    update_fields=[
                        "role",
                        "first_name",
                        "last_name",
                        "phone",
                        "email",
                        "is_active",
                        "updated_at",
                    ]
                )
                staff_link.role = _map_app_role_to_personnel_role(role)
                staff_link.est_actif = form.cleaned_data["is_active"]
                staff_link.date_fin = None if form.cleaned_data["is_active"] else timezone.now().date()
                staff_link.updated_at = timezone.now()
                staff_link.save(
                    update_fields=[
                        "role",
                        "est_actif",
                        "date_fin",
                        "updated_at",
                    ]
                )
                PersonnelEtablissementPermission.objects.update_or_create(
                    personnel_etablissement=staff_link,
                    defaults={
                        "can_manage_patients": permission_form.cleaned_data["can_manage_patients"],
                        "can_manage_appointments": permission_form.cleaned_data["can_manage_appointments"],
                        "can_declare_presences": permission_form.cleaned_data["can_declare_presences"],
                        "can_view_documents": permission_form.cleaned_data["can_view_documents"],
                        "created_at": getattr(existing_permission, "created_at", timezone.now()),
                        "updated_at": timezone.now(),
                    },
                )
        except SupabaseAdminError as exc:
            if exc.is_unexpected_failure:
                user_obj.role = role
                user_obj.first_name = form.cleaned_data["first_name"]
                user_obj.last_name = form.cleaned_data["last_name"]
                user_obj.phone = form.cleaned_data.get("phone") or ""
                user_obj.email = original_email
                user_obj.is_active = form.cleaned_data["is_active"]
                user_obj.updated_at = timezone.now()
                user_obj.save(
                    update_fields=[
                        "role",
                        "first_name",
                        "last_name",
                        "phone",
                        "is_active",
                        "updated_at",
                    ]
                )
                staff_link.role = _map_app_role_to_personnel_role(role)
                staff_link.est_actif = form.cleaned_data["is_active"]
                staff_link.date_fin = None if form.cleaned_data["is_active"] else timezone.now().date()
                staff_link.updated_at = timezone.now()
                staff_link.save(
                    update_fields=[
                        "role",
                        "est_actif",
                        "date_fin",
                        "updated_at",
                    ]
                )
                PersonnelEtablissementPermission.objects.update_or_create(
                    personnel_etablissement=staff_link,
                    defaults={
                        "can_manage_patients": permission_form.cleaned_data["can_manage_patients"],
                        "can_manage_appointments": permission_form.cleaned_data["can_manage_appointments"],
                        "can_declare_presences": permission_form.cleaned_data["can_declare_presences"],
                        "can_view_documents": permission_form.cleaned_data["can_view_documents"],
                        "created_at": getattr(existing_permission, "created_at", timezone.now()),
                        "updated_at": timezone.now(),
                    },
                )
                messages.warning(
                    request,
                    "Profil local mis a jour, mais Supabase Auth a refuse la mise a jour. L'email de connexion est reste inchange.",
                )
                return redirect("admin_etablissement_staff_detail", user_id=user_obj.id)
            form.add_error(None, str(exc))
        except Exception as exc:
            form.add_error(None, f"Unable to update user: {exc}")
        else:
            messages.success(request, "Membre du personnel mis a jour avec succes.")
            return redirect("admin_etablissement_staff_detail", user_id=user_obj.id)

    return render(
        request,
        "admin_etablissement/staff/edit.html",
        {
            "form": form,
            "page_mode": "edit",
            "page_title": "Edit Staff",
            "page_heading": f"Edit {user_obj.first_name or ''} {user_obj.last_name or ''}".strip() or "Edit Staff",
            "submit_label": "Save Changes",
            "user_obj": user_obj,
            "etablissement": etablissement,
            "staff_link": staff_link,
            "permission_form": permission_form,
        },
    )


@login_required
@role_required(["admin_etablissement"])
def admin_etablissement_staff_delete(request, user_id):
    current_user_id = request.session.get("user_id")
    etablissement = _get_managed_facility_for_admin(current_user_id)
    if not etablissement:
        messages.error(request, "Aucun etablissement n'est associe a cet administrateur.")
        return redirect("dashboard")

    staff_link = get_object_or_404(
        _get_staff_links_queryset(etablissement).filter(_admin_etablissement_staff_link_role_filter()),
        personnel_user_id=user_id,
    )
    user_obj = staff_link.personnel_user
    if request.method != "POST":
        return redirect("admin_etablissement_staff_detail", user_id=user_obj.id)

    service = SupabaseAdminService()
    try:
        delete_result = service.delete_auth_user(user_id=str(user_obj.id))
    except SupabaseAdminError as exc:
        messages.error(request, str(exc))
        return redirect("admin_etablissement_staff_detail", user_id=user_obj.id)

    AppUser.objects.filter(pk=user_obj.id).delete()

    if delete_result.get("soft_deleted"):
        messages.success(request, "Compte du personnel supprime de l'application avec suppression douce dans Auth.")
    else:
        messages.success(request, "Compte du personnel supprime avec succes.")
    return redirect("admin_etablissement_staff_list")


@login_required
@role_required(["super_admin"])
def super_admin_user_list(request):
    query = (request.GET.get("q") or "").strip()
    role_code = (request.GET.get("role") or "").strip()
    status = (request.GET.get("status") or "").strip()
    doctor_role_filter = (
        Q(role__code__iexact="medecin")
        | Q(role__code__iexact="doctor")
        | Q(role__nom__iexact="medecin")
        | Q(role__nom__iexact="doctor")
    )
    doctor_role_option_filter = (
        Q(code__iexact="medecin")
        | Q(code__iexact="doctor")
        | Q(nom__iexact="medecin")
        | Q(nom__iexact="doctor")
    )

    users = AppUser.objects.select_related("role").exclude(doctor_role_filter).order_by("-created_at")
    roles = Role.objects.exclude(doctor_role_option_filter).order_by("nom")

    if query:
        users = users.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )

    if role_code and role_code.lower() not in {"medecin", "doctor"}:
        users = users.filter(role__code=role_code)

    if status == "active":
        users = users.filter(is_active=True)
    elif status == "inactive":
        users = users.filter(is_active=False)

    return render(
        request,
        "super_admin/users/list.html",
        {
            "users": users,
            "roles": roles,
            "filters": {
                "q": query,
                "role": role_code,
                "status": status,
            },
            "users_count": users.count(),
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_user_detail(request, user_id):
    user_obj = get_object_or_404(AppUser.objects.select_related("role"), pk=user_id)
    return render(
        request,
        "super_admin/users/detail.html",
        {
            "user_obj": user_obj,
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_user_create(request):
    form = AppUserForm(request.POST or None, require_password=True)

    if request.method == "POST" and form.is_valid():
        service = SupabaseAdminService()
        role = form.cleaned_data["role"]
        password = form.cleaned_data["password"]

        try:
            with transaction.atomic():
                auth_user = service.create_auth_user(
                    email=form.cleaned_data["email"],
                    password=password,
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    phone=form.cleaned_data.get("phone") or "",
                    role_code=role.code if role else "",
                    require_password_change=True,
                )

                auth_user_id = auth_user["id"]
                existing_user = AppUser.objects.filter(pk=auth_user_id).first()
                if existing_user:
                    existing_user.role = role
                    existing_user.first_name = form.cleaned_data["first_name"]
                    existing_user.last_name = form.cleaned_data["last_name"]
                    existing_user.phone = form.cleaned_data.get("phone") or ""
                    existing_user.email = form.cleaned_data["email"]
                    existing_user.is_active = form.cleaned_data["is_active"]
                    existing_user.updated_at = timezone.now()
                    existing_user.save(
                        update_fields=[
                            "role",
                            "first_name",
                            "last_name",
                            "phone",
                            "email",
                            "is_active",
                            "updated_at",
                        ]
                    )
                else:
                    AppUser.objects.create(
                        id=auth_user_id,
                        role=role,
                        first_name=form.cleaned_data["first_name"],
                        last_name=form.cleaned_data["last_name"],
                        phone=form.cleaned_data.get("phone") or "",
                        email=form.cleaned_data["email"],
                        is_active=form.cleaned_data["is_active"],
                        created_at=timezone.now(),
                        updated_at=timezone.now(),
                    )
        except SupabaseAdminError as exc:
            form.add_error(None, str(exc))
        except Exception as exc:
            try:
                if "auth_user_id" in locals():
                    service.delete_auth_user(user_id=auth_user_id)
            except SupabaseAdminError:
                pass
            form.add_error(None, f"Unable to create user: {exc}")
        else:
            messages.success(request, "User created successfully.")
            return redirect("super_admin_user_list")

    return render(
        request,
        "super_admin/users/create.html",
        {
            "form": form,
            "page_mode": "create",
            "page_title": "Create User",
            "page_heading": "New Staff Profile",
            "submit_label": "Create Account",
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_user_edit(request, user_id):
    user_obj = get_object_or_404(AppUser.objects.select_related("role"), pk=user_id)
    form = AppUserForm(request.POST or None, instance=user_obj, require_password=False)

    if request.method == "POST" and form.is_valid():
        service = SupabaseAdminService()
        role = form.cleaned_data["role"]
        original_email = user_obj.email

        try:
            with transaction.atomic():
                service.update_auth_user(
                    user_id=str(user_obj.id),
                    email=form.cleaned_data["email"],
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    phone=form.cleaned_data.get("phone") or "",
                    role_code=role.code if role else "",
                    is_active=form.cleaned_data["is_active"],
                )

                user_obj.role = role
                user_obj.first_name = form.cleaned_data["first_name"]
                user_obj.last_name = form.cleaned_data["last_name"]
                user_obj.phone = form.cleaned_data.get("phone") or ""
                user_obj.email = form.cleaned_data["email"]
                user_obj.is_active = form.cleaned_data["is_active"]
                user_obj.updated_at = timezone.now()
                user_obj.save(
                    update_fields=[
                        "role",
                        "first_name",
                        "last_name",
                        "phone",
                        "email",
                        "is_active",
                        "updated_at",
                    ]
                )
        except SupabaseAdminError as exc:
            if exc.is_unexpected_failure:
                user_obj.role = role
                user_obj.first_name = form.cleaned_data["first_name"]
                user_obj.last_name = form.cleaned_data["last_name"]
                user_obj.phone = form.cleaned_data.get("phone") or ""
                user_obj.email = original_email
                user_obj.is_active = form.cleaned_data["is_active"]
                user_obj.updated_at = timezone.now()
                user_obj.save(
                    update_fields=[
                        "role",
                        "first_name",
                        "last_name",
                        "phone",
                        "is_active",
                        "updated_at",
                    ]
                )
                messages.warning(
                    request,
                    "Profil local mis a jour, mais Supabase Auth a refuse la mise a jour. L'email de connexion est reste inchange.",
                )
                return redirect("super_admin_user_detail", user_id=user_obj.id)
            form.add_error(None, str(exc))
        except Exception as exc:
            form.add_error(None, f"Unable to update user: {exc}")
        else:
            messages.success(request, "User updated successfully.")
            return redirect("super_admin_user_detail", user_id=user_obj.id)

    return render(
        request,
        "super_admin/users/edit.html",
        {
            "form": form,
            "page_mode": "edit",
            "page_title": "Edit User",
            "page_heading": f"Edit {user_obj.first_name or ''} {user_obj.last_name or ''}".strip() or "Edit User",
            "submit_label": "Save Changes",
            "user_obj": user_obj,
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_user_delete(request, user_id):
    user_obj = get_object_or_404(AppUser, pk=user_id)
    if request.method != "POST":
        return redirect("super_admin_user_detail", user_id=user_obj.id)

    service = SupabaseAdminService()
    try:
        delete_result = service.delete_auth_user(user_id=str(user_obj.id))
    except SupabaseAdminError as exc:
        messages.error(request, str(exc))
        return redirect("super_admin_user_detail", user_id=user_obj.id)

    AppUser.objects.filter(pk=user_obj.id).delete()

    if delete_result.get("soft_deleted"):
        messages.success(request, "User soft-deleted in auth and removed from the application.")
    else:
        messages.success(request, "User deleted successfully.")
    return redirect("super_admin_user_list")


@login_required
@role_required(["super_admin"])
def super_admin_user_reset_password(request, user_id):
    user_obj = get_object_or_404(AppUser.objects.select_related("role"), pk=user_id)
    form = UserPasswordResetForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        service = SupabaseAdminService()
        try:
            service.reset_auth_user_password(
                user_id=str(user_obj.id),
                password=form.cleaned_data["password"],
            )
        except SupabaseAdminError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Mot de passe temporaire defini avec succes.")
            return redirect("super_admin_user_detail", user_id=user_obj.id)

    return render(
        request,
        "super_admin/users/reset_password.html",
        {
            "form": form,
            "user_obj": user_obj,
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_facility_list(request):
    query = (request.GET.get("q") or "").strip()
    facility_type = (request.GET.get("type") or "").strip()
    status = (request.GET.get("status") or "").strip()

    facilities = Etablissement.objects.select_related("admin", "admin__role").order_by("-created_at")

    if query:
        facilities = facilities.filter(
            Q(nom__icontains=query)
            | Q(code__icontains=query)
            | Q(ville__icontains=query)
            | Q(email__icontains=query)
        )

    if facility_type:
        facilities = facilities.filter(type_etablissement=facility_type)

    if status == "active":
        facilities = facilities.filter(actif=True)
    elif status == "inactive":
        facilities = facilities.filter(actif=False)

    return render(
        request,
        "super_admin/facilities/list.html",
        {
            "facilities": facilities,
            "filters": {"q": query, "type": facility_type, "status": status},
            "facilities_count": facilities.count(),
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_facility_detail(request, facility_id):
    facility = get_object_or_404(Etablissement.objects.select_related("admin", "admin__role"), pk=facility_id)
    return render(request, "super_admin/facilities/detail.html", {"facility": facility})


@login_required
@role_required(["super_admin"])
def _legacy_super_admin_facility_create_unused(request):
    form = EtablissementForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        facility = form.save(commit=False)
        facility.created_at = timezone.now()
        facility.updated_at = timezone.now()
        facility.save()
        messages.success(request, "Etablissement créé avec succès.")
        return redirect("super_admin_facility_list")

    return render(
        request,
        "super_admin/facilities/create.html",
        {
            "form": form,
            "page_title": "Créer un établissement",
            "page_heading": "Nouvel établissement",
            "submit_label": "Créer l'établissement",
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_facility_create(request):
    form = EtablissementForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            facility = form.save(commit=False)
            facility.created_at = timezone.now()
            facility.updated_at = timezone.now()
            facility.save()

            messages.success(request, "Établissement créé avec succès.")
            return redirect("super_admin_facility_list")

        except IntegrityError as exc:
            form.add_error(None, f"Erreur d'intégrité : {exc}")

        except Exception as exc:
            form.add_error(None, f"Erreur lors de la création : {exc}")

    return render(
        request,
        "super_admin/facilities/create.html",
        {
            "form": form,
            "page_title": "Créer un établissement",
            "page_heading": "Nouvel établissement",
            "submit_label": "Créer l'établissement",
        },
    )

@login_required
@role_required(["super_admin"])
def super_admin_facility_edit(request, facility_id):
    facility = get_object_or_404(Etablissement.objects.select_related("admin", "admin__role"), pk=facility_id)
    form = EtablissementForm(request.POST or None, instance=facility)

    if request.method == "POST" and form.is_valid():
        try:
            facility = form.save(commit=False)
            facility.updated_at = timezone.now()
            facility.save()
            messages.success(request, "Etablissement mis a jour avec succes.")
            return redirect("super_admin_facility_detail", facility_id=facility.id)
        except IntegrityError as exc:
            form.add_error(None, f"Erreur d'integrite : {exc}")
        except Exception as exc:
            form.add_error(None, f"Erreur lors de la mise a jour : {exc}")

    return render(
        request,
        "super_admin/facilities/edit.html",
        {
            "form": form,
            "facility": facility,
            "page_title": "Modifier l'etablissement",
            "page_heading": f"Modifier {facility.nom}",
            "submit_label": "Enregistrer les modifications",
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_facility_delete(request, facility_id):
    facility = get_object_or_404(Etablissement, pk=facility_id)
    if request.method != "POST":
        return redirect("super_admin_facility_detail", facility_id=facility.id)

    facility.delete()
    messages.success(request, "Etablissement supprimé avec succès.")
    return redirect("super_admin_facility_list")


def _get_medecin_role():
    return (
        Role.objects.filter(
            Q(code__iexact="medecin")
            | Q(code__iexact="médecin")
            | Q(code__iexact="doctor")
            | Q(code__icontains="medec")
            | Q(code__icontains="doctor")
            | Q(nom__iexact="medecin")
            | Q(nom__iexact="médecin")
            | Q(nom__iexact="doctor")
            | Q(nom__icontains="medec")
            | Q(nom__icontains="doctor")
        )
        .order_by("nom")
        .first()
    )


@login_required
@role_required(["super_admin"])
def super_admin_doctor_list(request):
    query = (request.GET.get("q") or "").strip()
    specialite = (request.GET.get("specialite") or "").strip()
    status = (request.GET.get("status") or "").strip()

    doctors = Medecin.objects.select_related("user", "user__role").order_by("-user__created_at", "-id")

    if query:
        doctors = doctors.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__email__icontains=query)
            | Q(user__phone__icontains=query)
            | Q(specialite__icontains=query)
        )

    if specialite:
        doctors = doctors.filter(specialite__iexact=specialite)

    if status == "active":
        doctors = doctors.filter(user__is_active=True)
    elif status == "inactive":
        doctors = doctors.filter(user__is_active=False)

    specialites = (
        Medecin.objects.order_by("specialite")
        .values_list("specialite", flat=True)
        .distinct()
    )

    return render(
        request,
        "super_admin/doctors/list.html",
        {
            "doctors": doctors,
            "specialites": [item for item in specialites if item],
            "filters": {"q": query, "specialite": specialite, "status": status},
            "doctors_count": doctors.count(),
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_doctor_detail(request, doctor_id):
    doctor = get_object_or_404(Medecin.objects.select_related("user__role"), pk=doctor_id)
    return render(request, "super_admin/doctors/detail.html", {"doctor": doctor})


@login_required
@role_required(["super_admin"])
def super_admin_doctor_create(request):
    form = MedecinForm(request.POST or None, require_password=True)

    if request.method == "POST" and form.is_valid():
        service = SupabaseAdminService()
        doctor_role = _get_medecin_role()
        if not doctor_role:
            form.add_error(None, "Le role medecin est introuvable.")
        else:
            try:
                with transaction.atomic():
                    auth_user = service.create_auth_user(
                        email=form.cleaned_data["email"],
                        password=form.cleaned_data["password"],
                        first_name=form.cleaned_data["first_name"],
                        last_name=form.cleaned_data["last_name"],
                        phone=form.cleaned_data["telephone"],
                        role_code=doctor_role.code,
                        require_password_change=True,
                    )

                    auth_user_id = auth_user["id"]
                    user_obj = AppUser.objects.filter(pk=auth_user_id).first()
                    if user_obj:
                        user_obj.role = doctor_role
                        user_obj.first_name = form.cleaned_data["first_name"]
                        user_obj.last_name = form.cleaned_data["last_name"]
                        user_obj.phone = form.cleaned_data["telephone"]
                        user_obj.email = form.cleaned_data["email"]
                        user_obj.is_active = form.cleaned_data["is_active"]
                        user_obj.updated_at = timezone.now()
                        user_obj.save(
                            update_fields=[
                                "role",
                                "first_name",
                                "last_name",
                                "phone",
                                "email",
                                "is_active",
                                "updated_at",
                            ]
                        )
                    else:
                        user_obj = AppUser.objects.create(
                            id=auth_user_id,
                            role=doctor_role,
                            first_name=form.cleaned_data["first_name"],
                            last_name=form.cleaned_data["last_name"],
                            phone=form.cleaned_data["telephone"],
                            email=form.cleaned_data["email"],
                            is_active=form.cleaned_data["is_active"],
                            created_at=timezone.now(),
                            updated_at=timezone.now(),
                        )

                    Medecin.objects.create(
                        specialite=form.cleaned_data["specialite"],
                        photo_url=form.cleaned_data.get("photo_url") or None,
                        bio=form.cleaned_data.get("bio") or None,
                        langues=form.cleaned_data.get("langues_input") or [],
                        note=form.cleaned_data.get("note"),
                        user=user_obj,
                        numero_ordre=form.cleaned_data.get("numero_ordre") or None,
                        signature_name=form.cleaned_data.get("signature_name") or None,
                    )
            except SupabaseAdminError as exc:
                form.add_error(None, str(exc))
            except Exception as exc:
                try:
                    if "auth_user_id" in locals():
                        service.delete_auth_user(user_id=auth_user_id)
                except SupabaseAdminError:
                    pass
                form.add_error(None, f"Unable to create doctor: {exc}")
            else:
                messages.success(request, "Medecin cree avec succes.")
                return redirect("super_admin_doctor_list")

    return render(
        request,
        "super_admin/doctors/create.html",
        {
            "form": form,
            "page_mode": "create",
            "page_title": "Ajouter un medecin",
            "page_heading": "Nouveau profil medecin",
            "submit_label": "Creer le compte medecin",
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_doctor_edit(request, doctor_id):
    doctor = get_object_or_404(Medecin.objects.select_related("user__role"), pk=doctor_id)
    user_obj = doctor.user
    form = MedecinForm(
        request.POST or None,
        instance=doctor,
        require_password=False,
        linked_user=user_obj,
    )

    if request.method == "POST" and form.is_valid():
        service = SupabaseAdminService()
        doctor_role = _get_medecin_role()
        original_email = user_obj.email if user_obj else None
        if not doctor_role:
            form.add_error(None, "Le role medecin est introuvable.")
        elif not user_obj:
            form.add_error(None, "Ce medecin n'est relie a aucun utilisateur.")
        else:
            try:
                with transaction.atomic():
                    service.update_auth_user(
                        user_id=str(user_obj.id),
                        email=form.cleaned_data["email"],
                        first_name=form.cleaned_data["first_name"],
                        last_name=form.cleaned_data["last_name"],
                        phone=form.cleaned_data["telephone"],
                        role_code=doctor_role.code,
                        is_active=form.cleaned_data["is_active"],
                    )

                    user_obj.role = doctor_role
                    user_obj.first_name = form.cleaned_data["first_name"]
                    user_obj.last_name = form.cleaned_data["last_name"]
                    user_obj.phone = form.cleaned_data["telephone"]
                    user_obj.email = form.cleaned_data["email"]
                    user_obj.is_active = form.cleaned_data["is_active"]
                    user_obj.updated_at = timezone.now()
                    user_obj.save(
                        update_fields=[
                            "role",
                            "first_name",
                            "last_name",
                            "phone",
                            "email",
                            "is_active",
                            "updated_at",
                        ]
                    )

                    doctor.specialite = form.cleaned_data["specialite"]
                    doctor.photo_url = form.cleaned_data.get("photo_url") or None
                    doctor.bio = form.cleaned_data.get("bio") or None
                    doctor.langues = form.cleaned_data.get("langues_input") or []
                    doctor.note = form.cleaned_data.get("note")
                    doctor.numero_ordre = form.cleaned_data.get("numero_ordre") or None
                    doctor.signature_name = form.cleaned_data.get("signature_name") or None
                    doctor.save(
                        update_fields=[
                            "specialite",
                            "photo_url",
                            "bio",
                            "langues",
                            "note",
                            "numero_ordre",
                            "signature_name",
                        ]
                    )
            except SupabaseAdminError as exc:
                if exc.is_unexpected_failure:
                    user_obj.role = doctor_role
                    user_obj.first_name = form.cleaned_data["first_name"]
                    user_obj.last_name = form.cleaned_data["last_name"]
                    user_obj.phone = form.cleaned_data["telephone"]
                    user_obj.email = original_email
                    user_obj.is_active = form.cleaned_data["is_active"]
                    user_obj.updated_at = timezone.now()
                    user_obj.save(
                        update_fields=[
                            "role",
                            "first_name",
                            "last_name",
                            "phone",
                            "is_active",
                            "updated_at",
                        ]
                    )

                    doctor.specialite = form.cleaned_data["specialite"]
                    doctor.photo_url = form.cleaned_data.get("photo_url") or None
                    doctor.bio = form.cleaned_data.get("bio") or None
                    doctor.langues = form.cleaned_data.get("langues_input") or []
                    doctor.note = form.cleaned_data.get("note")
                    doctor.numero_ordre = form.cleaned_data.get("numero_ordre") or None
                    doctor.signature_name = form.cleaned_data.get("signature_name") or None
                    doctor.save(
                        update_fields=[
                            "specialite",
                            "photo_url",
                            "bio",
                            "langues",
                            "note",
                            "numero_ordre",
                            "signature_name",
                        ]
                    )
                    doctor.updated_at = timezone.now()

                    messages.warning(
                        request,
                        "Profil local du medecin mis a jour, mais Supabase Auth a refuse la mise a jour. L'email de connexion est reste inchange.",
                    )
                    return redirect("super_admin_doctor_detail", doctor_id=doctor.id)
                form.add_error(None, str(exc))
            except Exception as exc:
                form.add_error(None, f"Unable to update doctor: {exc}")
            else:
                messages.success(request, "Medecin mis a jour avec succes.")
                return redirect("super_admin_doctor_detail", doctor_id=doctor.id)

    return render(
        request,
        "super_admin/doctors/edit.html",
        {
            "form": form,
            "doctor": doctor,
            "page_mode": "edit",
            "page_title": "Modifier le medecin",
            "page_heading": f"Modifier {doctor.full_name}",
            "submit_label": "Enregistrer les modifications",
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_doctor_delete(request, doctor_id):
    doctor = get_object_or_404(Medecin.objects.select_related("user"), pk=doctor_id)
    if request.method != "POST":
        return redirect("super_admin_doctor_detail", doctor_id=doctor.id)

    service = SupabaseAdminService()
    user_id = str(doctor.user_id) if doctor.user_id else None
    doctor.delete()

    if user_id:
        try:
            service.delete_auth_user(user_id=user_id)
        except SupabaseAdminError as exc:
            messages.warning(
                request,
                f"Profil medecin supprime, mais le compte auth n'a pas pu etre supprime: {exc}",
            )
            return redirect("super_admin_doctor_list")

    messages.success(request, "Medecin supprime avec succes.")
    return redirect("super_admin_doctor_list")


@login_required
@role_required(["super_admin"])
def super_admin_doctor_link_account(request, doctor_id):
    doctor = get_object_or_404(Medecin.objects.select_related("user", "user__role"), pk=doctor_id)
    form = DoctorAccountLinkForm(request.POST or None, doctor=doctor)

    if request.method == "POST" and form.is_valid():
        selected_user = form.cleaned_data["user"]
        doctor_role = _get_medecin_role()
        if not doctor_role:
            form.add_error(None, "Le role medecin est introuvable.")
        else:
            selected_user.role = doctor_role
            selected_user.updated_at = timezone.now()
            selected_user.save(update_fields=["role", "updated_at"])

            doctor.user = selected_user
            doctor.updated_at = timezone.now()
            doctor.save(update_fields=["user", "updated_at"])

            messages.success(request, "Compte utilisateur lie au medecin avec succes.")
            return redirect("super_admin_doctor_detail", doctor_id=doctor.id)

    return render(
        request,
        "super_admin/doctors/link_account.html",
        {
            "form": form,
            "doctor": doctor,
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_doctor_reset_password(request, doctor_id):
    doctor = get_object_or_404(Medecin.objects.select_related("user", "user__role"), pk=doctor_id)
    if not doctor.user:
        messages.error(request, "Ce medecin n'est relie a aucun compte utilisateur.")
        return redirect("super_admin_doctor_detail", doctor_id=doctor.id)

    form = UserPasswordResetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        service = SupabaseAdminService()
        try:
            service.reset_auth_user_password(
                user_id=str(doctor.user.id),
                password=form.cleaned_data["password"],
            )
        except SupabaseAdminError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Mot de passe temporaire du medecin defini avec succes.")
            return redirect("super_admin_doctor_detail", doctor_id=doctor.id)

    return render(
        request,
        "super_admin/doctors/reset_password.html",
        {
            "form": form,
            "doctor": doctor,
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_role_list(request):
    query = (request.GET.get("q") or "").strip()
    roles = Role.objects.order_by("nom", "code")
    if query:
        roles = roles.filter(
            Q(code__icontains=query)
            | Q(nom__icontains=query)
            | Q(description__icontains=query)
        )

    return render(
        request,
        "super_admin/roles/list.html",
        {
            "roles": roles,
            "filters": {"q": query},
            "roles_count": roles.count(),
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_role_create(request):
    form = RoleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        role_obj = form.save(commit=False)
        role_obj.id = uuid.uuid4()
        role_obj.created_at = timezone.now()
        role_obj.save()
        messages.success(request, "Role cree avec succes.")
        return redirect("super_admin_role_list")

    return render(
        request,
        "super_admin/roles/form.html",
        {
            "form": form,
            "page_title": "Creer un role",
            "page_heading": "Nouveau role",
            "submit_label": "Creer le role",
            "page_mode": "create",
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_role_edit(request, role_id):
    role_obj = get_object_or_404(Role, pk=role_id)
    form = RoleForm(request.POST or None, instance=role_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Role mis a jour avec succes.")
        return redirect("super_admin_role_list")

    return render(
        request,
        "super_admin/roles/form.html",
        {
            "form": form,
            "role_obj": role_obj,
            "page_title": "Modifier le role",
            "page_heading": f"Modifier {role_obj.nom or role_obj.code}",
            "submit_label": "Enregistrer",
            "page_mode": "edit",
        },
    )


@login_required
@role_required(["super_admin"])
def super_admin_role_delete(request, role_id):
    role_obj = get_object_or_404(Role, pk=role_id)
    if request.method != "POST":
        return redirect("super_admin_role_list")

    if AppUser.objects.filter(role=role_obj).exists():
        messages.error(request, "Impossible de supprimer un role deja assigne a des utilisateurs.")
        return redirect("super_admin_role_list")

    role_obj.delete()
    messages.success(request, "Role supprime avec succes.")
    return redirect("super_admin_role_list")


def forbidden_view(request):
    return render(request, "errors/403.html")


def not_found_view(request):
    return render(request, "errors/404.html")


def server_error_view(request):
    return render(request, "errors/500.html")
