from pathlib import Path
from unittest.mock import patch

from odev.common.connectors.git import GitConnector
from odev.common.errors import ConnectorError

from tests.fixtures import OdevTestCase


class TestGitConnectorInit(OdevTestCase):
    def test_https_github_url(self):
        g = GitConnector("https://github.com/acme/myrepo")
        self.assertEqual(g.name, "acme/myrepo")

    def test_git_ssh_url(self):
        g = GitConnector("git@github.com:acme/myrepo.git")
        self.assertEqual(g.name, "acme/myrepo")

    def test_org_slash_repo(self):
        g = GitConnector("acme/myrepo")
        self.assertEqual(g.name, "acme/myrepo")

    def test_ssh_prefix_stripped_before_parse(self):
        g = GitConnector("git@github.com:org/repo")
        self.assertEqual(g.name, "org/repo")

    def test_invalid_repo_format_raises(self):
        with self.assertRaises(ConnectorError) as ctx:
            GitConnector("onlyonepart")
        self.assertIn("Invalid repository format", str(ctx.exception))


class TestGitConnectorPath(OdevTestCase):
    def test_explicit_path_takes_priority(self):
        explicit = Path("/explicit/path")
        g = GitConnector("acme/myrepo", path=explicit)
        self.assertEqual(g.path, explicit)

    def test_config_override_used_when_set(self):
        override = Path("/custom/path/myrepo")
        g = GitConnector("acme/myrepo")
        with patch.object(type(g.config.repository_paths), "get_path", return_value=override):
            self.assertEqual(g.path, override)

    def test_flat_fallback_when_standard_has_no_git(self):
        g = GitConnector("acme/myrepo")
        repositories = g.config.paths.repositories
        flat = repositories / "myrepo"
        with patch.object(type(g.config.repository_paths), "get_path", return_value=None):
            with patch("pathlib.Path.exists", side_effect=lambda p=None: Path.__eq__(p or Path(), flat / ".git") if p else False):
                # standard path has no .git, flat path does
                def exists_side_effect(self):
                    return self == flat / ".git"

                with patch.object(Path, "exists", exists_side_effect):
                    self.assertEqual(g.path, flat)

    def test_standard_path_used_when_git_present(self):
        g = GitConnector("acme/myrepo")
        standard = g.config.paths.repositories / "acme" / "myrepo"
        with patch.object(type(g.config.repository_paths), "get_path", return_value=None):
            with patch.object(Path, "exists", lambda self: self == standard / ".git"):
                self.assertEqual(g.path, standard)
