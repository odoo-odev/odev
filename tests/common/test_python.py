from pathlib import Path

import pytest

from odev.common import python


class TestCommonPython:
    def setup_method(self):
        """Create a new python manager for each test."""
        self.global_env = python.PythonEnv(path=None)

    def test_raise_if_no_executable(self):
        """Python manager should raise if no executable is found for the given version"""
        with pytest.raises(FileNotFoundError) as _:
            python.PythonEnv(path=None, version="1.0")

    def test_create_venv_global(self):
        """Python manager should not be able to create a venv if global"""
        with pytest.raises(RuntimeError) as _:
            self.global_env.create_venv()

    def test_create_venv_version(self, tmp_path):
        """Python manager should be able to create a venv with a specific version"""
        env = python.PythonEnv(path=tmp_path, version="3.8")
        env.create_venv()
        assert env.python.is_file()

    def test_install_packages(self, tmp_path):
        """Python manager should be able to install packages"""
        env = python.PythonEnv(path=tmp_path, version="3.8")
        env.create_venv()
        env.install_packages(["pytest"])
        assert (env.path / "lib/python3.8/site-packages/pytest/__main__.py").is_file()

    def test_install_requirements(self, tmp_path):
        """Python manager should be able to install packages from requirements.txt"""
        env = python.PythonEnv(path=tmp_path, version="3.8")
        env.create_venv()
        env.install_requirements(Path(__file__).parents[1] / "resources")
        assert (env.path / "lib/python3.8/site-packages/pytest/__main__.py").is_file()

    def test_install_requirements_missing_file(self, tmp_path):
        """Python manager should raise if requirements.txt is missing"""
        env = python.PythonEnv(path=tmp_path, version="3.8")
        env.create_venv()
        with pytest.raises(FileNotFoundError) as _:
            env.install_requirements(Path(__file__).parents[1] / "resources/missing")

    def test_run_script(self, tmp_path):
        """Python manager should be able to run a script"""
        env = python.PythonEnv(path=tmp_path, version="3.8")
        env.create_venv()
        result = env.run_script(Path(__file__).parents[1] / "resources/test_script.py", ["'Hello, odev!'"])
        assert result.stdout == b"Hello, odev!\n"

    def test_run_script_missing_file(self, tmp_path):
        """Python manager should raise if script is missing"""
        env = python.PythonEnv(path=tmp_path, version="3.8")
        env.create_venv()
        with pytest.raises(FileNotFoundError) as _:
            env.run_script(Path(__file__).parents[1] / "resources/missing")
