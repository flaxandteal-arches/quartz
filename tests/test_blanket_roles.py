"""Tests for the stopgap blanket-role resource-instance permission framework.

Exercises BlanketRoleDenyFramework directly (no global PERMISSION_FRAMEWORK
switch needed). It is a HARD ALLOWLIST GATE: superuser and Delegate get full
access, Heritage Officer gets view-everywhere plus change on Draft resources,
and everyone else is denied — including resource owners (principaluser) and
holders of explicit per-instance rows, which the gate overrides.

Run:
    python manage.py test tests.test_blanket_roles --settings="tests.test_settings"
"""

import os

from django.contrib.auth.models import Group, User
from django.test.utils import captured_stdout

from arches.app.models.models import (
    Node,
    ResourceInstanceLifecycle,
    ResourceInstanceLifecycleState,
)
from arches.app.models.resource import Resource
from arches.app.search.search_engine_factory import SearchEngineFactory
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
        path = os.path.join("tests/fixtures/resource_graphs", "Digital_Object.json")
        with captured_stdout():
            with open(path) as f:
                archesfile = JSONDeserializer().deserialize(f)
            ResourceGraphImporter(archesfile["graph"], overwrite_graphs=True)
        # The Digital_Object fixture pins nodes to a branch publication that is
        # never created, which trips a deferred FK check at test teardown. Clear
        # it — the graph remains a usable draft for attaching resources.
        Node.objects.filter(graph_id=DO_GRAPH_ID).update(sourcebranchpublication=None)
        cls.admin = User.objects.create(username="br_admin", is_superuser=True)
        # NB: the graph is intentionally left unpublished. Publishing it inside
        # the test transaction leaves nodes referencing an as-yet-uncommitted
        # branch publication, which trips the deferred FK check at teardown; the
        # permission framework does not need a published graph here.

        # Two lifecycle states: Draft (Heritage-Officer-editable) and a
        # non-Draft state, so we can prove the state-gated edit.
        lifecycle = ResourceInstanceLifecycle.objects.create(name="test-lifecycle")
        cls.draft_state = ResourceInstanceLifecycleState.objects.create(
            name="Draft",
            action_label="Draft",
            is_initial_state=True,
            can_edit_resource_instances=True,
            resource_instance_lifecycle=lifecycle,
        )
        cls.final_state = ResourceInstanceLifecycleState.objects.create(
            name="Published",
            action_label="Publish",
            is_initial_state=False,
            can_edit_resource_instances=False,
            resource_instance_lifecycle=lifecycle,
        )

        cls.delegate = User.objects.create(username="br_delegate")
        cls.officer = User.objects.create(username="br_officer")
        cls.other = User.objects.create(username="br_other")  # no blanket group

        delegate_group, _ = Group.objects.get_or_create(name=FULL_ACCESS_GROUPS[0])
        officer_group, _ = Group.objects.get_or_create(name=READ_ACCESS_GROUPS[0])
        cls.delegate.groups.add(delegate_group)
        cls.officer.groups.add(officer_group)

        # A plain (non-Draft) resource.
        cls.resource = Resource(
            graph_id=DO_GRAPH_ID, resource_instance_lifecycle_state=cls.final_state
        )
        cls.resource.save(index=False)

        # A Draft resource (editable by Heritage Officer).
        cls.draft_resource = Resource(
            graph_id=DO_GRAPH_ID, resource_instance_lifecycle_state=cls.draft_state
        )
        cls.draft_resource.save(index=False)

        # A resource OWNED by the ungrouped user, to prove the hard gate
        # overrides the base owner (principaluser) short-circuit.
        cls.owned_resource = Resource(
            graph_id=DO_GRAPH_ID,
            resource_instance_lifecycle_state=cls.final_state,
            principaluser=cls.other,
        )
        cls.owned_resource.save(index=False)

        cls.fw = BlanketRoleDenyFramework()

    def _permitted(self, user, perm, resource=None):
        return self.fw.check_resource_instance_permissions(
            user, None, perm, resource=resource if resource is not None else self.resource
        )["permitted"]

    # ---- direct access ---------------------------------------------------
    def test_superuser_has_full_access(self):
        for perm in (
            "view_resourceinstance",
            "change_resourceinstance",
            "delete_resourceinstance",
        ):
            self.assertTrue(self._permitted(self.admin, perm), perm)

    def test_delegate_has_full_access(self):
        for perm in (
            "view_resourceinstance",
            "change_resourceinstance",
            "delete_resourceinstance",
        ):
            self.assertTrue(self._permitted(self.delegate, perm), perm)

    def test_officer_read_only_on_non_draft(self):
        self.assertTrue(self._permitted(self.officer, "view_resourceinstance"))
        self.assertFalse(self._permitted(self.officer, "change_resourceinstance"))
        self.assertFalse(self._permitted(self.officer, "delete_resourceinstance"))

    def test_officer_can_change_draft_but_not_delete(self):
        r = self.draft_resource
        self.assertTrue(self._permitted(self.officer, "view_resourceinstance", r))
        self.assertTrue(self._permitted(self.officer, "change_resourceinstance", r))
        self.assertFalse(self._permitted(self.officer, "delete_resourceinstance", r))

    def test_ungrouped_user_is_denied(self):
        self.assertFalse(self._permitted(self.other, "view_resourceinstance"))
        self.assertFalse(self._permitted(self.other, "change_resourceinstance"))

    def test_hard_gate_overrides_owner_short_circuit(self):
        # The ungrouped user OWNS this resource (principaluser); the base
        # framework would permit, but the hard gate denies.
        r = self.owned_resource
        self.assertFalse(self._permitted(self.other, "view_resourceinstance", r))
        self.assertFalse(self._permitted(self.other, "change_resourceinstance", r))
        # ...while Delegate still gets full access to it.
        self.assertTrue(self._permitted(self.delegate, "change_resourceinstance", r))

    # ---- search / bulk ---------------------------------------------------
    def test_get_allowed_instances_blanket_vs_denied(self):
        rid = str(self.resource.pk)
        self.assertIn(rid, self.fw.get_allowed_instances(self.delegate))
        self.assertIn(rid, self.fw.get_allowed_instances(self.officer))
        # Ungrouped user is hard-gated to nothing (no fall-through to base).
        self.assertEqual([], self.fw.get_allowed_instances(self.other))

    def test_search_filter_unrestricted_for_blanket_only(self):
        # Blanket users get an empty Bool (no permission restriction); others
        # get a match-nothing filter.
        blanket = self.fw.get_permission_search_filter(self.delegate)
        restricted = self.fw.get_permission_search_filter(self.other)
        self.assertNotEqual(
            blanket.dsl if hasattr(blanket, "dsl") else str(blanket),
            restricted.dsl if hasattr(restricted, "dsl") else str(restricted),
        )
