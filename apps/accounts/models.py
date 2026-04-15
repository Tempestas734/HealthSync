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
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
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
