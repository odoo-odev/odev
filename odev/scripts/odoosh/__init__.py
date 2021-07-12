"""Package with odoo.sh cli commands modules"""

from ...utils import import_submodules


# Auto-import submodules
__all__ = import_submodules(__path__, globals(), package=__name__)
