from packaging.version import InvalidVersion

from odev.common.version import OdooVersion
from tests.fixtures import OdevTestCase


class TestCommonVersion(OdevTestCase):
    """Version should be parsed according to Odoo's standards."""

    def test_01_major(self):
        parsed = OdooVersion("13.0")
        self.assertEqual(parsed.major, 13)
        self.assertEqual(parsed.minor, 0)
        self.assertEqual(parsed.module, (0, 0, 0))
        self.assertFalse(parsed.saas)
        self.assertFalse(parsed.master)
        self.assertEqual(str(parsed), "13.0")

    def test_02_module(self):
        parsed = OdooVersion("17.0.1.2.3")
        self.assertEqual(parsed.major, 17)
        self.assertEqual(parsed.minor, 0)
        self.assertEqual(parsed.module, (1, 2, 3))
        self.assertFalse(parsed.saas)
        self.assertFalse(parsed.master)
        self.assertEqual(str(parsed), "17.0")

    def test_03_saas(self):
        parsed = OdooVersion("saas~16.4")
        self.assertEqual(parsed.major, 16)
        self.assertEqual(parsed.minor, 4)
        self.assertEqual(parsed.module, (0, 0, 0))
        self.assertTrue(parsed.saas)
        self.assertFalse(parsed.master)
        self.assertEqual(str(parsed), "saas-16.4")

    def test_04_master(self):
        parsed = OdooVersion("master")
        self.assertEqual(parsed.major, 0)
        self.assertEqual(parsed.minor, 0)
        self.assertEqual(parsed.module, (0, 0, 0))
        self.assertFalse(parsed.saas)
        self.assertTrue(parsed.master)
        self.assertEqual(str(parsed), "master")

    def test_05_invalid(self):
        with self.assertRaises(InvalidVersion):
            OdooVersion("invalid")
