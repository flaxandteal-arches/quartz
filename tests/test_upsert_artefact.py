"""End-to-end tests for Artefact payload upserts.

The test loads the real Artefact graph and exercises ``process_artefact``
against persisted Arches resources. It deliberately seeds a Draft with values
that are not supplied by the payload, both inside and outside a managed
nodegroup, to guard against an upsert deleting user-entered data.

Run:
    python manage.py test tests.test_upsert_artefact --settings="tests.test_settings"
"""

from pathlib import Path

from django.contrib.auth.models import User
from django.test.utils import captured_stdout

from arches.app.models import models
from arches.app.models.graph import Graph
from arches.app.models.resource import Resource
from arches.app.models.tile import Tile
from arches.app.utils.betterJSONSerializer import JSONDeserializer
from arches.app.utils.data_management.resource_graphs.importer import (
    import_graph as ResourceGraphImporter,
)
from arches_controlled_lists.models import List, ListItem, ListItemValue
from arches_resource_version_manager.models import VersionedResource

from tests.base_test import ArchesTestCase

from quartz.utils.payload_utils import i18n_string, parse_reference_node
from quartz.utils.upsert_artefact import (
    ARCHAEOLOGY_DISCOVERY_TYPE_LIST_NAME,
    ARCHAEOLOGY_STATUS_LIST_NAME,
    ARCHAEOLOGY_STATUS_NODEGROUP,
    ARTEFACT_GRAPH_ID,
    ARTEFACT_NAMES_NODEGROUP,
    DISCOVERY_METHOD_LIST_NAME,
    DISCOVERY_NODEGROUP,
    NODE_ARCHAEOLOGY_DISCOVERY_TYPE,
    NODE_ARCHAEOLOGY_STATUS,
    NODE_ARTEFACT_NAME,
    NODE_DISCOVERY_METHOD,
    process_artefact,
)


ARTEFACT_GRAPH_PATH = (
    Path(__file__).resolve().parents[1]
    / "quartz"
    / "pkg"
    / "graphs"
    / "resource_models"
    / "Artefact.json"
)

# Genuine Artefact graph nodes deliberately not populated by the payload.
DISCOVERY_NOTE_NODE = "74a12bd8-8625-11ea-b4f8-f875a44e0e11"
COPYRIGHT_NODEGROUP = "0324f681-eeca-11eb-9db9-a87eeabdefba"
COPYRIGHT_NOTE_NODE = "0324f684-eeca-11eb-81b7-a87eeabdefba"


