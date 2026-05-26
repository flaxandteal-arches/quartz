from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.urls import include, path, re_path

import django_saml2_auth.views

from quartz.views.detsi_api import DynamicsHeritageSyncView


handler400 = "arches.app.views.main.custom_400"
handler403 = "arches.app.views.main.custom_403"
handler404 = "arches.app.views.main.custom_404"
handler500 = "arches.app.views.main.custom_500"

# Ensure Arches core urls are superseded by project-level urls
urlpatterns = [
    re_path(r"^sso/", include("django_saml2_auth.urls")),
    re_path(r"^sso/signin/$", django_saml2_auth.views.signin, name="saml2_signin"),
    path("", include("arches.urls")),
    path("", include("arches_controlled_lists.urls")),
    path("", include("arches_component_lab.urls")),
    path("", include("arches_her.urls")),
    path(
        "api/dynamics/heritage-item/",
        DynamicsHeritageSyncView.as_view(),
        name="dynamics_heritage_sync",
    ),
    path("", include("arches_search.urls")),
    path("", include("arches_notifications.urls")),
    path("", include("certificate_generator.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Only handle i18n routing in active project. This will still handle the routes provided by Arches core and Arches applications,
# but handling i18n routes in multiple places causes application errors.
if settings.ROOT_URLCONF == __name__:
    if settings.SHOW_LANGUAGE_SWITCH is True:
        urlpatterns = i18n_patterns(*urlpatterns)

    urlpatterns.append(path("i18n/", include("django.conf.urls.i18n")))

if settings.DEBUG:
    from django.contrib.staticfiles import views
    from django.urls import re_path

    urlpatterns += [
        re_path(r"^static/(?P<path>.*)$", views.serve),
    ]
