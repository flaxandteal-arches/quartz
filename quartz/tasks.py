import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def run_public_export(
    visibility=None,
    output_dir="public_export",
    use_drafts=False,
    use_latest_minor=False,
    indent=2,
    as_user=None,
    push=False,
    trigger=False,
    event_type="prebuild",
    blob_name=None,
    image_visibility=None,
):
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
        blob_name or os.environ.get("STARCHES_PREBUILD_BLOB_NAME") or "prebuild.tgz"
    )
    labels = visibility or ["Public", "Staging"]
    try:
        user, user_messages = resolve_export_user(as_user)
    except ValueError as e:
        logger.error("Public export aborted resolving user %r: %s", as_user, e)
        return {"export": {"messages": [("error", str(e))]}, "packaging": None}

    pipeline = run_export_pipeline(
        labels,
        output_dir=output_dir,
        use_drafts=use_drafts,
        use_latest_minor=use_latest_minor,
        indent=indent or None,
        user=user,
        image_required_labels=image_visibility or ["Available", "Public"],
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
        pipeline["result"],
        push=push,
        trigger=trigger,
        event_type=event_type,
        blob_name=blob_name,
    )
    return {"export": export_section, "packaging": packaging}


@shared_task
def export_and_push_public_heritage(
    output_dir,
    push=False,
    trigger=False,
    event_type="prebuild",
    blob_name="prebuild.tgz",
):
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
            result["triggered_status"] = trigger_validation_build(event_type=event_type)
        except RuntimeError as e:
            logger.warning("Skipping trigger: %s", e)
            result["skipped"].append(f"trigger: {e}")
        except Exception as e:  # noqa: BLE001
            logger.exception("Trigger failed")
            result["errors"].append(f"trigger: {e}")

    return result


@shared_task(bind=True)
def export_register_xml_task(self, userid, request_values):
    """Background version of the XML register export from the search panel.

    Mirrors ``arches.app.tasks.export_search_results``: re-runs the search as
    the requesting user, writes the register XML to a SearchExportHistory
    record (served by the Arches ``/files/<id>`` route) and returns the
    notification payload that ``update_user_task_record`` turns into the bell
    message and email.
    """
    import datetime
    from datetime import timedelta
    from io import BytesIO

    from django.contrib.auth.models import User
    from django.core.files.base import ContentFile
    from django.http import HttpRequest
    from django.utils.translation import gettext as _

    from arches.app.models import models
    from arches.app.models.system_settings import settings
    from arches.app.tasks import create_user_task_record
    from arches.app.utils.message_contexts import return_message_context
    from arches.app.utils.permission_backend import get_nodegroups_by_perm

    from quartz.utils.public_xml_export import export_register_xml
    from quartz.views.search_export import get_search_resource_ids

    settings.update_from_db()
    create_user_task_record(self.request.id, self.name, userid)
    user = User.objects.get(id=userid)

    email = request_values.get("email", [None])[0]
    export_name = request_values.get("exportName", [None])[0]

    request = HttpRequest()
    request.method = "GET"
    request.user = user
    request.path = request_values["path"]
    for key, value in request_values.items():
        if key != "path":
            request.GET.__setitem__(key, value[0])

    ids = get_search_resource_ids(request)
    buffer = BytesIO()
    result = export_register_xml(
        ids,
        buffer,
        permitted_nodegroups=get_nodegroups_by_perm(user, "models.read_nodegroup"),
    )
    logger.info(
        "XML export task for %s: %s places written, %s skipped (other graph), "
        "%s skipped (not Public), %s skipped (not Entered)",
        user.username,
        result["count"],
        result["skipped_other_graph"],
        result["skipped_not_public"],
        result["skipped_not_entered"],
    )

    expires = datetime.datetime.now() + timedelta(
        seconds=settings.CELERY_SEARCH_EXPORT_EXPIRES
    )
    expires_text = expires.strftime("%A, %d %B %Y")

    if result["count"] == 0:
        return {
            "taskid": self.request.id,
            "msg": _(
                "Your XML export finished, but none of the results are Public "
                "Heritage Items with status Entered, so there is no file."
            ),
            "notiftype_name": "Search Export Download Ready",
            "context": return_message_context(
                greeting=_("Hello,\nYour XML export finished with nothing to export."),
                closing_text=_("Thank you"),
                email=email,
                additional_context={"username": user.first_name or user.username},
            ),
        }

    history = models.SearchExportHistory(
        user=user,
        numberofinstances=result["count"],
        url=request.path,
    )
    history.save()
    name = (
        f"{export_name}.xml"
        if export_name and export_name != "Arches Export"
        else f"heritage-register-{datetime.date.today().isoformat()}.xml"
    )
    history.downloadfile.save(name, ContentFile(buffer.getvalue()))
    history.save()

    context = return_message_context(
        greeting=_(
            "Hello,\nYour request to download a set of search results is now ready. "
            "You have until {} to access this download, after which time it'll be deleted."
        ).format(expires_text),
        closing_text=_("Thank you"),
        email=email,
        additional_context={
            "link": str(history.searchexportid),
            "button_text": _("Download Now"),
            "name": export_name,
            "email_link": str(settings.PUBLIC_SERVER_ADDRESS).rstrip("/")
            + "/files/"
            + str(history.searchexportid),
            "username": user.first_name or user.username,
        },
    )
    return {
        "taskid": self.request.id,
        "msg": _(
            "Your search '{}' is ready for download. You have until {} to access "
            "this file, after which we'll automatically remove it."
        ).format(export_name, expires_text),
        "notiftype_name": "Search Export Download Ready",
        "context": context,
    }
