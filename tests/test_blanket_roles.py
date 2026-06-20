"""Tests for the stopgap blanket-role resource-instance permission framework.

Exercises BlanketRoleDenyFramework directly (no global PERMISSION_FRAMEWORK
switch needed): Delegate gets full access, Heritage Officer read-only, everyone
else denied, and the framework only ever UPGRADES the deny baseline.

Run:
    python manage.py test tests.test_blanket_roles --settings="tests.test_settings"
"""

import os

from django.contrib.auth.models import Group, User
from django.test.utils import captured_stdout

from arches.app.models.graph import Graph
from arches.app.models.resource import Resource
from arches.app.utils.betterJSONSerializer import JSONDeserializer
from arches.app.utils.data_management.resource_graphs.importer import (
    import_graph as ResourceGraphImporter,
)

from tests.base_test import ArchesTestCase

from quartz.permissions.blanket_roles import (
    BlanketRoleDenyFramework,
    FULL_ACCESS_GROUPS,
    READ_ACCESS_GROUPS,
)

DO_GRAPH_ID = "a535a235-8481-11ea-a6b9-f875a44e0e11"


class BlanketRoleFrameworkTests(ArchesTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        # A resource to check against (Digital Object is the smallest fixture).
        path = os.path.join(
            "tests/fixtures/resource_graphs", "Digital_Object.json"
        )
        with captured_stdout():
            with open(path) as f:
                archesfile = JSONDeserializer().deserialize(f)
            ResourceGraphImporter(archesfile["graph"], overwrite_graphs=True)
        cls.admin = User.objects.create(username="br_admin", is_superuser=True)
        Graph.objects.get(pk=DO_GRAPH_ID).publish(user=cls.admin)

        cls.resource = Resource(graph_id=DO_GRAPH_ID)
        cls.resource.save(index=False)

        delegate_group, _ = Group.objects.get_or_create(name=FULL_ACCESS_GROUPS[0])
        officer_group, _ = Group.objects.get_or_create(name=READ_ACCESS_GROUPS[0])

        cls.delegate = User.objects.create(username="br_delegate")
        cls.delegate.groups.add(delegate_group)
        cls.officer = User.objects.create(username="br_officer")
        cls.officer.groups.add(officer_group)
        cls.other = User.objects.create(username="br_other")  # no blanket group

        cls.fw = BlanketRoleDenyFramework()

    def _permitted(self, user, perm):
        return self.fw.check_resource_instance_permissions(
            user, None, perm, resource=self.resource
        )["permitted"]

    # ---- direct access ---------------------------------------------------
    def test_delegate_has_full_access(self):
        for perm in (
            "view_resourceinstance",
            "change_resourceinstance",
            "delete_resourceinstance",
        ):
            self.assertTrue(self._permitted(self.delegate, perm), perm)

    def test_officer_is_read_only(self):
        self.assertTrue(self._permitted(self.officer, "view_resourceinstance"))
        self.assertFalse(self._permitted(self.officer, "change_resourceinstance"))
        self.assertFalse(self._permitted(self.officer, "delete_resourceinstance"))

    def test_ungrouped_user_is_denied(self):
        self.assertFalse(self._permitted(self.other, "view_resourceinstance"))
        self.assertFalse(self._permitted(self.other, "change_resourceinstance"))

    # ---- search / bulk ---------------------------------------------------
    def test_get_allowed_instances_blanket_vs_denied(self):
        rid = str(self.resource.pk)
        self.assertIn(rid, self.fw.get_allowed_instances(self.delegate))
        self.assertIn(rid, self.fw.get_allowed_instances(self.officer))
        # Ungrouped user falls through to the deny framework (no access here).
        self.assertNotIn(rid, self.fw.get_allowed_instances(self.other))

    def test_search_filter_unrestricted_for_blanket_only(self):
        # Blanket users get an empty Bool (no permission restriction); others
        # get the standard groups_read/users_read restriction.
        blanket = self.fw.get_permission_search_filter(self.delegate)
        restricted = self.fw.get_permission_search_filter(self.other)
        self.assertNotEqual(
            blanket.dsl if hasattr(blanket, "dsl") else str(blanket),
            restricted.dsl if hasattr(restricted, "dsl") else str(restricted),
        )
