import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from odev.common import ssh_hosts
from odev.common.connectors.git import GitConnector
from odev.common.errors import ConnectorError
from odev.common.ssh_hosts import SshDestination, UntrustedHostError

from tests.fixtures import OdevTestCase


HOST = "git.example.com"


class TestSshDestination(OdevTestCase):
    def test_scp_like_url(self):
        self.assertEqual(
            SshDestination.parse("git@git.example.com:group/project.git"),
            SshDestination(HOST, user="git"),
        )

    def test_scp_like_url_without_user(self):
        self.assertEqual(SshDestination.parse("git.example.com:group/project.git"), SshDestination(HOST))

    def test_ssh_url_with_port(self):
        self.assertEqual(
            SshDestination.parse("ssh://git@git.example.com:2222/group/project.git"),
            SshDestination(HOST, 2222, "git"),
        )

    def test_ssh_url_without_port(self):
        self.assertEqual(SshDestination.parse("ssh://git.example.com/group/project.git"), SshDestination(HOST))

    def test_ssh_url_with_a_port_ssh_cannot_use(self):
        self.assertIsNone(SshDestination.parse("ssh://git@git.example.com:70000/group/project.git"))
        self.assertIsNone(SshDestination.parse("ssh://git@git.example.com:port/group/project.git"))

    def test_scp_like_url_to_an_address_in_brackets(self):
        self.assertIsNone(SshDestination.parse("git@[::1]:group/project.git"))

    def test_https_url(self):
        self.assertIsNone(SshDestination.parse("https://git.example.com/group/project.git"))

    def test_file_url(self):
        self.assertIsNone(SshDestination.parse("file:///srv/git/project.git"))

    def test_local_path(self):
        self.assertIsNone(SshDestination.parse("/srv/git/project.git"))
        self.assertIsNone(SshDestination.parse("./project.git"))


