from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.urls import include, path, re_path

import django_saml2_auth.views

from quartz.views.detsi_api import DynamicsHeritageSyncView
from quartz.views.resource import VersionedResourceEditorView

handler400 = "arches.app.views.main.custom_400"
handler403 = "arches.app.views.main.custom_403"
handler404 = "arches.app.views.main.custom_404"
handler500 = "arches.app.views.main.custom_500"

# Machine-to-machine API endpoints — must never be language-prefixed.
_api_urlpatterns = [
    path(
        "api/dynamics/heritage-item/",
        DynamicsHeritageSyncView.as_view(),
        name="dynamics_heritage_sync",
    ),
]

# Ensure Arches core urls are superseded by project-level urls
_app_urlpatterns = [
    re_path(r"^sso/", include("django_saml2_auth.urls")),
    re_path(r"^sso/signin/$", django_saml2_auth.views.signin, name="saml2_signin"),
    path("", include("arches_modular_reports.urls")),
    path("", include("arches_search.urls")),
    re_path(
        r"^resource/(?P<resourceid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/copy$",
        VersionedResourceEditorView.as_view(action="copy"),
        name="resource_copy",
    ),
    re_path(
        r"^resource/(?P<resourceid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$",
        VersionedResourceEditorView.as_view(),
        name="resource_editor",
    ),
    path("", include("arches.urls")),
    path("", include("arches_controlled_lists.urls")),
    path("", include("arches_her.urls")),
    path("", include("certificate_generator.urls")),
    path("", include("arches_notifications.urls")),
    path("", include("arches_modular_reports.urls")),
    path("", include("arches_resource_version_manager.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns = (
    _app_urlpatterns
    + _api_urlpatterns
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
)

# Only handle i18n routing in active project. This will still handle the routes provided by Arches core and Arches applications,
# but handling i18n routes in multiple places causes application errors.
if settings.ROOT_URLCONF == __name__:
    if settings.SHOW_LANGUAGE_SWITCH is True:
        urlpatterns = (
            i18n_patterns(*_app_urlpatterns)
            + _api_urlpatterns
            + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
        )

    urlpatterns.append(path("i18n/", include("django.conf.urls.i18n")))

if settings.DEBUG:
    from django.contrib.staticfiles import views
    from django.urls import re_path

    urlpatterns += [
        re_path(r"^static/(?P<path>.*)$", views.serve),
    ]
