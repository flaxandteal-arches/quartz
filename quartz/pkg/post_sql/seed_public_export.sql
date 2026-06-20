-- =====================================================================
-- Public Export: service group, login-disabled user, and the nodegroup
-- read-permission whitelist that mirrors quartz-starches/prebuild/
-- permissions.json.
--
-- WHY post_sql: load_package runs load_sql(..., "post_sql") AFTER
-- load_graphs, in the same invocation, so every nodegroup exists and the
-- alias -> nodegroup_id join below resolves. This supersedes:
--   * migration 0010_seed_public_export_group_and_user (group/user existence)
--   * the post-load `manage.py sync_public_export_group` step (perms)
-- Both are folded into this one correctly-timed, self-contained hook.
--
-- IDEMPOTENT: load_sql re-runs this on EVERY load_package and swallows
-- errors silently, so every statement is re-runnable (ON CONFLICT / delete-
-- then-insert) and the whole file executes as one transaction.
--
-- DEFAULT-ALLOW for nodegroups: a nodegroup with no object permission is
-- readable by default (arches_permission_base.get_nodegroups_by_perm_for_
-- user_or_group). So this group is only restrictive if we EXPLICITLY deny
-- (no_access_to_nodegroup) every covered nodegroup that is not whitelisted.
--
-- SOURCE OF TRUTH is permissions.json. The VALUES lists below were generated
-- from it; if it changes, regenerate them (or run `manage.py
-- sync_public_export_group`, which reads permissions.json directly). Graph
-- keys map to graph names by inserting a space before internal capitals
-- (HeritageItem -> "Heritage Item"); "Licence" is kept verbatim.
-- =====================================================================

-- 1. Group ------------------------------------------------------------
INSERT INTO auth_group (name)
VALUES ('Public Export')
ON CONFLICT (name) DO NOTHING;

-- 2. Login-disabled service account (unusable password '!', not staff/super).
--    ON CONFLICT keeps an existing account's credentials untouched.
INSERT INTO auth_user (
    username, password, is_superuser, is_staff, is_active,
    first_name, last_name, email, date_joined
)
VALUES ('public_export', '!', false, false, true, '', '', '', now())
ON CONFLICT (username) DO NOTHING;

-- 3. Membership (single-group is enforced elsewhere; .add-style idempotent) -
INSERT INTO auth_user_groups (user_id, group_id)
SELECT u.id, g.id
FROM auth_user u, auth_group g
WHERE u.username = 'public_export' AND g.name = 'Public Export'
ON CONFLICT (user_id, group_id) DO NOTHING;

