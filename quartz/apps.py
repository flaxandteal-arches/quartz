from django.apps import AppConfig
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


# Registered at module-import time (during AppConfig discovery) so it runs
# before anything connected in arches.app.signals via that app's ready().
# django_saml2_auth calls django.contrib.auth.login(request, user, backend)
# without going through authenticate(), so user.backend is never set as an
# attribute — only stored in the session. Arches' user_logged_in receiver
# reads user.backend directly and AttributeErrors. Set it here first.
@receiver(user_logged_in, dispatch_uid="quartz.ensure_user_backend")
def ensure_user_backend(sender, user, request, **kwargs):
    if not hasattr(user, "backend"):
        user.backend = "django.contrib.auth.backends.ModelBackend"


class QuartzConfig(AppConfig):
    name = "quartz"
    is_arches_application = True
