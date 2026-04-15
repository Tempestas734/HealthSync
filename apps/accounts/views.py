import requests

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import login_required
from .decorators import role_required
from .forms import AppUserForm, EtablissementForm, MedecinForm
from .models import AppUser
from .models import ETABLISSEMENT_TYPE_LABELS
from .models import Etablissement, Medecin, Role
from .services import SupabaseAdminError, SupabaseAdminService


def home_view(request):
    return render(request, "home/index.html")


def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

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
            messages.error(request, "Invalid credentials")
            return render(request, "auth/login.html")

        access_token = data["access_token"]
        user_id = data["user"]["id"]

        try:
            user = AppUser.objects.select_related("role").get(id=user_id)
        except AppUser.DoesNotExist:
            messages.error(request, "User not registered")
            return render(request, "auth/login.html")

        request.session["access_token"] = access_token
        request.session["user_id"] = str(user.id)
        request.session["role"] = user.role.code if user.role else None

        return redirect("dashboard")

    return render(request, "auth/login.html")


def logout_view(request):
    request.session.flush()
    return redirect("login")


@login_required
def dashboard(request):
    role = request.session.get("role")

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

    if role in ["medecin", "doctor"]:
        return render(request, "dashboard/doctor.html")

    if role in ["secretaire", "secretary"]:
        return render(request, "dashboard/secretary.html")

    if role == "patient":
        return render(request, "dashboard/patient.html")

    return render(request, "dashboard/default.html")


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
        service.delete_auth_user(user_id=str(user_obj.id))
    except SupabaseAdminError as exc:
        messages.error(request, str(exc))
        return redirect("super_admin_user_detail", user_id=user_obj.id)

    messages.success(request, "User deleted successfully.")
    return redirect("super_admin_user_list")


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
def super_admin_facility_create(request):
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
def super_admin_facility_edit(request, facility_id):
    facility = get_object_or_404(Etablissement.objects.select_related("admin", "admin__role"), pk=facility_id)
    form = EtablissementForm(request.POST or None, instance=facility)

    if request.method == "POST" and form.is_valid():
        facility = form.save(commit=False)
        facility.updated_at = timezone.now()
        facility.save()
        messages.success(request, "Etablissement mis à jour avec succès.")
        return redirect("super_admin_facility_detail", facility_id=facility.id)

    return render(
        request,
        "super_admin/facilities/edit.html",
        {
            "form": form,
            "facility": facility,
            "page_title": "Modifier l'établissement",
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


def forbidden_view(request):
    return render(request, "errors/403.html")


def not_found_view(request):
    return render(request, "errors/404.html")


def server_error_view(request):
    return render(request, "errors/500.html")
