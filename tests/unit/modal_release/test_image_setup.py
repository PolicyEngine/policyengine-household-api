from policyengine_household_api.modal_release import _image_setup


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
