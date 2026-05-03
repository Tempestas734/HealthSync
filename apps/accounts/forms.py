import re
import unicodedata
from datetime import datetime

from django import forms
from django.db.models import Q
from django.utils import timezone

from .models import (
    AppUser,
    ETABLISSEMENT_TYPE_LABELS,
    Etablissement,
    Medecin,
    MedecinEtablissementInvitation,
    MedecinIndisponibilite,
    MedecinPresence,
    Patient,
    Role,
)

COUNTRY_CITY_CHOICES = {
    "Maroc": [
        "Casablanca",
        "Rabat",
        "Marrakech",
        "Fes",
        "Tanger",
        "Agadir",
        "Meknes",
        "Oujda",
        "Kenitra",
        "Tetouan",
        "Safi",
        "El Jadida",
        "Beni Mellal",
        "Nador",
        "Taza",
        "Laayoune",
        "Dakhla",
    ],
    "France": [
        "Paris",
        "Marseille",
        "Lyon",
        "Toulouse",
        "Nice",
        "Nantes",
        "Montpellier",
        "Strasbourg",
        "Bordeaux",
        "Lille",
    ],
    "Espagne": [
        "Madrid",
        "Barcelone",
        "Valence",
        "Seville",
        "Malaga",
        "Bilbao",
    ],
    "Algerie": [
        "Alger",
        "Oran",
        "Constantine",
        "Annaba",
        "Blida",
    ],
    "Tunisie": [
        "Tunis",
        "Sfax",
        "Sousse",
        "Kairouan",
        "Bizerte",
    ],
}

SPECIALITE_CHOICES = [
    ("", "Choisir une specialite"),
    ("Cardiologie", "Cardiologie"),
    ("Dermatologie", "Dermatologie"),
    ("Endocrinologie", "Endocrinologie"),
    ("Gastro-enterologie", "Gastro-enterologie"),
    ("Gynecologie", "Gynecologie"),
    ("Medecine generale", "Medecine generale"),
    ("Neurologie", "Neurologie"),
    ("Ophtalmologie", "Ophtalmologie"),
    ("ORL", "ORL"),
    ("Pediatrie", "Pediatrie"),
    ("Pneumologie", "Pneumologie"),
    ("Psychiatrie", "Psychiatrie"),
    ("Radiologie", "Radiologie"),
    ("Rhumatologie", "Rhumatologie"),
    ("Traumatologie", "Traumatologie"),
    ("Urologie", "Urologie"),
]

COMMON_LANGUAGE_CHOICES = [
    ("Arabe", "Arabe"),
    ("Francais", "Francais"),
    ("Anglais", "Anglais"),
]


def _slug_code_part(value, fallback):
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    letters_only = "".join(char for char in ascii_value.upper() if char.isalpha())
    if not letters_only:
        letters_only = fallback
    return letters_only[:3].ljust(3, "X")


class AppUserForm(forms.ModelForm):
    password = forms.CharField(
        required=False,
        min_length=8,
        widget=forms.PasswordInput(
            attrs={
                "class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                "placeholder": "Temporary password",
            }
        ),
        help_text="Required only when creating a new account.",
    )

    class Meta:
        model = AppUser
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "role",
            "is_active",
        ]
        widgets = {
            "first_name": forms.TextInput(
                attrs={
                    "class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                    "placeholder": "First name",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                    "placeholder": "Last name",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                    "placeholder": "user@example.com",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                    "placeholder": "+212 ...",
                }
            ),
            "role": forms.Select(
                attrs={
                    "class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={
                    "class": "h-4 w-4 rounded border-outline-variant text-primary focus:ring-primary/20",
                }
            ),
        }

    def __init__(self, *args, require_password=False, allowed_role_codes=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_password = require_password
        self.allowed_role_codes = {code.lower() for code in (allowed_role_codes or [])}
        doctor_role_filter = (
            Q(code__iexact="medecin")
            | Q(code__iexact="doctor")
            | Q(nom__iexact="medecin")
            | Q(nom__iexact="doctor")
        )
        role_queryset = Role.objects.exclude(doctor_role_filter)
        if self.allowed_role_codes:
            allowed_filter = Q()
            for role_code in self.allowed_role_codes:
                allowed_filter |= Q(code__iexact=role_code) | Q(nom__iexact=role_code)
            role_queryset = Role.objects.filter(allowed_filter)
        current_role = getattr(self.instance, "role", None)
        current_role_code = getattr(current_role, "code", None)
        current_role_name = getattr(current_role, "nom", None)
        if (
            self.instance.pk
            and (
                (current_role_code and current_role_code.lower() in {"medecin", "doctor"})
                or (current_role_name and current_role_name.lower() in {"medecin", "doctor"})
            )
        ):
            role_queryset = Role.objects.all()
        self.fields["role"].queryset = role_queryset.order_by("nom")
        self.fields["role"].required = bool(self.allowed_role_codes)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].required = True
        self.fields["password"].required = require_password

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("Email is required.")

        qs = AppUser.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if self.require_password and not password:
            raise forms.ValidationError("Password is required when creating a user.")
        return password


