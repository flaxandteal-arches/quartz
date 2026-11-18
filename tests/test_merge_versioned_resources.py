from unittest import mock

from django.test.utils import captured_stdout
from django.urls import resolve, reverse

from arches.app.models import models
from arches.app.models.resource import Resource
from arches.app.utils.betterJSONSerializer import JSONDeserializer
from arches.app.utils.data_management.resource_graphs.importer import (
    import_graph as ResourceGraphImporter,
)
from arches_resource_version_manager.models import VersionedResource

from tests.base_test import ArchesTestCase
from quartz.views import related_resources as view_module

DO_GRAPH_ID = "a535a235-8481-11ea-a6b9-f875a44e0e11"


class MergeVersionedResourcesTests(ArchesTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with captured_stdout():
            with open("tests/fixtures/resource_graphs/Digital_Object.json") as f:
                ResourceGraphImporter(
                    JSONDeserializer().deserialize(f)["graph"], overwrite_graphs=True
                )
        # Same teardown FK workaround as test_blanket_roles.
        models.Node.objects.filter(graph_id=DO_GRAPH_ID).update(
            sourcebranchpublication=None
        )

        lifecycle = models.ResourceInstanceLifecycle.objects.create(name="versions")
        states = {
            name: models.ResourceInstanceLifecycleState.objects.create(
                name=name,
                action_label=name,
                is_initial_state=name == "Draft",
                resource_instance_lifecycle=lifecycle,
            )
            for name in ("Draft", "Active", "Retired")
        }

        def resource(state="Draft", group=None):
            instance = models.ResourceInstance(
                graph_id=DO_GRAPH_ID, resource_instance_lifecycle_state=states[state]
            )
            instance.save()
            if group:
                VersionedResource.objects.create(
                    resourceinstance=instance, resource_group_id=group
                )
            return instance

        def link(source, target):
            models.ResourceXResource.objects.create(
                from_resource=source,
                to_resource=target,
                from_resource_graph_id=DO_GRAPH_ID,
                to_resource_graph_id=DO_GRAPH_ID,
            )

        cls.person = resource()
        cls.document = resource()
        cls.draft = resource("Draft", "item")
        cls.active = resource("Active", "item")
        cls.retired = resource("Retired", "item")
        cls.active_only = resource("Active", "finalised-item")

        # Each version's copied tile links it to the person.
        for version in (cls.draft, cls.active, cls.retired, cls.active_only):
            link(version, cls.person)
        # The document's own tile points at one specific version.
        link(cls.document, cls.active)
        # The Draft's working_copy points at itself.
        link(cls.draft, cls.draft)

    def related_to(self, viewed):
        def not_indexed(index, id):
            return {"docs": [{"_id": i, "found": False} for i in id]}

        # Only the relation query is under test: search and permissions are stubbed.
        with (
            mock.patch.object(view_module.se, "search", side_effect=not_indexed),
            mock.patch.object(
                view_module, "get_filtered_instances", return_value=(False, [])
            ),
            mock.patch.object(
                view_module.permission_backend,
                "get_resource_types_by_perm",
                return_value=[DO_GRAPH_ID],
            ),
        ):
            ret = view_module.merged_related_resources(
                Resource.objects.get(pk=viewed.pk)
            )
        others = {
            (
                rel["to_resource"]
                if rel["from_resource"] == viewed.pk
                else rel["from_resource"]
            )
            for rel in ret["resource_relationships"]
        }
        self.assertEqual(ret["total"]["value"], len(others))
        return others

    def test_related_url_uses_merged_view(self):
        url = reverse("related_resources", kwargs={"resourceid": str(self.person.pk)})
        self.assertIs(
            resolve(url).func.view_class, view_module.MergedVersionRelatedResourcesView
        )

    def test_lists_draft_and_versions_without_draft(self):
        self.assertEqual(
            self.related_to(self.person), {self.draft.pk, self.active_only.pk}
        )

    def test_keeps_a_link_made_to_a_specific_version(self):
        self.assertEqual(self.related_to(self.document), {self.active.pk})

    def test_viewed_version_keeps_its_own_relations(self):
        self.assertEqual(self.related_to(self.retired), {self.person.pk})

    def test_leaves_out_self_links(self):
        self.assertEqual(self.related_to(self.draft), {self.person.pk})
