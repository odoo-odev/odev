from unittest.mock import patch

from odev.common.config import Config

from tests.fixtures import OdevTestCase


class TestConfig(OdevTestCase):
    """Tests for the persistence of the configuration file, which concurrent odev processes share."""

    def test_save_replaces_the_file_atomically(self):
        config = self.odev.config
        config.save()

        self.assertEqual(config.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(config.path.parent.glob(f".{config.path.name}.*")), [])

    def test_loading_a_complete_file_does_not_rewrite_it(self):
        path = self.odev.config.path
        content = path.read_text()
        modified = path.stat().st_mtime_ns

        Config(self.odev.config.name)

        self.assertEqual(path.read_text(), content)
        self.assertEqual(path.stat().st_mtime_ns, modified)

    def test_failed_save_keeps_the_previous_file(self):
        config = self.odev.config
        content = config.path.read_text()

        with patch.object(config.parser, "write", side_effect=OSError("disk full")), self.assertRaises(OSError):
            config.save()

        self.assertEqual(config.path.read_text(), content)
        self.assertEqual(list(config.path.parent.glob(f".{config.path.name}.*")), [])
