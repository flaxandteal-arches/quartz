"""
Django settings for quartz project.
"""

import os
import inspect
import semantic_version
from datetime import datetime, timedelta
from django.utils.translation import gettext_lazy as _

try:
    from arches.settings import *
except ImportError:
    pass

TIME_ZONE = "Australia/Brisbane"

APP_NAME = "quartz"
APP_VERSION = semantic_version.Version(major=0, minor=0, patch=0)
APP_ROOT = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))

WEBPACK_LOADER = {
    "DEFAULT": {
        "STATS_FILE": os.path.join(APP_ROOT, "..", "webpack/webpack-stats.json"),
    },
}

# NOTE: this requires request as a param in authenticate(...) calls
# AUTHENTICATION_BACKENDS += ("axes.backends.AxesStandaloneBackend",)

DATATYPE_LOCATIONS.append("quartz.datatypes")
FUNCTION_LOCATIONS.append("quartz.functions")
ETL_MODULE_LOCATIONS.append("quartz.etl_modules")
SEARCH_COMPONENT_LOCATIONS.append("quartz.search_components")
PERMISSION_LOCATIONS.append("quartz.permissions")

# Resource-instance permissions are confined to an allowlist via the stopgap
# Delegate / Heritage Officer blanket-role framework (see
# quartz.permissions.blanket_roles): superuser and Delegate get full access,
# Heritage Officer gets view-everywhere plus change on Draft resources, and
# everyone else is denied. This is now the default; set QUARTZ_BLANKET_ROLES=False
# to fall back to the Arches default-ALLOW framework.
#
# SECURITY: this is a HARD GATE — it overrides the base owner (principaluser)
# short-circuit and explicit per-instance grants, so any active non-superuser NOT
# in a blanket group loses ALL resource-instance access. Before rolling this out
# to an environment that previously ran allow-by-default, run
# `manage.py blanket_roles_preflight` to list who would be affected (it also
# re-seeds the blanket groups).
if os.environ.get("QUARTZ_BLANKET_ROLES", "True").lower() in ("true", "1", "yes"):
    PERMISSION_FRAMEWORK = "blanket_roles.BlanketRoleDenyFramework"

LOCALE_PATHS.insert(0, os.path.join(APP_ROOT, "locale"))

FILE_TYPE_CHECKING = "lenient"
FILE_TYPES = [
    "mkv",
    "webm",
    "avi",
    "mp4",
    "mpg",
    "avi",
    "mov",
    # 3D model file types #
    "hrc",
    "js",
    "bin",
    "json",
    "laz",
    "las",
    "stl",
    "3dm",
    "3ds",
    "3mf",
    "amf",
    "bim",
    "brep",
    "dae",
    "fbx",
    "fcstd",
    "gltf",
    "glb",
    "ifc",
    "iges",
    "step",
    "obj",
    "off",
    "ply",
    "wrl",
    # 3D model file types end #
    "bmp",
    "gif",
    "jpg",
    "jpeg",
    "jfif",
    "arw",
    "json",
    "pdf",
    "png",
    "psd",
    "rtf",
    "tif",
    "tiff",
    "xlsx",
    "xls",
    "csv",
    "zip",
    # audio #
    "wma",
    "mp3",
    # documents #
    "doc",
    "docx",
    "docm",
    "txt",
    "htm",
    "ppt",
    "pptx",
    "pptm",
    # geo / CAD / misc #
    "mxd",
    "skp",
    "kmz",
    "dmc",
    "lnk",
    "msg",
]
FILENAME_GENERATOR = "arches.app.utils.storage_filename_generator.generate_filename"
# Subdirectory / object-key prefix under MEDIA_ROOT (or the Azure blob
# container) where uploaded files are stored. Cantaloupe must resolve the bare
# IIIF identifier to this same prefix:
#   - local docker: the cantaloupe-data volume is mounted at this dir on the
#     Arches side and at /imageroot on the Cantaloupe side (see
#     docker/docker-compose.yml).
#   - Azure: set the Cantaloupe AzureStorageSource path_prefix to
#     "<UPLOADED_FILES_DIR>/" so it reads the same blob keys Django writes.
UPLOADED_FILES_DIR = os.environ.get("UPLOADED_FILES_DIR", "")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-1#dmpd#$*y+ebl73yp89-rgrlp7)$dsc3yh2d35@b4y@j5n^ge"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ROOT_URLCONF = "quartz.urls"
ROOT_HOSTCONF = "quartz.hosts"

