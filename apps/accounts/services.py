import logging

import requests
from django.conf import settings


logger = logging.getLogger(__name__)


class SupabaseAdminError(Exception):
    def __init__(self, message, *, status_code=None, payload=None, action=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload
        self.action = action

    @property
    def is_unexpected_failure(self):
        return (
            self.status_code is not None
            and self.status_code >= 500
            and isinstance(self.payload, dict)
            and self.payload.get("error_code") == "unexpected_failure"
        )


class SupabaseAdminService:
    def __init__(self):
        self.base_url = settings.SUPABASE_URL.rstrip("/")
        self.service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY

    def _headers(self):
        if not self.base_url or not self.service_role_key:
            raise SupabaseAdminError(
                "Supabase admin configuration is missing. Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
            )
        return {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
        }

    def create_auth_user(self, *, email, password, first_name, last_name, phone, role_code, require_password_change=False):
        payload = {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "role": role_code,
                "requires_password_change": require_password_change,
            },
        }
        response = requests.post(
            f"{self.base_url}/auth/v1/admin/users",
            headers=self._headers(),
            json=payload,
            timeout=15,
        )
        self._raise_for_status(response, "create auth user")
        return response.json()

    def update_auth_user(self, *, user_id, email, first_name, last_name, phone, role_code, is_active):
        payload = {
            "email": email,
            "user_metadata": {
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "role": role_code,
            },
            "ban_duration": "none" if is_active else "876000h",
        }
        response = requests.put(
            f"{self.base_url}/auth/v1/admin/users/{user_id}",
            headers=self._headers(),
            json=payload,
            timeout=15,
        )
        self._raise_for_status(response, "update auth user")
        return response.json()

    def update_current_user_password(self, *, access_token, password):
        response = requests.put(
            f"{self.base_url}/auth/v1/user",
            headers={
                "apikey": settings.SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "password": password,
                "data": {
                    "requires_password_change": False,
                },
            },
            timeout=15,
        )
        self._raise_for_status(response, "update current user password")
        return response.json()

    def get_auth_user(self, *, user_id):
        response = requests.get(
            f"{self.base_url}/auth/v1/admin/users/{user_id}",
            headers=self._headers(),
            timeout=15,
        )
        self._raise_for_status(response, "get auth user")
        return response.json()

    def delete_auth_user(self, *, user_id):
        response = self._delete_auth_user_request(user_id=user_id, should_soft_delete=False)
        payload = self._extract_error_payload(response)
        if response.ok:
            return {"soft_deleted": False}

        if self._should_retry_soft_delete(response, payload):
            logger.warning(
                "Supabase hard delete failed for user %s. Retrying with soft delete. Payload: %s",
                user_id,
                payload,
            )
            soft_delete_response = self._delete_auth_user_request(user_id=user_id, should_soft_delete=True)
            if soft_delete_response.ok:
                return {"soft_deleted": True}

            self._raise_for_status(soft_delete_response, "soft delete auth user")

        self._raise_for_status(response, "delete auth user")
        return {"soft_deleted": False}

    def _delete_auth_user_request(self, *, user_id, should_soft_delete):
        params = {"should_soft_delete": "true"} if should_soft_delete else None
        return requests.delete(
            f"{self.base_url}/auth/v1/admin/users/{user_id}",
            headers=self._headers(),
            params=params,
            timeout=15,
        )

    @staticmethod
    def _raise_for_status(response, action):
        if response.ok:
            return

        payload = SupabaseAdminService._extract_error_payload(response)

        logger.warning("Supabase admin %s failed: %s", action, payload)
        raise SupabaseAdminError(
            f"Unable to {action}: {payload}",
            status_code=response.status_code,
            payload=payload,
            action=action,
        )

    @staticmethod
    def _extract_error_payload(response):
        try:
            return response.json()
        except ValueError:
            return response.text

    @staticmethod
    def _should_retry_soft_delete(response, payload):
        if response.status_code < 500:
            return False
        if not isinstance(payload, dict):
            return False
        return payload.get("error_code") == "unexpected_failure"
