"""
Test Heritage Officer permissions via the BlanketRoleDenyFramework.

Run: python manage.py shell < tests/scripts/test_heritage_officer_perms.py

Creates ephemeral test users, exercises every permission path, then cleans up.
"""

import sys
from django.contrib.auth.models import User, Group
from arches.app.models.models import ResourceInstance, ResourceInstanceLifecycleState
from arches.app.models.system_settings import settings as sys_settings
from quartz.permissions.blanket_roles import BlanketRoleDenyFramework

fw = BlanketRoleDenyFramework()

PASS = 0
FAIL = 0

def check(label, actual, expected):
    global PASS, FAIL
    ok = actual == expected
    mark = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{mark}] {label}: got {actual!r}, expected {expected!r}", flush=True)
    return ok


# ── Setup ──────────────────────────────────────────────────────────────────

TEST_PREFIX = "_permtest_"

def make_user(username, groups=None):
    u, _ = User.objects.get_or_create(
        username=f"{TEST_PREFIX}{username}",
        defaults={"is_active": True},
    )
    u.set_password("testpass")
    u.save()
    u.groups.clear()
    if groups:
        for g in groups:
            grp = Group.objects.get(name=g)
            u.groups.add(grp)
    return u


print("\n=== Setting up test users ===", flush=True)
officer = make_user("officer", ["Heritage Officer"])
delegate = make_user("delegate", ["Delegate"])
nobody = make_user("nobody")
print(f"  officer:  {officer.username} (groups: {[g.name for g in officer.groups.all()]})")
print(f"  delegate: {delegate.username} (groups: {[g.name for g in delegate.groups.all()]})")
print(f"  nobody:   {nobody.username} (groups: {[g.name for g in nobody.groups.all()]})")


# ── Find test resources ────────────────────────────────────────────────────

print("\n=== Finding test resources ===", flush=True)

sys_settings_id = sys_settings.SYSTEM_SETTINGS_RESOURCE_ID

lifecycle_states = ResourceInstanceLifecycleState.objects.all()
draft_state_names = {str(s.pk): s.name for s in lifecycle_states if s.name == "Draft"}
non_draft_state_names = {str(s.pk): s.name for s in lifecycle_states if s.name != "Draft"}

print(f"  Draft states: {draft_state_names}")
print(f"  Non-draft states (sample): {dict(list(non_draft_state_names.items())[:5])}")

draft_resource = (
    ResourceInstance.objects.filter(
        resource_instance_lifecycle_state_id__in=draft_state_names.keys()
    )
    .exclude(resourceinstanceid=sys_settings_id)
    .select_related("resource_instance_lifecycle_state")
    .first()
)

non_draft_resource = (
    ResourceInstance.objects.filter(
        resource_instance_lifecycle_state_id__in=non_draft_state_names.keys()
    )
    .exclude(resourceinstanceid=sys_settings_id)
    .select_related("resource_instance_lifecycle_state")
    .first()
)

sys_resource = None
if sys_settings_id:
    sys_resource = ResourceInstance.objects.filter(
        resourceinstanceid=sys_settings_id
    ).first()

if draft_resource:
    state = draft_resource.resource_instance_lifecycle_state
    print(f"  Draft resource:     {draft_resource.pk} (state: {getattr(state, 'name', '?')})")
else:
    print("  WARNING: No Draft resource found — Draft-specific tests will be skipped")

if non_draft_resource:
    state = non_draft_resource.resource_instance_lifecycle_state
    print(f"  Non-draft resource: {non_draft_resource.pk} (state: {getattr(state, 'name', '?')})")
else:
    print("  WARNING: No non-Draft resource found — non-Draft tests will be skipped")

if sys_resource:
    print(f"  System settings:    {sys_resource.pk}")
else:
    print("  WARNING: No system settings resource found")


# ── Test: Heritage Officer ─────────────────────────────────────────────────

print("\n=== Heritage Officer: view access ===", flush=True)

def check_perm(user, resource, permission):
    return fw.check_resource_instance_permissions(
        user, str(resource.pk), permission,
    )

if non_draft_resource:
    r = check_perm(officer, non_draft_resource, "view_resourceinstance")
    check("view non-Draft resource", r["permitted"], True)

if draft_resource:
    r = check_perm(officer, draft_resource, "view_resourceinstance")
    check("view Draft resource", r["permitted"], True)


print("\n=== Heritage Officer: change access ===", flush=True)

if draft_resource:
    r = check_perm(officer, draft_resource, "change_resourceinstance")
    check("change Draft resource", r["permitted"], True)

if non_draft_resource:
    r = check_perm(officer, non_draft_resource, "change_resourceinstance")
    check("change non-Draft resource (should be denied)", r["permitted"], False)


