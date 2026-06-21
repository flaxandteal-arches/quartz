"""Permission-boundary tests for the "Export to Website" endpoint.

The button is only cosmetic; this guards the real gate — the view must 403
without quartz.export_to_website and pass it for the Delegate group and
superusers. CELERY_BROKER_URL is forced empty so the permitted path stops at
the broker guard (503) instead of trying to reach a real broker, making the
"permission passed" assertion deterministic without mocking Celery.

Run:
    python manage.py test tests.test_website_export_view --settings="tests.test_settings"
"""

from http import HTTPStatus

from django.contrib.auth.models import Group, User
from django.test import override_settings
from django.urls import reverse

from tests.base_test import ArchesTestCase


@override_settings(CELERY_BROKER_URL="")
class WebsiteExportPermissionTests(ArchesTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Migration 0010 creates the Delegate group; 0011 creates the
        # 'export_to_website' permission and grants it to Delegate.
        delegate = Group.objects.get(name="Delegate")

        cls.delegate_user = User.objects.create_user("we_delegate", password="x")
        cls.delegate_user.groups.add(delegate)
        cls.plain_user = User.objects.create_user("we_plain", password="x")
        cls.super_user = User.objects.create_superuser(
            "we_super", email="", password="x"
        )

        cls.url = reverse("website_export")

    def test_forbidden_without_permission(self):
        self.client.force_login(self.plain_user)
        self.assertEqual(
            self.client.post(self.url).status_code, HTTPStatus.FORBIDDEN
        )

    def test_anonymous_is_forbidden(self):
        self.assertEqual(
            self.client.post(self.url).status_code, HTTPStatus.FORBIDDEN
        )

    def test_get_not_allowed(self):
        # POST-only; a GET must never run the action.
        self.client.force_login(self.delegate_user)
        self.assertEqual(
            self.client.get(self.url).status_code,
            HTTPStatus.METHOD_NOT_ALLOWED,
        )

    def test_delegate_passes_permission(self):
        self.client.force_login(self.delegate_user)
        # Permission passes -> reaches the broker guard -> 503 (broker empty).
        self.assertEqual(
            self.client.post(self.url).status_code,
            HTTPStatus.SERVICE_UNAVAILABLE,
        )

    def test_superuser_passes_permission(self):
        self.client.force_login(self.super_user)
        self.assertEqual(
            self.client.post(self.url).status_code,
            HTTPStatus.SERVICE_UNAVAILABLE,
        )
