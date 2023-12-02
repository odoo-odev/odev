import re
from pathlib import Path
from sys import maxsize as infinity
from typing import Callable, Literal, Mapping

import autoflake  # type: ignore [import]
import black
import isort
import lxml.etree as ET
from jinja2 import Environment, FileSystemLoader

from odev.common.logging import logging


logger = logging.getLogger(__name__)


class Template:
    """Generate, render and write templates to files."""

    def __init__(
        self,
        path: Path,
        name: str,
        lang: Literal["py", "xml", "txt"],
        filters: Mapping["str", Callable] = None,
        data: Mapping[str, str] = None,
    ):
        """Initialize the template.
        :param path: The path to the template file.
        :param lang: The language used in the template.
        :param filters: The Jinja2 filters to use when rendering the template.
        :param data: The data to render the template with.
        """
        self.path = path
        """The path to the template file."""

        self.name = name
        """The name of the file the rendered template will be saved to."""

        self.lang = lang
        """The language used in the template."""

        self.data: Mapping[str, str] = data or {}
        """The data to render the template with."""

        self.env = Environment(loader=FileSystemLoader(self.path.parent), keep_trailing_newline=True)
        """The Jinja2 environment used to render the template."""

        self.env.filters.update(filters or {})

    def render(
        self,
        pretty: bool = True,
        line_length: int = infinity,
        run_isort: bool = True,
        run_autoflake: bool = True,
    ) -> str:
        """Render the template with the given data.
        :param data: The data to render the template with.
        :param pretty: Whether or not to pretty print the rendered template.
        :param line_length: The maximum line length to use when formatting the template.
        :param run_isort: Whether or not to run isort on the template.
        :param run_autoflake: Whether or not to run autoflake on the template.
        :return: The rendered template.
        """
        template = self.env.get_template(self.path.name)
        rendered = template.render(data=self.data)

        if not pretty:
            return rendered

        try:
            rendered = self.prettify(rendered, line_length, run_isort, run_autoflake)
        except black.NothingChanged:
            pass
        else:
            return rendered

    def prettify(
        self,
        text: str,
        line_length: int = infinity,
        run_isort: bool = True,
        run_autoflake: bool = True,
    ) -> str:
        """Format the rendered template with common linters.
        :param text: The rendered template to format.
        :param line_length: The maximum line length to use when formatting the template.
        :param run_isort: Whether or not to run isort on the template.
        :param run_autoflake: Whether or not to run autoflake on the template.
        :return: The formatted template.
        """
        if self.lang == "py":
            return self.prettify_py(text, line_length, run_isort, run_autoflake)

        if self.lang == "xml":
            return self.prettify_xml(text)

        return text

    def prettify_py(
        self,
        text: str,
        line_length: int = infinity,
        run_isort: bool = True,
        run_autoflake: bool = True,
    ) -> str:
        """Format the rendered template with common linters for the Python language.
        :param text: The rendered template to format.
        :param line_length: The maximum line length to use when formatting the template.
        :param run_isort: Whether or not to run isort on the template.
        :param run_autoflake: Whether or not to run autoflake on the template.
        :return: The formatted template.
        """
        black_config = black.FileMode(line_length=line_length)
        text = black.format_str(text, mode=black_config)

        if self.name == "__init__.py":
            return text

        if run_isort:
            text = isort.code(
                text,
                force_single_line=True,
                single_line_exclusions=["odoo"],
            )

        if run_autoflake:
            text = autoflake.fix_code(
                text,
                remove_all_unused_imports=True,
                remove_duplicate_keys=True,
                remove_unused_variables=True,
            )

        return text

    def prettify_xml(self, text: str) -> str:
        """Format the rendered template with common linters for the XML language.
        :param text: The rendered template to format.
        :return: The formatted template.
        """
        parser = ET.XMLParser(remove_blank_text=True, strip_cdata=False)
        root = ET.fromstring(text.encode(), parser)
        ET.indent(root, space=" " * 4)
        return ET.tostring(
            root,
            pretty_print=True,
            xml_declaration=True,
            encoding="utf-8",
        ).decode("utf-8")

    def save(self, text: str, path: Path) -> None:
        """Save the rendered template to disk.
        :param text: The rendered template to save to disk.
        :param path: The path to save the rendered template to.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        text = self.merge(path, text)

        with path.open("w") as file:
            file.write(text)

    def merge(self, path: Path, text: str) -> str:
        """Merge the rendered template with an existing file.
        :param path: The path to the existing file.
        :param text: The rendered template to merge with the existing file.
        """
        if not path.exists():
            return text

        if self.lang == "xml":
            text = self.merge_xml(path, text)

        if self.lang == "py":
            text = self.merge_py(path, text)

        if self.lang in ["txt", "csv"]:
            if re.match(r"^requirements.*\.txt$", path.name):
                text = self.merge_requirements(path, text)
            else:
                text = self.merge_txt(path, text)

        return text

    def merge_txt(self, path: Path, text: str, add_space: bool = False) -> str:
        """Merge the rendered template with an existing text file.
        :param path: The path to the existing text file.
        :param text: The rendered template to merge with the existing text file.
        :param add_space: Whether or not to add a space between the existing text and the rendered template.
        """
        with path.open() as file:
            content = file.read()

        space = "\n" * (int(add_space) + 1)

        if content.endswith(space):
            return content + text

        return space.join([content.rstrip(), text])

    def merge_py(self, path: Path, text: str) -> str:
        """Merge the rendered template with an existing Python file.
        :param path: The path to the existing Python file.
        :param text: The rendered template to merge with the existing Python file.
        """
        return self.merge_txt(path, text, add_space=True)

    def merge_xml(self, path: Path, text: str) -> str:
        """Merge the rendered template with an existing XML file.
        :param path: The path to the existing XML file.
        :param text: The rendered template to merge with the existing XML file.
        """
        parser = ET.XMLParser(remove_blank_text=True, strip_cdata=False)
        root = ET.fromstring(text.encode(), parser)

        with path.open() as file:
            content = file.read()

        existing_root = ET.fromstring(content.encode(), parser)

        for child in root:
            existing_root.append(child)

        return self.prettify_xml(ET.tostring(existing_root).decode("utf-8"))

    def merge_requirements(self, path: Path, text: str) -> str:
        """Merge the rendered template with an existing requirements.txt file.
        :param path: The path to the existing requirements.txt file.
        :param text: The rendered template to merge with the existing requirements.txt file.
        """
        with path.open() as file:
            content = file.read()

        return "\n".join(sorted(set(content.splitlines() + text.splitlines())))
