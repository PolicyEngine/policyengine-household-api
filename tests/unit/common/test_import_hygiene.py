"""Structural guards for the household-common lib's dependency closure.

The slim analytics writer image installs policyengine-household-common, so
this lib must never pull numpy, SQLAlchemy, modal, or country model packages
at import time (issue #1603 was exactly such a leak).
"""

from pathlib import Path
import subprocess
import sys

COMMON_PACKAGE = (
    Path("libs") / "household-common" / "policyengine_household_common"
)

HEAVY_MODULES = (
    "numpy",
    "modal",
    "sqlalchemy",
    "policyengine_core",
    "policyengine_uk",
    "policyengine_us",
    "policyengine_household_api",
)


def test_common_init_files_stay_empty_of_imports():
    for init_file in sorted(COMMON_PACKAGE.rglob("__init__.py")):
        source = init_file.read_text()
        for line in source.splitlines():
            stripped = line.strip()
            assert not stripped.startswith(("import ", "from ")), (
                f"{init_file} must not import at package-init time; "
                f"found: {stripped!r}"
            )


def test_common_modules_import_without_heavy_dependencies():
    module_names = sorted(
        "policyengine_household_common."
        + str(path.relative_to(COMMON_PACKAGE))[: -len(".py")]
        .replace("/", ".")
        .replace("\\", ".")
        for path in COMMON_PACKAGE.rglob("*.py")
        if path.name != "__init__.py"
    )
    probe_lines = ["import sys"]
    probe_lines += [f"import {name}" for name in module_names]
    probe_lines += [
        f"heavy = [m for m in {HEAVY_MODULES!r} if m in sys.modules]",
        "assert not heavy, f'common pulled heavy modules: {heavy}'",
    ]

    result = subprocess.run(
        [sys.executable, "-c", "\n".join(probe_lines)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
