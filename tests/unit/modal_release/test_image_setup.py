from policyengine_household_api import deployment as _image_setup


def test_worker_image_uses_uv_for_package_version_overlays(monkeypatch):
    from policyengine_household_modal import images

    calls = []

    class FakeImage:
        def uv_sync(self, *args, **kwargs):
            calls.append(("uv_sync", args, kwargs))
            return self

        def uv_pip_install(self, *packages, **kwargs):
            calls.append(("uv_pip_install", packages, kwargs))
            return self

        def pip_install(self, *packages):
            raise AssertionError(
                f"worker image should use uv_pip_install, got {packages}"
            )

        def add_local_python_source(self, *args, **kwargs):
            calls.append(("add_local_python_source", args, kwargs))
            return self

        def add_local_dir(self, *args, **kwargs):
            calls.append(("add_local_dir", args, kwargs))
            return self

        def run_function(self, *args, **kwargs):
            calls.append(("run_function", args, kwargs))
            return self

    def debian_slim(*args, **kwargs):
        calls.append(("debian_slim", args, kwargs))
        return FakeImage()

    from policyengine_household_api.deployment import (
        PACKAGE_VERSIONS_ENV,
    )

    monkeypatch.setenv(
        PACKAGE_VERSIONS_ENV,
        '{"uk":"2.31.0","us":"1.691.1"}',
    )
    monkeypatch.setattr(images.modal.Image, "debian_slim", debian_slim)

    images.household_api_worker_image()

    assert (
        "uv_pip_install",
        (
            "policyengine_uk==2.31.0",
            "policyengine_us==1.691.1",
        ),
        {},
    ) in calls


def test_snapshot_tax_benefit_systems_preloads_all_country_packages(
    monkeypatch,
):
    loaded_packages = []
    initialized_packages = []

    class FakeCountryPackage:
        def __init__(self, package_name):
            self.package_name = package_name

        def CountryTaxBenefitSystem(self):
            initialized_packages.append(self.package_name)

    def import_module(package_name):
        loaded_packages.append(package_name)
        return FakeCountryPackage(package_name)

    monkeypatch.setattr(_image_setup.importlib, "import_module", import_module)

    _image_setup.snapshot_tax_benefit_systems()

    assert loaded_packages == [
        "policyengine_uk",
        "policyengine_us",
        "policyengine_canada",
        "policyengine_ng",
        "policyengine_il",
    ]
    assert initialized_packages == loaded_packages