DEFAULT_HOST = "quartz"

# Modify this line as needed for your project to connect to elasticsearch with a password that you generate
ELASTICSEARCH_CONNECTION_OPTIONS = {
    "request_timeout": 30,
    "verify_certs": False,
    "basic_auth": ("elastic", "E1asticSearchforArche5"),
}

# If you need to connect to Elasticsearch via an API key instead of username/password, use the syntax below:
# ELASTICSEARCH_CONNECTION_OPTIONS = {"request_timeout": 30, "verify_certs": False, "api_key": "<ENCODED_API_KEY>"}
# ELASTICSEARCH_CONNECTION_OPTIONS = {"request_timeout": 30, "verify_certs": False, "api_key": ("<ID>", "<API_KEY>")}

# Your Elasticsearch instance needs to be configured with xpack.security.enabled=true to use API keys - update elasticsearch.yml or .env file and restart.

# Set the ELASTIC_PASSWORD environment variable in either the docker-compose.yml or .env file to the password you set for the elastic user,
# otherwise a random password will be generated.

# API keys can be generated via the Elasticsearch API: https://www.elastic.co/guide/en/elasticsearch/reference/current/security-api-create-api-key.html
# Or Kibana: https://www.elastic.co/guide/en/kibana/current/api-keys.html

# a prefix to append to all elasticsearch indexes, note: must be lower case
ELASTICSEARCH_PREFIX = "quartz"

ELASTICSEARCH_CUSTOM_INDEXES = []
# [{
#     'module': 'quartz.search_indexes.sample_index.SampleIndex',
#     'name': 'my_new_custom_index', <-- follow ES index naming rules
#     'should_update_asynchronously': False  <-- denotes if asynchronously updating the index would affect custom functionality within the project.
# }]

KIBANA_URL = "http://localhost:5601/"
KIBANA_CONFIG_BASEPATH = "kibana"  # must match Kibana config.yml setting (server.basePath) but without the leading slash,
# also make sure to set server.rewriteBasePath: true

LOAD_DEFAULT_ONTOLOGY = False
LOAD_PACKAGE_ONTOLOGIES = True

# This is the namespace to use for export of data (for RDF/XML for example)
# It must point to the url where you host your site
# Make sure to use a trailing slash
ARCHES_NAMESPACE_FOR_DATA_EXPORT = "http://localhost:8000/"

DATABASES = {
    "default": {
        "ATOMIC_REQUESTS": False,
        "AUTOCOMMIT": True,
        "CONN_MAX_AGE": 0,
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "HOST": "localhost",
        "NAME": "quartz",
        "OPTIONS": {
            "options": "-c cursor_tuple_fraction=1",
        },
        "PASSWORD": "postgis",
        "PORT": "5432",
        "POSTGIS_TEMPLATE": "template_postgis",
        "TEST": {"CHARSET": None, "COLLATION": None, "MIRROR": None, "NAME": None},
        "TIME_ZONE": None,
        "USER": "postgres",
    }
}

SEARCH_THUMBNAILS = False

INSTALLED_APPS = (
    "quartz",
    "webpack_loader",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "django_hosts",
    "rest_framework",
    "arches_modular_reports",
    "arches_search",
    "arches_component_lab",
    "arches_controlled_lists",
    "arches_notifications",
    "arches_querysets",
    "arches_resource_version_manager",
    "arches",
    "arches.app.models",
    "arches.management",
    "guardian",
    "django_recaptcha",
    "revproxy",
    "corsheaders",
    "oauth2_provider",
    "django_celery_results",
    "django_migrate_sql",
    "pgtrigger",
    "django_saml2_auth",  # SAML2 SSO Authentication
    # "silk",
    "certificate_generator",
    "axes",
)

# Placing this last ensures any templates provided by Arches Applications
# take precedence over core arches templates in arches/app/templates.
INSTALLED_APPS += (
    "arches_model_viewer",
    "arches.app",
    "django.contrib.admin",
    "django.contrib.postgres",
    "arches_her",
    "arches_id_generator",
)

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    #'arches.app.utils.middleware.TokenMiddleware',
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "arches.app.utils.middleware.ModifyAuthorizationHeader",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "oauth2_provider.middleware.OAuth2TokenMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "arches.app.utils.middleware.SetAnonymousUser",
    # "silk.middleware.SilkyMiddleware",
    # "axes.middleware.AxesMiddleware",
]