class EtablissementForm(forms.ModelForm):
    class Meta:
        model = Etablissement
        fields = [
            "nom",
            "code",
            "type_etablissement",
            "admin",
            "pays",
            "ville",
            "adresse",
            "telephone",
            "email",
            "site_web",
            "latitude",
            "longitude",
            "description",
            "actif",
        ]
        widgets = {
            "nom": forms.TextInput(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20"}),
            "code": forms.TextInput(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20", "placeholder": "Genere automatiquement", "readonly": "readonly"}),
            "type_etablissement": forms.Select(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20"}),
            "admin": forms.Select(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20"}),
            "pays": forms.Select(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20"}),
            "ville": forms.Select(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20"}),
            "adresse": forms.TextInput(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20", "placeholder": "Adresse complete"}),
            "telephone": forms.TextInput(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20"}),
            "email": forms.EmailInput(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20"}),
            "site_web": forms.URLInput(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20"}),
            "latitude": forms.NumberInput(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20", "step": "0.000001"}),
            "longitude": forms.NumberInput(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20", "step": "0.000001"}),
            "description": forms.Textarea(
                attrs={
                    "class": "mt-2 w-full rounded-xl border-0 bg-surface-container-lowest px-4 py-3 focus:ring-2 focus:ring-primary/20",
                    "rows": 3,
                }
            ),
            "actif": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-outline-variant text-primary focus:ring-primary/20"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["type_etablissement"].widget.choices = [("", "Choisir un type")] + [
            (key, label) for key, label in ETABLISSEMENT_TYPE_LABELS.items()
        ]
        admin_role_filter = Q(role__code__iexact="admin_etablissement") | Q(role__nom__iexact="admin_etablissement")
        self.fields["admin"].queryset = AppUser.objects.select_related("role").filter(admin_role_filter).order_by("first_name", "last_name", "email")
        self.fields["admin"].required = False
        self.fields["admin"].empty_label = "Choisir un admin d'etablissement"
        self.fields["admin"].label_from_instance = lambda user: (
            f"{((user.first_name or '') + ' ' + (user.last_name or '')).strip() or user.email} ({user.email or user.id})"
        )
        self.fields["code"].label = "Code Etablissement"
        self.fields["code"].required = False
        self.fields["code"].help_text = "Format automatique : TYP-VIL-001"
        self.fields["pays"].widget.choices = [("", "Choisir un pays")] + [
            (country, country) for country in COUNTRY_CITY_CHOICES.keys()
        ]
        self.fields["ville"].widget.choices = [("", "Choisir une ville")]

    def _build_code_prefix(self):
        type_value = self.cleaned_data.get("type_etablissement")
        city_value = self.cleaned_data.get("ville")
        if not type_value or not city_value:
            return None

        type_label = ETABLISSEMENT_TYPE_LABELS.get(type_value, type_value)
        type_part = _slug_code_part(type_label, "TYP")
        city_part = _slug_code_part(city_value, "VIL")
        return f"{type_part}-{city_part}"

    def _generate_code(self):
        prefix = self._build_code_prefix()
        if not prefix:
            return None

        current_code = (getattr(self.instance, "code", None) or "").strip().upper()
        if current_code.startswith(f"{prefix}-"):
            return current_code

        existing_codes = Etablissement.objects.filter(code__istartswith=f"{prefix}-")
        if self.instance.pk:
            existing_codes = existing_codes.exclude(pk=self.instance.pk)

        highest_sequence = 0
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{3}})$", re.IGNORECASE)
        for existing_code in existing_codes.values_list("code", flat=True):
            if not existing_code:
                continue
            match = pattern.match(existing_code.strip())
            if match:
                highest_sequence = max(highest_sequence, int(match.group(1)))

        return f"{prefix}-{highest_sequence + 1:03d}"

    def clean(self):
        cleaned_data = super().clean()
        generated_code = self._generate_code()
        if generated_code:
            cleaned_data["code"] = generated_code
        elif not self.instance.pk:
            self.add_error("code", "Le code sera genere quand le type et la ville seront renseignes.")
        return cleaned_data

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            return None
        qs = Etablissement.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Un etablissement avec cet email existe deja.")
        return email


class MedecinForm(forms.ModelForm):
    first_name = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                "placeholder": "Prenom",
            }
        )
    )
    last_name = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                "placeholder": "Nom",
            }
        )
    )
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                "placeholder": "medecin@example.com",
            }
        )
    )
    telephone = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                "placeholder": "+212 ...",
            }
        )
    )
    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(
            attrs={"class": "h-4 w-4 rounded border-outline-variant text-primary focus:ring-primary/20"}
        ),
    )
    password = forms.CharField(
        required=False,
        min_length=8,
        widget=forms.PasswordInput(
            attrs={
                "class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                "placeholder": "Mot de passe temporaire",
            }
        ),
        help_text="Requis uniquement lors de la creation d'un compte medecin.",
    )
    langues = forms.MultipleChoiceField(
        required=False,
        choices=COMMON_LANGUAGE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Langues",
    )
    autres_langues = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                "placeholder": "Espagnol, Allemand...",
            }
        ),
        help_text="Ajoute ici toute autre langue maitrisee, separee par des virgules.",
        label="Autres langues",
    )

    class Meta:
        model = Medecin
        fields = [
            "specialite",
            "numero_ordre",
            "signature_name",
            "photo_url",
            "bio",
            "note",
        ]
        widgets = {
            "specialite": forms.Select(
                attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20"},
                choices=SPECIALITE_CHOICES,
            ),
            "numero_ordre": forms.TextInput(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20", "placeholder": "Numero d'ordre"}),
            "signature_name": forms.TextInput(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20", "placeholder": "Nom de signature"}),
            "photo_url": forms.URLInput(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20", "placeholder": "https://..."}),
            "bio": forms.Textarea(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-lowest px-4 py-3 focus:ring-2 focus:ring-primary/20", "rows": 3, "placeholder": "Presentation courte du medecin"}),
            "note": forms.NumberInput(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20", "min": "0", "max": "5", "step": "0.1"}),
        }

    def __init__(self, *args, require_password=False, linked_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_password = require_password
        self.linked_user = linked_user
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["telephone"].required = True
        self.fields["specialite"].required = True
        self.fields["password"].required = require_password
        self.fields["email"].required = True
        if self.instance and self.instance.pk and self.instance.langues:
            selected_common_languages = []
            other_languages = []
            common_values = {value for value, _ in COMMON_LANGUAGE_CHOICES}
            for language in self.instance.langues:
                if language in common_values:
                    selected_common_languages.append(language)
                else:
                    other_languages.append(language)
            self.fields["langues"].initial = selected_common_languages
            self.fields["autres_langues"].initial = ", ".join(other_languages)
        if linked_user:
            self.fields["first_name"].initial = linked_user.first_name
            self.fields["last_name"].initial = linked_user.last_name
            self.fields["email"].initial = linked_user.email
            self.fields["telephone"].initial = linked_user.phone
            self.fields["is_active"].initial = linked_user.is_active

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("Email is required.")

        user_qs = AppUser.objects.filter(email__iexact=email)
        if self.linked_user and self.linked_user.pk:
            user_qs = user_qs.exclude(pk=self.linked_user.pk)
        if user_qs.exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean_telephone(self):
        telephone = (self.cleaned_data.get("telephone") or "").strip()
        if not telephone:
            raise forms.ValidationError("Phone is required.")
        qs = AppUser.objects.filter(phone__iexact=telephone)
        if self.linked_user and self.linked_user.pk:
            qs = qs.exclude(pk=self.linked_user.pk)
        if qs.exists():
            raise forms.ValidationError("A doctor with this phone already exists.")
        return telephone

    def clean_note(self):
        note = self.cleaned_data.get("note")
        if note is None:
            return None
        if note < 0 or note > 5:
            raise forms.ValidationError("La note doit etre comprise entre 0 et 5.")
        return note

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if self.require_password and not password:
            raise forms.ValidationError("Password is required when creating a doctor.")
        return password

    def clean_autres_langues(self):
        raw_value = (self.cleaned_data.get("autres_langues") or "").strip()
        if not raw_value:
            return []

        values = []
        for item in raw_value.split(","):
            normalized = item.strip()
            if normalized and normalized not in values:
                values.append(normalized)
        return values

    def clean(self):
        cleaned_data = super().clean()
        selected_languages = cleaned_data.get("langues") or []
        other_languages = cleaned_data.get("autres_langues") or []

        merged_languages = []
        for language in [*selected_languages, *other_languages]:
            if language and language not in merged_languages:
                merged_languages.append(language)

        cleaned_data["langues_input"] = merged_languages
        return cleaned_data


class PasswordSetupForm(forms.Form):
    new_password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full rounded-md bg-surface-container-highest px-4 py-4 outline-none transition-all focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary/20",
                "placeholder": "••••••••••••",
            }
        ),
        label="Nouveau mot de passe",
    )
    confirm_password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full rounded-md bg-surface-container-highest px-4 py-4 outline-none transition-all focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary/20",
                "placeholder": "••••••••••••",
            }
        ),
        label="Confirmer le mot de passe",
    )

    def clean_new_password(self):
        password = self.cleaned_data["new_password"]
        if len(password) < 8:
            raise forms.ValidationError("Le mot de passe doit contenir au moins 8 caracteres.")
        if not any(char.isupper() for char in password):
            raise forms.ValidationError("Le mot de passe doit contenir au moins une majuscule.")
        if not any(char.isdigit() for char in password):
            raise forms.ValidationError("Le mot de passe doit contenir au moins un chiffre.")
        if not any(not char.isalnum() for char in password):
            raise forms.ValidationError("Le mot de passe doit contenir au moins un caractere special.")
        return password

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")
        if new_password and confirm_password and new_password != confirm_password:
            self.add_error("confirm_password", "La confirmation du mot de passe ne correspond pas.")
        return cleaned_data


