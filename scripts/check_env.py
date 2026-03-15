#!/usr/bin/env python3
"""Lightweight environment preflight for local development."""

from __future__ import annotations

import importlib
import sys


REQUIRED_MODULES = {
    "yaml": "PyYAML",
    "jinja2": "Jinja2",
    "niche_scout": 'the editable project install (`pip install -e ".[dev]"`)',
    "pandas": "pandas",
    "playwright": "playwright",
    "pydantic": "pydantic",
    "rapidfuzz": "rapidfuzz",
    "rich": "rich",
    "streamlit": "streamlit",
    "tenacity": "tenacity",
    "typer": "typer",
    "pytest": "pytest",
}


def main() -> int:
    missing: list[tuple[str, str]] = []
    for module_name, package_name in REQUIRED_MODULES.items():
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            missing.append((module_name, package_name))

    if not missing:
        print("Environment preflight OK.")
        return 0

    print("Missing Python modules:")
    for module_name, package_name in missing:
        if module_name == "yaml":
            print(f"  - {module_name} (provided by {package_name})")
        elif module_name == "niche_scout":
            print(f"  - {module_name} (install the project itself with {package_name})")
        else:
            print(f"  - {module_name} (package: {package_name})")
    print()
    print("Install project and dev dependencies with:")
    print('  pip install -e ".[dev]"')
    print()
    print("If Playwright browsers are not installed yet, run:")
    print("  playwright install chromium")
    print("On Linux, you may also need:")
    print("  playwright install --with-deps chromium")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