MIDDLEWARE.insert(  # this must resolve to first MIDDLEWARE entry
    0, "django_hosts.middleware.HostsRequestMiddleware"
)

MIDDLEWARE.append(  # this must resolve last MIDDLEWARE entry
    "django_hosts.middleware.HostsResponseMiddleware"
)

STATICFILES_DIRS = build_staticfiles_dirs(app_root=APP_ROOT)

REFERENCES_INDEX_NAME = "references"
ELASTICSEARCH_CUSTOM_INDEXES = [
    {
        "module": "arches_controlled_lists.search_indexes.reference_index.ReferenceIndex",
        "name": REFERENCES_INDEX_NAME,
        "should_update_asynchronously": True,
    }
]
TERM_SEARCH_TYPES = [
    {
        "type": "term",
        "label": _("Term Matches"),
        "key": "terms",
        "module": "arches.app.search.search_term.TermSearch",
    },
    {
        "type": "concept",
        "label": _("Concepts"),
        "key": "concepts",
        "module": "arches.app.search.concept_search.ConceptSearch",
    },
    {
        "type": "reference",
        "label": _("References"),
        "key": REFERENCES_INDEX_NAME,
        "module": "arches_controlled_lists.search_indexes.reference_index.ReferenceIndex",
    },
]

ES_MAPPING_MODIFIER_CLASSES = [
    "arches_controlled_lists.search.references_es_mapping_modifier.ReferencesEsMappingModifier"
]

TEMPLATES = build_templates_config(
    debug=DEBUG,
    app_root=APP_ROOT,
)

ALLOWED_HOSTS = []

SYSTEM_SETTINGS_LOCAL_PATH = os.path.join(
    APP_ROOT, "system_settings", "System_Settings.json"
)

MAPBOX_API_KEY = os.environ.get("MAPBOX_API_KEY", MAPBOX_API_KEY)

BASEMAPS = [
    {
        "name": "bright",
        "title": "Light",
        "url": os.environ.get(
            "BASEMAP_STYLE_URL",
            "https://tiles.openfreemap.org/styles/bright",
        ),
        "addtomap": True,
    }
]

WSGI_APPLICATION = "quartz.wsgi.application"

# URL that handles the media served from MEDIA_ROOT, used for managing stored files.
# It must end in a slash if set to a non-empty value.
MEDIA_URL = "/files/"

# Absolute filesystem path to the directory that will hold user-uploaded files.
MEDIA_ROOT = os.path.join(APP_ROOT)

# URL prefix for static files.
# Example: "http://media.lawrence.com/static/"
STATIC_URL = "/static/"

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/home/media/media.lawrence.com/static/"
STATIC_ROOT = os.path.join(APP_ROOT, "staticfiles")

AZURE_ACCOUNT_NAME = os.environ.get("AZURE_ACCOUNT_NAME", None)
AZURE_ACCOUNT_KEY = os.environ.get("AZURE_ACCOUNT_KEY", None)
AZURE_CONTAINER = os.environ.get("AZURE_CONTAINER", None)
AZURE_LOCATION = os.environ.get("AZURE_LOCATION", "")
AZURE_URL_EXPIRATION_SECS = int(os.environ.get("AZURE_URL_EXPIRATION_SECS", 3600))

# Separate container (same storage account) for the public-export prebuild
# artefact consumed by the starches validation pipeline.
STARCHES_VALIDATION_CONTAINER = os.environ.get(
    "STARCHES_VALIDATION_CONTAINER", "starches-validation"
)

# GitHub repository_dispatch target for triggering the validation build
# after the prebuild artefact is uploaded. "owner/repo" + a token with
# the repo (contents/dispatch) scope.
GITHUB_DISPATCH_REPO = os.environ.get("GITHUB_DISPATCH_REPO", None)
GITHUB_DISPATCH_TOKEN = os.environ.get("GITHUB_DISPATCH_TOKEN", None)

