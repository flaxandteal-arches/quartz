"""Stopgap blanket-role resource-instance permissions.

Extends the built-in default-DENY framework so that, under default-deny,
membership in two named groups conveys blanket resource-instance access
WITHOUT materialising per-instance guardian rows (which does not scale to a
large, churning resource set):

  * FULL_ACCESS_GROUPS  -> view/change/delete on every resource instance
  * READ_ACCESS_GROUPS  -> view on every resource instance

It is a per-request short-circuit (the same shape as Arches' built-in superuser
short-circuit), so new/changed/deleted resources need no maintenance — there is
nothing to re-grant, reindex, or clean up. Deliberately a stopgap until
arches-rbac-permissions is adopted.

Safety properties:
  * check_resource_instance_permissions is UPGRADE-ONLY — it lets the deny
    framework decide first and only ever flips a denial to permitted for a
    blanket-role member. It can never remove access the base framework grants.
  * The system-settings resource is never blanket-granted (stays
    System Administrator only).
  * Inactive/anonymous users are never blanket-granted.

This framework only takes effect when settings.PERMISSION_FRAMEWORK points at it
(env-gated, off by default), so importing it has no effect on production.
"""

from arches.app.models.models import ResourceInstance
from arches.app.models.system_settings import settings
from arches.app.permissions.arches_default_deny import (
    ArchesDefaultDenyPermissionFramework,
)
from arches.app.search.elasticsearch_dsl_builder import Bool

# Groups conveying blanket access. Membership only — no per-resource rows.
FULL_ACCESS_GROUPS = ["Delegate"]            # view + change + delete on all
READ_ACCESS_GROUPS = ["Heritage Officer"]    # view on all

VIEW_PERM = "view_resourceinstance"


class BlanketRoleDenyFramework(ArchesDefaultDenyPermissionFramework):
    def _blanket_grants(self, user, permission, resource=None):
        """Whether ``user`` gets ``permission`` purely via a blanket role."""
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_anonymous", False):
            return False
        # Never blanket-grant the system settings resource.
        if (
            resource is not None
            and str(resource.pk) == settings.SYSTEM_SETTINGS_RESOURCE_ID
        ):
            return False
        if self.user_in_group_by_name(user, FULL_ACCESS_GROUPS):
            return True
        if permission == VIEW_PERM and self.user_in_group_by_name(
            user, READ_ACCESS_GROUPS
        ):
            return True
        return False

    # ---- direct access (report / API by id) ------------------------------
    def check_resource_instance_permissions(
        self, user, resourceid, permission, *, resource=None
    ):
        # Upgrade-only: defer to the deny framework, then grant if a blanket
        # role applies. Never downgrades an already-permitted result.
        result = super().check_resource_instance_permissions(
            user, resourceid, permission, resource=resource
        )
        if not result.get("permitted") and self._blanket_grants(
            user, permission, result.get("resource")
        ):
            result["permitted"] = True
        return result

    # ---- search / bulk: mirror the superuser "sees everything" path -------
    def get_allowed_instances(
        self, user, search_engine=None, allresources=False, resources=None
    ):
        if self._blanket_grants(user, VIEW_PERM):
            if resources is not None:
                return resources
            return [
                str(rid)
                for rid in ResourceInstance.objects.exclude(
                    resourceinstanceid=settings.SYSTEM_SETTINGS_RESOURCE_ID
                ).values_list("resourceinstanceid", flat=True)
            ]
        return super().get_allowed_instances(
            user, search_engine, allresources, resources
        )

    def get_permission_search_filter(self, user):
        if self._blanket_grants(user, VIEW_PERM):
            return Bool()  # empty Bool = no permission restriction (match-all)
        return super().get_permission_search_filter(user)
