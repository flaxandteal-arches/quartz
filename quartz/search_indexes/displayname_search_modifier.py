from arches.app.search.es_mapping_modifier import EsMappingModifier

_CONDITION_REPORT_GRAPH_ID = "9fccd932-8e8f-4595-89bd-3cb04ddfecae"
# Nodegroup that drives the descriptor - users who can read the resource have access to it
_DESCRIPTOR_NODEGROUP_ID = "77cef118-454b-46e8-98a1-ab72095b3e3c"

class DisplaynameSearchModifier(EsMappingModifier):
    """
    Injects the computed displayname into the 'strings' search index so that
    term searches (e.g. by linked Heritage Item reference number) can find
    Condition Reports even though the value is not stored in any tile directly.
    """

    @staticmethod
    def add_search_terms(resourceinstance, document, terms):
        if str(resourceinstance.graph_id) != _CONDITION_REPORT_GRAPH_ID:
            return
        for dn in document.get("displayname", []):
            value = (dn.get("value") or "").strip()
            if value and value != "Undefined":
                document["strings"].append({
                    "string": value,
                    "nodegroup_id": _DESCRIPTOR_NODEGROUP_ID,
                    "provisional": False,
                })
