"""Trust the keys of SSH hosts on behalf of the user, before a live display hides the question ssh asks."""

import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path
from subprocess import CompletedProcess, SubprocessError, run as run_subprocess
from typing import NamedTuple
from urllib.parse import urlparse

from odev.common import string
from odev.common.console import console
from odev.common.errors import OdevError
from odev.common.logging import logging


SCP_URL_PATTERN = re.compile(r"^(?:(?P<user>[^@/\s]+)@)?(?P<host>[^:/\s]+):(?P<path>[^/\s]\S*)$")
"""An SSH URL in the scp-like syntax git accepts, as in `git@github.com:organization/repository.git`."""

SSH_DEFAULT_PORT = 22
"""The port a known hosts file leaves out of the name of a host."""

SSH_KEY_TYPES = "ed25519,ecdsa,rsa"
"""The types of host keys asked of a host that is not known yet."""

SSH_SCAN_TIMEOUT = 5
"""How many seconds a host is given to hand its keys over."""

SSH_COMMAND_TIMEOUT = 30
"""How many seconds any OpenSSH binary is given to answer."""

SSH_ASKING_POLICY = "ask"
"""The value of `StrictHostKeyChecking` under which ssh asks about a new host, rather than trust or refuse it."""

SSH_COMMAND_VARIABLES = ("GIT_SSH_COMMAND", "GIT_SSH")
"""The environment variables replacing the ssh command git runs, with options this module cannot see."""

SSH_FINGERPRINT_PATTERN = re.compile(r"^\d+ (?P<fingerprint>\S+) .*\((?P<type>[^)]+)\)$")
"""A line of `ssh-keygen -l`, as in `256 SHA256:... example.com (ED25519)`."""


logger = logging.getLogger(__name__)


_checked_hosts: set[str] = set()
"""The names of the hosts this process already settled, which are not worth checking again."""


class UntrustedHostError(OdevError):
    """Raised when the user refuses the key of an SSH host."""

    def __init__(self, host: str):
        super().__init__(f"The key of host {host!r} is not trusted")
        self.host = host


class SshDestination(NamedTuple):
    """Where an SSH URL connects to."""

    host: str
    """The host as written in the URL: a domain, an address or an alias of the ssh configuration."""

    port: int | None = None
    """The port the URL names, or None to leave the choice to the ssh configuration."""

    user: str | None = None
    """The user the URL names, which `Match` blocks of the ssh configuration may depend on."""

    @classmethod
    def parse(cls, url: str) -> "SshDestination | None":
        """Read the destination out of a git URL.

        Args:
            url: A git URL, in any syntax git accepts.

        Returns:
            The destination, or None if git does not reach that URL over SSH.
        """
        url = url.strip()

        if "://" in url:
            parsed = urlparse(url)

            try:
                port = parsed.port
            except ValueError:
                # Not a port ssh could connect to, git says so in its own words
                return None

            if parsed.scheme not in ("ssh", "git+ssh") or not parsed.hostname:
                return None

            return cls(parsed.hostname, port, parsed.username)

        if (match := SCP_URL_PATTERN.match(url)) and not match["host"].startswith("["):
            return cls(match["host"], user=match["user"])

        return None


def _execute(arguments: list[str], input_text: str | None = None) -> CompletedProcess[str] | None:
    """Run an OpenSSH binary without a shell, as hosts are read from user input.

    Args:
        arguments: The binary and its arguments.
        input_text: What to feed the binary on its standard input.

    Returns:
        The completed process, or None if the binary is missing or did not answer.
    """
    logger.debug(f"Running process: {shlex.join(arguments)}")

    try:
        return run_subprocess(  # noqa: S603 - no shell, and the binaries are OpenSSH's
            arguments,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=SSH_COMMAND_TIMEOUT,
        )
    except (OSError, SubprocessError) as error:
        logger.debug(f"Failed to run {arguments[0]!r}: {error}")
        return None


def resolve_options(destination: SshDestination) -> dict[str, str] | None:
    """Ask ssh what its configuration resolves a destination to, without connecting.

    Args:
        destination: The destination to resolve.

    Returns:
        The options of ssh by lowercase name, or None if ssh cannot tell.
    """
    arguments = ["ssh", "-G"]

    if destination.port is not None:
        arguments += ["-p", str(destination.port)]

    if destination.user is not None:
        arguments += ["-l", destination.user]

    process = _execute([*arguments, "--", destination.host])

    if process is None or process.returncode:
        return None

    options: dict[str, str] = {}

    for line in process.stdout.splitlines():
        name, _, value = line.strip().partition(" ")
        options.setdefault(name.lower(), value.strip())

    return options if "hostname" in options else None


def known_name(options: dict[str, str]) -> str:
    """The name ssh records a host under in a known hosts file.

    Args:
        options: The options ssh resolved for the host.

    Returns:
        The host key alias as it is, or the host name, with its port when that is not the default one.
    """
    if alias := options.get("hostkeyalias"):
        return alias

    name = options["hostname"]
    port = int(options.get("port") or SSH_DEFAULT_PORT)

    return name if port == SSH_DEFAULT_PORT else f"[{name}]:{port}"


