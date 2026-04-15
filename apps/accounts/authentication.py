import time
import requests
import jwt

from django.conf import settings
from rest_framework import authentication, exceptions

from .models import AppUser


class SupabaseJWTAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ", 1)[1].strip()
        if not token:
            return None

        payload = self._verify_token(token)
        user_id = payload.get("sub")

        if not user_id:
            raise exceptions.AuthenticationFailed("Token missing subject")

        try:
            user = AppUser.objects.select_related("role").get(id=user_id, is_active=True)
        except AppUser.DoesNotExist:
            raise exceptions.AuthenticationFailed("User not found in public.users")

        return (user, token)

    def _verify_token(self, token: str):
        jwks_url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"

        try:
            resp = requests.get(jwks_url, timeout=10)
            resp.raise_for_status()
            jwks = resp.json()
        except Exception as exc:
            raise exceptions.AuthenticationFailed(f"Unable to fetch JWKS: {exc}")

        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
        except Exception:
            raise exceptions.AuthenticationFailed("Invalid token header")

        key = None
        for jwk in jwks.get("keys", []):
            if jwk.get("kid") == kid:
                key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
                break

        if key is None:
            raise exceptions.AuthenticationFailed("Matching JWK not found")

        try:
            payload = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=settings.SUPABASE_JWT_AUDIENCE,
                options={"verify_exp": True},
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token expired")
        except jwt.InvalidTokenError as exc:
            raise exceptions.AuthenticationFailed(f"Invalid token: {exc}")

        exp = payload.get("exp")
        if exp and exp < time.time():
            raise exceptions.AuthenticationFailed("Token expired")

        return payload