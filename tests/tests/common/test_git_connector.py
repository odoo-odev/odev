from types import SimpleNamespace

from github import GithubException, UnknownObjectException

from odev.common.connectors.git import GitConnector, GithubConnector
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


class TestGithubConnectorRepositories(OdevTestCase):
    def __connector(self, get_repo) -> GithubConnector:
        """Build a connector already connected to a stand-in of the Github API."""
        connector = GithubConnector()
        connector._connection = SimpleNamespace(get_repo=get_repo)  # type: ignore [assignment]

        for attribute in ("connect", "disconnect"):
            patcher = self.patch(connector, attribute)
            patcher.start()
            self.addCleanup(patcher.stop)

        return connector

    def test_get_repository(self):
        repository = SimpleNamespace(full_name="acme/myrepo")
        connector = self.__connector(lambda name: repository)
        self.assertIs(connector.get_repository("acme/myrepo"), repository)

    def test_get_repository_missing(self):
        def get_repo(name: str):
            raise UnknownObjectException(404, None, None)

        connector = self.__connector(get_repo)
        self.assertIsNone(connector.get_repository("acme/missing"))

    def test_get_repository_error(self):
        def get_repo(name: str):
            raise GithubException(500, None, None)

        connector = self.__connector(get_repo)
        self.assertIsNone(connector.get_repository("acme/myrepo"))