if AZURE_ACCOUNT_NAME and AZURE_ACCOUNT_KEY and AZURE_CONTAINER:
    INSTALLED_APPS = (
        *INSTALLED_APPS,
        "storages",
    )
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.azure_storage.AzureStorage",
            "OPTIONS": {},
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

# when hosting Arches under a sub path set this value to the sub path eg : "/{sub_path}/"
FORCE_SCRIPT_NAME = None

RESOURCE_IMPORT_LOG = os.path.join(APP_ROOT, "logs", "resource_import.log")
DEFAULT_RESOURCE_IMPORT_USER = {"username": "admin", "userid": 1}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "format": "%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
        },
    },
    "handlers": {
        "file": {
            "level": "WARNING",  # DEBUG, INFO, WARNING, ERROR
            "class": "logging.FileHandler",
            "filename": os.path.join(APP_ROOT, "arches.log"),
            "formatter": "console",
        },
        "console": {
            "level": "WARNING",
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
    },
    "loggers": {
        "arches": {
            "handlers": ["file", "console"],
            "level": "WARNING",
            "propagate": True,
        },
        "quartz": {
            "handlers": ["file", "console"],
            "level": "WARNING",
            "propagate": True,
        },
        "django.request": {
            "handlers": ["file", "console"],
            "level": "WARNING",
            "propagate": True,
        },
    },
}

# Rate limit for authentication views
# See options (including None or python callables):
# https://django-ratelimit.readthedocs.io/en/stable/rates.html#rates-chapter
RATE_LIMIT = "5/m"

# Sets default max upload size to 15MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 15728640

# Unique session cookie ensures that logins are treated separately for each app
SESSION_COOKIE_NAME = "quartz"

# For more info on configuring your cache: https://docs.djangoproject.com/en/2.2/topics/cache/
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    },
    "user_permission": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "user_permission_cache",
    },
}

# Hide nodes and cards in a report that have no data
HIDE_EMPTY_NODES_IN_REPORT = False

BYPASS_UNIQUE_CONSTRAINT_TILE_VALIDATION = False
BYPASS_REQUIRED_VALUE_TILE_VALIDATION = False

DATE_IMPORT_EXPORT_FORMAT = (
    "%Y-%m-%d"  # Custom date format for dates imported from and exported to csv
)

# This is used to indicate whether the data in the CSV and SHP exports should be
# ordered as seen in the resource cards or not.
EXPORT_DATA_FIELDS_IN_CARD_ORDER = False

# Identify the usernames and duration (seconds) for which you want to cache the time wheel
CACHE_BY_USER = {"default": 3600 * 24, "anonymous": 3600 * 24}  # 24hrs  # 24hrs

TILE_CACHE_TIMEOUT = 600  # seconds
CLUSTER_DISTANCE_MAX = 5000  # meters
GRAPH_MODEL_CACHE_TIMEOUT = None

OAUTH_CLIENT_ID = os.getenv(
    "OAUTH_CLIENT_ID", ""
)  #'9JCibwrWQ4hwuGn5fu2u1oRZSs9V6gK8Vu8hpRC4'

APP_TITLE = "Arches | Heritage Data Management"
COPYRIGHT_TEXT = "All Rights Reserved."
COPYRIGHT_YEAR = "2019"

ENABLE_CAPTCHA = False
# RECAPTCHA_PUBLIC_KEY = ''
# RECAPTCHA_PRIVATE_KEY = ''
# RECAPTCHA_USE_SSL = False
NOCAPTCHA = True
# RECAPTCHA_PROXY = 'http://127.0.0.1:8000'

# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  #<-- Only need to uncomment this for testing without an actual email server
# EMAIL_USE_TLS = True
# EMAIL_HOST = 'smtp.gmail.com'
# EMAIL_HOST_USER = "xxxx@xxx.com"
# EMAIL_HOST_PASSWORD = 'xxxxxxx'
# EMAIL_PORT = 587
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.azurecomm.net")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)


DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

CELERY_BROKER_URL = ""  # RabbitMQ --> "amqp://guest:guest@localhost",  Redis --> "redis://localhost:6379/0"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_BACKEND = (
    "django-db"  # Use 'django-cache' if you want to use your cache as your backend
)
CELERY_TASK_SERIALIZER = "json"


CELERY_SEARCH_EXPORT_EXPIRES = 24 * 3600  # seconds
CELERY_SEARCH_EXPORT_CHECK = 3600  # seconds

