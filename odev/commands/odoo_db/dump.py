"""Downloads a dump from a SaaS or SH database."""

import os
import re
import subprocess
import tempfile
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import enlighten
from paramiko import PasswordRequiredException

from odev.exceptions import CommandAborted, SHConnectionError, SHDatabaseTooLarge
from odev.structures import commands
from odev.utils import logging, request
from odev.utils.credentials import CredentialsHelper
from odev.utils.odoo import get_database_name_from_url, sanitize_url
from odev.utils.os import mkdir
from odev.utils.ssh import SSHClient


_logger = logging.getLogger(__name__)


re_http = re.compile(r"^https?://")
re_url = re.compile(r"^https?:\/\/|(?:[a-zA-Z0-9-_]+(?:\.dev)?\.odoo\.(com|sh)|localhost|127\.0\.0\.[0-9]+)")
re_redirect = re.compile(r'href="([^"]+)')
re_csrf = re.compile(r'name="csrf_token"\svalue="([a-z0-9]+)"')
re_database = re.compile(r"<h2>Current database: <a[^>]+>([^<]+)")
re_directory = re.compile(r"(/|\\)$")
re_sh_dump = re.compile(r'href="//([a-z0-9]+.odoo.com/_long/paas/build/[0-9]+/dump)[a-z.]+\?token')
re_sh_token = re.compile(r'\?token=([^"]+)')
re_sh_mode = re.compile(r"Mode(?:.|\s)+?(?:<td>)([^<]+)")


