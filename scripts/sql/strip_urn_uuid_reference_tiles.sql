-- Strip the `urn:uuid:` prefix from reference-datatype tile URIs so they match
-- arches_controlled_lists_listitem.uri (bare UUID) and advanced search returns hits.
--
-- Tile value shape:  tiles.tiledata -> '<nodeid>'  ==  [ {"uri": "...", "labels": [...], "list_id": "..."}, ... ]
-- After running this you MUST reindex (reindex faithfully re-stores tile data into ES).
--
-- Both sections join tiles to nodes on nodegroupid. A tile's tiledata only ever
-- contains nodes from its own nodegroup, so without that equality predicate the
-- planner has no indexable join and falls back to scanning every tile once per
-- reference node (~2.4M tiles x N nodes on dev — minutes to hours).
--
-- NOTE: running this file with `psql -f` executes straight through to COMMIT.
-- Use `psql -s -f` (single-step) if you want to inspect section 3 and decide.

----------------------------------------------------------------------
-- 1. DRY RUN — how many tiles/values are affected, before touching anything
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

----------------------------------------------------------------------
-- 2. FIX — strip urn:uuid: from every reference node's tile URIs.
----------------------------------------------------------------------
BEGIN;

DO $$
DECLARE
    ref record;
BEGIN
    FOR ref IN
        SELECT nodeid, nodegroupid FROM nodes
        WHERE datatype = 'reference' AND nodegroupid IS NOT NULL
    LOOP
        UPDATE tiles t
        SET tiledata = jsonb_set(
            t.tiledata,
            ARRAY[ref.nodeid::text],
            (
                SELECT jsonb_agg(
                    CASE
                        WHEN e->>'uri' LIKE 'urn:uuid:%'
                        THEN jsonb_set(e, '{uri}',
                                       to_jsonb(regexp_replace(e->>'uri', '^urn:uuid:', '')))
                        ELSE e
                    END
                    ORDER BY ord
                )
                FROM jsonb_array_elements(t.tiledata -> ref.nodeid::text)
                     WITH ORDINALITY AS arr(e, ord)
            )
        )
        WHERE t.nodegroupid = ref.nodegroupid
          AND jsonb_typeof(t.tiledata -> ref.nodeid::text) = 'array'
          AND EXISTS (
              SELECT 1
              FROM jsonb_array_elements(t.tiledata -> ref.nodeid::text) x
              WHERE x->>'uri' LIKE 'urn:uuid:%'
          );
    END LOOP;
END $$;

----------------------------------------------------------------------
-- 3. VERIFY — same query as section 1, still inside the transaction.
--    Expect zero rows. Under `psql -s` you can cancel before the COMMIT below.
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

COMMIT;
