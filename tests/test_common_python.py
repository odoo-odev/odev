import shutil
import tempfile

from odev.common import python
from tests.fixtures import OdevTestCase


class TestCommonPython(OdevTestCase):
    def setUp(self):
        """Create a new python manager for each test."""
        self.global_env = python.PythonEnv(path=None)
        self.tmp_path = tempfile.mkdtemp()

    def tearDown(self) -> None:
        """Remove the temporary directory."""
        shutil.rmtree(self.tmp_path)

    def test_raise_if_no_executable(self):
        """Python manager should raise if no executable is found for the given version"""
        with self.assertRaises(FileNotFoundError):
            python.PythonEnv(path=None, version="1.0")

    def test_create_venv_global(self):
        """Python manager should not be able to create a venv if global"""
        with self.assertRaises(RuntimeError):
            self.global_env.create_venv()

    def test_create_venv_version(self):
        """Python manager should be able to create a venv with a specific version"""
        env = python.PythonEnv(path=self.tmp_path, version="3.10")
        env.create_venv()
        self.assertTrue(env.python.is_file(), "should create a python executable")

    def test_install_packages(self):
        """Python manager should be able to install packages"""
        env = python.PythonEnv(path=self.tmp_path, version="3.10")
        env.create_venv()
        env.install_packages(["pytest"])
        self.assertTrue(
            (env.path / "lib/python3.10/site-packages/pytest/__main__.py").is_file(), "should install pytest"
        )

    def test_install_requirements(self):
        """Python manager should be able to install packages from requirements.txt"""
        env = python.PythonEnv(path=self.tmp_path, version="3.10")
        env.create_venv()
        env.install_requirements(self.odev.tests_path / "requirements.txt")
        self.assertTrue(
            (env.path / "lib/python3.10/site-packages/pytest/__main__.py").is_file(), "should install pytest"
        )

    def test_install_requirements_missing_file(self):
        """Python manager should raise if requirements.txt is missing"""
        env = python.PythonEnv(path=self.tmp_path, version="3.10")
        env.create_venv()
        with self.assertRaises(FileNotFoundError):
            env.install_requirements(self.odev.tests_path / "missing")

    def test_run_script(self):
        """Python manager should be able to run a script"""
        env = python.PythonEnv(path=self.tmp_path, version="3.10")
        env.create_venv()
        result = env.run_script(self.odev.scripts_path / "test_script.py", ["'Hello, odev!'"])
        self.assertEqual(result.stdout, b"Hello, odev!\n", "should return the script output 'Hello, odev!'")

    def test_run_script_missing_file(self):
        """Python manager should raise if script is missing"""
        env = python.PythonEnv(path=self.tmp_path, version="3.10")
        env.create_venv()
        with self.assertRaises(FileNotFoundError):
            env.run_script(self.odev.scripts_path / "missing")