-- 4. Resolve every covered nodegroup to a read/deny decision -----------
DROP TABLE IF EXISTS _pe_decided;
CREATE TEMP TABLE _pe_decided AS
WITH covered(gname) AS (VALUES
    ('Bibliographic Source'),
    ('Archive Source'),
    ('Action'),
    ('Heritage Item'),
    ('Heritage Place'),
    ('Maritime Vessel'),
    ('Registry'),
    ('Activity'),
    ('Person'),
    ('Period'),
    ('Organization'),
    ('Licence'),
    ('Digital Object')
),
read_all(gname) AS (VALUES
    ('Bibliographic Source'),
    ('Archive Source'),
    ('Action')
),
read_root(gname) AS (VALUES
    ('Heritage Item'),
    ('Heritage Place'),
    ('Maritime Vessel'),
    ('Registry'),
    ('Activity'),
    ('Digital Object')
),
read_alias(gname, alias) AS (VALUES
    ('Heritage Item','addresses'),
    ('Heritage Item','construction_phases'),
    ('Heritage Item','current_base_map'),
    ('Heritage Item','descriptions'),
    ('Heritage Item','designation_and_protection_assignment'),
    ('Heritage Item','designation_and_protection_timespan'),
    ('Heritage Item','external_cross_references'),
    ('Heritage Item','geometry'),
    ('Heritage Item','coordinate_system'),
    ('Heritage Item','spatial_accuracy_qualifier'),
    ('Heritage Item','capture_scale'),
    ('Heritage Item','images'),
    ('Heritage Item','localities_administrative_areas'),
    ('Heritage Item','location_data'),
    ('Heritage Item','lot_on_plan'),
    ('Heritage Item','area_assignments'),
    ('Heritage Item','area_assignment'),
    ('Heritage Item','monument_names'),
    ('Heritage Item','monument_type'),
    ('Heritage Item','national_grid_references'),
    ('Heritage Item','system_reference_numbers'),
    ('Heritage Item','use_phase'),
    ('Heritage Item','associated_actors'),
    ('Heritage Place','addresses'),
    ('Heritage Place','construction_phases'),
    ('Heritage Place','current_base_map'),
    ('Heritage Place','descriptions'),
    ('Heritage Place','designation_and_protection_assignment'),
    ('Heritage Place','designation_and_protection_timespan'),
    ('Heritage Place','external_cross_references'),
    ('Heritage Place','geometry'),
    ('Heritage Place','coordinate_system'),
    ('Heritage Place','spatial_accuracy_qualifier'),
    ('Heritage Place','capture_scale'),
    ('Heritage Place','images'),
    ('Heritage Place','localities_administrative_areas'),
    ('Heritage Place','location_data'),
    ('Heritage Place','lot_on_plan'),
    ('Heritage Place','area_assignments'),
    ('Heritage Place','area_assignment'),
    ('Heritage Place','monument_names'),
    ('Heritage Place','monument_type'),
    ('Heritage Place','national_grid_references'),
    ('Heritage Place','system_reference_numbers'),
    ('Heritage Place','use_phase'),
    ('Heritage Place','associated_actors'),
    ('Maritime Vessel','names'),
    ('Maritime Vessel','descriptions'),
    ('Maritime Vessel','use_phase'),
    ('Maritime Vessel','construction_phases'),
    ('Maritime Vessel','national_grid_references'),
    ('Maritime Vessel','localities_administrative_areas'),
    ('Maritime Vessel','current_base_map'),
    ('Maritime Vessel','record_and_registry_membership'),
    ('Maritime Vessel','location_data'),
    ('Maritime Vessel','spatial_metadata_descriptions'),
    ('Maritime Vessel','geometry'),
    ('Registry','names'),
    ('Registry','descriptions'),
    ('Registry','associated_actors'),
    ('Activity','geometry'),
    ('Activity','activity_names'),
    ('Activity','activity_descriptions'),
    ('Activity','associated_license'),
    ('Licence','licence_number'),
    ('Licence','report'),
    ('Digital Object','names'),
    ('Digital Object','descriptions'),
    ('Digital Object','file_content'),
    ('Digital Object','file_format_type'),
    ('Digital Object','copyright'),
    ('Digital Object','creation'),
    ('Digital Object','external_cross_references'),
    ('Digital Object','resource_model_type')
),
-- Every card grouping node (nodeid = nodegroupid) of the published resource
-- models named in `covered`. Drafts/branches are excluded.
grouping_nodes AS (
    SELECT n.nodegroupid::text AS object_pk,
           n.alias,
           n.istopnode,
           (g.name->>'en') AS gname
    FROM nodes n
    JOIN graphs g ON g.graphid = n.graphid
    WHERE n.nodeid = n.nodegroupid
      AND n.source_identifier IS NULL
      AND g.source_identifier IS NULL
      AND g.isresource = true
      AND (g.name->>'en') IN (SELECT gname FROM covered)
)
SELECT gn.object_pk,
       CASE
           WHEN gn.gname IN (SELECT gname FROM read_all) THEN 'read_nodegroup'
           WHEN gn.istopnode AND gn.gname IN (SELECT gname FROM read_root)
               THEN 'read_nodegroup'
           WHEN EXISTS (
               SELECT 1 FROM read_alias ra
               WHERE ra.gname = gn.gname AND ra.alias = gn.alias
           ) THEN 'read_nodegroup'
           ELSE 'no_access_to_nodegroup'
       END AS codename
FROM grouping_nodes gn;

-- 5. Replace this group's perms on the covered nodegroups (delete-then-insert
--    so the whitelist is authoritative and re-runs cleanly).
DELETE FROM guardian_groupobjectpermission gop
USING auth_group g, django_content_type ct
WHERE gop.group_id = g.id
  AND gop.content_type_id = ct.id
  AND g.name = 'Public Export'
  AND ct.app_label = 'models' AND ct.model = 'nodegroup'
  AND gop.object_pk IN (SELECT object_pk FROM _pe_decided);

INSERT INTO guardian_groupobjectpermission (object_pk, content_type_id, group_id, permission_id)
SELECT d.object_pk, ct.id, g.id, p.id
FROM _pe_decided d
JOIN auth_group g ON g.name = 'Public Export'
JOIN django_content_type ct ON ct.app_label = 'models' AND ct.model = 'nodegroup'
JOIN auth_permission p ON p.content_type_id = ct.id AND p.codename = d.codename;

DROP TABLE IF EXISTS _pe_decided;
