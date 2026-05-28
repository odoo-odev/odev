"""Find custom fields (x_ prefix) that are not referenced anywhere in the database."""

import csv
import re
from io import StringIO

from odev.common import args, progress
from odev.common.commands import LocalDatabaseCommand
from odev.common.console import TableHeader
from odev.common.logging import logging


logger = logging.getLogger(__name__)


class UnusedFieldsCommand(LocalDatabaseCommand):
    """Find custom fields (prefixed with x_) that appear unused across views, server actions,
    automations, filters, record rules, mail templates, reports, exports, and computed/related
    field definitions.
    """

    _name = "unused-fields"
    _aliases = ["uf"]

    csv = args.Flag(aliases=["--csv"], description="Format output as CSV.")

    _CONTENT_QUERIES: list[tuple[str, list[str]]] = [
        ("SELECT arch_db FROM ir_ui_view", ["arch_db"]),
        ("SELECT code FROM ir_act_server WHERE code IS NOT NULL", ["code"]),
        ("SELECT compute, related FROM ir_model_fields WHERE compute IS NOT NULL OR related IS NOT NULL", ["compute", "related"]),
        ("SELECT domain FROM ir_filters WHERE domain IS NOT NULL", ["domain"]),
        ("SELECT domain_force FROM ir_rule WHERE domain_force IS NOT NULL", ["domain_force"]),
    ]
    """Queries that always exist in an Odoo database."""

    _OPTIONAL_CONTENT_QUERIES: list[tuple[str, str, list[str]]] = [
        ("mail_template", "SELECT body_html, subject FROM mail_template", ["body_html", "subject"]),
        ("ir_actions_report", "SELECT help FROM ir_actions_report WHERE help IS NOT NULL", ["help"]),
        ("ir_exports_line", "SELECT name FROM ir_exports_line WHERE name IS NOT NULL", ["name"]),
        ("base_automation", "SELECT filter_pre_domain, filter_domain FROM base_automation", ["filter_pre_domain", "filter_domain"]),
    ]
    """Queries that require checking table existence first."""

    def run(self):
        with progress.spinner("Collecting x_ fields"):
            fields = self._fetch_x_fields()

        if not fields:
            logger.info("No custom x_ fields found in this database.")
            return

        logger.debug(f"Found {len(fields)} x_ fields, scanning for usage...")

        with progress.spinner("Scanning database for field usage"):
            all_content = self._collect_search_content()

        with progress.spinner("Detecting unused fields"):
            unused = self._find_unused(fields, all_content)

        if not unused:
            logger.info("All custom x_ fields appear to be in use.")
            return

        headers = [
            TableHeader("Model"),
            TableHeader("Field Name"),
            TableHeader("Description"),
        ]
        rows = [[model, field_name, self._extract_label(description)] for model, field_name, description in unused]

        if self.args.csv:
            self.print(self._format_csv([h.title for h in headers], rows))
        else:
            self.table(headers, rows, title=f"Unused x_ Fields ({len(unused)} of {len(fields)})")
            self.console.clear_line()

    def _psql(self):
        """Return a connector to the target database (not the default 'postgres' db)."""
        return self._database.psql(self._database.name)

    def _fetch_x_fields(self) -> list[tuple[str, str, str]]:
        """Return all (model, name, field_description) rows for fields starting with x_."""
        with self._psql() as psql:
            result = psql.query(
                "SELECT model, name, field_description FROM ir_model_fields WHERE name LIKE 'x_%'"
                " AND name NOT LIKE 'x\\_plan%'"
            )
        return result or []

    def _table_exists(self, psql, table: str) -> bool:
        """Check whether a table exists in the database."""
        result = psql.query(
            f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table}'"
        )
        return bool(result and result[0][0])

    def _collect_search_content(self) -> str:
        """Gather all searchable content from the database and return it as one concatenated string."""
        parts: list[str] = []

        with self._psql() as psql:
            for query, _ in self._CONTENT_QUERIES:
                rows = psql.query(query) or []
                for row in rows:
                    parts.extend(str(v) for v in row if v)

            for table, query, _ in self._OPTIONAL_CONTENT_QUERIES:
                if self._table_exists(psql, table):
                    rows = psql.query(query) or []
                    for row in rows:
                        parts.extend(str(v) for v in row if v)

        return " ".join(parts)

    def _find_unused(
        self, fields: list[tuple[str, str, str]], content: str
    ) -> list[tuple[str, str, str]]:
        """Return fields whose name does not appear (as a whole word) in the content string."""
        unused = []
        for model, field_name, description in fields:
            pattern = rf"\b{re.escape(field_name)}\b"
            if not re.search(pattern, content):
                unused.append((model, field_name, description))
        return sorted(unused)

    def _extract_label(self, description) -> str:
        """Return a plain string label from a field_description value (may be dict or str)."""
        if isinstance(description, dict):
            return description.get("en_US") or next(iter(description.values()), "")
        return description or ""

    def _format_csv(self, headers: list[str], rows: list[list[str]]) -> str:
        """Format rows as a CSV string."""
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return output.getvalue()
