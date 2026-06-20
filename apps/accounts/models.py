import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models


ETABLISSEMENT_TYPE_LABELS = {
    "cabinet": "Cabinet",
    "hopital": "Hopital",
    "clinique": "Clinique",
    "laboratoire": "Laboratoire",
    "centre_radiologie": "Centre de radiologie",
    "pharmacie_partenaire": "Pharmacie partenaire",
}


class Role(models.Model):
    id = models.UUIDField(primary_key=True)
    code = models.TextField(unique=True)
    nom = models.TextField()
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "roles"

    @property
    def display_name(self):
        return self.nom or self.code

    def __str__(self):
        return self.display_name


class AppUser(models.Model):
    id = models.UUIDField(primary_key=True)
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="role_id",
        related_name="users",
    )
    first_name = models.TextField(null=True, blank=True)
    last_name = models.TextField(null=True, blank=True)
    phone = models.TextField(null=True, blank=True)
    email = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "users"

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def role_display_name(self):
        if not self.role:
            return None
        return self.role.display_name

    def __str__(self):
        return self.email or str(self.id)


class Etablissement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    nom = models.TextField()
    type_etablissement = models.TextField()
    admin = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="admin_id",
        related_name="managed_facilities",
    )
    pays = models.TextField(null=True, blank=True)
    ville = models.TextField(null=True, blank=True)
    adresse = models.TextField(null=True, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    telephone = models.TextField(null=True, blank=True)
    email = models.TextField(null=True, blank=True)
    site_web = models.TextField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    code = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "etablissements"

    @property
    def type_display_name(self):
        return ETABLISSEMENT_TYPE_LABELS.get(self.type_etablissement, self.type_etablissement)

    @property
    def admin_display_name(self):
        if not self.admin:
            return None
        full_name = f"{self.admin.first_name or ''} {self.admin.last_name or ''}".strip()
        return full_name or self.admin.email or str(self.admin.id)

    def __str__(self):
        return self.nom


class Medecin(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    specialite = models.TextField()
    photo_url = models.TextField(null=True, blank=True)
    bio = models.TextField(null=True, blank=True)
    langues = ArrayField(models.TextField(), null=True, blank=True)
    note = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    user = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="user_id",
        related_name="doctor_profile",
    )
    numero_ordre = models.TextField(null=True, blank=True)
    signature_name = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "medecins"

    @property
    def full_name(self):
        if self.user:
            return f"{self.user.first_name or ''} {self.user.last_name or ''}".strip()
        return ""

    @property
    def first_name(self):
        return self.user.first_name if self.user else None

    @property
    def last_name(self):
        return self.user.last_name if self.user else None

    @property
    def email(self):
        return self.user.email if self.user else None

    @property
    def telephone(self):
        return self.user.phone if self.user else None

    @property
    def is_active(self):
        if not self.user:
            return False
        return self.user.is_active

    @property
    def created_at(self):
        return self.user.created_at if self.user else None

    @property
    def languages_display(self):
        return ", ".join(self.langues or [])

    def __str__(self):
        return self.full_name or (self.email or str(self.id))


class MedecinEtablissementInvitation(models.Model):
    ROLE_CHOICES = (
        ("medecin", "Medecin"),
        ("chef_service", "Chef de service"),
        ("consultant", "Consultant"),
    )

    STATUS_CHOICES = (
        ("pending", "En attente"),
        ("accepted", "Acceptee"),
        ("rejected", "Refusee"),
        ("expired", "Expiree"),
        ("cancelled", "Annulee"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    medecin = models.ForeignKey(
        Medecin,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column="medecin_id",
        related_name="facility_invitations",
    )
    medecin_email = models.TextField()
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        db_column="etablissement_id",
        related_name="doctor_invitations",
    )
    invited_by_user = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="invited_by_user_id",
        related_name="sent_doctor_invitations",
    )
    role = models.TextField(default="medecin")
    invitation_token = models.TextField(unique=True)
    pin_hash = models.TextField()
    pin_expires_at = models.DateTimeField(null=True, blank=True)
    status = models.TextField(default="pending")
    can_issue_prescriptions = models.BooleanField(default=True)
    can_sign_documents = models.BooleanField(default=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "medecin_etablissement_invitations"

    @property
    def doctor_display_name(self):
        if self.medecin and self.medecin.full_name:
            return self.medecin.full_name
        return self.medecin_email

    @property
    def status_display_name(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    @property
    def role_display_name(self):
        return dict(self.ROLE_CHOICES).get(self.role, self.role)


class MedecinEtablissement(models.Model):
    ROLE_CHOICES = (
        ("medecin", "Medecin"),
        ("chef_service", "Chef de service"),
        ("consultant", "Consultant"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    medecin = models.ForeignKey(
        Medecin,
        on_delete=models.CASCADE,
        db_column="medecin_id",
        related_name="facility_links",
    )
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        db_column="etablissement_id",
        related_name="doctor_links",
    )
    role = models.TextField(default="medecin")
    est_principal = models.BooleanField(default=False)
    created_at = models.DateTimeField()
    pin_hash = models.TextField(null=True, blank=True)
    pin_updated_at = models.DateTimeField(null=True, blank=True)
    actif = models.BooleanField(default=True)
    can_issue_prescriptions = models.BooleanField(default=True)
    can_sign_documents = models.BooleanField(default=True)
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "medecin_etablissements"

    @property
    def role_display_name(self):
        return dict(self.ROLE_CHOICES).get(self.role, self.role)


class PersonnelEtablissement(models.Model):
    ROLE_CHOICES = (
        ("admin", "Admin"),
        ("medecin", "Medecin"),
        ("infirmier", "Infirmier"),
        ("secretaire", "Secretaire"),
        ("assistant", "Assistant"),
        ("receptionniste", "Receptionniste"),
        ("technicien", "Technicien"),
        ("staff_frontdesk", "Staff Frontdesk"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        db_column="etablissement_id",
        related_name="personnel_links",
    )
    personnel_user = models.ForeignKey(
        AppUser,
        on_delete=models.CASCADE,
        db_column="personnel_user_id",
        related_name="facility_personnel_links",
    )
    role = models.TextField(default="assistant")
    service = models.TextField(null=True, blank=True)
    matricule = models.TextField(null=True, blank=True)
    est_actif = models.BooleanField(default=True)
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField()
    pin_hash = models.TextField(null=True, blank=True)
    pin_updated_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "personnel_etablissements"

    @property
    def role_display_name(self):
        return dict(self.ROLE_CHOICES).get(self.role, self.role)


class PersonnelEtablissementPermission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    personnel_etablissement = models.OneToOneField(
        PersonnelEtablissement,
        on_delete=models.CASCADE,
        db_column="personnel_etablissement_id",
        related_name="permissions",
    )
    can_manage_patients = models.BooleanField(default=False)
    can_manage_appointments = models.BooleanField(default=False)
    can_declare_presences = models.BooleanField(default=False)
    can_view_documents = models.BooleanField(default=False)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "personnel_etablissement_permissions"


class MedecinPresence(models.Model):
    STATUS_CHOICES = (
        ("present", "Present"),
        ("absent", "Absent"),
        ("delayed", "Delayed"),
        ("replaced", "Replaced"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    medecin = models.ForeignKey(
        Medecin,
        on_delete=models.CASCADE,
        db_column="medecin_id",
        related_name="presence_logs",
    )
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        db_column="etablissement_id",
        related_name="doctor_presence_logs",
    )
    declared_by_user = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="declared_by_user_id",
        related_name="declared_doctor_presences",
    )
    presence_date = models.DateField()
    check_in_time = models.DateTimeField(null=True, blank=True)
    check_out_time = models.DateTimeField(null=True, blank=True)
    status = models.TextField(default="present")
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "medecin_presences"

    @property
    def status_display_name(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)


class MedecinIndisponibilite(models.Model):
    TYPE_CHOICES = (
        ("absence", "Absence"),
        ("conge", "Conge"),
        ("formation", "Formation"),
        ("indisponible", "Indisponible"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medecin = models.ForeignKey(
        Medecin,
        on_delete=models.CASCADE,
        db_column="medecin_id",
        related_name="indisponibilites",
    )
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        db_column="etablissement_id",
        related_name="doctor_unavailability_entries",
    )
    declared_by_user = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="declared_by_user_id",
        related_name="declared_doctor_unavailability_entries",
    )
    type_indisponibilite = models.TextField(default="indisponible")
    motif = models.TextField()
    date_debut = models.DateField()
    date_fin = models.DateField()
    heure_debut = models.TimeField(null=True, blank=True)
    heure_fin = models.TimeField(null=True, blank=True)
    toute_la_journee = models.BooleanField(default=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "medecin_indisponibilites"
        ordering = ("date_debut", "heure_debut", "created_at")

    @property
    def type_display_name(self):
        return dict(self.TYPE_CHOICES).get(self.type_indisponibilite, self.type_indisponibilite)

    @property
    def full_day_label(self):
        return "Toute la journee" if self.toute_la_journee else "Horaire specifique"


class MedecinHoraireSemaine(models.Model):
    WEEKDAY_CHOICES = (
        (0, "Lundi"),
        (1, "Mardi"),
        (2, "Mercredi"),
        (3, "Jeudi"),
        (4, "Vendredi"),
        (5, "Samedi"),
        (6, "Dimanche"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medecin = models.ForeignKey(
        Medecin,
        on_delete=models.CASCADE,
        db_column="medecin_id",
        related_name="weekly_schedules",
    )
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        db_column="etablissement_id",
        related_name="doctor_weekly_schedules",
    )
    weekday = models.IntegerField()
    is_active = models.BooleanField(default=False)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "medecin_horaires_semaine"
        ordering = ("weekday", "created_at")

    @property
    def weekday_display_name(self):
        return dict(self.WEEKDAY_CHOICES).get(self.weekday, str(self.weekday))


class MedecinHoraireIntervalle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    horaire = models.ForeignKey(
        MedecinHoraireSemaine,
        on_delete=models.CASCADE,
        db_column="horaire_id",
        related_name="intervals",
    )
    ordre = models.IntegerField(default=1)
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "medecin_horaire_intervalles"
        ordering = ("ordre", "heure_debut", "created_at")


class Patient(models.Model):
    GENDER_CHOICES = (
        ("male", "Homme"),
        ("female", "Femme"),
        ("other", "Autre"),
    )

    BLOOD_GROUP_CHOICES = (
        ("A+", "A+"),
        ("A-", "A-"),
        ("B+", "B+"),
        ("B-", "B-"),
        ("AB+", "AB+"),
        ("AB-", "AB-"),
        ("O+", "O+"),
        ("O-", "O-"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="user_id",
        related_name="patient_profiles",
    )
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="etablissement_id",
        related_name="patients",
    )
    patient_code = models.TextField(null=True, blank=True)
    barcode_value = models.TextField(unique=True)
    first_name = models.TextField()
    last_name = models.TextField()
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.TextField(null=True, blank=True)
    phone = models.TextField(null=True, blank=True)
    email = models.TextField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    blood_group = models.TextField(null=True, blank=True)
    emergency_contact_name = models.TextField(null=True, blank=True)
    emergency_contact_phone = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "patients"

    @property
    def full_name(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip()


class PatientVitalSign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        db_column="patient_id",
        related_name="vital_signs",
    )
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="etablissement_id",
        related_name="patient_vital_signs",
    )
    exam_session_id = models.UUIDField(null=True, blank=True)
    measured_by_user = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="measured_by_user_id",
        related_name="measured_patient_vital_signs",
    )
    temperature_c = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    heart_rate_bpm = models.IntegerField(null=True, blank=True)
    spo2_percent = models.IntegerField(null=True, blank=True)
    systolic_bp = models.IntegerField(null=True, blank=True)
    diastolic_bp = models.IntegerField(null=True, blank=True)
    respiratory_rate_bpm = models.IntegerField(null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    blood_glucose_mg_dl = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    measurement_source = models.TextField(default="kiosk")
    notes = models.TextField(null=True, blank=True)
    measured_at = models.DateTimeField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "patient_vital_signs"
        ordering = ("-measured_at", "-created_at")

    @property
    def blood_pressure_display(self):
        if self.systolic_bp is None and self.diastolic_bp is None:
            return None
        return f"{self.systolic_bp or '-'} / {self.diastolic_bp or '-'} mmHg"


class Measurement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    session_id = models.UUIDField()
    type = models.TextField()
    value = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.TextField()
    measured_at = models.DateTimeField()
    source = models.TextField(default="sensor")

    class Meta:
        managed = False
        db_table = "measurements"
        ordering = ("-measured_at", "-id")


class ExamSession(models.Model):
    STATUS_CHOICES = (
        ("pending", "En attente"),
        ("active", "Active"),
        ("completed", "Terminee"),
        ("cancelled", "Annulee"),
        ("expired", "Expiree"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_at = models.DateTimeField()
    device_id = models.TextField(null=True, blank=True)
    consent_id = models.UUIDField(null=True, blank=True)
    user = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="user_id",
        related_name="exam_sessions",
    )
    rfid_tag_uid = models.TextField(null=True, blank=True)
    status = models.TextField(default="pending")
    patient = models.ForeignKey(
        Patient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="patient_id",
        related_name="exam_sessions",
    )
    session_pin = models.TextField(null=True, blank=True)
    mode = models.TextField(default="guest")

    class Meta:
        managed = False
        db_table = "exam_sessions"
        ordering = ("-created_at",)

    @property
    def status_display_name(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    @property
    def is_completed(self):
        return self.status == "completed"

    @property
    def is_active(self):
        return self.status == "active"

    @property
    def is_pending(self):
        return self.status == "pending"


class Appointment(models.Model):
    STATUS_CHOICES = (
        ("pending", "En attente"),
        ("confirmed", "Confirme"),
        ("cancelled", "Annule"),
        ("completed", "Termine"),
        ("no_show", "Absent"),
        ("follow_up_planned", "Suivi planifie"),
    )

    SOURCE_CHOICES = (
        ("mobile_app", "Application mobile"),
        ("web_portal", "Portail web"),
        ("hospital_desk", "Accueil etablissement"),
    )

    REQUESTED_BY_TYPE_CHOICES = (
        ("family", "Famille"),
        ("patient", "Patient"),
        ("doctor", "Medecin"),
        ("secretary", "Secretaire"),
        ("nurse", "Infirmier"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        db_column="patient_id",
        related_name="appointments",
    )
    medecin = models.ForeignKey(
        Medecin,
        on_delete=models.CASCADE,
        db_column="medecin_id",
        related_name="appointments",
    )
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        db_column="etablissement_id",
        related_name="appointments",
    )
    scheduled_at = models.DateTimeField()
    status = models.TextField(default="pending")
    reason = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_by_user = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="created_by_user_id",
        related_name="created_appointments",
    )
    requested_by_type = models.TextField(null=True, blank=True)
    requested_by_id = models.UUIDField(null=True, blank=True)
    source = models.TextField(default="web_portal")
    follow_up_of_appointment = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="follow_up_of_appointment_id",
        related_name="follow_up_appointments",
    )
    cancelled_by_user = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="cancelled_by_user_id",
        related_name="cancelled_appointments",
    )
    cancel_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    duration_minutes = models.IntegerField(default=15)
    scheduled_end_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "appointments"
        ordering = ("scheduled_at", "created_at")

    @property
    def status_display_name(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)
