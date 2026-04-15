from .models import AppUser


class SupabaseUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_id = request.session.get("user_id")

        if user_id:
            try:
                request.user = AppUser.objects.select_related("role").get(id=user_id)
            except AppUser.DoesNotExist:
                request.user = None
        else:
            request.user = None

        return self.get_response(request)