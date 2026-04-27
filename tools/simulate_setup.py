#!/usr/bin/env python3
import os
import pty
import select
import shutil
import sys
import time


# This script simulates a user interaction with 'odev setup' for documentation GIFs.
# It handles the interaction sequence. The prompt and 'odev setup' command typing
# are handled by record.sh to ensure a consistent look.


def run_simulation():  # noqa: PLR0912, PLR0915
    # 1. CLEANUP & PREP
    config_dir = os.path.expanduser("~/.config/odev")
    if os.path.exists(config_dir):
        shutil.rmtree(config_dir)
    os.makedirs(config_dir, exist_ok=True)

    # Pre-create a clean config so defaults look professional in the GIF
    config_file = os.path.join(config_dir, "odev.cfg")
    with open(config_file, "w") as f:
        f.write("[paths]\nrepositories = /home/odev/repos\ndumps = /home/odev/dumps\n")

    # 2. ENVIRONMENT
    os.environ["GIT_AUTHOR_NAME"] = "Odev Developer"
    os.environ["GIT_AUTHOR_EMAIL"] = "odev@example.com"
    os.environ["COLUMNS"] = "100"
    os.environ["LINES"] = "24"

    # Ensure terminal environment is stable for Rich/InquirerPy
    os.environ["TERM"] = "xterm-256color"
    # Suppress prompt_toolkit CPR (Cursor Position Request) warnings
    # which can cause misalignment in recorded pseudo-terminals
    os.environ["PROMPT_TOOLKIT_NO_CPR"] = "1"

    # Add local bin for symlinks
    local_bin = os.path.expanduser("~/.local/bin")
    os.makedirs(local_bin, exist_ok=True)
    os.environ["PATH"] = f"{local_bin}:{os.environ.get('PATH', '')}"

    orig_home = os.environ.get("ORIG_HOME", os.path.expanduser("~"))
    repo_root = os.environ.get("REPO_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    venv_python = os.path.join(orig_home, ".config/odev/venv/bin/python3")
    python_bin = venv_python if os.path.exists(venv_python) else sys.executable
    main_py = os.path.join(repo_root, "main.py")

    # 3. REAL INTERACTION
    pid, fd = pty.fork()
    if pid == 0:
        # Child process
        os.execv(python_bin, [python_bin, main_py, "setup"])  # noqa: S606
    else:
        # Sequence of inputs: (delay_after_last_action, text_to_type)
        inputs = [
            (3.0, "\r"),  # 1. Repositories path (Enter for default)
            (2.0, "\r"),  # 2. Dumps path (Enter for default)
            (2.0, "n"),  # 3. Import Odoo?
            (2.5, "\r"),  # 4. Update mode selection (Enter for default: Ask)
            (1.5, "1\r"),  # 5. Update interval
            (1.5, "y"),  # 6. Completion
            (2.0, "y"),  # 7. Telemetry
        ]

        input_idx = 0
        last_action_time = time.time()

        try:
            while True:
                r, _, _ = select.select([fd], [], [], 0.05)
                if fd in r:
                    try:
                        data = os.read(fd, 4096)
                        if not data:
                            break
                        sys.stdout.buffer.write(data)
                        sys.stdout.buffer.flush()
                    except OSError:
                        break

                now = time.time()
                if input_idx < len(inputs):
                    delay, text = inputs[input_idx]
                    if now - last_action_time > delay:
                        for char in text:
                            os.write(fd, char.encode())
                            time.sleep(0.03)
                            # Drain output during typing
                            r2, _, _ = select.select([fd], [], [], 0)
                            if fd in r2:
                                try:
                                    d = os.read(fd, 1024)
                                    sys.stdout.buffer.write(d)
                                    sys.stdout.buffer.flush()
                                except OSError:
                                    pass

                        if text not in ["\r", "\n"] and not text.endswith("\r"):
                            os.write(fd, b"\n")

                        input_idx += 1
                        last_action_time = time.time()

        except KeyboardInterrupt:
            pass
        finally:
            time.sleep(2)
            os.close(fd)


if __name__ == "__main__":
    run_simulation()
