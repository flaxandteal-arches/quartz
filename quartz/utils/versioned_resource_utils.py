from typing import Optional

from arches_resource_version_manager.models import VersionedResource


def calculate_next_version(
    current_draft_version: VersionedResource, is_final: bool, version_from_payload: str
) -> tuple[int, int, int]:

    if is_final:
        # Finalize = minor bump (majors come from Dynamics only).
        if version_from_payload is not None:
            major_version = int(version_from_payload)
            return major_version, 0, 0
        return (
            current_draft_version.major_version,
            current_draft_version.minor_version + 1,
            0,
        )

    if current_draft_version is None:
        major_version = (
            int(version_from_payload) if version_from_payload is not None else 0
        )
        return major_version, 0, 1
    else:
        return (
            current_draft_version.major_version,
            current_draft_version.minor_version,
            getattr(current_draft_version, "patch_version", 0) + 1,
        )


def increment_draft_version(
    current_draft_version: VersionedResource,
    is_final: bool,
    version_from_payload: Optional[str] = None,
) -> VersionedResource:
    """
    Finalize (is_final=True): bump minor, reset patch to 0.
    Archive (is_final=False): bump patch only.
    Major versions are set externally by Dynamics payloads.
    """

    next_major, next_minor, next_patch = calculate_next_version(
        current_draft_version,
        is_final,
        version_from_payload,
    )
    current_draft_version.major_version = next_major
    current_draft_version.minor_version = next_minor
    current_draft_version.patch_version = next_patch
    return current_draft_version
