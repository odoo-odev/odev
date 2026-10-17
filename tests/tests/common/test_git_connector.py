import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from git import Repo
from github import GithubException, UnknownObjectException

from odev.common.connectors.git import GitConnector, GithubConnector, RepositoryReference
from odev.common.errors import ConnectorError
from odev.common.odoobin import OdoobinProcess

from tests.fixtures import OdevTestCase


GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "odev",
    "GIT_AUTHOR_EMAIL": "odev@example.com",
    "GIT_COMMITTER_NAME": "odev",
    "GIT_COMMITTER_EMAIL": "odev@example.com",
}


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

    def test_github_has_no_nested_namespaces(self):
        with self.assertRaises(ConnectorError):
            GitConnector("https://github.com/acme/myrepo/tree/main")

    def test_longer_name_without_a_domain_raises(self):
        with self.assertRaises(ConnectorError):
            GitConnector("odoo/odoo/17.0")


class TestRepositoryReference(OdevTestCase):
    """A repository is hosted on GitHub unless its name or URL says otherwise."""

    def assertReference(self, repository: str, host: str, namespace: str, name: str):  # noqa: N802
        self.assertEqual(RepositoryReference.parse(repository), RepositoryReference(host, namespace, name))

    def test_name_of_two_parts_is_hosted_on_github(self):
        self.assertReference("acme/myrepo", "github.com", "acme", "myrepo")

    def test_longer_name_starts_with_its_host(self):
        self.assertReference("gitlab.com/group/project", "gitlab.com", "group", "project")
        self.assertReference("gitlab.com/group/subgroup/project", "gitlab.com", "group/subgroup", "project")

    def test_https_url(self):
        self.assertReference("https://gitlab.com/group/subgroup/project.git", "gitlab.com", "group/subgroup", "project")
        self.assertReference("https://gitlab.com/group/project/", "gitlab.com", "group", "project")

    def test_scp_like_ssh_url(self):
        self.assertReference(
            "git@gitlab.acme.com:group/subgroup/project.git", "gitlab.acme.com", "group/subgroup", "project"
        )

    def test_scp_like_ssh_url_without_user(self):
        self.assertReference("gitlab.com:group/project.git", "gitlab.com", "group", "project")
        self.assertReference("github.com:acme/myrepo.git", "github.com", "acme", "myrepo")

    def test_ssh_url_leaves_the_port_out_of_the_host(self):
        self.assertReference("ssh://git@GitLab.acme.com:2222/group/project.git", "gitlab.acme.com", "group", "project")

    def test_github_subdomains_are_github(self):
        self.assertReference("ssh://git@ssh.github.com:443/acme/myrepo.git", "github.com", "acme", "myrepo")
        self.assertReference("https://www.github.com/acme/myrepo", "github.com", "acme", "myrepo")

    def test_gitlab_page_url_stops_at_the_project(self):
        self.assertReference("https://gitlab.com/group/project/-/tree/main", "gitlab.com", "group", "project")

    def test_directory_is_named_as_on_github(self):
        self.assertReference("/srv/git/acme/myrepo.git", "github.com", "acme", "myrepo")
        self.assertReference("file:///srv/git/acme/myrepo.git", "github.com", "acme", "myrepo")

    def test_missing_namespace(self):
        self.assertIsNone(RepositoryReference.parse("myrepo"))
        self.assertIsNone(RepositoryReference.parse("https://gitlab.com/project"))

    def test_full_name_reads_back_to_the_same_reference(self):
        for repository in ("acme/myrepo", "gitlab.com/group/project", "gitlab.com/group/subgroup/project"):
            with self.subTest(repository=repository):
                reference = cast(RepositoryReference, RepositoryReference.parse(repository))
                self.assertEqual(reference.full_name, repository)


