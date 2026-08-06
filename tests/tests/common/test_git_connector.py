import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from git import Repo
from github import GithubException, UnknownObjectException

from odev.common.connectors.git import GitConnector, GithubConnector
from odev.common.errors import ConnectorError
from odev.common.odoobin import OdoobinProcess

from tests.fixtures import OdevTestCase


class GitRepositoryMixin:
    """Build throwaway git repositories on disk to exercise the connector against real remotes."""

    def make_repository(self, *parts: str, remote: str | None = "git@github.com:acme/myrepo.git") -> Path:
        """Create a git repository in a temporary directory.
        :param parts: The directories to nest the repository into, relative to the temporary directory.
        :param remote: The URL of the remote to configure, or None to leave the repository without one.
        :return: The path to the repository.
        """
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        path = root.joinpath(*parts)
        path.mkdir(parents=True)
        repository = Repo.init(path)

        if remote is not None:
            repository.create_remote("origin", remote)

        return path


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


class TestGitConnectorName(GitRepositoryMixin, OdevTestCase):
    """The repository name must come from the git remote whenever one is available."""

    def test_name_from_remote_overrides_directory_names(self):
        """Regression for #92: a repository cloned outside of the `<organization>/<repository>`
        convention must be named after its remote, not after the directories it lives in.
        """
        path = self.make_repository("dev", "tutorials", remote="git@github.com:jlom/tutorials.git")
        connector = GitConnector("dev/tutorials", path)
        self.assertEqual(connector.name, "jlom/tutorials")
        self.assertEqual(connector.path, path)

    def test_name_from_https_remote(self):
        path = self.make_repository("myrepo", remote="https://github.com/acme/myrepo.git")
        self.assertEqual(GitConnector("whatever/myrepo", path).name, "acme/myrepo")

    def test_name_from_non_origin_remote(self):
        path = self.make_repository("myrepo", remote=None)
        Repo(path).create_remote("upstream", "git@github.com:acme/upstreamed.git")
        self.assertEqual(GitConnector("whatever/myrepo", path).name, "acme/upstreamed")

    def test_origin_remote_wins_over_others(self):
        path = self.make_repository("myrepo", remote="git@github.com:acme/origin-repo.git")
        Repo(path).create_remote("upstream", "git@github.com:other/upstream-repo.git")
        self.assertEqual(GitConnector("whatever/myrepo", path).name, "acme/origin-repo")

    def test_fallback_to_repo_argument_without_remote(self):
        path = self.make_repository("myrepo", remote=None)
        self.assertEqual(GitConnector("acme/myrepo", path).name, "acme/myrepo")

    def test_fallback_to_repo_argument_on_unparseable_remote(self):
        path = self.make_repository("myrepo", remote="myrepo")
        self.assertEqual(GitConnector("acme/myrepo", path).name, "acme/myrepo")

    def test_absolute_path_without_remote_uses_directory_names(self):
        path = self.make_repository("acme", "myrepo", remote=None)
        self.assertEqual(GitConnector(path.as_posix()).name, "acme/myrepo")

    def test_path_that_is_not_a_repository_parses_the_name(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        connector = GitConnector("acme/myrepo", root)
        self.assertEqual(connector.name, "acme/myrepo")
        self.assertEqual(connector.path, root)


class TestGitConnectorPath(GitRepositoryMixin, OdevTestCase):
    def test_path_defaults_to_the_configured_repositories_directory(self):
        connector = GitConnector("acme/myrepo")
        self.assertEqual(connector.path, self.odev.config.paths.repositories / "acme/myrepo")

    def test_explicit_path_is_used_as_is(self):
        path = self.make_repository("myrepo")
        self.assertEqual(GitConnector("acme/myrepo", path).path, path)


class TestOdoobinAdditionalRepositories(GitRepositoryMixin, OdevTestCase):
    """End-to-end guard for #92 at the level that persists the repository name."""

    def test_additional_repositories_resolve_to_the_real_directory(self):
        path = self.make_repository("dev", "tutorials", remote="git@github.com:jlom/tutorials.git")
        module = path / "my_module"
        module.mkdir()
        (module / "__init__.py").touch()
        (module / "__manifest__.py").write_text("{'name': 'My Module'}", encoding="utf-8")

        self.odev.config.paths.repositories = path.parent

        process = OdoobinProcess.__new__(OdoobinProcess)
        process._additional_addons_paths = [path]

        repository = next(process.additional_repositories)
        self.assertEqual(repository.name, "jlom/tutorials")
        self.assertEqual(repository.path, path, "the repositories root must not be duplicated in the path")
