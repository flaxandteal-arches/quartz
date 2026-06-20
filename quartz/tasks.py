import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def export_and_push_public_heritage(output_dir, push=False, trigger=False,
                                    event_type="prebuild",
                                    blob_name="prebuild.tgz"):
    """Package an exported public-heritage directory and optionally push it.

    Steps:
      1. Tar+gzip ``output_dir`` into prebuild.tgz.
      2. (if ``push``) upload the archive to the starches-validation
         Azure blob container.
      3. (if ``trigger``) fire a GitHub repository_dispatch event.

    Each remote step is independent and skipped cleanly when its
    configuration is absent, so dev runs still produce a local archive.

    Returns a result dict describing what happened.
    """
    from quartz.utils.public_export import (
        package_export,
        trigger_validation_build,
        upload_artifact,
    )

    result = {
        "archive_path": None,
        "uploaded_url": None,
        "triggered_status": None,
        "skipped": [],
        "errors": [],
    }

    result["archive_path"] = package_export(output_dir, archive_name=blob_name)

    if push:
        try:
            result["uploaded_url"] = upload_artifact(
                result["archive_path"], blob_name=blob_name
            )
        except RuntimeError as e:
            logger.warning("Skipping upload: %s", e)
            result["skipped"].append(f"upload: {e}")
        except Exception as e:  # noqa: BLE001 - surface but don't crash export
            logger.exception("Upload failed")
            result["errors"].append(f"upload: {e}")

    if trigger:
        try:
            result["triggered_status"] = trigger_validation_build(
                event_type=event_type
            )
        except RuntimeError as e:
            logger.warning("Skipping trigger: %s", e)
            result["skipped"].append(f"trigger: {e}")
        except Exception as e:  # noqa: BLE001
            logger.exception("Trigger failed")
            result["errors"].append(f"trigger: {e}")

    return result
