from rest_framework.permissions import BasePermission


class HasRole(BasePermission):
    allowed_roles = []

    def has_permission(self, request, view):
        user = request.user
        if not user:
            return False
        if not getattr(user, "role", None):
            return False
        return user.role.code in self.allowed_roles


class IsAdmin(HasRole):
    allowed_roles = ["super_admin", "admin_etablissement"]


class IsDoctor(HasRole):
    allowed_roles = ["medecin"]


class IsSecretary(HasRole):
    allowed_roles = ["secretaire"]


class CanManageAppointments(HasRole):
    allowed_roles = ["super_admin", "admin_etablissement", "medecin", "secretaire"]


class CanIssuePrescriptions(HasRole):
    allowed_roles = ["super_admin", "admin_etablissement", "medecin"]