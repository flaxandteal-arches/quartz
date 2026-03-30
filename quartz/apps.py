from django.apps import AppConfig


class QuartzConfig(AppConfig):
    name = "quartz"
    is_arches_application = True

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        def ensure_user_backend(sender, user, request, **kwargs):
            if not hasattr(user, "backend"):
                user.backend = "django.contrib.auth.backends.ModelBackend"

        user_logged_in.connect(ensure_user_backend)
