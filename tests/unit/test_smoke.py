from importlib.metadata import version

import orgknow


def test_package_is_installed_and_importable() -> None:
    # Distribution metadata only exists if uv installed the package, so this
    # catches a broken src/ layout that a plain import from the repo root would hide.
    assert orgknow.__name__ == "orgknow"
    assert version("orgknow") == "0.1.0"
