"""Project-side overrides for arches-search / core indexing.

These are applied at import time (from QuartzConfig.ready) so we don't have to
fork the arches-search app or arches core.
"""
import copy
import logging

from arches.app.datatypes.datatypes import FileListDataType

logger = logging.getLogger(__name__)


def _patch_file_list_append_to_document():
    """Tolerate legacy file-list metadata stored as plain strings.

    Core FileListDataType.append_to_document assumes each file's
    title/description/altText/attribution is an i18n dict ({lang: {value}})
    and does `f[field].keys()`. A lot of legacy data stores those as plain
    strings, raising AttributeError — which arches-search's reindex does not
    catch, so one bad tile aborts the entire `arches_search reindex_database`.

    We wrap the call to skip the best-effort metadata full-text on malformed
    data; the FileListSearch filename/size/extension rows are built separately
    in the indexer and are unaffected.
    """
    original = FileListDataType.append_to_document
    if getattr(original, "_quartz_guarded", False):
        return

    def append_to_document(self, document, nodevalue, nodeid, tile, provisional=False):
        try:
            return original(self, document, nodevalue, nodeid, tile, provisional)
        except (AttributeError, KeyError, TypeError):
            logger.debug(
                "Skipping file-list metadata indexing for tile %s node %s "
                "(malformed i18n metadata)",
                getattr(tile, "tileid", None),
                nodeid,
            )
            return None

    append_to_document._quartz_guarded = True
    FileListDataType.append_to_document = append_to_document


def _patch_search_indexing_post_save():
    """Index from a throwaway copy of the tile.

    EDTF indexing rewrites tile.data into its ES shape, which carries a UUID
    nodegroup_id on DB-loaded tiles, so the edit log write that follows fails.
    """
    from arches_search.functions.search_indexing import SearchIndexingFunction

    original = SearchIndexingFunction.post_save
    if getattr(original, "_quartz_guarded", False):
        return

    def post_save(self, tile, *args, **kwargs):
        index_tile = copy.copy(tile)
        index_tile.data = dict(tile.data)
        return original(self, index_tile, *args, **kwargs)

    post_save._quartz_guarded = True
    SearchIndexingFunction.post_save = post_save


_patch_file_list_append_to_document()
_patch_search_indexing_post_save()
