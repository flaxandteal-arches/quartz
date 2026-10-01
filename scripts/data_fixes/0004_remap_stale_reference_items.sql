-- Remap reference values whose item isn't in the node's list, by prefLabel.
-- Run after 0002 and 0003.
-- reindex-graphs: all

\set ON_ERROR_STOP on
\timing on

-- 0. Skip the deferred spatial trigger (per-tile at COMMIT); section 4 does its work.
SET session_replication_role = replica;

-- 1. Find stale values ONCE.
CREATE TEMP TABLE ref_remap_valid AS
SELECT DISTINCT list_id, uri FROM arches_controlled_lists_listitem;
ALTER TABLE ref_remap_valid ADD PRIMARY KEY (list_id, uri);

-- nodegroupid equality makes this join indexable.
CREATE TEMP TABLE ref_remap_stale AS
SELECT t.tileid, t.resourceinstanceid, n.nodeid::text AS nodeid,
       (n.config->>'controlledList')::uuid AS list_id,
       e.value AS old_value
FROM nodes n
JOIN tiles t ON t.nodegroupid = n.nodegroupid
CROSS JOIN LATERAL jsonb_array_elements(t.tiledata -> n.nodeid::text) AS e(value)
WHERE n.datatype = 'reference'
  AND n.config->>'controlledList' IS NOT NULL
  AND jsonb_typeof(t.tiledata -> n.nodeid::text) = 'array'
  AND NOT EXISTS (
      SELECT 1 FROM ref_remap_valid v
      WHERE v.list_id = (n.config->>'controlledList')::uuid
        AND v.uri = regexp_replace(e.value->>'uri', '^urn:uuid:', '')
  );

-- Labels renamed between lists; a stale value matches its own label or the alias.
CREATE TEMP TABLE ref_remap_aliases (old_label text PRIMARY KEY, new_label text NOT NULL);
INSERT INTO ref_remap_aliases VALUES ('Aerial Photography', 'Aerial and Satellite Photography');

CREATE TEMP TABLE ref_remap_candidates AS
WITH keys AS (
    SELECT DISTINCT nodeid, list_id, old_value FROM ref_remap_stale
)
SELECT k.nodeid, k.old_value, k.old_value->>'uri' AS old_uri,
       array_agg(DISTINCT i.id) FILTER (WHERE i.id IS NOT NULL) AS item_ids
FROM keys k
LEFT JOIN LATERAL jsonb_array_elements(k.old_value->'labels') l(label)
       ON l.label->>'valuetype_id' = 'prefLabel'
LEFT JOIN ref_remap_aliases a ON a.old_label = l.label->>'value'
LEFT JOIN arches_controlled_lists_listitemvalue lv
       ON lv.valuetype_id = 'prefLabel'
      AND lv.value IN (l.label->>'value', a.new_label)
      AND lv.languageid = l.label->>'language_id'
LEFT JOIN arches_controlled_lists_listitem i
       ON i.id = lv.list_item_id AND i.list_id = k.list_id
GROUP BY k.nodeid, k.old_value;

-- One stale uri whose labels disagree on the target is ambiguous: excluded.
CREATE TEMP TABLE ref_remap_map AS
SELECT c.nodeid, c.old_uri,
       jsonb_build_object(
           'uri', i.uri,
           'list_id', i.list_id::text,
           'labels', (
               SELECT jsonb_agg(jsonb_build_object(
                          'id', v.id::text,
                          'value', v.value,
                          'language_id', v.languageid,
                          'list_item_id', v.list_item_id::text,
                          'valuetype_id', v.valuetype_id)
                      ORDER BY v.valuetype_id, v.languageid)
               FROM arches_controlled_lists_listitemvalue v
               JOIN d_value_types d ON d.valuetype = v.valuetype_id AND d.category = 'label'
               WHERE v.list_item_id = i.id
           )
       ) AS new_value
FROM (
    SELECT nodeid, old_uri, min(item_ids[1]::text)::uuid AS item_id
    FROM ref_remap_candidates
    GROUP BY nodeid, old_uri
    HAVING bool_and(cardinality(item_ids) = 1)
       AND count(DISTINCT item_ids[1]) = 1
) c
JOIN arches_controlled_lists_listitem i ON i.id = c.item_id;
ALTER TABLE ref_remap_map ADD PRIMARY KEY (nodeid, old_uri);