def known_hosts_files(options: dict[str, str]) -> list[Path]:
    """The known hosts files ssh reads for a host.

    Args:
        options: The options ssh resolved for the host.

    Returns:
        The paths of the files, whether they exist or not, the one ssh writes to first.
    """
    return [
        Path(path).expanduser()
        for option in ("userknownhostsfile", "globalknownhostsfile")
        for path in shlex.split(options.get(option, ""))
        if path.lower() != "none"
    ]


def is_known(options: dict[str, str]) -> bool:
    """Look a host up in the known hosts files.

    Args:
        options: The options ssh resolved for the host.

    Returns:
        Whether one of the files already holds a key for the host.
    """
    name = known_name(options)

    for path in known_hosts_files(options):
        if not path.is_file():
            continue

        process = _execute(["ssh-keygen", "-F", name, "-f", path.as_posix()])

        if process is not None and not process.returncode and process.stdout.strip():
            return True

    return False


def scan_keys(options: dict[str, str]) -> list[str]:
    """Fetch the public keys a host presents.

    Args:
        options: The options ssh resolved for the host.

    Returns:
        Known hosts lines recording the host under the name ssh looks it up by, empty if it did not answer.
    """
    process = _execute(
        [
            "ssh-keyscan",
            "-T",
            str(SSH_SCAN_TIMEOUT),
            "-p",
            options.get("port") or str(SSH_DEFAULT_PORT),
            "-t",
            SSH_KEY_TYPES,
            "--",
            options["hostname"],
        ]
    )

    if process is None:
        return []

    name = known_name(options)
    keys: list[str] = []

    for line in process.stdout.splitlines():
        if not line.strip() or line.startswith("#"):
            continue

        _, _, key = line.strip().partition(" ")
        keys.append(f"{name} {key}")

    return keys


def fingerprints(keys: list[str]) -> list[str]:
    """Compute the fingerprints of scanned keys, as ssh shows them when it asks.

    Args:
        keys: Known hosts lines.

    Returns:
        One `TYPE fingerprint` per key ssh-keygen could read.
    """
    process = _execute(["ssh-keygen", "-l", "-f", "-"], input_text="\n".join(keys) + "\n")

    if process is None or process.returncode:
        return []

    return [
        f"{match['type']} {match['fingerprint']}"
        for line in process.stdout.splitlines()
        if (match := SSH_FINGERPRINT_PATTERN.match(line.strip()))
    ]


def _hash_names(keys: list[str]) -> list[str]:
    """Hash the host names of known hosts lines, for users who set `HashKnownHosts`."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "known_hosts"
        path.write_text("\n".join(keys) + "\n")
        process = _execute(["ssh-keygen", "-H", "-f", path.as_posix()])

        if process is None or process.returncode:
            return keys

        return path.read_text().splitlines()


def remember(options: dict[str, str], keys: list[str]) -> Path | None:
    """Record the keys of a host in the known hosts file of the user.

    Args:
        options: The options ssh resolved for the host.
        keys: Known hosts lines to append.

    Returns:
        The file the keys were added to, or None if the ssh configuration names no such file.
    """
    files = [Path(path).expanduser() for path in shlex.split(options.get("userknownhostsfile", ""))]

    if not files or files[0].as_posix().lower() == "none":
        return None

    path = files[0]

    if options.get("hashknownhosts") == "yes":
        keys = _hash_names(keys)

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    content = path.read_text()

    with path.open("a") as known_hosts:
        if content and not content.endswith("\n"):
            known_hosts.write("\n")

        known_hosts.write("\n".join(keys) + "\n")

    return path


def asks_about_new_hosts(options: dict[str, str]) -> bool:
    """Tell whether ssh would stop to ask about a host it does not know, and odev can ask in its place.

    Args:
        options: The options ssh resolved for the host.

    Returns:
        False when ssh trusts or refuses new hosts by itself, or reaches the host in a way a key scan cannot follow.
    """
    if options.get("stricthostkeychecking") != SSH_ASKING_POLICY or options.get("batchmode") == "yes":
        return False

    # A key scan connects directly: behind a proxy it reaches nothing, or another machine than ssh would
    return all(options.get(option, "none").lower() == "none" for option in ("proxyjump", "proxycommand"))


def ensure_trusted(url: str) -> None:
    """Ask the user whether to trust the host of a git URL, unless ssh already does or would not ask.

    Args:
        url: The URL git is about to reach.

    Raises:
        UntrustedHostError: The user refused the key of the host.
    """
    destination = SshDestination.parse(url)

    if destination is None or shutil.which("ssh") is None:
        return

    if any(os.environ.get(variable) for variable in SSH_COMMAND_VARIABLES):
        return

    options = resolve_options(destination)

    if options is None or not asks_about_new_hosts(options):
        return

    name = known_name(options)

    if name in _checked_hosts:
        return

    if not is_known(options):
        keys = scan_keys(options)
        host_fingerprints = fingerprints(keys)

        if not host_fingerprints:
            # Unreachable host or unreadable answer: git reports what is wrong better than a guess would
            _checked_hosts.add(name)
            return

        logger.warning(
            f"The authenticity of host {name!r} cannot be established, it presents the following keys:\n"
            + string.join_bullet(host_fingerprints)
        )

        if not console.confirm("Trust this host and continue?", default=False):
            raise UntrustedHostError(name)

        if (path := remember(options, keys)) is not None:
            logger.info(f"Added host {name!r} to {path.as_posix()}")

    _checked_hosts.add(name)
