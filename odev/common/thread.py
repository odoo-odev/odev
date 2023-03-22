"""Thread implementation with propagation of exceptions to the calling thread."""

from threading import Thread as BaseThread


__all__ = ["Thread"]


class Thread(BaseThread):
    """Thread implementation with propagation of exceptions to the calling thread."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._exception = None

    def run(self):
        try:
            super().run()
        except Exception as e:
            self._exception = e

    def join(self, *args, **kwargs):
        super().join(*args, **kwargs)

        if self._exception is not None:
            raise RuntimeError(f"Exception in thread {self.name}") from self._exception
