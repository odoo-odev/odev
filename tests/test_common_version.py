from packaging.version import InvalidVersion

from odev.common.version import OdooVersion
from tests.fixtures import OdevTestCase


class TestCommonVersion(OdevTestCase):
    def test_version_parsing(self):
        """Version should be parsed according to Odoo's standards."""
        parsed = OdooVersion("13.0")
        self.assertEqual(parsed.major, 13)
        self.assertEqual(parsed.minor, 0)
        self.assertEqual(parsed.module, (0, 0, 0))
        self.assertFalse(parsed.saas)
        self.assertFalse(parsed.master)
        self.assertEqual(str(parsed), "13.0")

        parsed = OdooVersion("17.0.1.2")
        self.assertEqual(parsed.major, 17)
        self.assertEqual(parsed.minor, 0)
        self.assertEqual(parsed.module, (1, 2, 0))
        self.assertFalse(parsed.saas)
        self.assertFalse(parsed.master)
        self.assertEqual(str(parsed), "17.0")

        parsed = OdooVersion("saas~16.4")
        self.assertEqual(parsed.major, 16)
        self.assertEqual(parsed.minor, 4)
        self.assertEqual(parsed.module, (0, 0, 0))
        self.assertTrue(parsed.saas)
        self.assertFalse(parsed.master)
        self.assertEqual(str(parsed), "saas-16.4")

        parsed = OdooVersion("master")
        self.assertEqual(parsed.major, 0)
        self.assertEqual(parsed.minor, 0)
        self.assertEqual(parsed.module, (0, 0, 0))
        self.assertFalse(parsed.saas)
        self.assertTrue(parsed.master)
        self.assertEqual(str(parsed), "master")

        with self.assertRaises(InvalidVersion):
            OdooVersion("invalid")