class ProcessArtefactIntegrationTests(ArchesTestCase):
    """Verify that an existing Artefact Draft is updated without data loss."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        with captured_stdout(), ARTEFACT_GRAPH_PATH.open() as graph_file:
            archesfile = JSONDeserializer().deserialize(graph_file)
            ResourceGraphImporter(archesfile["graph"], overwrite_graphs=True)

        cls.user, _ = User.objects.get_or_create(username="dynamics_user")

        Graph.objects.get(pk=ARTEFACT_GRAPH_ID).publish(user=cls.user)

        cls._add_list_values(DISCOVERY_METHOD_LIST_NAME, ["Incidental Find"])
        cls._add_list_values(
            ARCHAEOLOGY_DISCOVERY_TYPE_LIST_NAME,
            ["Archaeological Artefact / Site"],
        )
        cls._add_list_values(ARCHAEOLOGY_STATUS_LIST_NAME, ["Draft"])

    def setUp(self):
        super().setUp()
        self.payload = {
            "dpp_permitnumber": "710202",
            "dpp_discoveryreferencenumber": "incoming-legacy-id",
            "dpp_discoveryname": "Incoming payload name",
            "dpp_context": "Incidental Find",
            "dpp_archaeologytype": "Archaeological Artefact / Site",
            "dpp_archaeologystatus": "Draft",
        }

        self.original_discovery_note = "Keep this manually entered discovery note"
        self.original_copyright_note = "Keep this unrelated copyright note"
        self.resource = Resource(graph_id=ARTEFACT_GRAPH_ID)
        self.resource.resource_instance_lifecycle_state = (
            models.ResourceInstanceLifecycleState.objects.get(name="Draft")
        )
        self.resource.tiles.extend(
            [
                Tile(
                    nodegroup_id=DISCOVERY_NODEGROUP,
                    data={
                        DISCOVERY_NOTE_NODE: i18n_string(self.original_discovery_note),
                        NODE_DISCOVERY_METHOD: {"stale": "payload value"},
                    },
                ),
                Tile(
                    nodegroup_id=ARTEFACT_NAMES_NODEGROUP,
                    data={NODE_ARTEFACT_NAME: i18n_string("Previous payload name")},
                ),
                Tile(
                    nodegroup_id=COPYRIGHT_NODEGROUP,
                    data={
                        COPYRIGHT_NOTE_NODE: i18n_string(self.original_copyright_note)
                    },
                ),
            ]
        )
        self.resource.save(user=self.user, index=False)
        VersionedResource.objects.create(
            resourceinstance=self.resource,
            resource_group_id=self.payload["dpp_permitnumber"],
            major_version=4,
            minor_version=2,
            metadata={"source": "existing sample record"},
        )

    @classmethod
    def _add_list_values(cls, list_name, values):
        controlled_list, _ = List.objects.get_or_create(name=list_name)
        for sortorder, value in enumerate(values):
            item, _ = ListItem.objects.get_or_create(
                list=controlled_list,
                uri=f"https://example.test/{list_name}/{value}",
                defaults={"sortorder": sortorder},
            )
            ListItemValue.objects.get_or_create(
                list_item=item,
                value=value,
                valuetype_id="prefLabel",
                language_id="en",
            )

    def _tile(self, resource_id, nodegroup_id):
        return Tile.objects.get(
            resourceinstance_id=resource_id,
            nodegroup_id=nodegroup_id,
        )

    def test_existing_draft_preserves_non_payload_data_and_updates_payload_nodes(self):
        resource, created, version = process_artefact(self.payload, self.user)

        self.assertEqual(resource.pk, self.resource.pk)
        self.assertFalse(created)
        self.assertEqual(version, "4.3")

        # Nodes populated by the payload are updated in the existing tiles.
        name_tile = self._tile(self.resource.pk, ARTEFACT_NAMES_NODEGROUP)
        self.assertEqual(
            name_tile.data[NODE_ARTEFACT_NAME],
            i18n_string(self.payload["dpp_discoveryname"]),
        )
        discovery_tile = self._tile(self.resource.pk, DISCOVERY_NODEGROUP)
        self.assertEqual(
            discovery_tile.data[NODE_DISCOVERY_METHOD],
            parse_reference_node(
                self.payload["dpp_context"], DISCOVERY_METHOD_LIST_NAME
            ),
        )
        self.assertEqual(
            discovery_tile.data[NODE_ARCHAEOLOGY_DISCOVERY_TYPE],
            parse_reference_node(
                self.payload["dpp_archaeologytype"],
                ARCHAEOLOGY_DISCOVERY_TYPE_LIST_NAME,
            ),
        )
        status_tile = self._tile(self.resource.pk, ARCHAEOLOGY_STATUS_NODEGROUP)
        self.assertEqual(
            status_tile.data[NODE_ARCHAEOLOGY_STATUS],
            parse_reference_node(
                self.payload["dpp_archaeologystatus"], ARCHAEOLOGY_STATUS_LIST_NAME
            ),
        )

        # Data not provided by the payload survives, including a value sharing
        # a tile with managed payload nodes and data in an unrelated nodegroup.
        self.assertEqual(
            discovery_tile.data[DISCOVERY_NOTE_NODE],
            i18n_string(self.original_discovery_note),
        )
        self.assertEqual(
            self._tile(self.resource.pk, COPYRIGHT_NODEGROUP).data[
                COPYRIGHT_NOTE_NODE
            ],
            i18n_string(self.original_copyright_note),
        )

        current_version = VersionedResource.objects.get(pk=self.resource.pk)
        self.assertEqual(
            (current_version.major_version, current_version.minor_version), (4, 3)
        )
        self.assertEqual(current_version.metadata, self.payload)

        # The archival copy captures the original record before the update.
        archived_version = VersionedResource.objects.exclude(pk=self.resource.pk).get(
            resource_group_id=self.payload["dpp_permitnumber"]
        )
        archived_discovery_tile = self._tile(archived_version.pk, DISCOVERY_NODEGROUP)
        self.assertEqual(
            archived_discovery_tile.data[DISCOVERY_NOTE_NODE],
            i18n_string(self.original_discovery_note),
        )
        self.assertEqual(
            self._tile(archived_version.pk, ARTEFACT_NAMES_NODEGROUP).data[
                NODE_ARTEFACT_NAME
            ],
            i18n_string("Previous payload name"),
        )