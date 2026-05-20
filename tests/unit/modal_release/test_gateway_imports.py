import importlib
from importlib.abc import MetaPathFinder
import sys


class _ForbiddenImportGuard(MetaPathFinder):
    def __init__(self, blocked_roots: set[str]):
        self.blocked_roots = blocked_roots

    def find_spec(self, fullname, path=None, target=None):
        if any(
            fullname == root or fullname.startswith(f"{root}.")
            for root in self.blocked_roots
        ):
            raise AssertionError(
                f"Gateway import unexpectedly imported {fullname}"
            )
        return None


def test_gateway_import_keeps_gateway_image_dependency_boundary():
    _remove_modules(
        {
            "policyengine_household_api.modal_release.gateway",
            "policyengine_household_api.modal_release.routing_metadata",
            "policyengine_household_api.models",
            "policyengine_household_api.utils",
            "numpy",
            "pydantic",
        }
    )
    guard = _ForbiddenImportGuard(
        {
            "policyengine_household_api.models",
            "policyengine_household_api.utils",
            "numpy",
            "pydantic",
        }
    )

    sys.meta_path.insert(0, guard)
    try:
        importlib.import_module(
            "policyengine_household_api.modal_release.gateway"
        )
    finally:
        sys.meta_path.remove(guard)


def _remove_modules(module_roots: set[str]) -> None:
    for module_name in list(sys.modules):
        if any(
            module_name == root or module_name.startswith(f"{root}.")
            for root in module_roots
        ):
            sys.modules.pop(module_name, None)
