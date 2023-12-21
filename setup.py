from setuptools import setup, find_packages
from policyengine_api_light.constants import __version__

setup(
    name="policyengine-api-light",
    version=__version__,
    author="PolicyEngine",
    author_email="hello@policyengine.org",
    description="PolicyEngine API Light",
    packages=find_packages(),
    install_requires=[
        "flask>=1",
        "flask-cors>=3",
        "google-cloud-logging",
        "gunicorn",
        "markupsafe==2.0.1",
        "policyengine_canada==0.87.0",
        "policyengine-ng==0.5.1",
        "policyengine-il==0.1.0",
        "policyengine_uk==0.62.0",
        "policyengine_us==0.571.2",
        "Flask-Caching==2.0.2",
    ],
    extras_require={
        "dev": [
            "pytest-timeout",
        ],
    },
)
