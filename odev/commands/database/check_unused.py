"""Check a database for unused custom fields."""

import csv
import re
from io import StringIO
from pathlib import Path

from odev.common import args, progress
from odev.common.commands import LocalDatabaseCommand
from odev.common.console import TableHeader
from odev.common.logging import logging


logger = logging.getLogger(__name__)

_SKIP_DATA_CHECK = frozenset({"binary", "one2many", "many2many"})

_REASON_NOT_REFERENCED = "not referenced"
_REASON_NO_DATA = "no data"

_DEFAULT_CSV_FILENAME = "unused_fields.csv"


class CheckUnusedCommand(LocalDatabaseCommand):
    """Check a database for unused custom resources.

    Use --fields to detect x_ custom fields that are either not referenced anywhere
    (views, server actions, automations, filters, rules, templates, reports, exports)
    or are referenced but contain no meaningful data.
    """

    _name = "check-unused"
    _aliases = ["cu"]

    fields = args.Flag(
        aliases=["--fields"],
        description="Check for unused x_ custom fields (excludes x_plan fields).",
    )
    all_fields = args.Flag(
        aliases=["--all-fields"],
        description="Check for unused fields across all non-standard fields, not just x_ ones. (not yet implemented)",
    )
    save = args.String(
        aliases=["--save"],
        description=f"Save results to a CSV file instead of printing to the terminal. "
        f"Defaults to '{_DEFAULT_CSV_FILENAME}' when no path is given.",
        nargs="?",
        const=_DEFAULT_CSV_FILENAME,
    )

    _CONTENT_QUERIES: list[tuple[str, list[str]]] = [
        ("SELECT arch_db FROM ir_ui_view", ["arch_db"]),
        ("SELECT code FROM ir_act_server WHERE code IS NOT NULL", ["code"]),
        ("SELECT compute, related FROM ir_model_fields WHERE compute IS NOT NULL OR related IS NOT NULL", ["compute", "related"]),
        ("SELECT domain FROM ir_filters WHERE domain IS NOT NULL", ["domain"]),
        ("SELECT domain_force FROM ir_rule WHERE domain_force IS NOT NULL", ["domain_force"]),
    ]

    _OPTIONAL_CONTENT_QUERIES: list[tuple[str, str, list[str]]] = [
        ("mail_template", "SELECT body_html, subject FROM mail_template", ["body_html", "subject"]),
        ("ir_actions_report", "SELECT help FROM ir_actions_report WHERE help IS NOT NULL", ["help"]),
        ("ir_exports_line", "SELECT name FROM ir_exports_line WHERE name IS NOT NULL", ["name"]),
        ("base_automation", "SELECT filter_pre_domain, filter_domain FROM base_automation", ["filter_pre_domain", "filter_domain"]),
    ]

    def run(self):
        if self.args.all_fields:
            raise NotImplementedError("--all-fields is not yet implemented.")

        if not self.args.fields:
            raise self.error("Specify at least one check to run: --fields or --all-fields")

        self._run_fields_check()

    # ------------------------------------------------------------------
    # Fields check
    # ------------------------------------------------------------------

    def _run_fields_check(self):
        with progress.spinner("Collecting x_ fields"):
            fields = self._fetch_x_fields()

        if not fields:
            logger.info("No custom x_ fields found in this database.")
            return

        logger.debug(f"Found {len(fields)} custom x_ field(s), scanning for usage...")

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
            TableHeader("Reason"),
        ]
        rows = [
            [model, field_name, self._extract_label(description), reason]
            for model, field_name, description, reason in unused
        ]

        if self.args.save is not None:
            self._save_csv(Path(self.args.save), [h.title for h in headers], rows)
        else:
            self.table(headers, rows, title=f"Unused x_ Fields ({len(unused)} of {len(fields)})")
            self.console.clear_line()

    def _psql(self):
        """Return a connector to the target database (not the default 'postgres' db)."""
        return self._database.psql(self._database.name)

    def _fetch_x_fields(self) -> list[tuple]:
        with self._psql() as psql:
            result = psql.query(
                "SELECT model, name, field_description, ttype, store "
                "FROM ir_model_fields WHERE name LIKE 'x_%' AND name NOT LIKE 'x\\_plan%'"
            )
        return result or []

    def _table_exists(self, psql, table: str) -> bool:
        result = psql.query(
            f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table}'"
        )
        return bool(result and result[0][0])

    def _collect_search_content(self) -> str:
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
            return True

        try:
            return bool(psql.query(query))
        except Exception:
            return True

    def _extract_label(self, description) -> str:
        if isinstance(description, dict):
            return description.get("en_US") or next(iter(description.values()), "")
        return description or ""

    def _save_csv(self, path: Path, headers: list[str], rows: list[list[str]]) -> None:
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        path.write_text(output.getvalue(), encoding="utf-8")
        logger.info(f"Results saved to {path.resolve()}")