class TestGitConnectorHost(GitRepositoryMixin, OdevTestCase):
    """Names, paths and URLs must keep the host and every group of a repository not hosted on GitHub."""

    def test_github_repository(self):
        connector = GitConnector("https://github.com/acme/myrepo")
        self.assertEqual(connector.host, "github.com")
        self.assertEqual(connector.url, "https://github.com/acme/myrepo")
        self.assertEqual(connector.ssh_url, "git@github.com:acme/myrepo.git")

    def test_nested_repository_on_another_host(self):
        connector = GitConnector("https://gitlab.com/group/subgroup/project")
        self.assertEqual(connector.name, "gitlab.com/group/subgroup/project")
        self.assertEqual(connector.path, self.odev.config.paths.repositories / "gitlab.com/group/subgroup/project")
        self.assertEqual(connector.url, "https://gitlab.com/group/subgroup/project")
        self.assertEqual(connector.ssh_url, "git@gitlab.com:group/subgroup/project.git")
        self.assertEqual(GitConnector(connector.name), connector)

    def test_same_name_on_two_hosts_are_different_repositories(self):
        self.assertNotEqual(GitConnector("acme/myrepo"), GitConnector("gitlab.com/acme/myrepo"))

    def test_name_from_nested_remote(self):
        for remote in ("git@gitlab.com:group/subgroup/project.git", "https://gitlab.com/group/subgroup/project.git"):
            with self.subTest(remote=remote):
                path = self.make_repository("gitlab.com", "group", "subgroup", "project", remote=remote)
                self.assertEqual(GitConnector("whatever/project", path).name, "gitlab.com/group/subgroup/project")

    def test_remote_host_is_ignored_outside_of_its_directory(self):
        """A clone stored as `<organization>/<repository>` keeps that name whatever host its remote
        names: the host may be an alias of GitHub, and the name must resolve back to the clone.
        """
        for remote in (
            "git@github-work:acme/myrepo.git",
            "work:acme/myrepo.git",
            "git@gitlab.com:group/acme/myrepo.git",
        ):
            with self.subTest(remote=remote):
                path = self.make_repository("acme", "myrepo", remote=remote)
                self.assertEqual(GitConnector("acme/myrepo", path).name, "acme/myrepo")

    def test_remote_url_before_cloning(self):
        self.assertEqual(
            GitConnector("https://gitlab.com/group/project").remote_url, "git@gitlab.com:group/project.git"
        )

    def test_remote_url_keeps_the_port_of_an_ssh_url(self):
        url = "ssh://git@gitlab.acme.com:2222/group/project.git"
        self.assertEqual(GitConnector(url).remote_url, url)

    def test_remote_url_of_a_clone_is_its_remote(self):
        path = self.make_repository("myrepo", remote="https://github.com/acme/myrepo.git")
        self.assertEqual(GitConnector("acme/myrepo", path).remote_url, "https://github.com/acme/myrepo.git")


class TestGitConnectorDefaultBranch(GitRepositoryMixin, OdevTestCase):
    """The default branch is asked of git, so it resolves on any host and without an API token."""

    def make_clone(self, default_branch: str) -> Path:
        """Clone a throwaway repository whose default branch is the one given.
        :param default_branch: The branch the origin of the clone points its HEAD to.
        :return: The path to the clone.
        """
        origin = Repo(self.make_repository("acme", "origin", remote=None))
        origin.git.checkout("-b", default_branch)
        origin.git.commit(
            "--allow-empty", "-m", "Initial commit", env={"GIT_CONFIG_GLOBAL": "/dev/null"} | GIT_IDENTITY
        )

        path = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        Repo.clone_from(origin.working_dir, path)

        return path

    def test_default_branch_known_locally(self):
        path = self.make_clone("trunk")
        Repo(path).git.remote("set-url", "origin", "/nonexistent/acme/myrepo.git")
        self.assertEqual(GitConnector("acme/myrepo", path).default_branch, "trunk")

    def test_default_branch_pointing_to_a_deleted_branch_is_asked_of_the_remote(self):
        path = self.make_clone("trunk")
        Repo(path).git.symbolic_ref("refs/remotes/origin/HEAD", "refs/remotes/origin/renamed")
        self.assertEqual(GitConnector("acme/myrepo", path).default_branch, "trunk")

    def test_default_branch_asked_of_the_remote(self):
        path = self.make_clone("trunk")
        Repo(path).git.remote("set-head", "origin", "--delete")
        self.assertEqual(GitConnector("acme/myrepo", path).default_branch, "trunk")

    def test_default_branch_of_an_unreachable_remote(self):
        path = self.make_repository("myrepo", remote="/nonexistent/acme/myrepo.git")
        self.assertIsNone(GitConnector("acme/myrepo", path).default_branch)


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