print("\n=== Heritage Officer: delete access ===", flush=True)

if draft_resource:
    r = check_perm(officer, draft_resource, "delete_resourceinstance")
    check("delete Draft resource (should be denied)", r["permitted"], False)

if non_draft_resource:
    r = check_perm(officer, non_draft_resource, "delete_resourceinstance")
    check("delete non-Draft resource (should be denied)", r["permitted"], False)


# ── Test: Delegate ─────────────────────────────────────────────────────────

print("\n=== Delegate: full access ===", flush=True)

if non_draft_resource:
    r = check_perm(delegate, non_draft_resource, "view_resourceinstance")
    check("delegate view non-Draft", r["permitted"], True)

    r = check_perm(delegate, non_draft_resource, "change_resourceinstance")
    check("delegate change non-Draft", r["permitted"], True)

    r = check_perm(delegate, non_draft_resource, "delete_resourceinstance")
    check("delegate delete non-Draft", r["permitted"], True)


# ── Test: Ungrouped user ──────────────────────────────────────────────────

print("\n=== Ungrouped user: denied everything ===", flush=True)

if non_draft_resource:
    r = check_perm(nobody, non_draft_resource, "view_resourceinstance")
    check("nobody view (should be denied)", r["permitted"], False)

if draft_resource:
    r = check_perm(nobody, draft_resource, "change_resourceinstance")
    check("nobody change Draft (should be denied)", r["permitted"], False)


# ── Test: System settings resource ────────────────────────────────────────

print("\n=== System settings: Heritage Officer denied ===", flush=True)

if sys_resource:
    r = check_perm(officer, sys_resource, "view_resourceinstance")
    check("officer view system settings (should be denied)", r["permitted"], False)

    r = check_perm(delegate, sys_resource, "view_resourceinstance")
    check("delegate view system settings (should be denied)", r["permitted"], False)
else:
    print("  SKIPPED (no system settings resource)")


# ── Test: View-level gates (decorators / report) ─────────────────────────

print("\n=== View-level gates ===", flush=True)

from arches.app.utils.permission_backend import (
    user_can_edit_resource,
    user_is_resource_editor,
    group_required,
)

check("officer user_is_resource_editor", user_is_resource_editor(officer), True)
check("nobody user_is_resource_editor", user_is_resource_editor(nobody), False)
check("delegate user_is_resource_editor", user_is_resource_editor(delegate), True)

check("officer group_required('Resource Editor')", group_required(officer, "Resource Editor"), True)
check("nobody group_required('Resource Editor')", group_required(nobody, "Resource Editor"), False)

check("officer user_can_edit_resource (no resource)", user_can_edit_resource(officer), True)
check("nobody user_can_edit_resource (no resource)", user_can_edit_resource(nobody), False)

if draft_resource:
    check(
        "officer user_can_edit_resource (Draft)",
        user_can_edit_resource(officer, resource=draft_resource),
        True,
    )
if non_draft_resource:
    check(
        "officer user_can_edit_resource (non-Draft)",
        user_can_edit_resource(officer, resource=non_draft_resource),
        False,
    )


# ── Test: Search filter ───────────────────────────────────────────────────

print("\n=== Search filter ===", flush=True)

officer_filter = fw.get_permission_search_filter(officer)
nobody_filter = fw.get_permission_search_filter(nobody)

check(
    "officer search filter is match-all (empty Bool)",
    getattr(officer_filter, "empty", False),
    True,
)
check(
    "nobody search filter is NOT match-all",
    getattr(nobody_filter, "empty", False),
    False,
)


# ── Test: get_allowed_instances ───────────────────────────────────────────

print("\n=== get_allowed_instances ===", flush=True)

nobody_instances = fw.get_allowed_instances(nobody)
check("nobody gets no allowed instances", nobody_instances, [])

officer_instances = fw.get_allowed_instances(officer)
check("officer gets allowed instances (non-empty)", len(officer_instances) > 0, True)

if sys_settings_id:
    check(
        "officer allowed instances excludes system settings",
        sys_settings_id not in officer_instances
        and str(sys_settings_id) not in officer_instances,
        True,
    )


# ── Cleanup ───────────────────────────────────────────────────────────────

print("\n=== Cleanup ===", flush=True)
deleted, _ = User.objects.filter(username__startswith=TEST_PREFIX).delete()
print(f"  Deleted {deleted} test user(s)")


# ── Summary ───────────────────────────────────────────────────────────────

print(f"\n{'='*60}", flush=True)
print(f"  PASSED: {PASS}   FAILED: {FAIL}", flush=True)
print(f"{'='*60}", flush=True)

if FAIL:
    print("\nSome tests FAILED.", flush=True)
    sys.exit(1)
else:
    print("\nAll tests passed.", flush=True)
