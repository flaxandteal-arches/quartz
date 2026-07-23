-- Strip the `urn:uuid:` prefix from reference-datatype tile URIs so they match
-- arches_controlled_lists_listitem.uri (bare UUID) and advanced search returns hits.
--
-- Tile value shape:  tiles.tiledata -> '<nodeid>'  ==  [ {"uri": "...", "labels": [...], "list_id": "..."}, ... ]
-- After running this you MUST reindex (reindex faithfully re-stores tile data into ES).

----------------------------------------------------------------------
-- 1. DRY RUN — how many tiles/values are affected, before touching anything
----------------------------------------------------------------------
SELECT n.nodeid, n.name,
       count(*) FILTER (WHERE e.value->>'uri' LIKE 'urn:uuid:%') AS urn_values,
       count(*)                                                 AS total_values
FROM tiles t
JOIN nodes n ON n.datatype = 'reference'
             AND jsonb_typeof(t.tiledata -> n.nodeid::text) = 'array'
CROSS JOIN LATERAL jsonb_array_elements(t.tiledata -> n.nodeid::text) AS e(value)
GROUP BY n.nodeid, n.name
HAVING count(*) FILTER (WHERE e.value->>'uri' LIKE 'urn:uuid:%') > 0
ORDER BY urn_values DESC;

----------------------------------------------------------------------
-- 2. FIX — strip urn:uuid: from every reference node's tile URIs.
--    Wrap in a transaction; run the dry run again inside it to confirm 0 remain
--    before COMMIT.
----------------------------------------------------------------------
BEGIN;

DO $$
DECLARE
    ref_node uuid;
BEGIN
    FOR ref_node IN SELECT nodeid FROM nodes WHERE datatype = 'reference'
    LOOP
        UPDATE tiles t
        SET tiledata = jsonb_set(
            t.tiledata,
            ARRAY[ref_node::text],
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
                FROM jsonb_array_elements(t.tiledata -> ref_node::text)
                     WITH ORDINALITY AS arr(e, ord)
            )
        )
        WHERE jsonb_typeof(t.tiledata -> ref_node::text) = 'array'
          AND EXISTS (
              SELECT 1
              FROM jsonb_array_elements(t.tiledata -> ref_node::text) x
              WHERE x->>'uri' LIKE 'urn:uuid:%'
          );
    END LOOP;
END $$;

-- re-run section 1's query here; expect zero rows, then:
COMMIT;
