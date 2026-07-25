from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.http import HttpRequest

User = get_user_model()
DEV_EMAIL = "dev@localhost"

class DevAutoLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        if settings.DEBUG and not request.user.is_authenticated:
            user, _ = User.objects.get_or_create(
                email=DEV_EMAIL,
                defaults={"is_superuser": True, "is_staff": True},
            )
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_response(request)
