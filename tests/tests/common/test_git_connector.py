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
