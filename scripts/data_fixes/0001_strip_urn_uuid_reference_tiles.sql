-- Strip the urn:uuid: prefix from reference tile URIs so they match listitem.uri.
-- reindex-graphs: all

\set ON_ERROR_STOP on
\timing on

-- Skip the deferred spatial trigger (per-tile at COMMIT); sp_attr reads labels, not uri.
SET session_replication_role = replica;

DROP TABLE IF EXISTS urn_fix_queue;
-- nodegroupid equality makes this join indexable.
CREATE UNLOGGED TABLE urn_fix_queue AS
SELECT DISTINCT t.tileid
FROM nodes n
JOIN tiles t ON t.nodegroupid = n.nodegroupid
CROSS JOIN LATERAL jsonb_array_elements(t.tiledata -> n.nodeid::text) AS e(value)
WHERE n.datatype = 'reference'
  AND jsonb_typeof(t.tiledata -> n.nodeid::text) = 'array'
  AND e.value->>'uri' LIKE 'urn:uuid:%';

ALTER TABLE urn_fix_queue ADD PRIMARY KEY (tileid);

DROP TABLE IF EXISTS urn_fix_refnodes;
CREATE UNLOGGED TABLE urn_fix_refnodes AS
SELECT nodeid::text AS nodeid FROM nodes WHERE datatype = 'reference';

ALTER TABLE urn_fix_refnodes ADD PRIMARY KEY (nodeid);

SELECT count(*) AS tiles_to_fix FROM urn_fix_queue;

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

-- Sample check; expect mismatches = 0 and urn_under_non_reference_key = 0.
WITH sample AS (
    SELECT t.tileid, t.tiledata
    FROM tiles t JOIN urn_fix_queue q ON q.tileid = t.tileid
    LIMIT 20000
), rebuilt AS (
    SELECT s.tileid,
           s.tiledata AS old_data,
           coalesce(
               (
                   SELECT jsonb_object_agg(
                       kv.key,
                       CASE
                           WHEN rn.nodeid IS NOT NULL
                                AND jsonb_typeof(kv.value) = 'array'
                           THEN (
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
                   FROM jsonb_each(s.tiledata) kv
                   LEFT JOIN urn_fix_refnodes rn ON rn.nodeid = kv.key
               ),
               s.tiledata
           ) AS new_data
    FROM sample s
)
SELECT count(*) FILTER (
           WHERE new_data <> replace(old_data::text, 'urn:uuid:', '')::jsonb
       ) AS mismatches,
       count(*) FILTER (
           WHERE new_data = replace(old_data::text, 'urn:uuid:', '')::jsonb
       ) AS verified_lossless,
       (array_agg(tileid) FILTER (
           WHERE new_data <> replace(old_data::text, 'urn:uuid:', '')::jsonb
       ))[1:10] AS first_10_mismatching_tileids
FROM rebuilt;

SELECT count(*) AS urn_under_non_reference_key
FROM (
    SELECT t.tileid, t.tiledata
    FROM tiles t JOIN urn_fix_queue q ON q.tileid = t.tileid
    LIMIT 20000
) t
WHERE EXISTS (
    SELECT 1
    FROM jsonb_each(t.tiledata) kv
    LEFT JOIN urn_fix_refnodes rn ON rn.nodeid = kv.key
    WHERE rn.nodeid IS NULL
      AND kv.value::text LIKE '%urn:uuid:%'
);

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
