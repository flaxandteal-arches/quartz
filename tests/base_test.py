"""Minimal stand-in for the Arches base test case.

Arches' own ``tests/base_test.py`` lives at the arches *repo* root, alongside
(not inside) the ``arches`` package, so it is absent from PyPI wheels and
cannot be imported when arches is pip-installed (as in the main.yml CI job).
Rather than depend on an arches source checkout, this vendors the small
subset of ``ArchesTestCase`` that quartz's tests actually use:

  * ``LanguageSynchronizer`` sync so language-aware models behave,
  * loading the ontology from ``ONTOLOGY_PATH`` into the fresh test DB.

quartz's tests load their graph fixtures explicitly, so the upstream
``graph_fixtures`` machinery, OAuth application setup, and legacy package
loading are intentionally omitted.
"""

from django.core import management
from django.test import TestCase

from arches.app.models.models import Ontology
from arches.app.utils.i18n import LanguageSynchronizer

from tests import test_settings


class ArchesTestCase(TestCase):
    @classmethod
    def loadOntology(cls):
        if not Ontology.objects.exclude(ontologyid__isnull=True).exists():
            management.call_command(
                "load_ontology", source=test_settings.ONTOLOGY_PATH, verbosity=0
            )

    @classmethod
    def setUpTestData(cls):
        LanguageSynchronizer.synchronize_settings_with_db(update_published_graphs=False)
        cls.loadOntology()
