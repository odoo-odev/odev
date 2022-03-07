"""Downloads a dump from a SaaS or SH database."""

import gzip
import os
import re
import shutil
import subprocess
import tempfile
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

from odev.exceptions import CommandAborted, SHConnectionError, SHDatabaseTooLarge
from odev.structures import commands
from odev.utils import logging, request
from odev.utils.credentials import CredentialsHelper
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
    database_required = False
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
    ]

    def __init__(self, args: Namespace):
        super().__init__(args)
        self.destination = args.destination
        self.mode = "online" if re_url.match(args.source) else "local"

        if self.mode == "online":
            self.source = self.sanitize_url(f"""{'https://' if not re_http.match(args.source) else ''}{args.source}""")
            self.database = args.database
        else:
            self.database = args.source

    def sanitize_url(self, url, remove_after=".odoo.com"):
        return url[: url.index(remove_after) + len(remove_after)]

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
        if not self.db_exists(self.database):
            _logger.error(f"Database {self.database} doesn't exist or is not a Odoo database")
            return 1

        _logger.info(f"Generating dump for your local database {self.database}")

        is_db_clean = bool(
            self.run_queries("SELECT value FROM ir_config_parameter where key ='database.enterprise_code'")
        )

        timestamp = datetime.now().strftime("%Y%m%d")
        zip_filename = f"{timestamp}-{self.database}{'_clean' if is_db_clean else ''}_dump.zip"
        zip_path = Path(self.config["odev"].get("paths", "dumps"), zip_filename)

        if os.path.isfile(zip_path) and _logger.confirm(f"{zip_path} already exist do you want override it?"):
            os.remove(zip_path)

        with tempfile.TemporaryDirectory() as tmpdirname:
            dump_path = os.path.join(tmpdirname, "dump.sql")

            filestores_root = Path.home() / ".local/share/Odoo/filestore"
            filestore_path = filestores_root / self.database

            with ZipFile(zip_path, "w") as archive:
                if os.path.isdir(filestore_path) and _logger.confirm("Do you want to include your local filestores?"):
                    for root, dirs, files in os.walk(filestore_path):

                        clean_root = f"filestores/{root[len(str(filestore_path)):]}"

                        for file in files:
                            archive.write(os.path.join(root, file), os.path.join(clean_root, file))
                        for directory in dirs:
                            archive.write(os.path.join(root, directory), os.path.join(clean_root, directory))
                else:
                    filestore_path = os.path.join(tmpdirname, "filestores")

                    os.mkdir(filestore_path)
                    archive.write(filestore_path, "filestores")

                subprocess.run(
                    f"pg_dump -d {self.database} > {dump_path}", shell=True, check=True, stdout=subprocess.DEVNULL
                )
                archive.write(dump_path, "dump.sql")

        if not is_db_clean:
            _logger.warning("This is a cleaned database, don't use it on a production server")

        _logger.success(f"Dump {zip_path} successfully created")

    def dump_online(self):
        # ---------------------------------------------------------------------
        # Find out on which platform the database is running (SaaS or SH)
        # ---------------------------------------------------------------------
        _logger.info(f"Logging you in to {self.source} support console")

        support_url = f"{self.source}/_odoo/support"
        support_login_url = f"{support_url}/login"

        res = request.get(support_login_url)
        platform = "saas"

        if not self._check_response_status(res):
            # Retry without '/login' as the support page on odoo.sh is not database-dependant
            res = request.get(support_url)
            if not self._check_response_status(res):
                raise SHConnectionError(
                    f"Error fetching webpage, check the URL and try again [{res.status_code} - {res.reason}]"
                )
            platform = "sh"

        assert platform in ("saas", "sh")

        # ---------------------------------------------------------------------
        # Login to the support page
        # ---------------------------------------------------------------------

        with CredentialsHelper() as creds:
            login = creds.get("odoo.login", "Odoo login:", self.login)
            passwd = creds.secret("odoo.passwd", f"Odoo password for {login}:", self.password)

        reason = self.args.reason or _logger.ask("Reason (optional):")

        login_url = support_login_url if platform == "saas" else res.history[-1].headers.get("Location")

        res = request.post(
            login_url,
            data={
                "login": login,
                "password": passwd,
                "reason": reason,
                "csrf_token": self._get_response_data(res, re_csrf, "CSRF token"),
            },
            cookies={"session_id": res.cookies.get("session_id")},
            follow_redirects=False,
        )

        self._check_session(res)

        if platform == "sh":
            redirect = self._get_response_data(res, re_redirect, "redirect path")
            login_url = res.headers.get("Location")
            support_url = f"https://www.odoo.sh{redirect}"

        res = request.get(support_url, cookies={"session_id": res.cookies.get("session_id")})
        _logger.success(f"Successfully logged-in to {login_url}")

        # ---------------------------------------------------------------------
        # Get the link the the dump file and download it
        # ---------------------------------------------------------------------

        database_name = self.database or self._get_response_data(res, re_database, "database name")

        _logger.info(f"About to download dump file for {database_name}")

        ext = "dump" if platform == "saas" else "sql.gz"
        if _logger.confirm("Do you want to include the filestore?"):
            ext = "zip"

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
            overwrite = _logger.confirm("Do you wish to overwrite this file?")
            if not overwrite:
                raise CommandAborted()

        dump_url = self._get_dump_url_for_platform(res, platform, ext)

        if dump_url:
            if not re_http.match(dump_url):
                dump_url = "https://" + dump_url

            _logger.info(f"Downloading dump from {dump_url} to {destfile}...")
            _logger.warning("This may take a while, please be patient...")

            res = request.get(dump_url, cookies={"session_id": res.cookies.get("session_id")})

            if not self._check_response_status(res):
                _logger.warning(
                    "This database cannot be downloaded automatically, "
                    "maybe it is too big to be dumped in which case "
                    "please contact the SaaS Support team and ask them for a dump of the database"
                )

                raise SHDatabaseTooLarge(f"Error downloading dump from {dump_url}")

            with open(destfile, "wb") as file:
                file.write(res.content)

        elif _logger.confirm(f"Do you want to download the last daily backup for {database_name}?"):
            ext = "sql.gz"
            destfile = f"{base_dump_filename}.{ext}"
            sh_database = self._get_response_data(res, re_database, "database name")
            sh_build = sh_database.split("-")[-1]
            sh_path = f"/home/odoo/backup.daily/{sh_database}_daily.{ext}"
            ssh_url = f"{sh_build}@{self.source.split('/')[2]}"

            with SSHClient(url=ssh_url) as ssh:
                _logger.info(f"Downloading dump from {ssh_url}:{sh_path} to {destfile}...")
                _logger.warning("This may take a while, please be patient...")

                res = ssh.download(sh_path, destfile)

        self._check_dump(destfile)

        if ext == "sql.gz":
            _logger.info(f"Extracting `{base_dump_filename}.sql`")
            with gzip.open(destfile, "rb") as f_in:
                with open(f"{base_dump_filename}.sql", "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

        _logger.success("Successfully downloaded dump file")

        return 0

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

    def _get_dump_url_for_platform(self, res, platform, ext):
        dump_url = None

        if platform == "sh":
            token = self._get_response_data(res, re_sh_token, "Odoo SH token")
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

        elif platform == "saas":
            dump_url = f"{self.source}/saas_worker/dump.{ext}"

        return dump_url

    def _check_dump(self, path):
        if not os.path.isfile(path):
            raise Exception("Error while saving dump file to disk")