@skipUnless(shutil.which("ssh-keygen"), "OpenSSH is not installed")
class TestEnsureTrusted(OdevTestCase):
    """Run the real `ssh-keygen` against a throwaway known hosts file, with the network left out."""

    def setUp(self):
        super().setUp()
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.known_hosts = self.directory / "ssh" / "known_hosts"

        subprocess.run(  # noqa: S603
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "", "-f", (self.directory / "host_key").as_posix()],  # noqa: S607
            check=True,
        )
        self.public_key = (self.directory / "host_key.pub").read_text().strip()

        ssh_hosts._checked_hosts.clear()
        self.addCleanup(ssh_hosts._checked_hosts.clear)

    def options(self, **overrides: str) -> dict[str, str]:
        """The options ssh would resolve for the test host, pointing at the throwaway known hosts file."""
        return {
            "hostname": HOST,
            "port": "22",
            "stricthostkeychecking": "ask",
            "hashknownhosts": "no",
            "userknownhostsfile": f"{self.known_hosts.as_posix()} {self.known_hosts.as_posix()}2",
            "globalknownhostsfile": (self.directory / "global_known_hosts").as_posix(),
            **overrides,
        }

    def ensure_trusted(self, answer: bool, url: str = f"git@{HOST}:group/project.git", **overrides: str):
        """Check the test host, answering the prompt as told.

        Returns:
            The mocks standing in for the key scan and for the prompt.
        """
        options = self.options(**overrides)

        def scan_keys(options: dict[str, str]) -> list[str]:
            return [f"{ssh_hosts.known_name(options)} {self.public_key}"]

        with (
            patch.object(ssh_hosts, "resolve_options", return_value=options),
            patch.object(ssh_hosts, "scan_keys", side_effect=scan_keys) as scan,
            patch.object(ssh_hosts.console, "confirm", return_value=answer) as confirm,
        ):
            ssh_hosts.ensure_trusted(url)

        return scan, confirm

    def test_accepted_host_is_remembered(self):
        _, confirm = self.ensure_trusted(answer=True)

        confirm.assert_called_once()
        self.assertEqual(self.known_hosts.read_text(), f"{HOST} {self.public_key}\n")
        self.assertEqual(self.known_hosts.stat().st_mode & 0o777, 0o600)
        self.assertTrue(ssh_hosts.is_known(self.options()))

    def test_fingerprint_is_shown_before_asking(self):
        expected = subprocess.run(  # noqa: S603
            ["ssh-keygen", "-l", "-f", (self.directory / "host_key.pub").as_posix()],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()[1]

        with self.assertLogs(ssh_hosts.logger, "WARNING") as logs:
            self.ensure_trusted(answer=True)

        self.assertIn(f"ED25519 {expected}", "\n".join(logs.output))

    def test_refused_host_is_not_remembered(self):
        with self.assertRaises(UntrustedHostError):
            self.ensure_trusted(answer=False)

        self.assertFalse(self.known_hosts.exists())

    def test_refused_host_is_asked_about_again(self):
        with self.assertRaises(UntrustedHostError):
            self.ensure_trusted(answer=False)

        _, confirm = self.ensure_trusted(answer=True)
        confirm.assert_called_once()

    def test_known_host_is_not_asked_about(self):
        self.ensure_trusted(answer=True)
        ssh_hosts._checked_hosts.clear()

        scan, confirm = self.ensure_trusted(answer=False)

        scan.assert_not_called()
        confirm.assert_not_called()

    def test_host_is_checked_once_per_process(self):
        self.ensure_trusted(answer=True)

        with patch.object(ssh_hosts, "is_known") as is_known:
            self.ensure_trusted(answer=False)

        is_known.assert_not_called()

    def test_existing_entries_are_kept(self):
        self.known_hosts.parent.mkdir(parents=True)
        self.known_hosts.write_text(f"other.example.com {self.public_key}")

        self.ensure_trusted(answer=True)

        self.assertEqual(
            self.known_hosts.read_text(),
            f"other.example.com {self.public_key}\n{HOST} {self.public_key}\n",
        )

    def test_port_is_part_of_the_name(self):
        self.ensure_trusted(answer=True, url=f"ssh://git@{HOST}:2222/group/project.git", port="2222")

        self.assertEqual(self.known_hosts.read_text(), f"[{HOST}]:2222 {self.public_key}\n")
        self.assertTrue(ssh_hosts.is_known(self.options(port="2222")))
        self.assertFalse(ssh_hosts.is_known(self.options()))

    def test_host_key_alias_is_the_name(self):
        self.ensure_trusted(answer=True, hostkeyalias="forge")

        self.assertEqual(self.known_hosts.read_text(), f"forge {self.public_key}\n")

    def test_host_key_alias_carries_no_port(self):
        self.ensure_trusted(answer=True, hostkeyalias="forge", port="2222")

        self.assertEqual(self.known_hosts.read_text(), f"forge {self.public_key}\n")

    def test_names_are_hashed_when_configured(self):
        self.ensure_trusted(answer=True, hashknownhosts="yes")

        self.assertNotIn(HOST, self.known_hosts.read_text())
        self.assertTrue(ssh_hosts.is_known(self.options()))

    def test_policy_that_does_not_ask_is_left_to_ssh(self):
        for policy in ("false", "accept-new", "true"):
            with self.subTest(policy=policy):
                scan, confirm = self.ensure_trusted(answer=False, stricthostkeychecking=policy)

                scan.assert_not_called()
                confirm.assert_not_called()

    def test_batch_mode_is_left_to_ssh(self):
        scan, confirm = self.ensure_trusted(answer=False, batchmode="yes")

        scan.assert_not_called()
        confirm.assert_not_called()

    def test_host_behind_a_proxy_is_left_to_ssh(self):
        for option in ("proxyjump", "proxycommand"):
            with self.subTest(option=option):
                scan, confirm = self.ensure_trusted(answer=False, **{option: "bastion"})

                scan.assert_not_called()
                confirm.assert_not_called()

    def test_custom_ssh_command_is_left_alone(self):
        with patch.dict(ssh_hosts.os.environ, {"GIT_SSH_COMMAND": "ssh -F /dev/null"}):
            scan, confirm = self.ensure_trusted(answer=False)

        scan.assert_not_called()
        confirm.assert_not_called()

    def test_bypassed_prompt_refuses_the_host(self):
        with (
            patch.object(ssh_hosts, "resolve_options", return_value=self.options()),
            patch.object(ssh_hosts, "scan_keys", return_value=[f"{HOST} {self.public_key}"]),
            ssh_hosts.console.force_bypass_prompt(force=True),
            self.assertRaises(UntrustedHostError),
        ):
            ssh_hosts.ensure_trusted(f"git@{HOST}:group/project.git")

        self.assertFalse(self.known_hosts.exists())

    def test_ssh_reports_its_policy_in_the_words_expected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".conf") as config:
            process = subprocess.run(  # noqa: S603
                ["ssh", "-F", config.name, "-G", "-o", "StrictHostKeyChecking=ask", "-l", "git", "--", HOST],  # noqa: S607
                check=True,
                capture_output=True,
                text=True,
            )

        options = dict(line.split(" ", 1) for line in process.stdout.splitlines() if " " in line)
        self.assertEqual(options["hostname"], HOST)
        self.assertEqual(options["user"], "git")
        self.assertTrue(ssh_hosts.asks_about_new_hosts(options))

    def test_silent_host_is_left_to_git(self):
        with (
            patch.object(ssh_hosts, "resolve_options", return_value=self.options()),
            patch.object(ssh_hosts, "scan_keys", return_value=[]),
            patch.object(ssh_hosts.console, "confirm") as confirm,
        ):
            ssh_hosts.ensure_trusted(f"git@{HOST}:group/project.git")

        confirm.assert_not_called()
        self.assertFalse(self.known_hosts.exists())
        self.assertIn(HOST, ssh_hosts._checked_hosts)

    def test_https_url_is_not_checked(self):
        with patch.object(ssh_hosts, "resolve_options") as resolve_options:
            ssh_hosts.ensure_trusted(f"https://{HOST}/group/project.git")

        resolve_options.assert_not_called()

    def test_rewritten_url_is_the_one_checked(self):
        connector = GitConnector(f"https://{HOST}/group/project", self.directory / "clone")
        rewrite = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.git@{HOST}:.insteadOf",
            "GIT_CONFIG_VALUE_0": f"https://{HOST}/",
        }

        with (
            patch.dict(ssh_hosts.os.environ, rewrite),
            patch.object(GitConnector, "remote_url", f"https://{HOST}/group/project.git"),
            patch.object(ssh_hosts, "ensure_trusted") as ensure_trusted,
        ):
            connector._ensure_host_trusted()

        ensure_trusted.assert_called_once_with(f"git@{HOST}:group/project.git")

    def test_clone_stops_before_the_progress_bar(self):
        connector = GitConnector(f"{HOST}/group/project", self.directory / "clone")

        with (
            patch.object(ssh_hosts, "resolve_options", return_value=self.options()),
            patch.object(ssh_hosts, "scan_keys", return_value=[f"{HOST} {self.public_key}"]),
            patch.object(ssh_hosts.console, "confirm", return_value=False),
            patch.object(connector, "_git_progress") as git_progress,
            self.assertRaises(ConnectorError) as raised,
        ):
            connector.clone()

        git_progress.assert_not_called()
        self.assertIn(HOST, str(raised.exception))
