from collections import namedtuple

import pytest

from odev.utils.odoo import (
    InvalidVersion,
    branch_from_version,
    get_odoo_version,
    get_python_version,
    parse_odoo_version,
    version_from_branch,
)


OdooVersion = namedtuple("OdooVersion", "version, branch, major, minor, python")


@pytest.fixture
def versions_data():
    return [
        OdooVersion(Exception, "master", Exception, Exception, Exception),
        OdooVersion("5.0", "5.0", 5, 0, "2.7"),
        OdooVersion("6.0", "6.0", 6, 0, "2.7"),
        OdooVersion("6.1", "6.1", 6, 1, "2.7"),
        OdooVersion("7.0", "7.0", 7, 0, "2.7"),
        OdooVersion("7.saas~1", "saas-1", 7, 1, "2.7"),
        OdooVersion("7.saas~2", "saas-2", 7, 2, "2.7"),
        OdooVersion("7.saas~3", "saas-3", 7, 3, "2.7"),
        OdooVersion("7.saas~4", "saas-4", 7, 4, "2.7"),
        OdooVersion("7.saas~5", "saas-5", 7, 5, "2.7"),
        OdooVersion("8.0", "8.0", 8, 0, "2.7"),
        OdooVersion("8.saas~6", "saas-6", 8, 6, "2.7"),
        OdooVersion("9.0", "9.0", 9, 0, "2.7"),
        OdooVersion("9.saas~7", "saas-7", 9, 7, "2.7"),
        OdooVersion("9.saas~8", "saas-8", 9, 8, "2.7"),
        OdooVersion("9.saas~9", "saas-9", 9, 9, "2.7"),
        OdooVersion("9.saas~10", "saas-10", 9, 10, "2.7"),
        OdooVersion("9.saas~11", "saas-11", 9, 11, "2.7"),
        OdooVersion("9.saas~12", "saas-12", 9, 12, "2.7"),
        OdooVersion("9.saas~13", "saas-13", 9, 13, "2.7"),
        OdooVersion("10.0", "10.0", 10, 0, "2.7"),
        OdooVersion("10.saas~14", "saas-14", 10, 14, "2.7"),
        OdooVersion("10.saas~15", "saas-15", 10, 15, "2.7"),
        OdooVersion("10.saas~16", "saas-16", 10, 16, "2.7"),
        OdooVersion("10.saas~17", "saas-17", 10, 17, "2.7"),
        OdooVersion("10.saas~18", "saas-18", 10, 18, "2.7"),
        OdooVersion("11.0", "11.0", 11, 0, "3.5"),
        OdooVersion("saas~11.1", "saas-11.1", 11, 1, "3.5"),
        OdooVersion("saas~11.2", "saas-11.2", 11, 2, "3.5"),
        OdooVersion("saas~11.3", "saas-11.3", 11, 3, "3.5"),
        OdooVersion("saas~11.4", "saas-11.4", 11, 4, "3.5"),
        OdooVersion("saas~11.5", "saas-11.5", 11, 5, "3.5"),
        OdooVersion("12.0", "12.0", 12, 0, "3.6"),
        OdooVersion("saas~12.1", "saas-12.1", 12, 1, "3.6"),
        OdooVersion("saas~12.2", "saas-12.2", 12, 2, "3.6"),
        OdooVersion("saas~12.3", "saas-12.3", 12, 3, "3.6"),
        OdooVersion("saas~12.4", "saas-12.4", 12, 4, "3.6"),
        OdooVersion("saas~12.5", "saas-12.5", 12, 5, "3.6"),
        OdooVersion("13.0", "13.0", 13, 0, "3.6"),
        OdooVersion("saas~13.1", "saas-13.1", 13, 1, "3.6"),
        OdooVersion("saas~13.2", "saas-13.2", 13, 2, "3.6"),
        OdooVersion("saas~13.3", "saas-13.3", 13, 3, "3.6"),
        OdooVersion("saas~13.4", "saas-13.4", 13, 4, "3.6"),
        OdooVersion("saas~13.5", "saas-13.5", 13, 5, "3.6"),
        OdooVersion("14.0", "14.0", 14, 0, "3.8"),
        OdooVersion("saas~14.1", "saas-14.1", 14, 1, "3.8"),
        OdooVersion("saas~14.2", "saas-14.2", 14, 2, "3.8"),
        OdooVersion("saas~14.3", "saas-14.3", 14, 3, "3.8"),
        OdooVersion("saas~14.4", "saas-14.4", 14, 4, "3.8"),
        OdooVersion("saas~14.5", "saas-14.5", 14, 5, "3.8"),
        OdooVersion("15.0", "15.0", 15, 0, "3.8"),
        OdooVersion("saas~15.1", "saas-15.1", 15, 1, "3.8"),
        OdooVersion("saas~15.2", "saas-15.2", 15, 2, "3.8"),
        OdooVersion("saas~15.3", "saas-15.3", 15, 3, "3.8"),
    ]


def test_get_odoo_version(versions_data):
    for v in versions_data:
        for subv in (v.version, v.branch, f"{v.major}.{v.minor}"):
            if subv is Exception:
                with pytest.raises(TypeError):
                    get_odoo_version(subv)
            elif v.version is Exception:
                with pytest.raises(InvalidVersion):
                    get_odoo_version(subv)
            else:
                assert get_odoo_version(subv) == v.version, f"loose {subv} => odoo {v.version}"


def test_parse_odoo_version(versions_data):
    for v in versions_data:
        if v.version is Exception:
            with pytest.raises(TypeError):
                parse_odoo_version(v.version)
        else:
            parsed_version = parse_odoo_version(v.version)
            assert parsed_version.major == v.major, f"odoo {v.version} => major={v.major}"
            assert parsed_version.minor == v.minor, f"odoo {v.version} => minor={v.minor}"


def test_get_python_version(versions_data):
    for v in versions_data:
        if v.version is Exception:
            with pytest.raises(TypeError):
                get_python_version(v.version)
        else:
            assert get_python_version(v.version) == v.python, f"odoo {v.version} => python {v.python}"


def test_branch_from_version(versions_data):
    for v in versions_data:
        if v.version is Exception:
            with pytest.raises(TypeError):
                branch_from_version(v.version)
        else:
            assert branch_from_version(v.version) == v.branch, f"odoo {v.version} => branch {v.branch}"


def test_version_from_branch(versions_data):
    for v in versions_data:
        if v.branch is Exception:
            with pytest.raises(TypeError):
                version_from_branch(v.branch)
        elif v.branch == "master":
            assert version_from_branch(v.branch) == v.branch
        else:
            assert version_from_branch(v.branch) == v.version, f"branch {v.branch} => odoo {v.version}"
