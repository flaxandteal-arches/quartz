"""Unit tests for the Heritage Item XML register export helpers.

Pure logic only (no database): value extraction, place collection and XML
building. The Public and Entered selection and the end-to-end command are
exercised against a seeded DB by hand.

Run:
    python manage.py test tests.test_public_xml_export --settings="tests.test_settings"
"""

import xml.etree.ElementTree as ET
from io import BytesIO
from types import SimpleNamespace

from django.test import SimpleTestCase

from quartz.utils.public_xml_export import (
    CRITERION_DETAILS,
    NAMESPACE,
    build_xml_tree,
    choose_names,
    clean_text,
    collect_place,
    criterion_type,
    pick_text,
    place_to_element,
    reference_labels,
    register_date,
    write_xml_tree,
)

NS = {"q": NAMESPACE}


def ref(*labels, language="en"):
    return [
        {
            "uri": "u",
            "list_id": "l",
            "labels": [
                {
                    "id": "i",
                    "value": v,
                    "language_id": language,
                    "valuetype_id": "prefLabel",
                    "list_item_id": "x",
                }
                for v in labels
            ],
        }
    ]


def text(value, language="en"):
    return {language: {"value": value, "direction": "ltr"}}


def node(nodeid, nodegroup_id):
    return SimpleNamespace(nodeid=nodeid, nodegroup_id=nodegroup_id)


def tile(nodegroup_id, data, tileid=None, parent=None):
    return SimpleNamespace(
        nodegroup_id=nodegroup_id, data=data, tileid=tileid, parenttile_id=parent
    )


NODES = {
    "primary_reference_number": node("n-reg", "g-reg"),
    "monument_name": node("n-name", "g-name"),
    "monument_name_use_type": node("n-name-use", "g-name"),
    "monument_name_currency": node("n-name-cur", "g-name"),
    "description": node("n-desc", "g-desc"),
    "description_type": node("n-desc-type", "g-desc"),
    "street_value": node("n-street", "g-addr"),
    "building_number_value": node("n-num", "g-addr"),
    "full_address": node("n-full", "g-addr"),
    "suburbs": node("n-suburb", "g-addr"),
    "locality_value": node("n-locality", "g-addr"),
    "lga": node("n-lga", "g-addr"),
    "monument_type": node("n-type", "g-type"),
    "functional_type": node("n-theme", "g-theme"),
    "designation_or_protection_type": node("n-status", "g-desig"),
    "designation_start_date": node("n-start", "g-desig"),
    "local_heritage_list_criteria_type": node("n-crit", "g-desig"),
    "designation_description": node("n-sos", "g-sos"),
}


class ValueExtractionTests(SimpleTestCase):
    def test_pick_text_prefers_language_then_first(self):
        self.assertEqual(pick_text(text("Hi")), "Hi")
        self.assertEqual(pick_text({"fr": {"value": "Salut"}}), "Salut")
        self.assertEqual(
            pick_text({"en": {"value": "Hi"}, "fr": {"value": "Salut"}}, "fr"),
            "Salut",
        )

    def test_pick_text_handles_numbers_and_empty(self):
        self.assertEqual(pick_text(600001), "600001")
        self.assertEqual(pick_text(600001.0), "600001")
        self.assertIsNone(pick_text(None))
        self.assertIsNone(pick_text(text("   ")))

    def test_clean_text_strips_xml_illegal_characters(self):
        self.assertEqual(clean_text(" a\x00b\x0bc "), "abc")

    def test_reference_labels(self):
        self.assertEqual(reference_labels(ref("Hangar")), ["Hangar"])
        self.assertEqual(reference_labels(None), [])
        self.assertEqual(reference_labels("junk"), [])
        self.assertEqual(reference_labels(ref("Salut", language="fr")), ["Salut"])

    def test_register_date_uses_the_register_file_format(self):
        self.assertEqual(register_date("2010-10-08"), "2010-10-08 00:00:00")
        self.assertEqual(
            register_date("2010-10-08T00:00:00.000Z"), "2010-10-08 00:00:00"
        )
        self.assertIsNone(register_date(None))
        self.assertIsNone(register_date("not a date"))

    def test_criterion_type_and_wording_cover_a_to_h(self):
        self.assertEqual(criterion_type("A"), "Criterion A")
        self.assertEqual(criterion_type("Protected Area"), "Protected Area")
        self.assertEqual(
            sorted(CRITERION_DETAILS), [f"Criterion {c}" for c in "ABCDEFGH"]
        )


