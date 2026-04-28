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
        

def _patch_filelist_path_join():
    """
    Upstream FileListDataType.transform_value_for_tile builds a blob key via
    `"%s/%s" % (settings.UPLOADED_FILES_DIR, name)`, which yields a leading slash
    (e.g. `/foo.jpg`) when UPLOADED_FILES_DIR="". Every other call site in arches
    uses os.path.join. Patch to match.
    """
    import inspect
    import textwrap

    from arches.app.datatypes import datatypes as arches_datatypes

    method = arches_datatypes.FileListDataType.transform_value_for_tile
    src = textwrap.dedent(inspect.getsource(method))
    old = '"%s/%s" % (settings.UPLOADED_FILES_DIR, str(tile_file["name"]))'
    new = 'os.path.join(settings.UPLOADED_FILES_DIR, str(tile_file["name"]))'
    if old not in src:
        return
    namespace = arches_datatypes.__dict__.copy()
    exec(src.replace(old, new), namespace)
    arches_datatypes.FileListDataType.transform_value_for_tile = namespace[
        "transform_value_for_tile"
    ]