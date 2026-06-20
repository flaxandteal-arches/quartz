"""Re-export the Arches base test case into quartz's ``tests`` package.

quartz's tests run with ``--settings="tests.test_settings"``, so the top-level
``tests`` package resolves to THIS directory (which carries ``test_settings``),
not arches'. The test modules import ``tests.base_test.ArchesTestCase``, so the
class has to be reachable here. Re-export it from arches rather than copying the
file, to avoid drift when upstream changes.

Arches' own ``base_test`` does ``from tests import test_settings`` at import
time; because ``tests`` resolves to this package, that correctly picks up
quartz's ``tests/test_settings.py``.
"""

from arches.tests.base_test import ArchesTestCase  # noqa: F401
