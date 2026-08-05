from typing import Optional

from arches_resource_version_manager.models import VersionedResource


def calculate_next_version(
    current_draft_version: VersionedResource,
    is_final: bool,
    version_from_payload: str,
) -> tuple[int, int, int]:
    """Return (major, minor, patch) for the next version.

    Versioning layers:
      major - set by Dynamics (source of truth for the public site)
      minor - editor-promoted versions (publishable without Dynamics)
      patch - working draft counter (not public)

    Dynamics path (version_from_payload set):
      final   -> (payload_version, 0, 0)
      draft   -> (payload_version, 0, patch+1) for new; (major, minor, patch+1) for existing

    Editor path (version_from_payload is None):
      final   -> (major, minor+1, 0)   - promote within same major
      draft   -> (major, minor, patch+1)
    """

    if is_final:
        if version_from_payload is not None:
            # Dynamics-driven finalize: new major version
            # note that this relies on Dynamics sending consistent
            # incrementing majors to distinguish it from the editor.
            return int(version_from_payload), 0, 0
        else:
            # Editor-driven finalize: increment minor within current major
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
            current_draft_version.patch_version + 1,
        )


def increment_draft_version(
    current_draft_version: VersionedResource,
    is_final: bool,
    version_from_payload: Optional[str] = None,
) -> VersionedResource:
    """Increment version numbers on the draft VersionedResource.

    Dynamics finalize: bumps major (from payload), resets minor and patch.
    Editor finalize:   bumps minor, resets patch.
    Draft save:        bumps patch only.
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


def format_version(major: int, minor: int, patch: int) -> str:
    return f"{major}.{minor}.{patch}"
