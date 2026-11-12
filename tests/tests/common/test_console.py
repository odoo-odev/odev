from pathlib import Path
from unittest.mock import PropertyMock, patch

from InquirerPy.prompts.checkbox import CheckboxPrompt
from InquirerPy.prompts.confirm import ConfirmPrompt

from odev.common.console import Console
from odev.common.errors import OdevError

from tests.fixtures import OdevTestCase


REAL_BYPASS_PROMPT = Console.__dict__["bypass_prompt"]
"""Reference to the real `Console.bypass_prompt` property, taken before the test fixtures patch it away to prevent
tests from waiting for user input.
"""


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


class TestCommonConsoleNonInteractive(OdevTestCase):
    """Prompts should never wait for the user in non-interactive mode."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.console = Console()

    def setUp(self):
        super().setUp()
        self.enterContext(patch.object(Console, "bypass_prompt", REAL_BYPASS_PROMPT))
        self.enterContext(patch.object(Console, "_non_interactive", new=True))
        self.enterContext(patch.object(Console, "_bypass_prompt", new=False))

    def test_01_defaults_are_assumed(self):
        """Prompts with a default should be answered with it without waiting for the user."""
        with patch.object(ConfirmPrompt, "_run", side_effect=AssertionError("prompt was run")):
            self.assertTrue(self.console.confirm("Pull changes now?", default=True))

    def test_02_prompt_without_default(self):
        """Prompts without an answer to fall back on should fail rather than wait for the user."""
        with self.assertRaisesRegex(OdevError, "non-interactive mode"):
            self.console.secret("Session password:")

        with self.assertRaisesRegex(OdevError, "non-interactive mode"):
            self.console.text("Specific commit SHA to track:")

        with self.assertRaisesRegex(OdevError, "non-interactive mode"):
            self.console.fuzzy("Select a branch to track:", [("master", None)])

        with self.assertRaisesRegex(OdevError, "non-interactive mode"):
            self.console.checkbox("Select databases to whitelist:", choices=[("test", None)])

    def test_03_destructive_confirmation(self):
        """Discarding data should not be confirmed on behalf of the user unless prompts were bypassed explicitly."""
        with self.assertRaisesRegex(OdevError, "without --force"):
            self.console.confirm("Overwrite it?", default=True, destructive=True)

        self.assertFalse(self.console.confirm("Overwrite it?", default=False, destructive=True))

        with self.console.force_bypass_prompt(force=True):
            self.assertTrue(self.console.confirm("Overwrite it?", default=True, destructive=True))

    def test_04_force_bypass_prompt_is_restored(self):
        """Leaving a forced bypass should restore the explicit value, not the one implied by non-interactive mode."""
        with self.console.force_bypass_prompt(force=True):
            pass

        self.assertFalse(Console._bypass_prompt)

    def test_05_force_bypass_prompt_is_restored_on_error(self):
        """An error raised while prompts are bypassed should not leave them bypassed for the rest of the run."""
        with self.assertRaises(OdevError), self.console.force_bypass_prompt(force=True):
            raise OdevError("Failed to delete the database")

        self.assertFalse(Console._bypass_prompt)

        with self.assertRaisesRegex(OdevError, "without --force"):
            self.console.confirm("Overwrite it?", default=True, destructive=True)
