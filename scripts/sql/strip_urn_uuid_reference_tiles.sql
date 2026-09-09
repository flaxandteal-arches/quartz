-- Strip the `urn:uuid:` prefix from reference-datatype tile URIs so they match
-- arches_controlled_lists_listitem.uri (bare UUID) and advanced search returns hits.
--
-- Tile value shape:  tiles.tiledata -> '<nodeid>'  ==  [ {"uri": "...", "labels": [...], "list_id": "..."}, ... ]
-- After running this you MUST reindex (reindex faithfully re-stores tile data into ES).
--
----------------------------------------------------------------------
-- WHY THIS SCRIPT LOOKS LIKE THIS (read before "simplifying" it)
----------------------------------------------------------------------
-- The previous version did the whole rewrite in ONE transaction. That hangs
-- forever on any environment with active spatial views. On fat-qtz-stg it ran
-- 90 minutes on COMMIT with no measurable progress and had to be cancelled.
--
-- Cause: tiles carries
--     __arches_trg_update_spatial_attributes
--     AFTER INSERT OR DELETE OR UPDATE ... DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
-- Deferred means it does NOT fire per statement -- it fires once per updated row
-- at COMMIT. ~1.75M tiles here (53.8% of 3.26M contain 'urn:uuid:'), so COMMIT
-- had 1.75M invocations queued. Each one loops `spatial_views where isactive`
-- and, per match, runs a dynamic INSERT..SELECT joining resource_instances ->
-- geojson_geometries -> one LEFT JOIN tiles per attribute nodegroup, aggregating
-- over everything and then filtering to a single resource with HAVING.
-- Measured: ~1GB temp spill per invocation, 44GB cumulative.
--
-- So: suppress the trigger and do the bulk rewrite. No rebuild is needed
-- afterwards -- see "WHY THERE IS NO SPATIAL VIEW REBUILD" below.
--
-- Why this completed on fat-qtz-dev but not stg: dev has 0 active spatial_views
-- (10 defined, none active), stg has 4. With none active the trigger's loop body
-- never executes and each invocation returns immediately. Table sizes are
-- comparable and do NOT explain the difference. dev is not a valid rehearsal for
-- this script -- check `select count(*) from spatial_views where isactive` first.
--
----------------------------------------------------------------------
-- HOW TO RUN IT -- detached, inside the postgres pod
----------------------------------------------------------------------
-- psql sessions reach the DB through the Istio sidecar (pg_stat_activity shows
-- client_addr 127.0.0.6). A long silent statement sends no bytes and Envoy cuts
-- the connection at ~1h idle: "server closed the connection unexpectedly".
-- The backend keeps running regardless, so you lose visibility, not the work.
-- Run it detached inside the pod and poll the log instead:
--
--   kubectl -n <ns> cp strip_urn_uuid_reference_tiles.sql \
--       <ns>-postgresql-0:/tmp/ -c postgresql
--   kubectl -n <ns> exec <ns>-postgresql-0 -c postgresql -- bash -c \
--       'nohup psql -U postgres -d arches -f /tmp/strip_urn_uuid_reference_tiles.sql \
--        > /tmp/urnfix.log 2>&1 &'
--   kubectl -n <ns> exec <ns>-postgresql-0 -c postgresql -- tail -f /tmp/urnfix.log
--
-- Safe to re-run: stripping an already-stripped URI is a no-op.
--
----------------------------------------------------------------------
-- WHY THERE IS NO SPATIAL VIEW REBUILD
----------------------------------------------------------------------
-- Suppressing the trigger normally leaves sp_attr_<slug> stale, and the only
-- repair Arches offers is __arches_refresh_spatial_views(), which DROPs four
-- views (<slug>_point/_linestring/_polygon/_mixed_geom) plus the sp_attr_ table
-- per active view and rebuilds them. That is the disruptive part: DROP VIEW
-- takes ACCESS EXCLUSIVE, so it queues behind any in-flight GeoServer query and
-- every later query queues behind it -- a stall for the length of the rebuild.
-- (It does NOT leave a window where the views are missing: the refresh is one
-- statement, and Postgres DDL is transactional. Readers block, they do not error.)
--
-- None of that is necessary here, because this script cannot change what the
-- spatial views show. sp_attr_ columns are filled by
-- __arches_get_node_display_value, which for datatype 'reference' calls
-- __arches_controlled_lists_get_reference_label_list. That resolves labels via
--     reference_data -> 'labels' -> 0 ->> 'list_item_id'
-- and never reads 'uri' -- the only field this script rewrites.
--
-- Verified 2026-09-09, locally, on real imported data: 131 dirty tiles across 2
-- resources, four affected nodes being heritage_item view columns (Feature Shape,
-- Capture Scale, Spatial Accuracy Qualifier, Designation or Protection Type).
-- md5 of sp_attr_heritage_item was identical before and after the strip, and a
-- Feature Shape tile still carrying 'urn:uuid:' resolved to "Centroid".
--
-- If you change this script to rewrite anything OTHER than 'uri', that reasoning
-- lapses -- re-add `SELECT __arches_refresh_spatial_views();` before the RESET.
-- Before relying on this in a new environment, confirm the label function still
-- keys off list_item_id:
--     \sf __arches_controlled_lists_get_reference_label_list

\set ON_ERROR_STOP on
\timing on

