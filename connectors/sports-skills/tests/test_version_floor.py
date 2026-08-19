"""Regression tests for the sports-skills connector dependency floor.

Pods bake a pinned sports-skills into system site-packages; the connector
only hot-upgrades when the baked copy is older than the floor declared here.
"""
import importlib.util
import os
import re

# Load module with hyphenated filename using importlib
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "sports_skills_connector",
    os.path.join(_parent_dir, "sports-skills.py")
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


def test_min_version_is_0_33_0():
    assert _module._MIN_VERSION == (0, 33, 0)


def test_pip_package_pins_the_same_floor():
    assert _module._PIP_PACKAGE == "sports-skills>=0.33.0,<1.0"


def test_runtime_requirement_docs_recommend_no_older_floor():
    """The docstring must not tell operators to pin below _MIN_VERSION."""
    floors = re.findall(r"sports-skills>=([0-9][0-9.]*)", _module.__doc__)
    assert floors, "runtime requirement docs must state a sports-skills floor"
    assert all(f == "0.33.0" for f in floors), floors


def test_upgrade_target_stays_in_tmp():
    assert _module._TARGET_DIR == "/tmp/sports-skills-site"
