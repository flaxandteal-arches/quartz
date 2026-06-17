import logging

import requests

from arches.app.utils.search_thumbnail_fetcher import SearchThumbnailFetcher
from arches.app.utils.search_thumbnail_fetcher_factory import SearchThumbnailFetcherFactory
from arches.app.views.manifest_manager import ManifestManagerView

logger = logging.getLogger(__name__)


@SearchThumbnailFetcherFactory.register("076f9381-7b00-11e9-8d6b-80000b44d1d9")
class HeritageItemFetcher(SearchThumbnailFetcher):
    def get_thumbnail(self, retrieve=False):
        try:
            files = self.resource.get_node_values("Images")
        except Exception:
            logger.exception("get_node_values failed for resource %s", self.resource.pk)
            return None
        if not files:
            return None
        if not retrieve:
            return True
        identifier = files[0].get("name", "")
        if not identifier:
            return None
        thumbnail_url = f"{ManifestManagerView.cantaloupe_uri}/2/{identifier}/full/!200,200/0/default.jpg"
        try:
            resp = requests.get(thumbnail_url, timeout=10)
            resp.raise_for_status()
        except Exception:
            logger.exception("Failed to fetch thumbnail from Cantaloupe: %s", thumbnail_url)
            return None
        return (resp.content, "image/jpeg")