class NameTests(SimpleTestCase):
    def test_register_name_prefers_use_type_then_current(self):
        names = [
            ("Old Name", "Former", "Former"),
            ("Registered Name", "Registered", "Current"),
            ("Primary Name", "Primary", "Current"),
        ]
        primary, alternates = choose_names(names)
        self.assertEqual(primary, "Registered Name")
        self.assertEqual(alternates, ["Old Name", "Primary Name"])

    def test_unmarked_names_fall_back_to_current_then_alphabetical(self):
        primary, alternates = choose_names(
            [("B", None, "Former"), ("C", None, "Current"), ("A", None, "Current")]
        )
        self.assertEqual((primary, alternates), ("A", ["B", "C"]))

    def test_no_names_and_duplicate_alternates(self):
        self.assertEqual(choose_names([]), (None, []))
        self.assertEqual(
            choose_names([("X", "Primary", None), ("X", "Alternative", None)]),
            ("X", []),
        )


class CollectAndBuildTests(SimpleTestCase):
    def tiles(self):
        return [
            tile("g-reg", {"n-reg": 602764}),
            tile(
                "g-name",
                {
                    "n-name": text("Kingaroy Peanut Silos"),
                    "n-name-use": ref("Registered"),
                    "n-name-cur": ref("Current"),
                },
            ),
            tile(
                "g-name",
                {"n-name": text("Peanut Silos"), "n-name-use": ref("Alternative")},
            ),
            tile(
                "g-desc",
                {"n-desc": text("<p>Desc</p>"), "n-desc-type": ref("Description")},
            ),
            tile(
                "g-desc", {"n-desc": text("<p>Hist</p>"), "n-desc-type": ref("History")}
            ),
            tile(
                "g-desc",
                {"n-desc": text("<p>Skipped</p>"), "n-desc-type": ref("Abstract")},
            ),
            tile(
                "g-addr",
                {
                    "n-num": text("117-131"),
                    "n-street": text("Haly Street"),
                    "n-suburb": ref("KINGAROY"),
                    "n-lga": ref("SOUTH BURNETT REGIONAL COUNCIL"),
                },
            ),
            tile("g-type", {"n-type": ref("Silo")}),
            tile("g-type", {"n-type": ref("Silo")}),
            tile("g-theme", {"n-theme": ref("05 Developing economies")}),
            tile(
                "g-desig",
                {"n-status": ref("Entered"), "n-start": "2010-10-08"},
                tileid="t-entered",
            ),
            tile("g-desig", {"n-crit": ref("D")}, tileid="t-d"),
            tile("g-desig", {"n-crit": ref("A")}, tileid="t-a"),
            tile("g-sos", {"n-sos": text("<p>A statement</p>")}, parent="t-a"),
            tile("g-sos", {"n-sos": text("<p>D statement</p>")}, parent="t-d"),
            tile("g-other", {"n-x": "ignored"}),
        ]

    def test_collect_place(self):
        place = collect_place(self.tiles(), NODES)
        self.assertEqual(place["register_id"], "602764")
        self.assertEqual(place["name"], "Kingaroy Peanut Silos")
        self.assertEqual(place["alternate_names"], ["Peanut Silos"])
        self.assertEqual(place["description"], "<p>Desc</p>")
        self.assertEqual(place["history"], "<p>Hist</p>")
        self.assertEqual(place["street_address"], "117-131 Haly Street")
        self.assertEqual(place["suburbs"], ["KINGAROY"])
        self.assertEqual(place["lgas"], ["SOUTH BURNETT REGIONAL COUNCIL"])
        self.assertEqual(place["register_entry_date"], "2010-10-08 00:00:00")
        self.assertEqual(place["place_types"], ["Silo"])  # de-duplicated
        self.assertEqual(place["themes"], ["05 Developing economies"])

    def test_each_criterion_gets_its_own_statement_via_the_parent_tile(self):
        place = collect_place(self.tiles(), NODES)
        self.assertEqual(
            place["criteria"],
            [("A", "<p>A statement</p>"), ("D", "<p>D statement</p>")],
        )

    def test_statement_without_a_parent_criterion_is_not_attached(self):
        tiles = self.tiles() + [tile("g-sos", {"n-sos": text("orphan")}, parent="nope")]
        statements = [s for _, s in collect_place(tiles, NODES)["criteria"]]
        self.assertNotIn("orphan", statements)

    def test_only_the_entered_date_is_the_register_entry_date(self):
        tiles = [
            tile(
                "g-desig",
                {"n-status": ref("Removed"), "n-start": "2020-01-01"},
                tileid="t1",
            ),
            tile(
                "g-desig",
                {"n-status": ref("Entered"), "n-start": "2010-10-08"},
                tileid="t2",
            ),
        ]
        self.assertEqual(
            collect_place(tiles, NODES)["register_entry_date"], "2010-10-08 00:00:00"
        )

    def test_address_falls_back_to_full_address_and_locality(self):
        tiles = [
            tile("g-addr", {"n-full": text("1 Main St"), "n-locality": text("TOWN")})
        ]
        place = collect_place(tiles, NODES)
        self.assertEqual(place["street_address"], "1 Main St")
        self.assertEqual(place["suburbs"], ["TOWN"])

    def test_missing_node_leaves_field_empty(self):
        nodes = {k: v for k, v in NODES.items() if k != "lga"}
        self.assertEqual(collect_place(self.tiles(), nodes)["lgas"], [])

    def test_element_order_matches_the_register_file(self):
        el = place_to_element(collect_place(self.tiles(), NODES))
        tags = [c.tag.replace("{%s}" % NAMESPACE, "") for c in el]
        self.assertEqual(
            tags,
            [
                "place_ref",
                "name",
                "description",
                "history",
                "street_address",
                "suburb",
                "lga",
                "register_entry_date",
                "alternate_name",
                "place_type",
                "thematic_framework",
                "criterion",
                "criterion",
            ],
        )
        self.assertEqual(el.get("type"), "State Heritage")

    def test_criterion_element_has_type_detail_and_statement(self):
        el = place_to_element(collect_place(self.tiles(), NODES))
        criterion = el.findall("q:criterion", NS)[0]
        self.assertEqual(criterion.get("type"), "Criterion A")
        self.assertEqual(criterion.get("detail"), CRITERION_DETAILS["Criterion A"])
        self.assertEqual(criterion.text, "<p>A statement</p>")

    def test_empty_optional_elements_are_omitted(self):
        el = place_to_element(collect_place([tile("g-reg", {"n-reg": 5})], NODES))
        self.assertEqual([c.tag.split("}")[1] for c in el], ["place_ref"])

    def test_tree_is_namespaced_sorted_numerically_and_round_trips(self):
        def place(ref_id):
            return place_to_element(
                collect_place([tile("g-reg", {"n-reg": ref_id})], NODES)
            )

        tree = build_xml_tree(
            [(place(10), "10", "c"), (place(9), "9", "a"), (place(None), None, "b")]
        )
        buffer = BytesIO()
        write_xml_tree(tree, buffer)
        raw = buffer.getvalue().decode("utf-8")
        self.assertIn(f'<heritage_places xmlns="{NAMESPACE}">', raw)
        root = ET.fromstring(raw)
        self.assertEqual(root.tag, "{%s}heritage_places" % NAMESPACE)
        refs = [p.findtext("q:place_ref", namespaces=NS) for p in root]
        self.assertEqual(refs, ["9", "10", None])
        # Text is escaped HTML, as in the register file.
        el = place_to_element(collect_place(self.tiles(), NODES))
        buffer = BytesIO()
        write_xml_tree(build_xml_tree([(el, "602764", "x")]), buffer)
        self.assertIn("&lt;p&gt;Desc&lt;/p&gt;", buffer.getvalue().decode("utf-8"))