CREATE TEMP TABLE ref_remap_nodes AS SELECT DISTINCT nodeid FROM ref_remap_map;
ALTER TABLE ref_remap_nodes ADD PRIMARY KEY (nodeid);

CREATE TEMP TABLE ref_remap_queue AS
SELECT DISTINCT s.tileid, s.resourceinstanceid
FROM ref_remap_stale s
JOIN ref_remap_map m ON m.nodeid = s.nodeid AND m.old_uri = s.old_value->>'uri';
ALTER TABLE ref_remap_queue ADD PRIMARY KEY (tileid);

SELECT g.name->>'en' AS graph, n.name AS node,
       count(*) AS stale_values,
       count(*) FILTER (WHERE m.nodeid IS NOT NULL) AS remappable,
       count(*) FILTER (WHERE m.nodeid IS NULL AND cardinality(c.item_ids) > 1) AS ambiguous,
       count(*) FILTER (WHERE m.nodeid IS NULL AND coalesce(cardinality(c.item_ids), 0) = 0) AS unmatched
FROM ref_remap_stale s
JOIN nodes n ON n.nodeid::text = s.nodeid
JOIN graphs g ON g.graphid = n.graphid
JOIN ref_remap_candidates c ON c.nodeid = s.nodeid AND c.old_value = s.old_value
LEFT JOIN ref_remap_map m ON m.nodeid = s.nodeid AND m.old_uri = s.old_value->>'uri'
GROUP BY 1, 2
ORDER BY 3 DESC;

SELECT n.name AS node,
       s.old_value->'labels'->0->>'value' AS old_label, s.old_value->>'uri' AS old_uri,
       m.new_value->'labels'->0->>'value' AS new_label, m.new_value->>'uri' AS new_uri,
       count(*) AS values
FROM ref_remap_stale s
JOIN nodes n ON n.nodeid::text = s.nodeid
LEFT JOIN ref_remap_map m ON m.nodeid = s.nodeid AND m.old_uri = s.old_value->>'uri'
GROUP BY 1, 2, 3, 4, 5
ORDER BY 1, 6 DESC;

SELECT count(*) AS tiles_to_rewrite, count(DISTINCT resourceinstanceid) AS resources
FROM ref_remap_queue;

CREATE FUNCTION pg_temp.ref_remap(tiledata jsonb) RETURNS jsonb
LANGUAGE sql STABLE AS $$
    SELECT coalesce(
        (
            SELECT jsonb_object_agg(
                kv.key,
                CASE
                    WHEN rn.nodeid IS NOT NULL AND jsonb_typeof(kv.value) = 'array'
                    THEN (
                        SELECT coalesce(jsonb_agg(coalesce(m.new_value, e) ORDER BY ord), '[]'::jsonb)
                        FROM jsonb_array_elements(kv.value) WITH ORDINALITY AS a(e, ord)
                        LEFT JOIN ref_remap_map m ON m.nodeid = kv.key AND m.old_uri = e->>'uri'
                    )
                    ELSE kv.value
                END
            )
            FROM jsonb_each(tiledata) kv
            LEFT JOIN ref_remap_nodes rn ON rn.nodeid = kv.key
        ),
        tiledata  -- jsonb_object_agg over an empty tiledata is NULL
    )
$$;

-- 1b. Sample check; expect all counts but checked_tiles to be 0.
WITH sample AS (
    SELECT t.tileid, t.tiledata AS old_data, pg_temp.ref_remap(t.tiledata) AS new_data
    FROM tiles t JOIN ref_remap_queue q ON q.tileid = t.tileid
    LIMIT 20000
)
SELECT count(*) AS checked_tiles,
       count(*) FILTER (WHERE new_data = old_data) AS unchanged_but_queued,
       count(*) FILTER (
           WHERE (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(old_data) k)
              <> (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(new_data) k)
       ) AS key_set_changed,
       count(*) FILTER (
           WHERE EXISTS (
               SELECT 1 FROM jsonb_each(old_data) kv
               WHERE kv.key NOT IN (SELECT nodeid FROM ref_remap_nodes)
                 AND kv.value IS DISTINCT FROM new_data->kv.key
           )
       ) AS other_node_changed,
       count(*) FILTER (
           WHERE EXISTS (
               SELECT 1 FROM ref_remap_nodes rn
               WHERE jsonb_typeof(old_data->rn.nodeid) = 'array'
                 AND jsonb_array_length(old_data->rn.nodeid) <> jsonb_array_length(new_data->rn.nodeid)
           )
       ) AS array_length_changed
