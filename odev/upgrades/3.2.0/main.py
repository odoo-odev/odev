import logging
import os
import subprocess
import sys


_logger: logging.Logger = logging.getLogger(__name__)


def run() -> None:
    pip_cmd: str = f"{sys.executable} -m pip"

    def pip_freeze() -> str:
        return subprocess.getoutput(f"{pip_cmd} freeze").lower()

    restart: bool = False

    if "giturlparse.py" in pip_freeze():
        subprocess.run(f"{pip_cmd} uninstall -y giturlparse.py giturlparse", shell=True)
        restart |= True

    if "giturlparse" not in pip_freeze():
        subprocess.run(f"{pip_cmd} install --upgrade giturlparse==0.10", shell=True)
        restart |= True

    if restart:
        _logger.info("Restarting odev after packages upgrade")
        os.execv(sys.argv[0], sys.argv)
