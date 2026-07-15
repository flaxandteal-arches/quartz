"""Stopgap blanket-role resource-instance permissions (hard allowlist gate).

Extends the built-in default-DENY framework so that resource-instance access is
confined to a small allowlist of roles, WITHOUT materialising per-instance
guardian rows (which does not scale to a large, churning resource set):

  * superuser           -> view/change/delete on every resource instance
  * FULL_ACCESS_GROUPS  -> view/change/delete on every resource instance
  * READ_ACCESS_GROUPS  -> view on every resource instance, AND change on
                           resources whose lifecycle state is ``Draft``
  * everyone else       -> DENIED

Unlike a plain upgrade-only blanket, this is a HARD GATE: the allowlisted roles
decide the outcome outright, so it both grants blanket access to those roles and
DENIES everyone else even where the base framework would have granted access via
the owner short-circuit (``principaluser``) or explicit per-instance rows. It is
a per-request short-circuit (the same shape as Arches' built-in superuser
short-circuit), so new/changed/deleted resources need no maintenance. Deliberately
a stopgap until arches-rbac-permissions is adopted.

Safety properties:
  * The system-settings resource is never touched here (stays
    System Administrator only, per the base framework).
  * Inactive/anonymous users are never granted access.

This framework only takes effect when settings.PERMISSION_FRAMEWORK points at it
(env-gated, off by default), so importing it has no effect on production.
"""

from arches.app.models.models import ResourceInstance
from arches.app.models.system_settings import settings
from arches.app.permissions.arches_default_deny import (
    ArchesDefaultDenyPermissionFramework,
)
from arches.app.search.elasticsearch_dsl_builder import Bool, Ids

# Groups conveying blanket access. Membership only — no per-resource rows.
FULL_ACCESS_GROUPS = ["Delegate"]            # view + change + delete on all
READ_ACCESS_GROUPS = ["Heritage Officer"]    # view on all + change on Draft only

VIEW_PERM = "view_resourceinstance"
CHANGE_PERM = "change_resourceinstance"

# Lifecycle state name (ResourceInstanceLifecycleState.name) that Heritage
# Officers are allowed to edit. Matches the existing check in
# quartz/functionsmulticard_resource_descriptor.py.
DRAFT_STATE_NAME = "Draft"


class BlanketRoleDenyFramework(ArchesDefaultDenyPermissionFramework):
    # ---- helpers ---------------------------------------------------------
    def _eligible(self, user):
        """Only active, authenticated, non-anonymous users can be granted."""
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_anonymous", False):
            return False
        return True

    def _is_draft(self, resource):
        """Whether ``resource`` is in the editable ``Draft`` lifecycle state."""
        if resource is None:
            return False
        state = getattr(resource, "resource_instance_lifecycle_state", None)
        # I18n_String.__eq__ compares str-to-str, so this is locale-safe.
        return state is not None and getattr(state, "name", None) == DRAFT_STATE_NAME

    def _blanket_viewer(self, user):
        """Roles that may view EVERY instance (drives the search match-all path).

        Superusers are handled by the base framework's own superuser path, so
        they are deliberately excluded here.
        """
        if not self._eligible(user):
            return False
        return self.user_in_group_by_name(
            user, FULL_ACCESS_GROUPS + READ_ACCESS_GROUPS
        )

    def _grant(self, user, permission, resource):
        """Hard-gate decision for a single (resource, permission).

        Returns True only for the allowlisted roles; everyone else is denied,
        overriding the base owner short-circuit and explicit per-instance rows.
        """
        if not self._eligible(user):
            return False
        # Superuser and Delegate: full access to every (non system-settings) resource.
        if user.is_superuser or self.user_in_group_by_name(user, FULL_ACCESS_GROUPS):
            return True
        # Heritage Officer: view everything; change only Draft; never delete.
        if self.user_in_group_by_name(user, READ_ACCESS_GROUPS):
            if permission == VIEW_PERM:
                return True
            if permission == CHANGE_PERM and self._is_draft(resource):
                return True
        return False

    # ---- direct access (report / API by id) ------------------------------
    def check_resource_instance_permissions(
        self, user, resourceid, permission, *, resource=None
    ):
        result = super().check_resource_instance_permissions(
            user, resourceid, permission, resource=resource
        )
        resource = result.get("resource")
        # Preserve the base System Administrator gating for system settings.
        if (
            resource is not None
            and str(resource.pk) == settings.SYSTEM_SETTINGS_RESOURCE_ID
        ):
            return result
        # Hard gate: the allowlist decides outright — this both upgrades (blanket
        # grant) and downgrades (overrides owner short-circuit / explicit rows).
        result["permitted"] = self._grant(user, permission, resource)
        return result

    # ---- search / bulk: mirror the superuser "sees everything" path -------
    def get_allowed_instances(
        self, user, search_engine=None, allresources=False, resources=None
    ):
        if getattr(user, "is_superuser", False):
            # Keep superusers on the base framework's native (ES) path.
            return super().get_allowed_instances(
                user, search_engine, allresources, resources
            )
        if self._blanket_viewer(user):
            if resources is not None:
                return resources
            return [
                str(rid)
                for rid in ResourceInstance.objects.exclude(
                    resourceinstanceid=settings.SYSTEM_SETTINGS_RESOURCE_ID
                ).values_list("resourceinstanceid", flat=True)
            ]
        # Hard gate: everyone else sees nothing — no fall-through to base grants.
        return []

    def get_permission_search_filter(self, user):
        if self._blanket_viewer(user):
            return Bool()  # empty Bool = no permission restriction (match-all)
        if getattr(user, "is_superuser", False):
            return super().get_permission_search_filter(user)
        # Hard gate: match nothing (empty ids query never matches a document).
        return Bool().filter(Ids(ids=[]))
