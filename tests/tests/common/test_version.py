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

    def test_06_major_only(self):
        """A version without a minor number should default it to zero."""
        parsed = OdooVersion("17")
        self.assertEqual(parsed.major, 17)
        self.assertEqual(parsed.minor, 0)
        self.assertEqual(str(parsed), "17.0")

    def test_07_enterprise(self):
        """The enterprise marker should be parsed but left out of the string representation."""
        parsed = OdooVersion("17.0+e")
        self.assertTrue(parsed.enterprise)
        self.assertEqual(str(parsed), "17.0")
        self.assertFalse(OdooVersion("17.0").enterprise)

    def test_08_repr(self):
        """The representation should wrap the string version."""
        self.assertEqual(repr(OdooVersion("saas~16.4")), "OdooVersion(saas-16.4)")


class TestCommonVersionBool(OdevTestCase):
    """A version should be falsy only when it carries no version information at all."""

    def test_01_empty(self):
        """An empty version has nothing set and should be falsy.

        `module` is padded to `MIN_VERSION_LENGTH`, so it is never an empty tuple and cannot be tested on
        its own truthiness.
        """
        self.assertFalse(OdooVersion(""))
        self.assertFalse(OdooVersion("0.0"))

    def test_02_not_empty(self):
        """Any version component being set should make the version truthy."""
        self.assertTrue(OdooVersion("17.0"))
        self.assertTrue(OdooVersion("0.1"))
        self.assertTrue(OdooVersion("master"))
        self.assertTrue(OdooVersion("0.0.1.0.0"))


class TestCommonVersionOrdering(OdevTestCase):
    """Versions should sort the way Odoo releases succeed each other.

    Ordering is what picks a revision when odev has several to choose from, so it matters as much as
    parsing does.
    """

    def test_01_major_versions(self):
        """Newer major versions should sort after older ones."""
        self.assertLess(OdooVersion("15.0"), OdooVersion("16.0"))
        self.assertGreater(OdooVersion("17.0"), OdooVersion("16.0"))

    def test_02_saas_between_majors(self):
        """A SaaS version should sort after the major it branches off, and before the next one."""
        self.assertGreater(OdooVersion("saas~16.4"), OdooVersion("16.0"))
        self.assertLess(OdooVersion("saas~16.4"), OdooVersion("17.0"))
        self.assertGreater(OdooVersion("saas~16.4"), OdooVersion("saas~16.2"))

    def test_03_saas_after_same_numbered_version(self):
        """At equal numbers, a SaaS version should sort after the stable one."""
        self.assertGreater(OdooVersion("saas~16.0"), OdooVersion("16.0"))

    def test_04_master_is_the_newest(self):
        """Master is the development version and should sort after every numbered version."""
        self.assertGreater(OdooVersion("master"), OdooVersion("17.0"))
        self.assertGreater(OdooVersion("master"), OdooVersion("saas~17.4"))

    def test_05_enterprise_after_community(self):
        """At equal versions, the enterprise edition should sort after the community one."""
        self.assertGreater(OdooVersion("17.0+e"), OdooVersion("17.0"))

    def test_06_module_versions(self):
        """Module versions should be compared component by component, ignoring trailing zeros."""
        self.assertLess(OdooVersion("17.0.1.0.0"), OdooVersion("17.0.1.1.0"))
        self.assertEqual(OdooVersion("17.0.1.0.0"), OdooVersion("17.0.1"))

    def test_07_equality_and_hash(self):
        """Equal versions should compare equal and hash alike, whatever their notation."""
        self.assertEqual(OdooVersion("17.0"), OdooVersion("17.0"))
        self.assertEqual(hash(OdooVersion("17.0")), hash(OdooVersion("17.0")))
        self.assertEqual(OdooVersion("saas~16.4"), OdooVersion("saas-16.4"))
        self.assertNotEqual(OdooVersion("17.0"), OdooVersion("16.0"))

    def test_08_sorting(self):
        """Sorting a set of versions should yield the chronological order of the releases."""
        versions = ["master", "16.0", "saas~16.4", "17.0", "15.0", "saas~17.2"]
        expected = ["15.0", "16.0", "saas-16.4", "17.0", "saas-17.2", "master"]

        self.assertEqual([str(version) for version in sorted(map(OdooVersion, versions))], expected)