CELERY_BEAT_SCHEDULE = {
    "delete-expired-search-export": {
        "task": "arches.app.tasks.delete_file",
        "schedule": CELERY_SEARCH_EXPORT_CHECK,
    },
    "notification": {
        "task": "arches.app.tasks.message",
        "schedule": CELERY_SEARCH_EXPORT_CHECK,
        "args": ("Celery Beat is Running",),
    },
}

# Set to True if you want to send celery tasks to the broker without being able to detect celery.
# This might be necessary if the worker pool is regulary fully active, with no idle workers, or if
# you need to run the celery task using solo pool (e.g. on Windows). You may need to provide another
# way of monitoring celery so you can detect the background task not being available.
CELERY_CHECK_ONLY_INSPECT_BROKER = False

CANTALOUPE_DIR = os.path.join(APP_ROOT, UPLOADED_FILES_DIR)
CANTALOUPE_HTTP_ENDPOINT = "http://cantaloupe:8182/"

ACCESSIBILITY_MODE = False

RENDERERS = [
    {
        "name": "imagereader",
        "title": "Image Reader",
        "description": "Displays most image file types",
        "id": "5e05aa2e-5db0-4922-8938-b4d2b7919733",
        "iconclass": "fa fa-camera",
        "component": "views/components/cards/file-renderers/imagereader",
        "ext": "",
        "type": "image/*",
        "exclude": "tif,tiff,psd",
    },
    {
        "name": "pdfreader",
        "title": "PDF Reader",
        "description": "Displays pdf files",
        "id": "09dec059-1ee8-4fbd-85dd-c0ab0428aa94",
        "iconclass": "fa fa-file",
        "component": "views/components/cards/file-renderers/pdfreader",
        "ext": "pdf",
        "type": "application/pdf",
        "exclude": "tif,tiff,psd",
    },
    {
        "name": "modelviewer",
        "title": "3D Model Viewer",
        "description": "Displays 3D models via Online 3D Viewer",
        "id": "7c8b3e1a-2d9f-4a6b-8e5c-1f3d7a9b2e0c",
        "iconclass": "fa fa-cube",
        "component": "views/components/cards/file-renderers/modelviewer",
        "type": "",
        "ext": "stl,3dm,3ds,3mf,amf,bim,brep,dae,fbx,fcstd,gltf,glb,ifc,iges,step,obj,off,ply,wrl",
        "exclude": "",
    },
    {
        # Users upload a .zip containing a converted Potree octree
        # (metadata.json / cloud.js + sibling files). A post_save signal
        # in arches_model_viewer.signals extracts the archive to a
        # sibling storage directory; the front-end viewer reads from
        # there. Works on local FileSystemStorage and Azure Blob
        # (django-storages) without backend-specific code.
        "name": "pointcloudviewer",
        "title": "Point Cloud Viewer",
        "description": "Streams Potree-format point clouds (uploaded as zipped octrees).",
        "id": "9d1f2c3a-4b5e-6789-abcd-1234567890ab",
        "iconclass": "fa fa-braille",
        "component": "views/components/cards/file-renderers/pointcloudviewer",
        "type": "application/zip",
        "ext": "zip",
        "exclude": "",
    },
]

# By setting RESTRICT_MEDIA_ACCESS to True, media file requests outside of Arches will checked against nodegroup permissions.
RESTRICT_MEDIA_ACCESS = False

# By setting RESTRICT_CELERY_EXPORT_FOR_ANONYMOUS_USER to True, if the user is attempting
# to export search results above the SEARCH_EXPORT_IMMEDIATE_DOWNLOAD_THRESHOLD
# value and is not signed in with a user account then the request will not be allowed.
RESTRICT_CELERY_EXPORT_FOR_ANONYMOUS_USER = False

# Dictionary containing any additional context items for customising email templates
EXTRA_EMAIL_CONTEXT = {
    "salutation": _("Hi"),
    "expiration": (
        datetime.now() + timedelta(seconds=CELERY_SEARCH_EXPORT_EXPIRES)
    ).strftime("%A, %d %B %Y"),
}

# see https://docs.djangoproject.com/en/1.9/topics/i18n/translation/#how-django-discovers-language-preference
# to see how LocaleMiddleware tries to determine the user's language preference
# (make sure to check your accept headers as they will override the LANGUAGE_CODE setting!)
# also see get_language_from_request in django.utils.translation.trans_real.py
# to see how the language code is derived in the actual code

