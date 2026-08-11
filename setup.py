"""Shim for the one thing `pyproject.toml` cannot declare: a custom `build_py`.

Every field of the distribution — name, version, floor, the empty dependency set,
the package mapping and the package data — is declared in `pyproject.toml` and
deliberately not restated here. The only reason this file exists is that a
command class is Python, not TOML.

The build filter is loaded **by path** rather than imported as
`packaging.machina_sports_canonical.build`. `packaging/` at a repository root is
already a hazard: `setuptools` resolves a distribution of that name, and a
regular package here would shadow it during the build. Keeping this directory
un-importable and loading the file directly removes the hazard instead of
documenting it.
"""

import importlib.util
from pathlib import Path

from setuptools import setup

BUILD_FILTER_PATH = (Path(__file__).resolve().parent / "packaging"
                     / "machina_sports_canonical" / "build.py")


def build_filter():
    spec = importlib.util.spec_from_file_location(
        "machina_sports_canonical_build_filter", BUILD_FILTER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


setup(cmdclass={"build_py": build_filter().build_py})