class MedecinEtablissementInvitationForm(forms.ModelForm):
    doctor_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "w-full bg-surface-container-low border-none rounded-md px-4 py-3 focus:ring-2 focus:ring-primary/20 transition-all outline-none",
                "placeholder": "Dr. Jean Dupont",
            }
        ),
        label="Nom complet",
    )

    class Meta:
        model = MedecinEtablissementInvitation
        fields = [
            "doctor_name",
            "medecin_email",
            "role",
            "can_issue_prescriptions",
            "can_sign_documents",
        ]
        widgets = {
            "medecin_email": forms.EmailInput(
                attrs={
                    "class": "w-full bg-surface-container-low border-none rounded-md pl-12 pr-4 py-3 focus:ring-2 focus:ring-primary/20 transition-all outline-none",
                    "placeholder": "nom@etablissement.fr",
                }
            ),
            "role": forms.Select(
                choices=MedecinEtablissementInvitation.ROLE_CHOICES,
                attrs={
                    "class": "w-full bg-surface-container-low border-none rounded-md px-4 py-3 focus:ring-2 focus:ring-primary/20 transition-all outline-none",
                },
            ),
            "can_issue_prescriptions": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-outline-variant text-primary focus:ring-primary/20"}
            ),
            "can_sign_documents": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-outline-variant text-primary focus:ring-primary/20"}
            ),
        }

    def __init__(self, *args, **kwargs):
        self.etablissement = kwargs.pop("etablissement", None)
        super().__init__(*args, **kwargs)
        self.fields["medecin_email"].label = "Email professionnel"
        self.fields["role"].label = "Role invite"
        self.fields["can_issue_prescriptions"].label = "Peut emettre des prescriptions"
        self.fields["can_sign_documents"].label = "Peut signer des documents"
        self.fields["doctor_name"].required = True
        self.fields["medecin_email"].required = True

    def clean_medecin_email(self):
        email = (self.cleaned_data.get("medecin_email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("L'email professionnel est obligatoire.")

        qs = MedecinEtablissementInvitation.objects.filter(
            medecin_email__iexact=email,
            status="pending",
        )
        if self.etablissement:
            qs = qs.filter(etablissement=self.etablissement)
        if qs.exists():
            raise forms.ValidationError("Une invitation en attente existe deja pour cet email.")
        return email


class DoctorInvitationDecisionForm(forms.Form):
    ACTION_CHOICES = (
        ("accept", "Accepter"),
        ("reject", "Refuser"),
    )

    action = forms.ChoiceField(choices=ACTION_CHOICES)
    pin_code = forms.CharField(
        min_length=4,
        max_length=20,
        widget=forms.PasswordInput(
            attrs={
                "class": "bg-surface-container-lowest border-none rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20",
                "placeholder": "Code PIN",
            }
        ),
        label="Code PIN",
    )

    def clean_action(self):
        action = (self.cleaned_data.get("action") or "").strip()
        if action not in {"accept", "reject"}:
            raise forms.ValidationError("Action invalide.")
        return action


class MedecinPresenceForm(forms.Form):
    STATUS_CHOICES = MedecinPresence.STATUS_CHOICES

    medecin_id = forms.UUIDField(widget=forms.HiddenInput())
    check_in_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(
            attrs={
                "class": "w-full bg-surface-container-highest border-none rounded-lg px-4 py-3 text-sm focus:ring-2 focus:ring-primary/20",
                "type": "time",
            }
        ),
    )
    check_out_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(
            attrs={
                "class": "w-full bg-surface-container-highest border-none rounded-lg px-4 py-3 text-sm focus:ring-2 focus:ring-primary/20",
                "type": "time",
            }
        ),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "w-full bg-surface-container-highest border-none rounded-lg px-4 py-3 text-sm focus:ring-2 focus:ring-primary/20 placeholder:text-slate-400",
                "rows": 3,
                "placeholder": "Enter reason for delay or specific handover notes...",
            }
        ),
    )

    def __init__(self, *args, presence_date=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.presence_date = presence_date or timezone.localdate()

    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get("check_in_time")
        check_out = cleaned_data.get("check_out_time")
        if check_in and check_out and check_out < check_in:
            self.add_error("check_out_time", "Check-out must be after check-in.")
        return cleaned_data

    def build_datetime(self, field_name):
        value = self.cleaned_data.get(field_name)
        if not value:
            return None
        naive_value = datetime.combine(self.presence_date, value)
        return timezone.make_aware(naive_value, timezone.get_current_timezone())


class MedecinIndisponibiliteForm(forms.ModelForm):
    class Meta:
        model = MedecinIndisponibilite
        fields = [
            "medecin",
            "type_indisponibilite",
            "motif",
            "date_debut",
            "date_fin",
            "heure_debut",
            "heure_fin",
            "toute_la_journee",
            "notes",
        ]
        widgets = {
            "medecin": forms.Select(
                attrs={"class": "w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20"}
            ),
            "type_indisponibilite": forms.Select(
                attrs={"class": "w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20"}
            ),
            "motif": forms.TextInput(
                attrs={
                    "class": "w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                    "placeholder": "Ex: Congres medical, absence exceptionnelle...",
                }
            ),
            "date_debut": forms.DateInput(
                attrs={
                    "class": "w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                    "type": "date",
                }
            ),
            "date_fin": forms.DateInput(
                attrs={
                    "class": "w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                    "type": "date",
                }
            ),
            "heure_debut": forms.TimeInput(
                attrs={
                    "class": "w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                    "type": "time",
                }
            ),
            "heure_fin": forms.TimeInput(
                attrs={
                    "class": "w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                    "type": "time",
                }
            ),
            "toute_la_journee": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-outline-variant text-primary focus:ring-primary/20"}
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                    "rows": 3,
                    "placeholder": "Notes internes sur l'indisponibilite.",
                }
            ),
        }

    def __init__(self, *args, doctor_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["medecin"].queryset = doctor_queryset if doctor_queryset is not None else Medecin.objects.none()
        self.fields["medecin"].label_from_instance = lambda doctor: (
            f"{doctor.full_name or doctor.email or doctor.id} - {doctor.specialite or 'Sans specialite'}"
        )
        self.fields["motif"].label = "Motif"
        self.fields["toute_la_journee"].label = "Toute la journee"

    def clean(self):
        cleaned_data = super().clean()
        date_debut = cleaned_data.get("date_debut")
        date_fin = cleaned_data.get("date_fin")
        heure_debut = cleaned_data.get("heure_debut")
        heure_fin = cleaned_data.get("heure_fin")
        toute_la_journee = cleaned_data.get("toute_la_journee")

        if date_debut and date_fin and date_fin < date_debut:
            self.add_error("date_fin", "La date de fin doit etre posterieure ou egale a la date de debut.")

        if not toute_la_journee:
            if not heure_debut:
                self.add_error("heure_debut", "L'heure de debut est requise.")
            if not heure_fin:
                self.add_error("heure_fin", "L'heure de fin est requise.")
            if heure_debut and heure_fin and heure_fin <= heure_debut and date_debut == date_fin:
                self.add_error("heure_fin", "L'heure de fin doit etre apres l'heure de debut.")

        return cleaned_data


class PatientForm(forms.ModelForm):
    gender = forms.ChoiceField(
        required=False,
        choices=[],
        widget=forms.Select(
            attrs={
                "class": "w-full bg-surface-container-low border-none rounded-xl py-4 px-5 text-sm focus:ring-2 focus:ring-primary/20 transition-all font-medium text-slate-900",
            }
        ),
    )
    blood_group = forms.ChoiceField(
        required=False,
        choices=[],
        widget=forms.Select(
            attrs={
                "class": "w-full bg-white/10 border-none rounded-xl py-4 px-5 text-sm focus:ring-2 focus:ring-white/20 transition-all font-bold appearance-none cursor-pointer",
                }
        ),
    )

    class Meta:
        model = Patient
        fields = [
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "phone",
            "email",
            "address",
            "blood_group",
            "emergency_contact_name",
            "emergency_contact_phone",
            "is_active",
        ]
        widgets = {
            "first_name": forms.TextInput(
                attrs={
                    "class": "w-full bg-surface-container-low border-none rounded-xl py-4 px-5 text-sm focus:ring-2 focus:ring-primary/20 transition-all placeholder:text-slate-400 font-medium",
                    "placeholder": "Entrez le prenom",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "class": "w-full bg-surface-container-low border-none rounded-xl py-4 px-5 text-sm focus:ring-2 focus:ring-primary/20 transition-all placeholder:text-slate-400 font-medium",
                    "placeholder": "Entrez le nom de famille",
                }
            ),
            "date_of_birth": forms.DateInput(
                attrs={
                    "class": "w-full bg-surface-container-low border-none rounded-xl py-4 px-5 text-sm focus:ring-2 focus:ring-primary/20 transition-all font-medium text-slate-900",
                    "type": "date",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "w-full bg-white border-none rounded-xl py-4 px-5 text-sm focus:ring-2 focus:ring-primary/20 transition-all font-medium",
                    "placeholder": "+212 6 00 00 00 00",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "w-full bg-white border-none rounded-xl py-4 px-5 text-sm focus:ring-2 focus:ring-primary/20 transition-all font-medium",
                    "placeholder": "patient@exemple.com",
                }
            ),
            "address": forms.Textarea(
                attrs={
                    "class": "w-full bg-white border-none rounded-xl py-4 px-5 text-sm focus:ring-2 focus:ring-primary/20 transition-all font-medium min-h-[116px] resize-none",
                    "placeholder": "Rue, Code Postal, Ville...",
                    "rows": 4,
                }
            ),
            "emergency_contact_name": forms.TextInput(
                attrs={
                    "class": "w-full bg-white border-none rounded-xl py-4 px-5 text-sm focus:ring-2 focus:ring-primary/20 transition-all font-medium",
                    "placeholder": "Nom complet du proche",
                }
            ),
            "emergency_contact_phone": forms.TextInput(
                attrs={
                    "class": "w-full bg-white border-none rounded-xl py-4 px-5 text-sm focus:ring-2 focus:ring-primary/20 transition-all font-medium",
                    "placeholder": "+212 6 00 00 00 00",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-outline-variant text-primary focus:ring-primary/20"}
            ),
        }

    def __init__(self, *args, etablissement=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.etablissement = etablissement
        self.fields["gender"].choices = [("", "Selectionner..."), *Patient.GENDER_CHOICES]
        self.fields["gender"].required = False
        self.fields["blood_group"].choices = [("", "Selectionner..."), *Patient.BLOOD_GROUP_CHOICES]
        self.fields["first_name"].label = "Prenom"
        self.fields["last_name"].label = "Nom"
        self.fields["date_of_birth"].label = "Date de naissance"
        self.fields["gender"].label = "Sexe"
        self.fields["phone"].label = "Telephone"
        self.fields["email"].label = "E-mail"
        self.fields["address"].label = "Adresse complete"
        self.fields["blood_group"].label = "Groupe sanguin"
        self.fields["emergency_contact_name"].label = "Nom du contact"
        self.fields["emergency_contact_phone"].label = "Telephone d'urgence"
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True

    def _build_patient_prefix(self):
        city_part = _slug_code_part(getattr(self.etablissement, "ville", None), "PAT")
        return f"PAT-{city_part}"

    def generate_patient_code(self):
        prefix = self._build_patient_prefix()
        existing_codes = Patient.objects.filter(patient_code__istartswith=f"{prefix}-")
        if self.instance.pk:
            existing_codes = existing_codes.exclude(pk=self.instance.pk)

        highest_sequence = 0
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{4}})$", re.IGNORECASE)
        for existing_code in existing_codes.values_list("patient_code", flat=True):
            if not existing_code:
                continue
            match = pattern.match(existing_code.strip())
            if match:
                highest_sequence = max(highest_sequence, int(match.group(1)))
        return f"{prefix}-{highest_sequence + 1:04d}"

    def generate_barcode_value(self, patient_code):
        return f"BC-{patient_code}-{timezone.now().strftime('%Y%m%d%H%M%S')}"

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        return email or None

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        return phone or None

    def clean_gender(self):
        gender = (self.cleaned_data.get("gender") or "").strip()
        return gender or None

    def clean_emergency_contact_phone(self):
        phone = (self.cleaned_data.get("emergency_contact_phone") or "").strip()
        return phone or None

    def clean(self):
        cleaned_data = super().clean()
        if not self.etablissement:
            raise forms.ValidationError("Aucun etablissement actif n'est associe a ce compte.")

        patient_code = self.generate_patient_code()
        cleaned_data["generated_patient_code"] = patient_code
        cleaned_data["generated_barcode_value"] = self.generate_barcode_value(patient_code)
        return cleaned_data
