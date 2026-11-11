"""Unit tests for safe updates to existing Artefact tiles.

These tests deliberately avoid graph imports and database writes. They verify
the invariant required by ``process_artefact``: Dynamics-managed node values
are cleared and replaced, while all other existing tile data is retained.

Run:
    python manage.py test tests.test_upsert_artefact --settings="tests.test_settings"
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from quartz.utils.upsert_artefact import (
    DISCOVERY_NODEGROUP,
    NODE_ARCHAEOLOGY_DISCOVERY_TYPE,
    NODE_ARTEFACT_NAME,
    NODE_DISCOVERY_METHOD,
    _clear_managed_node_values,
    _make_or_update_tiles_from_cache,
)


UNMANAGED_DISCOVERY_NOTE_NODE = "74a12bd8-8625-11ea-b4f8-f875a44e0e11"
UNMANAGED_NODEGROUP = "unmanaged-nodegroup"
UNMANAGED_NODE = "unmanaged-node"


class ManagedTileUpdateTests(TestCase):
    """Test the existing-tile update path without an Arches graph or database."""

    def setUp(self):
        self.discovery_tile = SimpleNamespace(
            nodegroup_id=DISCOVERY_NODEGROUP,
            data={
                NODE_DISCOVERY_METHOD: {"old": "Dynamics value"},
                NODE_ARCHAEOLOGY_DISCOVERY_TYPE: {"old": "Dynamics type"},
                UNMANAGED_DISCOVERY_NOTE_NODE: {"en": {"value": "Keep me"}},
            },
        )
        self.unmanaged_tile = SimpleNamespace(
            nodegroup_id=UNMANAGED_NODEGROUP,
            data={
                NODE_ARTEFACT_NAME: {"en": {"value": "Never touch me"}},
                UNMANAGED_NODE: {"en": {"value": "Keep me too"}},
            },
        )

    def test_clear_removes_only_managed_nodes_from_managed_tiles(self):
        with patch(
            "quartz.utils.upsert_artefact.models.TileModel.objects.filter",
            return_value=[self.discovery_tile],
        ) as tile_filter, patch(
            "quartz.utils.upsert_artefact.models.TileModel.objects.bulk_update"
        ) as bulk_update:
            _clear_managed_node_values("resource-id")

        tile_filter.assert_called_once()
        self.assertEqual(
            self.discovery_tile.data,
            {UNMANAGED_DISCOVERY_NOTE_NODE: {"en": {"value": "Keep me"}}},
        )
        self.assertEqual(
            self.unmanaged_tile.data,
            {
                NODE_ARTEFACT_NAME: {"en": {"value": "Never touch me"}},
                UNMANAGED_NODE: {"en": {"value": "Keep me too"}},
            },
        )
        bulk_update.assert_called_once_with([self.discovery_tile], ["data"])

    def test_cache_update_replaces_payload_nodes_and_keeps_other_node_data(self):
        tiles = _make_or_update_tiles_from_cache(
            DISCOVERY_NODEGROUP,
            {
                NODE_DISCOVERY_METHOD: {"incoming": "Dynamics value"},
                NODE_ARCHAEOLOGY_DISCOVERY_TYPE: {"incoming": "Dynamics type"},
            },
            existing_tiles_by_nodegroup={DISCOVERY_NODEGROUP: [self.discovery_tile]},
        )

        self.assertEqual(tiles, [self.discovery_tile])
        self.assertEqual(
            self.discovery_tile.data[NODE_DISCOVERY_METHOD],
            {"incoming": "Dynamics value"},
        )
        self.assertEqual(
            self.discovery_tile.data[NODE_ARCHAEOLOGY_DISCOVERY_TYPE],
            {"incoming": "Dynamics type"},
        )
        self.assertEqual(
            self.discovery_tile.data[UNMANAGED_DISCOVERY_NOTE_NODE],
            {"en": {"value": "Keep me"}},
        )

    def test_update_does_not_modify_tiles_in_other_nodegroups(self):
        existing_tiles_by_nodegroup = {
            DISCOVERY_NODEGROUP: [self.discovery_tile],
            UNMANAGED_NODEGROUP: [self.unmanaged_tile],
        }

        _make_or_update_tiles_from_cache(
            DISCOVERY_NODEGROUP,
            {NODE_DISCOVERY_METHOD: {"incoming": "Dynamics value"}},
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )

        self.assertEqual(
            self.unmanaged_tile.data,
            {
                NODE_ARTEFACT_NAME: {"en": {"value": "Never touch me"}},
                UNMANAGED_NODE: {"en": {"value": "Keep me too"}},
            },
        )