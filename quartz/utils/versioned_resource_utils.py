from typing import Optional

from arches_resource_version_manager.models import VersionedResource


def calculate_next_version(
    current_draft_version: VersionedResource, is_final: bool, version_from_payload: str
) -> tuple[int, int]:

    if is_final or (current_draft_version is None):
        major_version = (
            int(version_from_payload)
            if version_from_payload
            else current_draft_version.major_version + 1
        )
        return major_version, 0
    return current_draft_version.major_version, current_draft_version.minor_version + 1


def increment_draft_version(
    current_draft_version: VersionedResource,
    is_final: bool,
    version_from_payload: Optional[str] = None,
) -> VersionedResource:
    """
    Increment the major version (and reset minor version to 0) if is_final is True,
    otherwise increment the minor version, then return the updated draft VersionedResource.
    Assumes a Draft already exists for the resource group.
    """

    next_major, next_minor = calculate_next_version(
        current_draft_version,
        is_final,
        version_from_payload,
    )
    current_draft_version.major_version = next_major
    current_draft_version.minor_version = next_minor
    return current_draft_version
