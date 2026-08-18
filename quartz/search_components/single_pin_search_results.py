from arches.app.search.components.search_results import SearchResultsFilter

details = {
    "searchcomponentid": "",
    "name": "Search Results",
    "icon": "",
    "modulename": "single_pin_search_results.py",
    "classname": "SinglePinSearchResultsFilter",
    "type": "search-results-type",
    "componentpath": "views/components/search/search-results",
    "componentname": "search-results",
    "config": {},
}


def _pins_at_real_points(source):
    for geometry in source.get("geometries", []):
        for feature in geometry["geom"]["features"]:
            if feature["geometry"]["type"] == "Point":
                lon, lat = feature["geometry"]["coordinates"]
                yield {
                    "point": {"lon": lon, "lat": lat},
                    "nodegroup_id": geometry["nodegroup_id"],
                    "provisional": geometry["provisional"],
                }


def prune_duplicate_points(source):
    """Pin a resource at its actual point geometries rather than at the bounding-box
    centre of every geometry tile. Resources with no point geometry keep the pins
    Arches gave them, or they would vanish from the marker and cluster layers.
    """
    pins = list(_pins_at_real_points(source))
    if pins:
        source["points"] = pins


class SinglePinSearchResultsFilter(SearchResultsFilter):
    def post_search_hook(self, search_query_object, response_object, **kwargs):
        super().post_search_hook(search_query_object, response_object, **kwargs)

        for result in response_object["results"]["hits"]["hits"]:
            prune_duplicate_points(result["_source"])
