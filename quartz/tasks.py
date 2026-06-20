import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def run_public_export(visibility=None, output_dir="public_export",
                      use_drafts=False, indent=2, as_user=None,
                      push=False, trigger=False, event_type="prebuild",
                      blob_name=None):
    """Full public-export pipeline as a single worker task.

    ``blob_name`` names BOTH the local archive and the uploaded blob. When not
    passed explicitly it is taken from the STARCHES_PREBUILD_BLOB_NAME env var
    (resolved on the worker, so a k8s Job can target a per-environment blob via
    its own env), falling back to 'prebuild.tgz'.

    Runs the whole thing end-to-end with nothing pre-staged: resolves the
    export user (defaults to 'anonymous'), selects + writes the Heritage Item
    export to ``output_dir``, then packages and optionally pushes/triggers.

    Unlike export_and_push_public_heritage (which only packages an existing
    directory), this generates ``output_dir`` itself — so a bare
    ``run_public_export.delay()`` produces and ships the prebuild on the worker.

    Returns a dict with an ``export`` section (pipeline messages/diagnostics)
    and a ``packaging`` section (archive path / upload / trigger), or packaging
    None when nothing was exported.
    """
    import os

    from quartz.utils.public_export import (
        resolve_export_user,
        run_export_pipeline,
    )

    blob_name = (
        blob_name
        or os.environ.get("STARCHES_PREBUILD_BLOB_NAME")
        or "prebuild.tgz"
    )
    labels = visibility or ["Public", "Staging"]
    try:
        user, user_messages = resolve_export_user(as_user)
    except ValueError as e:
        return {"export": {"messages": [("error", str(e))]}, "packaging": None}

    pipeline = run_export_pipeline(
        labels,
        output_dir=output_dir,
        use_drafts=use_drafts,
        indent=indent or None,
        user=user,
    )
    pipeline["messages"] = user_messages + pipeline["messages"]

    export_section = {
        "result": pipeline["result"],
        "export_ids": pipeline["export_ids"],
        "missing_final_groups": pipeline["missing_final_groups"],
        "messages": pipeline["messages"],
        "diagnostics": pipeline["diagnostics"],
    }
    if not pipeline["result"]:
        return {"export": export_section, "packaging": None}

    # Reuse the packaging/push task body (runs inline here, not via .delay()).
    packaging = export_and_push_public_heritage(
        pipeline["result"], push=push, trigger=trigger,
        event_type=event_type, blob_name=blob_name,
    )
    return {"export": export_section, "packaging": packaging}


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
