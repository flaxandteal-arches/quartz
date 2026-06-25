"""Tests that Archeology_Payload.json values are mapped to the correct
Arches tile nodegroups and node IDs by _build_managed_tiles.

Each tile-builder function is exercised in isolation: parse_reference_node,
make_or_update_tiles, get_or_create_person_resource_from_name,
get_or_create_digitial_object_resource_from_name, and
VersionedResource.objects.get_current_draft are all mocked so the test
requires no Arches graph fixture and no live database writes.

Run:
    python manage.py test tests.test_upsert_artefact --settings="tests.test_settings"
"""

import json
import os
import uuid
from unittest.mock import patch

from django.test import TestCase

from quartz.utils.payload_utils import make_tile
from quartz.utils.upsert_artefact import (
    _build_managed_tiles,
    ARCHAEOLOGY_STATUS_NODEGROUP,
    ARTEFACT_NAMES_NODEGROUP,
    ASSOCIATED_MONUMENTS_NODEGROUP,
    CAPTURE_SCALE_NODEGROUP,
    CONDITION_ASSESSMENT_NODEGROUP,
    COORDINATE_SYSTEM_NODEGROUP,
    DEACTIVATION_REASON_NODEGROUP,
    DESCRIPTIONS_NODEGROUP,
    DIGITAL_OBJECT_NODEGROUP,
    DISCOVERY_NODEGROUP,
    EXTERNAL_CROSS_REFS_NODEGROUP,
    GEOMETRY_NODEGROUP,
    IMPORTANT_SOURCE_NODEGROUP,
    NODE_ARCHAEOLOGY_STATUS,
    NODE_ARCHAEOLOGY_DISCOVERY_TYPE,
    NODE_ARTEFACT_NAME,
    NODE_ARTEFACT_TYPE,
    NODE_ASSOCIATED_PERSON,
    NODE_CAPTURE_SCALE,
    NODE_COORDINATE_SYSTEM,
    NODE_DATE_OF_ASSESSMENT_END,
    NODE_DATE_OF_ASSESSMENT_START,
    NODE_DEACTIVATION_REASON,
    NODE_DESCRIPTION,
    NODE_DESCRIPTION_TYPE,
    NODE_DIGITAL_OBJECT,
    NODE_DISCOVERY_METHOD,
    NODE_EXTERNAL_CROSS_REF,
    NODE_GEOSPATIAL_COORDS,
    NODE_IMPORTANT_SOURCE,
    NODE_LEGACY_ID,
    NODE_PERMISSION,
    NODE_PRIMARY_REF_NUM,
    NODE_SPATIAL_ACCURACY,
    NODE_SPATIAL_METADATA_NOTES,
    PERMISSION_NODEGROUP,
    PRODUCTION_NODEGROUP,
    SPATIAL_ACCURACY_NODEGROUP,
    SPATIAL_METADATA_DESCRIPTIONS_NODEGROUP,
    SYSTEM_REF_NODEGROUP,
    VERSION_NUMBER,
    VERSIONING_NODEGROUP,
)

_PAYLOAD_PATH = os.path.join(os.path.dirname(__file__), "..", "Archeology_Payload.json")

_FAKE_PERSON_ID = str(uuid.uuid4())
_FAKE_DO_ID = str(uuid.uuid4())


def _fake_parse_reference_node(value, list_name):
    return {"__value": value, "__list": list_name}


def _fake_make_or_update_tiles(nodegroup_id, data, parent_tile_id=None, resource_instance_ref=None):
    item = data[0] if isinstance(data, list) else data
    return [make_tile(nodegroup_id, item, parent_tile_id)]


