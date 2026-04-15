from rest_framework import serializers


ROLE_PERMISSIONS = {
    "super_admin": [
        "manage_users",
        "manage_roles",
        "manage_establishments",
        "manage_appointments",
        "manage_prescriptions",
        "view_all_patients",
    ],
    "admin_etablissement": [
        "manage_establishment_staff",
        "manage_appointments",
        "manage_prescriptions",
        "view_establishment_patients",
    ],
    "medecin": [
        "view_own_appointments",
        "manage_own_appointments",
        "issue_prescriptions",
        "view_assigned_patients",
    ],
    "secretaire": [
        "manage_appointments",
        "view_establishment_patients",
    ],
    "infirmier": [
        "view_establishment_patients",
        "view_appointments",
    ],
    "patient": [
        "view_own_profile",
        "view_own_appointments",
        "view_own_prescriptions",
    ],
    "family_member": [
        "view_linked_patients",
    ],
    "pharmacien": [
        "view_prescriptions",
        "dispense_prescriptions",
    ],
}


class MeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField(allow_null=True)
    first_name = serializers.CharField(allow_null=True)
    last_name = serializers.CharField(allow_null=True)
    phone = serializers.CharField(allow_null=True)
    is_active = serializers.BooleanField()
    role = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    def get_role(self, obj):
        return obj.role.code if obj.role else None

    def get_permissions(self, obj):
        role_code = obj.role.code if obj.role else None
        return ROLE_PERMISSIONS.get(role_code, [])