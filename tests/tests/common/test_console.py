from pathlib import Path
from unittest.mock import PropertyMock, patch

from InquirerPy.prompts.checkbox import CheckboxPrompt

from odev.common.console import Console

from tests.fixtures import OdevTestCase


class TestCommonConsoleCheckbox(OdevTestCase):
    """Checkbox prompts should be answered with their defaults when prompts are bypassed."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.console = Console()

    def test_01_bypass_returns_defaults(self):
        """A bypassed checkbox should return its defaults without waiting for the user."""
        with patch.object(CheckboxPrompt, "_run", side_effect=AssertionError("prompt was run")):
            selected = self.console.checkbox(
                "Select the repositories to update:",
                choices=[("odoo", "odoo (3 commits)"), ("enterprise", "enterprise (5 commits)"), ("themes", None)],
                defaults=["odoo", "enterprise"],
            )

        self.assertEqual(selected, ["odoo", "enterprise"])

    def test_02_bypass_values_are_not_strings(self):
        """The values of the choices are returned as they are, only their names are displayed."""
        odoo_path, enterprise_path = Path("odoo"), Path("enterprise")

        with (
            patch.object(CheckboxPrompt, "_run", side_effect=AssertionError("prompt was run")),
            self.console.capture() as capture,
        ):
            selected = self.console.checkbox(
                "Select the repositories to update:",
                choices=[(odoo_path, "Community"), (enterprise_path, "Enterprise")],
                defaults=[enterprise_path, odoo_path],
            )

        self.assertEqual(selected, [odoo_path, enterprise_path])
        self.assertIn("Community and Enterprise", capture.get())

    def test_03_bypass_empty_defaults(self):
        """Explicitly selecting nothing by default is an answer of its own."""
        with patch.object(CheckboxPrompt, "_run", side_effect=AssertionError("prompt was run")):
            selected = self.console.checkbox("Select databases to delete:", choices=[("test", None)], defaults=[])

        self.assertEqual(selected, [])

    def test_04_bypass_without_defaults(self):
        """A checkbox with no defaults has no answer to give and should still ask the user."""
        with patch.object(CheckboxPrompt, "_run", return_value=["test"]) as run:
            selected = self.console.checkbox("Select databases to whitelist:", choices=[("test", None)])

        run.assert_called_once_with()
        self.assertEqual(selected, ["test"])

    def test_05_no_bypass(self):
        """The user should be asked when prompts are not bypassed, whatever the defaults."""
        with (
            patch.object(Console, "bypass_prompt", new_callable=PropertyMock, return_value=False),
            patch.object(CheckboxPrompt, "_run", return_value=["themes"]) as run,
        ):
            selected = self.console.checkbox(
                "Select the repositories to update:",
                choices=[("odoo", None), ("themes", None)],
                defaults=["odoo"],
            )

        run.assert_called_once_with()
        self.assertEqual(selected, ["themes"])