class DumpCommand(commands.LocalDatabaseCommand, commands.OdooComCliMixin):
    """
    Download a dump of a SaaS or SH database and save it locally.
    You can choose whether to download the filestore or not.
    """

    name = "dump"
    add_database_argument = False
    arguments = [
        {
            "aliases": ["source"],
            "metavar": "DATABASE|URL",
            "help": """
            One of the following:
                - a local odoo database,
                - URL to the database to dump, in the form of https://db.odoo.com
            """,
        },
        {
            "aliases": ["destination"],
            "metavar": "dest",
            "nargs": "?",
            "help": "Directory to which the dumped file will be saved once downloaded",
        },
        {
            "aliases": ["-x", "--no-extract"],
            "dest": "extract",
            "action": "store_false",
            "help": "Don't extract dump.sql from the compressed dump file once downloaded",
        },
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.destination = args.destination
        self.mode = "online" if re_url.match(args.source) else "local"

        if self.mode == "online":
            self.source = sanitize_url(args.source)
        else:
            self.source = self.database = args.source

        self.extract = args.extract

    def _check_response_status(self, res):
        return 200 <= res.status_code < 400

    def run(self):
        """
        Dumps a SaaS or SH database.
        """
        if self.mode == "online":
            return self.dump_online()
        else:
            return self.dump_localdb()

    def dump_localdb(self):
        if not self.db_exists(self.source):
            _logger.error(f"Database {self.source} doesn't exist or is not a Odoo database")
            return 1

        _logger.info(f"Generating dump for your local database {self.source}")

        is_db_clean = bool(
            self.run_queries("SELECT value FROM ir_config_parameter where key ='database.enterprise_code'")
        )

        timestamp = datetime.now().strftime("%Y%m%d")
        zip_filename = f"{timestamp}-{self.source}{'_clean' if is_db_clean else ''}_dump.zip"
        zip_path = Path(self.destination or self.config["odev"].get("paths", "dump"))
        zip_path_full = Path(zip_path, zip_filename)

        if not os.path.isdir(zip_path):
            os.mkdir(zip_path)
            _logger.success(f"{zip_path} folder successfully created")
        else:
            if os.path.isfile(zip_path_full) and _logger.confirm(
                f"{zip_path_full} already exist do you want override it?"
            ):
                os.remove(zip_path_full)

        with tempfile.TemporaryDirectory() as tmpdirname:
            dump_path = os.path.join(tmpdirname, "dump.sql")

            filestore_root = Path.home() / ".local/share/Odoo/filestore"
            filestore_path = filestore_root / self.source

            with ZipFile(zip_path_full, "w") as archive:
                if os.path.isdir(filestore_path) and _logger.confirm("Do you want to include your local filestore?"):
                    for root, dirs, files in os.walk(filestore_path):

                        clean_root = f"filestore/{root[len(str(filestore_path)):]}"

                        for file in files:
                            archive.write(os.path.join(root, file), os.path.join(clean_root, file))
                        for directory in dirs:
                            archive.write(os.path.join(root, directory), os.path.join(clean_root, directory))
                else:
                    filestore_path = os.path.join(tmpdirname, "filestore")

                    os.mkdir(filestore_path)
                    archive.write(filestore_path, "filestore")

                subprocess.run(
                    f"pg_dump -d {self.source} > {dump_path}", shell=True, check=True, stdout=subprocess.DEVNULL
                )
                archive.write(dump_path, "dump.sql")

        if not is_db_clean:
            _logger.warning("This is a cleaned database, don't use it on a production server")

        _logger.success(f"Dump {zip_path_full} successfully created")

    def dump_online(self):
        _logger.info(f"Logging you in to {self.source} support console")

        with CredentialsHelper() as creds:
            login = creds.get("odoo.login", "Odoo login:", self.login)

        filestore = _logger.confirm("Do you want to include the filestore?")
        ext = "zip" if filestore else "sql.gz"

        database_name = get_database_name_from_url(self.source)

        _logger.info(f"About to download dump file for {database_name}")

        destdir = self.destination or os.path.join(self.config["odev"].get("paths", "dump"), database_name)
        destdir += "/" if not re_directory.search(destdir) else ""

        if not os.path.isdir(destdir):
            mkdir(destdir)

        timestamp = datetime.now().strftime("%Y%m%d")
        base_dump_filename = f"{destdir}{timestamp}_{database_name}.dump"
        destfile = f"{base_dump_filename}.{ext}"

        if os.path.isfile(destfile):
            _logger.warning(
                f"The file {destfile} already exists, "
                f"indicating that you most probably already dumped this database today",
            )
            if _logger.confirm("Do you wish to use the already downloaded dump ?"):
                # self.argv is present if the dump command is called directly from the command line
                if self.argv:
                    raise CommandAborted()
                else:
                    return 0

        res = request.get(f"{self.source}/_odoo/support/login")
        if not self._check_response_status(res):
            destfile = self.dump_sh(login, destfile, ext)
        else:
            destfile = self.dump_saas(login, destfile, ext)

        self._check_dump(destfile)

        _logger.success("Successfully downloaded dump file")

        return 0

    def dump_saas(self, login, destfile, ext):
        dump_url = f"{self.source}/saas_worker/dump.{ext}"

        _logger.info(f"Downloading dump from {dump_url} to {destfile}...")
        _logger.warning("This may take a while, please be patient...")
        with CredentialsHelper() as creds:
            api_key = creds.secret(
                "odoo.api_key",
                f"Odoo api key for {login} (make sure debug mode is active on odoo.com to generate the key):",
            )
            params = {"support-login": login, "support-pass": api_key}
            with request.get(dump_url, params, stream=True) as response:
                if not self._check_response_status(response):
                    raise Exception(
                        "Access Error, verify that you have Tech Support access and that your odoo api key is correct"
                    )
                content_length = int(response.headers.get("Content-Length", False))
                bar_format = (
                    "{desc}{desc_pad}{percentage:3.0f}%|{bar}| "
                    "{count:!.2j}{unit} / {total:!.2j}{unit} [{elapsed}<{eta}, {rate:!.2j}{unit}/s]"
                )
                with open(destfile, "wb") as file, enlighten.get_manager(set_scroll=False) as manager, manager.counter(
                    total=float(content_length),
                    desc="downloading",
                    unit="B",
                    bar_format=bar_format,
                ) as pbar:
                    for block in response.iter_content(1024):
                        file.write(block)
                        pbar.update(float(len(block)))
            return destfile

    def dump_sh(self, login, destfile, ext):

        res = request.get(f"{self.source}/_odoo/support")
        if not self._check_response_status(res):
            raise SHConnectionError(
                f"Error fetching webpage, check the URL and try again [{res.status_code} - {res.reason}]"
            )

        login_url = res.history[-1].headers.get("Location")
        with CredentialsHelper() as creds:
            passwd = creds.secret("odoo.passwd", f"Odoo password for {login}:", self.password)
            res = request.post(
                login_url,
                data={
                    "login": login,
                    "password": passwd,
                    "csrf_token": self._get_response_data(res, re_csrf, "CSRF token"),
                },
                cookies={"session_id": res.cookies.get("session_id")},
                follow_redirects=False,
            )
            self._check_session(res)

        redirect = self._get_response_data(res, re_redirect, "redirect path")
        login_url = res.headers.get("Location")
        support_url = f"https://www.odoo.sh{redirect}"

        res = request.get(support_url, cookies={"session_id": res.cookies.get("session_id")})
        _logger.success(f"Successfully logged-in to {login_url}")

        # ---------------------------------------------------------------------
        # Get the link the the dump file and download it
        # ---------------------------------------------------------------------

        token = self._get_response_data(res, re_sh_token, "Odoo SH token")
        dump_url = False
        try:
            dump_url = self._get_response_data(res, re_sh_dump, "dump URL")
            dump_url = f"{dump_url}.{ext}?token={token}"
        except SHConnectionError:
            _logger.warning(
                "This database cannot be downloaded automatically through the support page, "
                "likely because it is too big to be dumped"
            )

            branch_mode = self._get_response_data(res, re_sh_mode, "environment")

            if branch_mode != "production":
                raise SHDatabaseTooLarge(f"Downloading large dumps is not supported for {branch_mode} databases")
        if dump_url:
            if not re_http.match(dump_url):
                dump_url = "https://" + dump_url

            _logger.info(f"Downloading dump from {dump_url} to {destfile}...")
            _logger.warning("This may take a while, please be patient...")

            with request.get(dump_url, cookies={"session_id": res.cookies.get("session_id")}, stream=True) as response:
                if not self._check_response_status(response):
                    _logger.warning(
                        "This database cannot be downloaded automatically, "
                        "maybe it is too big to be dumped in which case "
                        "please contact the SaaS Support team and ask them for a dump of the database"
                    )

                    raise SHDatabaseTooLarge(f"Error downloading dump from {dump_url}")

                with open(destfile, "wb") as file, enlighten.get_manager(set_scroll=False) as manager, manager.counter(
                    desc="downloading",
                    unit="B",
                    bar_format="{desc}{count:!.2j}{unit} [{elapsed}, {rate:!.2j}{unit}/s]",
                ) as pbar:
                    block_size = 1024
                    for block in response.iter_content(block_size):
                        file.write(block)
                        pbar.update(block_size)

        elif _logger.confirm("Do you want to download the last daily backup for the database?"):
            destfile = re.sub(".zip$", ".sql.gz", destfile)
            sh_database = self._get_response_data(res, re_database, "database name")
            sh_build = sh_database.split("-")[-1]
            sh_path = f"/home/odoo/backup.daily/{sh_database}_daily.sql.gz"
            ssh_url = f"{sh_build}@{self.source.split('/')[2]}"

            try:
                with SSHClient(url=ssh_url) as ssh:
                    _logger.info(f"Downloading dump from {ssh_url}:{sh_path} to {destfile}...")
                    _logger.warning("This may take a while, please be patient...")

                    res = ssh.download(sh_path, destfile)
            except PasswordRequiredException:
                raise Exception("Access Error, verify that your private key is set on your odoo.sh profile")
        else:
            raise CommandAborted()
        return destfile

    def _check_session(self, res):
        if not self._check_response_status(res) or "Location" not in res.headers:
            raise Exception("Error logging you in, check your credentials and try again")

        if not res.cookies.get("session_id"):
            raise Exception("Invalid session id, check your credentials and try again")

    def _get_response_data(self, res, regex, token_name="data"):
        match = re.findall(regex, res.text)

        if not match:
            raise SHConnectionError(f"Error fetching {token_name} in {res.url}")

        return match[~0]

    def _check_dump(self, path):
        if not os.path.isfile(path):
            raise Exception("Error while saving dump file to disk")