class ArcheologyPayloadTileTest(TestCase):
    """Verify every payload field lands in the expected nodegroup and node."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open(_PAYLOAD_PATH) as f:
            cls.payload = json.load(f)

    def setUp(self):
        self.resource_id = str(uuid.uuid4())

        self._patches = [
            patch(
                "quartz.utils.upsert_artefact.parse_reference_node",
                side_effect=_fake_parse_reference_node,
            ),
            patch(
                "quartz.utils.upsert_artefact.make_or_update_tiles",
                side_effect=_fake_make_or_update_tiles,
            ),
            patch(
                "quartz.utils.upsert_artefact.get_or_create_person_resource_from_name",
                return_value=_FAKE_PERSON_ID,
            ),
            patch(
                "quartz.utils.upsert_artefact.get_or_create_digitial_object_resource_from_name",
                return_value=_FAKE_DO_ID,
            ),
            patch(
                "quartz.utils.upsert_artefact.VersionedResource.objects.get_current_draft",
                return_value=None,
            ),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(self._stop_patches)

        tiles = _build_managed_tiles(self.payload, 0, 0, self.resource_id)
        self._by_ng = {}
        for tile in tiles:
            ng = str(tile.nodegroup_id)
            self._by_ng.setdefault(ng, []).append(tile)

    def _stop_patches(self):
        for p in self._patches:
            p.stop()

    def _tile(self, nodegroup_id):
        tiles = self._by_ng.get(nodegroup_id, [])
        self.assertEqual(
            len(tiles), 1,
            f"Expected exactly 1 tile for nodegroup {nodegroup_id}, got {len(tiles)}",
        )
        return tiles[0]

    def _tiles(self, nodegroup_id):
        return self._by_ng.get(nodegroup_id, [])

    # ── System Reference Numbers ──────────────────────────────────────────────

    def test_system_ref_permit_number(self):
        self.assertEqual(self._tile(SYSTEM_REF_NODEGROUP).data[NODE_PRIMARY_REF_NUM], 710202)

    def test_system_ref_legacy_id(self):
        self.assertEqual(
            self._tile(SYSTEM_REF_NODEGROUP).data[NODE_LEGACY_ID],
            {"en": {"value": "101577", "direction": "ltr"}},
        )

    # ── Version ───────────────────────────────────────────────────────────────

    def test_version_is_0_0_for_new_resource(self):
        self.assertEqual(
            self._tile(VERSIONING_NODEGROUP).data[VERSION_NUMBER],
            {"en": {"value": "0.0", "direction": "ltr"}},
        )

    # ── Deactivation Reason ───────────────────────────────────────────────────

    def test_deactivation_reason(self):
        self.assertEqual(
            self._tile(DEACTIVATION_REASON_NODEGROUP).data[NODE_DEACTIVATION_REASON]["__value"],
            "Archived",
        )

    # ── Artefact Name ─────────────────────────────────────────────────────────

    def test_name(self):
        expected = "Copper/bronze token, basement of Liberty Hall (QHR 600583), Ipswich"
        self.assertEqual(
            self._tile(ARTEFACT_NAMES_NODEGROUP).data[NODE_ARTEFACT_NAME],
            {"en": {"value": expected, "direction": "ltr"}},
        )

    # ── External Cross Reference ──────────────────────────────────────────────

    def test_external_ref(self):
        self.assertEqual(
            self._tile(EXTERNAL_CROSS_REFS_NODEGROUP).data[NODE_EXTERNAL_CROSS_REF],
            {"en": {"value": "Some external reference number", "direction": "ltr"}},
        )

    # ── Descriptions ──────────────────────────────────────────────────────────

    def test_two_description_tiles(self):
        self.assertEqual(len(self._tiles(DESCRIPTIONS_NODEGROUP)), 2)

    def test_description_texts(self):
        texts = {
            t.data[NODE_DESCRIPTION]["en"]["value"]
            for t in self._tiles(DESCRIPTIONS_NODEGROUP)
        }
        self.assertIn("Some summary of the discovery", texts)
        self.assertIn("A response to the discovery", texts)

    def test_description_type_labels(self):
        labels = {
            t.data[NODE_DESCRIPTION_TYPE]["__value"]
            for t in self._tiles(DESCRIPTIONS_NODEGROUP)
        }
        self.assertEqual(labels, {"Summary", "Response"})

    # ── Important Source of Information ───────────────────────────────────────

    def test_important_source(self):
        self.assertEqual(
            self._tile(IMPORTANT_SOURCE_NODEGROUP).data[NODE_IMPORTANT_SOURCE]["__value"],
            "Yes",
        )

    # ── Permission to Interfere ───────────────────────────────────────────────

    def test_permission(self):
        self.assertEqual(
            self._tile(PERMISSION_NODEGROUP).data[NODE_PERMISSION]["__value"],
            "No",
        )

    # ── Production / Artefact Type ────────────────────────────────────────────

    def test_artefact_subtype(self):
        self.assertEqual(
            self._tile(PRODUCTION_NODEGROUP).data[NODE_ARTEFACT_TYPE]["__value"],
            "Archaeological Artefact or Feature",
        )

    def test_three_associated_persons(self):
        # dpp_contact + dpp_applicant + ownerid → 3 person resource instances
        persons = self._tile(PRODUCTION_NODEGROUP).data[NODE_ASSOCIATED_PERSON]
        self.assertEqual(len(persons), 3)

    def test_associated_persons_have_resource_ids(self):
        persons = self._tile(PRODUCTION_NODEGROUP).data[NODE_ASSOCIATED_PERSON]
        for person in persons:
            self.assertEqual(person["resourceId"], _FAKE_PERSON_ID)

    # ── Discovery ─────────────────────────────────────────────────────────────

    def test_discovery_context(self):
        self.assertEqual(
            self._tile(DISCOVERY_NODEGROUP).data[NODE_DISCOVERY_METHOD]["__value"],
            "Incidental Find",
        )

    def test_discovery_archaeology_type(self):
        self.assertEqual(
            self._tile(DISCOVERY_NODEGROUP).data[NODE_ARCHAEOLOGY_DISCOVERY_TYPE]["__value"],
            "Archaeological Artefact / Site",
        )

    # ── Condition Assessment (dates) ──────────────────────────────────────────

    def test_date_of_discovery(self):
        self.assertEqual(
            self._tile(CONDITION_ASSESSMENT_NODEGROUP).data[NODE_DATE_OF_ASSESSMENT_START],
            "2026-03-24",
        )

    def test_notification_date(self):
        self.assertEqual(
            self._tile(CONDITION_ASSESSMENT_NODEGROUP).data[NODE_DATE_OF_ASSESSMENT_END],
            "2026-04-22",
        )

    # ── Archaeology Status ────────────────────────────────────────────────────

    def test_archaeology_status(self):
        self.assertEqual(
            self._tile(ARCHAEOLOGY_STATUS_NODEGROUP).data[NODE_ARCHAEOLOGY_STATUS]["__value"],
            "Recorded",
        )

    # ── Digital Object (eDocs) ────────────────────────────────────────────────

    def test_digital_object_tile_has_one_reference(self):
        refs = self._tile(DIGITAL_OBJECT_NODEGROUP).data[NODE_DIGITAL_OBJECT]
        self.assertEqual(len(refs), 1)

    def test_digital_object_resource_id(self):
        ref = self._tile(DIGITAL_OBJECT_NODEGROUP).data[NODE_DIGITAL_OBJECT][0]
        self.assertEqual(ref["resourceId"], _FAKE_DO_ID)

    # ── Geometry (GPS) ────────────────────────────────────────────────────────

    def test_geometry_is_feature_collection(self):
        fc = self._tile(GEOMETRY_NODEGROUP).data[NODE_GEOSPATIAL_COORDS]
        self.assertEqual(fc["type"], "FeatureCollection")

    def test_geometry_has_one_point_feature(self):
        features = self._tile(GEOMETRY_NODEGROUP).data[NODE_GEOSPATIAL_COORDS]["features"]
        self.assertEqual(len(features), 1)
        self.assertEqual(features[0]["geometry"]["type"], "Point")

    def test_geometry_coordinates(self):
        coords = self._tile(GEOMETRY_NODEGROUP).data[NODE_GEOSPATIAL_COORDS]["features"][0][
            "geometry"
        ]["coordinates"]
        lon, lat = coords  # GeoJSON order: [lon, lat]
        self.assertAlmostEqual(lon, 153.02512345, places=5)
        self.assertAlmostEqual(lat, -27.46989921, places=5)

    # ── GPS sub-tiles ─────────────────────────────────────────────────────────

    def test_capture_scale(self):
        self.assertEqual(
            self._tile(CAPTURE_SCALE_NODEGROUP).data[NODE_CAPTURE_SCALE]["__value"],
            "Aerial Photography",
        )

    def test_spatial_accuracy(self):
        self.assertEqual(
            self._tile(SPATIAL_ACCURACY_NODEGROUP).data[NODE_SPATIAL_ACCURACY]["__value"],
            "Map",
        )

    def test_coordinate_system(self):
        self.assertEqual(
            self._tile(COORDINATE_SYSTEM_NODEGROUP).data[NODE_COORDINATE_SYSTEM]["__value"],
            "GDA2020 LAT/LONG",
        )

    def test_spatial_metadata_notes_contain_all_coordinates(self):
        notes = self._tile(SPATIAL_METADATA_DESCRIPTIONS_NODEGROUP).data[
            NODE_SPATIAL_METADATA_NOTES
        ]["en"]["value"]
        self.assertIn("Latitude: 99.000", notes)
        self.assertIn("Longitude: 22.000", notes)
        self.assertIn("Easting: 444444", notes)
        self.assertIn("Northing: 555555", notes)

    # ── No associated monuments (heritage item not found) ────────────────────

    def test_no_associated_monuments_when_heritage_item_not_in_versioned_resource(self):
        # VersionedResource.objects.get_current_draft is mocked to return None,
        # so the heritage item "600222" cannot be resolved and no tile is built.
        self.assertEqual(self._tiles(ASSOCIATED_MONUMENTS_NODEGROUP), [])
