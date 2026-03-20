"""Compatibility helpers for deprecation APIs that vary by Python version."""

from __future__ import annotations

import functools
import sys
import warnings
from collections.abc import Callable
from typing import Any, TypeVar


__all__ = ["deprecated"]

if sys.version_info >= (3, 13):
    from warnings import deprecated
else:
    _DeprecatedFunc = TypeVar("_DeprecatedFunc", bound=Callable[..., Any])

    def deprecated(
        message: str,
        /,
        *,
        category: type[Warning] = DeprecationWarning,
    ) -> Callable[[_DeprecatedFunc], _DeprecatedFunc]:
        """Shim for ``warnings.deprecated`` (Python 3.13+)."""

        def decorator(func: _DeprecatedFunc) -> _DeprecatedFunc:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                warnings.warn(message, category, stacklevel=2)
                return func(*args, **kwargs)

            return wrapper  # type: ignore[return-value]

        return decorator