####### TO GENERATE .PO FILES DO THE FOLLOWING ########
# run the following commands
# language codes used in the command should be in the form (which is slightly different
# form the form used in the LANGUAGE_CODE and LANGUAGES settings below):
# --local={countrycode}_{REGIONCODE} <-- countrycode is lowercase, regioncode is uppercase, also notice the underscore instead of hyphen
# commands to run (to generate files for "British English, German, and Spanish"):
# django-admin.py makemessages --ignore=env/* --local=de --local=en --local=en_GB --local=es  --extension=htm,py
# django-admin.py compilemessages


# default language of the application
# language code needs to be all lower case with the form:
# {langcode}-{regioncode} eg: en, en-gb ....
# a list of language codes can be found here http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = "en"

# list of languages to display in the language switcher,
# if left empty or with a single entry then the switch won't be displayed
# language codes need to be all lower case with the form:
# {langcode}-{regioncode} eg: en, en-gb ....
# a list of language codes can be found here http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGES = [
    #   ('de', _('German')),
    ("en", _("English")),
    #   ('en-gb', _('British English')),
    #   ('es', _('Spanish')),
]

# override this to permenantly display/hide the language switcher
SHOW_LANGUAGE_SWITCH = len(LANGUAGES) > 1

# Implement this class to associate custom documents to the ES resource index
# See tests.views.search_tests.TestEsMappingModifier class for example
# ES_MAPPING_MODIFIER_CLASSES = ["quartz.search.es_mapping_modifier.EsMappingModifier"]

SAML2_AUTH = {
    "METADATA_AUTO_CONF_URL": os.environ.get(
        "SAML2_METADATA_URL",
        "https://login.microsoftonline.com/<tenant-id>/federationmetadata/2007-06/federationmetadata.xml",
    ),
    "DEFAULT_NEXT_URL": os.environ.get("SAML2_DEFAULT_NEXT_URL", "/"),
    "CREATE_USER": True,
    "NEW_USER_PROFILE": {
        "USER_GROUPS": [],
        "ACTIVE_STATUS": True,
        "STAFF_STATUS": False,
        "SUPERUSER_STATUS": False,
    },
    "ATTRIBUTES_MAP": {
        "email": "emailAddress",
        "username": "name",
        "first_name": "displayname",
        "last_name": "displayname",
    },
    "TOKEN_REQUIRED": False,
    "ASSERTION_URL": os.environ.get("SAML2_ASSERTION_URL", "http://localhost:8000"),
    "ENTITY_ID": os.environ.get("SAML2_ENTITY_ID", ""),
    "AUTHN_REQUESTS_SIGNED": False,
    "LOGOUT_REQUESTS_SIGNED": False,
    "WANT_ASSERTIONS_SIGNED": True,
    "WANT_RESPONSE_SIGNED": False,
}

# Login/Logout redirect URLs
LOGIN_URL = "/auth/"
LOGIN_REDIRECT_URL = os.environ.get("LOGIN_REDIRECT_URL", "/")
LOGOUT_REDIRECT_URL = os.environ.get("LOGOUT_REDIRECT_URL", "/")
ENABLE_USER_SIGNUP = bool(os.environ.get("ENABLE_USER_SIGNUP", False))

# Session cookie settings for SSO
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = False

# Arches Search
INDEX_BATCH_SIZE = int(os.environ.get("INDEX_BATCH_SIZE", 500))


try:
    from .package_settings import *
except ImportError:
    try:
        from package_settings import *
    except ImportError as e:
        pass

try:
    from .settings_local import *
except ImportError as e:
    try:
        from settings_local import *
    except ImportError as e:
        pass

# Append after all other settings (including arches_her) have been loaded
_condition_report_modifier = "quartz.search_indexes.displayname_search_modifier.DisplaynameSearchModifier"
ES_MAPPING_MODIFIER_CLASSES = list(locals().get("ES_MAPPING_MODIFIER_CLASSES") or [])
if _condition_report_modifier not in ES_MAPPING_MODIFIER_CLASSES:
    ES_MAPPING_MODIFIER_CLASSES.append(_condition_report_modifier)
