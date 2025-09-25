"""Thread implementation with propagation of exceptions to the calling thread."""

from threading import Thread as BaseThread

from odev.common.string import normalize_indent


__all__ = ["Thread"]


class Thread(BaseThread):
    """Thread implementation with propagation of exceptions to the calling thread."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._exception = None

    def run(self):
        try:
            super().run()
        except Exception as e:  # noqa: BLE001 - we want to catch all exceptions in the thread
            self._exception = e

    def join(self, *args, **kwargs):
        super().join(*args, **kwargs)

        if self._exception is not None:
            raise RuntimeError(
                normalize_indent(
                    f"""
                    Exception in thread {self.name}:
                        {self._exception.__class__.__name__}: {self._exception}
                    """
                )
            ) from self._exception
