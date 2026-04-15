import logging

import requests
from django.conf import settings


logger = logging.getLogger(__name__)


class SupabaseAdminError(Exception):
    pass


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

    def create_auth_user(self, *, email, password, first_name, last_name, phone, role_code):
        payload = {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "role": role_code,
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

    def delete_auth_user(self, *, user_id):
        response = requests.delete(
            f"{self.base_url}/auth/v1/admin/users/{user_id}",
            headers=self._headers(),
            timeout=15,
        )
        self._raise_for_status(response, "delete auth user")
        return True

    @staticmethod
    def _raise_for_status(response, action):
        if response.ok:
            return

        try:
            payload = response.json()
        except ValueError:
            payload = response.text

        logger.warning("Supabase admin %s failed: %s", action, payload)
        raise SupabaseAdminError(f"Unable to {action}: {payload}")
