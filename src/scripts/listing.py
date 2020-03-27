# -*- coding: utf-8 -*-

from clint.textui import puts, indent, columns, colored
import re

from . import script
from .. import utils


re_flag_all = re.compile(r'\s(-.*a.*|--all)\s')


class ListingScript(script.Script):

    titles = [
        'Database',
        'Status',
        'Version',
        'PID',
        'Port',
        'URL',
        'Filestore',
    ]

    def col_width(self, col_data, max_width=None):
        """
        Calculate the optimal width for a column based on its data.
        """

        width = 0
        for s in col_data:
            if s is not None and len(str(s)) > width:
                width = len(str(s))

        if max_width is not None and width > max_width:
            width = max_width

        return width

    def run(self, database, options):
        """
        Lists local Odoo names.
        """

        names = self.db_list()
        statuses = []
        versions = []
        pids = []
        ports = []
        urls = []
        filestores = []

        for name in names:
            status = self.db_runs(name)

            statuses.append(colored.green('running') if status else colored.red('inactive'))
            versions.append('%s (%s)' % (self.db_version_clean(name), 'enterprise' if self.db_enterprise(name) else 'standard'))
            filestores.append(self.db_filestore(name))

            if status:
                pids.append(self.db_pid(name))
                ports.append(self.db_port(name))
                urls.append(self.db_url(name))
            else:
                pids.append('')
                ports.append('')
                urls.append('')

        w_names = self.col_width(names + [self.titles[0]])
        w_statuses = self.col_width(statuses + [self.titles[1]], len('inactive'))
        w_versions = self.col_width(versions + [self.titles[2]])
        w_pids = self.col_width(pids + [self.titles[3]])
        w_ports = self.col_width(ports + [self.titles[4]])
        w_urls = self.col_width(urls + [self.titles[5]], 40)
        w_filestores = self.col_width(filestores + [self.titles[6]], 80)

        hbar = '+'.join([
            '-' * (w_names + 2),
            '-' * (w_statuses + 2),
            '-' * (w_versions + 2),
            '-' * (w_pids + 2),
            '-' * (w_ports + 2),
            '-' * (w_urls + 2),
            '-' * (w_filestores + 2),
        ])
        hbar = '+%s+' % (hbar)

        puts(hbar)
        puts(columns(
            ['|', 1],
            [colored.green(self.titles[0]), w_names],
            ['|', 1],
            [colored.green(self.titles[1]), w_statuses],
            ['|', 1],
            [colored.green(self.titles[2]), w_versions],
            ['|', 1],
            [colored.green(self.titles[3]), w_pids],
            ['|', 1],
            [colored.green(self.titles[4]), w_ports],
            ['|', 1],
            [colored.green(self.titles[5]), w_urls],
            ['|', 1],
            [colored.green(self.titles[6]), w_filestores],
            ['|', 1],
        ))
        puts(hbar)

        for name, status, version, pid, port, url, filestore in zip(names, statuses, versions, pids, ports, urls, filestores):

            pid = str(pid) if pid else ''
            port = str(port) if port else ''
            url = str(url) if url else ''

            puts(columns(
                ['|', 1],
                [name, w_names],
                ['|', 1],
                [status, w_statuses],
                ['|', 1],
                [version, w_versions],
                ['|', 1],
                [pid, w_pids],
                ['|', 1],
                [port, w_ports],
                ['|', 1],
                [url, w_urls],
                ['|', 1],
                [filestore, w_filestores],
                ['|', 1],
            ))

        puts(hbar)

        return 0
