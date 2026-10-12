# Data fixes

One-off fixes to existing data. Put them in `data_fixes/` as numbered `.sql` or `.sh` files:

```
data_fixes/0004_describe_the_fix.sql
```

Run these commands inside the arches container.

## List what's been applied

```
python manage.py data_fixes
```

## Apply pending fixes

```
python manage.py data_fixes --apply
```

Runs pending fixes in order, then reindexes Elasticsearch and arches-search.

## Mark fixes as applied without running them

```
python manage.py data_fixes --mark-applied 0001
python manage.py data_fixes --mark-applied all
```

Use `all` on a fresh environment.

## Writing a fix

- Make it safe to run twice.
- Add `-- reindex-graphs: all` (or graph ids) if it changes resource data.

```sql
-- What this fixes.
-- reindex-graphs: all

\set ON_ERROR_STOP on

BEGIN;

UPDATE tiles
SET tiledata = ...
WHERE ...;  -- only rows that still need fixing, so a re-run does nothing

COMMIT;
```
