from django.apps import AppConfig


class QuartzConfig(AppConfig):
    name = "quartz"
    is_arches_application = True

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        def ensure_user_backend(sender, user, request, **kwargs):
            if not hasattr(user, "backend"):
                user.backend = "django.contrib.auth.backends.ModelBackend"

        user_logged_in.connect(ensure_user_backend)

        _patch_filelist_path_join()
        _patch_renderer_ext_csv()


def _patch_renderer_ext_csv():
    """
    Upstream arches.app.datatypes.datatypes.FileListDataType.get_compatible_renderers
    compares renderer["ext"] as a single string, while renderer["exclude"] is CSV.
    This patch makes `ext` accept a comma-separated list too, so one RENDERERS entry
    can cover many extensions (e.g. the 3D model viewer covering stl,obj,gltf,...).

    Remove once the upstream PR lands in the arches version we track.
    """
    import inspect

    from pathlib import Path

    from django.conf import settings

    from arches.app.datatypes import datatypes as arches_datatypes

    sentinel = 'extension.lower() == renderer["ext"].lower()'
    original_src = inspect.getsource(
        arches_datatypes.FileListDataType.get_compatible_renderers
    )
    if sentinel not in original_src:
        return  # upstream has changed — bail out so we don't apply stale logic

    def get_compatible_renderers(self, file_data):
        extension = Path(file_data["name"]).suffix.strip(".")
        compatible_renderers = []
        for renderer in settings.RENDERERS:
            renderer_exts = [
                e.strip().lower()
                for e in renderer["ext"].split(",")
                if e.strip()
            ]
            if extension.lower() in renderer_exts:
                compatible_renderers.append(renderer["id"])
            else:
                excluded = [e.strip() for e in renderer["exclude"].split(",")]
                if extension not in excluded:
                    renderer_mime = renderer["type"].split("/")
                    file_mime = file_data["type"].split("/")
                    if len(renderer_mime) == 2 and len(file_mime) == 2:
                        renderer_class, renderer_type = renderer_mime
                        file_class = file_mime[0]
                        if (
                            renderer_class.lower() == file_class.lower()
                            and renderer_type == "*"
                        ):
                            compatible_renderers.append(renderer["id"])
        return compatible_renderers

    arches_datatypes.FileListDataType.get_compatible_renderers = (
        get_compatible_renderers
    )


def _patch_filelist_path_join():
    """
    Upstream bug in arches.app.datatypes.datatypes.FileListDataType.transform_value_for_tile:
    builds a blob key via `"%s/%s" % (settings.UPLOADED_FILES_DIR, name)`, which yields
    a leading slash (e.g. `/foo.jpg`) when UPLOADED_FILES_DIR="". Every other call site
    in arches uses os.path.join. Patch to match.

    Remove once the upstream PR lands in the arches version we track.
    """
    import inspect
    import textwrap

    from arches.app.datatypes import datatypes as arches_datatypes

    method = arches_datatypes.FileListDataType.transform_value_for_tile
    src = textwrap.dedent(inspect.getsource(method))
    old = '"%s/%s" % (settings.UPLOADED_FILES_DIR, str(tile_file["name"]))'
    new = 'os.path.join(settings.UPLOADED_FILES_DIR, str(tile_file["name"]))'
    if old not in src:
        return  # upstream already fixed or line moved — bail out silently
    namespace = arches_datatypes.__dict__.copy()
    exec(src.replace(old, new), namespace)
    arches_datatypes.FileListDataType.transform_value_for_tile = namespace[
        "transform_value_for_tile"
    ]