FROM sample;

\if :{?apply}
\else
    \echo 'Dry run only -- nothing written. Re-run with -v apply=1 to apply.'
    \quit
\endif

-- 2. Section 3 drains the queue; section 4 needs the resources.
CREATE TEMP TABLE ref_remap_resources AS
SELECT DISTINCT resourceinstanceid FROM ref_remap_queue;
ALTER TABLE ref_remap_resources ADD PRIMARY KEY (resourceinstanceid);

-- 3. Rewrite in committed batches.
DO $$
DECLARE
    batch uuid[];
    done  bigint := 0;
BEGIN
    LOOP
        SELECT array_agg(tileid) INTO batch
        FROM (SELECT tileid FROM ref_remap_queue LIMIT 5000) q;

        EXIT WHEN batch IS NULL;

        UPDATE tiles t
        SET tiledata = pg_temp.ref_remap(t.tiledata)
        WHERE t.tileid = ANY(batch);

        DELETE FROM ref_remap_queue WHERE tileid = ANY(batch);

        done := done + array_length(batch, 1);
        RAISE NOTICE '% tiles done', done;

        COMMIT;
    END LOOP;
END $$;

-- 4. Recompute the affected sp_attr_<slug> columns for affected resources.
DO $$
DECLARE
    spv record;
    n   record;
    updated bigint;
BEGIN
    FOR spv IN SELECT * FROM spatial_views WHERE isactive LOOP
        FOR n IN
            SELECT nd.nodeid, nd.nodegroupid, nd.alias
            FROM jsonb_to_recordset(spv.attributenodes) AS a(nodeid uuid)
            JOIN nodes nd ON nd.nodeid = a.nodeid
            JOIN ref_remap_nodes rn ON rn.nodeid = nd.nodeid::text
        LOOP
            EXECUTE format(
                'UPDATE %I.%I s
                 SET %I = (
                     SELECT __arches_agg_get_node_display_value(DISTINCT t.tiledata, %L::uuid, %L)
                     FROM tiles t
                     WHERE t.resourceinstanceid = s.resourceinstanceid::uuid
                       AND t.nodegroupid = %L::uuid
                 )
                 WHERE s.resourceinstanceid IN (SELECT resourceinstanceid::text FROM ref_remap_resources)',
                spv.schema, 'sp_attr_' || spv.slug, __arches_slugify(n.alias),
                n.nodeid, spv.languageid, n.nodegroupid
            );
            GET DIAGNOSTICS updated = ROW_COUNT;
            RAISE NOTICE 'sp_attr_%.%: % rows', spv.slug, __arches_slugify(n.alias), updated;
        END LOOP;
    END LOOP;
END $$;

-- 5. VERIFY -- only 'ambiguous'/'unmatched' values from section 1 should remain.
SELECT g.name->>'en' AS graph, n.name AS node, count(*) AS still_stale
FROM nodes n
JOIN graphs g ON g.graphid = n.graphid
JOIN tiles t ON t.nodegroupid = n.nodegroupid
CROSS JOIN LATERAL jsonb_array_elements(t.tiledata -> n.nodeid::text) AS e(value)
WHERE n.nodeid::text IN (SELECT nodeid FROM ref_remap_nodes)
  AND jsonb_typeof(t.tiledata -> n.nodeid::text) = 'array'
  AND NOT EXISTS (
      SELECT 1 FROM ref_remap_valid v
      WHERE v.list_id = (n.config->>'controlledList')::uuid
        AND v.uri = regexp_replace(e.value->>'uri', '^urn:uuid:', '')
  )
GROUP BY 1, 2;

RESET session_replication_role;

