import tempfile
from pathlib import Path
from textwrap import dedent

from odev.common.debug import find_debuggers

from tests.fixtures import OdevTestCase


IR_QWEB_SOURCE = dedent(
    """
    class IrQweb:
        def _debug_trace(self, debugger, values):
            if not debugger:
                breakpoint()

        def _render(self):
            breakpoint()
    """
)


class TestCommonDebug(OdevTestCase):
    """Calls to debuggers shipped with Odoo should not be mistaken for ones left behind by a developer."""

    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp())
        self.ir_qweb = self.root / "odoo" / "addons" / "base" / "models" / "ir_qweb.py"
        self.ir_qweb.parent.mkdir(parents=True)

    def test_01_ignores_upstream_debug_trace(self):
        """The `breakpoint()` in `_debug_trace` is skipped, another one in the same file is still reported."""
        self.ir_qweb.write_text(IR_QWEB_SOURCE)

        self.assertEqual(find_debuggers(self.root), [(self.ir_qweb, 8)])

    def test_02_ignores_upstream_debug_trace_after_shift(self):
        """The exclusion follows the function when lines are added above it."""
        self.ir_qweb.write_text("\n" * 50 + IR_QWEB_SOURCE)

        self.assertEqual(find_debuggers(self.root), [(self.ir_qweb, 58)])

    def test_03_reports_same_function_elsewhere(self):
        """A `_debug_trace` function in another file is not covered by the exclusion."""
        other = self.root / "custom_addon" / "models" / "ir_qweb.py"
        other.parent.mkdir(parents=True)
        other.write_text(IR_QWEB_SOURCE)

        self.assertEqual(sorted(find_debuggers(other.parent)), [(other, 5), (other, 8)])
