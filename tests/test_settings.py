"""
ARCHES - a program developed to inventory and manage immovable cultural heritage.
Copyright (C) 2013 J. Paul Getty Trust and World Monuments Fund

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import os

from quartz.settings import *

PACKAGE_NAME = "quartz"

PROJECT_TEST_ROOT = os.path.join(os.path.dirname(__file__), "..", "tests")
MEDIA_ROOT = os.path.join(PROJECT_TEST_ROOT, "fixtures", "data")

# Arches' base_test loads this into a fresh test DB via ``load_ontology``.
# Use the arches-her package's CIDOC CRM (6.2.1 "Human-Made" naming) rather
# than arches' trimmed test fixture, since the quartz graphs reference classes
# absent from the latter (e.g. E24_Physical_Human-Made_Thing).
ONTOLOGY_PATH = os.path.join(PROJECT_TEST_ROOT, "fixtures", "ontologies", "cidoc_crm")

BUSINESS_DATA_FILES = (
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

DATABASES = {
    "default": {
        "ATOMIC_REQUESTS": False,
        "AUTOCOMMIT": True,
        "CONN_MAX_AGE": 0,
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        # Honour the standard Arches PG* env vars so the same settings work both
        # when run directly on the runner (main.yml, services on localhost) and
        # inside a container job where Postgres is reached by service hostname
        # (project.yml Test-Public-Export). Defaults preserve the original
        # localhost behaviour, so main.yml is unaffected.
        "HOST": os.environ.get("PGHOST", "localhost"),
        "NAME": os.environ.get("PGDBNAME", "quartz"),
        "OPTIONS": {
            "options": "-c cursor_tuple_fraction=1",
        },
        "PASSWORD": os.environ.get("PGPASSWORD", "postgis"),
        "PORT": os.environ.get("PGPORT", "5432"),
        "POSTGIS_TEMPLATE": "template_postgis",
        "TEST": {"CHARSET": None, "COLLATION": None, "MIRROR": None, "NAME": None},
        "TIME_ZONE": None,
        "USER": os.environ.get("PGUSERNAME", "postgres"),
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    },
    "user_permission": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
        "LOCATION": "user_permission_cache",
    },
}

LOGGING["loggers"]["arches"]["level"] = "ERROR"

ELASTICSEARCH_PREFIX = "test"

TEST_RUNNER = "arches.test.runner.ArchesTestRunner"
SILENCED_SYSTEM_CHECKS.append(
    "arches.W001",  # Cache backend does not support rate-limiting
)

ELASTICSEARCH_HOSTS = [
    # int(): some environments inject the port as a string via env vars, which
    # the elasticsearch-py client rejects (TypeError comparing str < int).
    # ESHOST/ESPORT let a container job point at the elasticsearch service by
    # hostname; defaults keep the original localhost behaviour for main.yml.
    {
        "scheme": "http",
        "host": os.environ.get("ESHOST", "localhost"),
        "port": int(os.environ.get("ESPORT", ELASTICSEARCH_HTTP_PORT)),
    }
]
