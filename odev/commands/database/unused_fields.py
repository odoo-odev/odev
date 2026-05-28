"""Find custom fields (x_ prefix) that are not referenced anywhere in the database."""

import csv
import re
from io import StringIO

from odev.common import args, progress
from odev.common.commands import LocalDatabaseCommand
from odev.common.console import TableHeader
from odev.common.logging import logging


logger = logging.getLogger(__name__)

# Field types where we skip the data-presence check entirely
_SKIP_DATA_CHECK = frozenset({"binary", "one2many", "many2many"})

# Reason labels shown in output
_REASON_NOT_REFERENCED = "not referenced"
_REASON_NO_DATA = "no data"


class UnusedFieldsCommand(LocalDatabaseCommand):
    """Find custom fields (prefixed with x_) that appear unused across views, server actions,
    automations, filters, record rules, mail templates, reports, exports, and computed/related
    field definitions. Also flags fields that are referenced in views but contain no meaningful
    data in the database.
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
            logger.info("No custom fields found in this database.")
            return

        logger.debug(f"Found {len(fields)} custom field(s), scanning for usage...")

        with progress.spinner("Scanning database for field usage"):
            all_content = self._collect_search_content()

        with progress.spinner("Detecting unused fields"):
            unused = self._find_unused(fields, all_content)

        if not unused:
            logger.info("All custom fields appear to be in use.")
            return

        headers = [
            TableHeader("Model"),
            TableHeader("Field Name"),
            TableHeader("Description"),
            TableHeader("Reason"),
        ]
        rows = [
            [model, field_name, self._extract_label(description), reason]
            for model, field_name, description, reason in unused
        ]

        if self.args.csv:
            self.print(self._format_csv([h.title for h in headers], rows))
        else:
            self.table(headers, rows, title=f"Unused x_ Fields ({len(unused)} of {len(fields)})")
            self.console.clear_line()

    def _psql(self):
        """Return a connector to the target database (not the default 'postgres' db)."""
        return self._database.psql(self._database.name)

    def _fetch_x_fields(self) -> list[tuple]:
        """Return all x_ fields (excluding x_plan) as (model, name, description, ttype, store)."""
        with self._psql() as psql:
            result = psql.query(
                "SELECT model, name, field_description, ttype, store "
                "FROM ir_model_fields WHERE name LIKE 'x_%' AND name NOT LIKE 'x\\_plan%'"
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

    def _find_unused(self, fields: list[tuple], all_content: str) -> list[tuple]:
        """Return (model, field_name, description, reason) for all unused fields.

        A field is unused if:
        - its name does not appear (as a whole word) anywhere in the scanned content, OR
        - it is referenced in content but is stored and contains no meaningful data.
        """
        not_referenced: list[tuple] = []
        to_check_data: list[tuple] = []

        for model, field_name, description, ttype, store in fields:
            pattern = rf"\b{re.escape(field_name)}\b"
            if not re.search(pattern, all_content):
                not_referenced.append((model, field_name, description, _REASON_NOT_REFERENCED))
            elif store and ttype not in _SKIP_DATA_CHECK:
                to_check_data.append((model, field_name, description, ttype))

        empty: list[tuple] = []
        if to_check_data:
            with self._psql() as psql:
                for model, field_name, description, ttype in to_check_data:
                    if not self._field_has_data(psql, model, field_name, ttype):
                        empty.append((model, field_name, description, _REASON_NO_DATA))

        return sorted(not_referenced + empty)

    def _field_has_data(self, psql, model: str, field_name: str, ttype: str) -> bool:
        """Return True if the field has at least one meaningful (non-empty) value in the DB."""
        table = model.replace(".", "_")

        if ttype == "boolean":
            query = f'SELECT 1 FROM "{table}" WHERE "{field_name}" = TRUE LIMIT 1'
        elif ttype in ("integer", "float", "monetary"):
            query = f'SELECT 1 FROM "{table}" WHERE "{field_name}" IS NOT NULL AND "{field_name}" != 0 LIMIT 1'
        elif ttype in ("char", "text", "html", "selection"):
            query = f"SELECT 1 FROM \"{table}\" WHERE \"{field_name}\" IS NOT NULL AND \"{field_name}\" != '' LIMIT 1"
        elif ttype in ("many2one", "date", "datetime", "reference"):
            query = f'SELECT 1 FROM "{table}" WHERE "{field_name}" IS NOT NULL LIMIT 1'
        else:
            return True  # unknown type — assume it has data

        try:
            return bool(psql.query(query))
        except Exception:
            return True  # table or column missing — skip

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
