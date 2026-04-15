from django import forms
from django.db.models import Q

from .models import AppUser, ETABLISSEMENT_TYPE_LABELS, Etablissement, Medecin, Role

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

    def __init__(self, *args, require_password=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_password = require_password
        doctor_role_filter = (
            Q(code__iexact="medecin")
            | Q(code__iexact="doctor")
            | Q(nom__iexact="medecin")
            | Q(nom__iexact="doctor")
        )
        role_queryset = Role.objects.exclude(doctor_role_filter)
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
        self.fields["role"].required = False
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
            "code": forms.TextInput(attrs={"class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20", "placeholder": "Code postal"}),
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
        self.fields["code"].label = "Code postal"
        self.fields["pays"].widget.choices = [("", "Choisir un pays")] + [
            (country, country) for country in COUNTRY_CITY_CHOICES.keys()
        ]
        self.fields["ville"].widget.choices = [("", "Choisir une ville")]

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code:
            return None
        qs = Etablissement.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Un etablissement avec ce code postal existe deja.")
        return code

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
    langues_input = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "mt-2 w-full rounded-xl border-0 bg-surface-container-low px-4 py-3 focus:ring-2 focus:ring-primary/20",
                "placeholder": "Francais, Anglais, Arabe",
            }
        ),
        help_text="Separez les langues par des virgules.",
        label="Langues",
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
            self.fields["langues_input"].initial = ", ".join(self.instance.langues)
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

    def clean_langues_input(self):
        raw_value = (self.cleaned_data.get("langues_input") or "").strip()
        if not raw_value:
            return []
        values = []
        for item in raw_value.split(","):
            normalized = item.strip()
            if normalized and normalized not in values:
                values.append(normalized)
        return values