----------------------------------------------------------------------
-- 0. Suppress the deferred spatial trigger for THIS SESSION only.
----------------------------------------------------------------------
-- Both triggers on tiles are tgenabled='O' (origin); in replica mode only
-- 'R'/'A' triggers fire, so no spatial events are queued.
--
-- This also suppresses the FK constraint triggers. Safe HERE because the update
-- below only rewrites the tiledata jsonb -- it never touches resourceinstanceid,
-- nodegroupid or parenttileid. Do not copy this into a script that changes FK
-- columns.
--
-- Preferred over `ALTER TABLE tiles DISABLE TRIGGER ...`, which needs an
-- ACCESS EXCLUSIVE lock on tiles, applies to every session, and leaves the
-- trigger disabled cluster-wide if this script dies halfway.
SET session_replication_role = replica;

----------------------------------------------------------------------
-- 1. Build the work list ONCE.
----------------------------------------------------------------------
-- Re-deriving the predicate per batch would re-scan 3.2M tiles every iteration
-- (O(n^2)). The nodegroupid equality is what makes this join indexable -- a
-- tile's tiledata only ever contains nodes from its own nodegroup, so without it
-- the planner scans every tile once per reference node.
DROP TABLE IF EXISTS urn_fix_queue;
CREATE UNLOGGED TABLE urn_fix_queue AS
SELECT DISTINCT t.tileid
FROM nodes n
JOIN tiles t ON t.nodegroupid = n.nodegroupid
CROSS JOIN LATERAL jsonb_array_elements(t.tiledata -> n.nodeid::text) AS e(value)
WHERE n.datatype = 'reference'
  AND jsonb_typeof(t.tiledata -> n.nodeid::text) = 'array'
  AND e.value->>'uri' LIKE 'urn:uuid:%';

ALTER TABLE urn_fix_queue ADD PRIMARY KEY (tileid);

-- Only reference-datatype keys get rewritten. Without this the rewrite would
-- strip 'urn:uuid:' from any array-of-objects value carrying a "uri" key,
-- whatever its datatype.
DROP TABLE IF EXISTS urn_fix_refnodes;
CREATE UNLOGGED TABLE urn_fix_refnodes AS
SELECT nodeid::text AS nodeid FROM nodes WHERE datatype = 'reference';

ALTER TABLE urn_fix_refnodes ADD PRIMARY KEY (nodeid);

SELECT count(*) AS tiles_to_fix FROM urn_fix_queue;

----------------------------------------------------------------------
-- 2. Rewrite in committed batches.
----------------------------------------------------------------------
DO $$
DECLARE
    batch uuid[];
    done  bigint := 0;
BEGIN
    LOOP
        SELECT array_agg(tileid) INTO batch
        FROM (SELECT tileid FROM urn_fix_queue LIMIT 5000) q;

        EXIT WHEN batch IS NULL;

        UPDATE tiles t
        SET tiledata = coalesce(
            (
                SELECT jsonb_object_agg(
                    kv.key,
                    CASE
                        WHEN rn.nodeid IS NOT NULL
                             AND jsonb_typeof(kv.value) = 'array'
                        THEN (
                            -- coalesce: jsonb_agg over an empty array returns NULL
                            SELECT coalesce(
                                jsonb_agg(
                                    CASE
                                        WHEN e->>'uri' LIKE 'urn:uuid:%'
                                        THEN jsonb_set(e, '{uri}',
                                                       to_jsonb(substr(e->>'uri', 10)))
                                        ELSE e
                                    END
                                    ORDER BY ord
                                ),
                                '[]'::jsonb
                            )
                            FROM jsonb_array_elements(kv.value)
                                 WITH ORDINALITY AS a(e, ord)
                        )
                        ELSE kv.value
                    END
                )
                FROM jsonb_each(t.tiledata) kv
                LEFT JOIN urn_fix_refnodes rn ON rn.nodeid = kv.key
            ),
            t.tiledata  -- guard: jsonb_object_agg over an empty tiledata is NULL
        )
        WHERE t.tileid = ANY(batch);

        DELETE FROM urn_fix_queue WHERE tileid = ANY(batch);

        done := done + array_length(batch, 1);
        RAISE NOTICE '% tiles done', done;

        COMMIT;  -- PG11+ transaction control in DO; keeps the trigger queue empty
    END LOOP;
END $$;

DROP TABLE IF EXISTS urn_fix_queue;
DROP TABLE IF EXISTS urn_fix_refnodes;

----------------------------------------------------------------------
-- 3. VERIFY -- expect zero rows.
----------------------------------------------------------------------
SELECT n.nodeid, n.name,
       count(*) FILTER (WHERE e.value->>'uri' LIKE 'urn:uuid:%') AS urn_values,
       count(*)                                                 AS total_values
FROM nodes n
JOIN tiles t ON t.nodegroupid = n.nodegroupid
CROSS JOIN LATERAL jsonb_array_elements(t.tiledata -> n.nodeid::text) AS e(value)
WHERE n.datatype = 'reference'
  AND jsonb_typeof(t.tiledata -> n.nodeid::text) = 'array'
GROUP BY n.nodeid, n.name
HAVING count(*) FILTER (WHERE e.value->>'uri' LIKE 'urn:uuid:%') > 0
ORDER BY urn_values DESC;

RESET session_replication_role;

-- Now reindex Elasticsearch.
