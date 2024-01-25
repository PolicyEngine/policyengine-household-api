from setuptools import setup, find_packages
from policyengine_household_api.constants import __version__

setup(
    name="policyengine-household-api",
    version=__version__,
    author="PolicyEngine",
    author_email="hello@policyengine.org",
    description="PolicyEngine Household API",
    packages=find_packages(),
    install_requires=[
        "Authlib<1.3.0",
        "cloud-sql-python-connector",
        "flask>=2.2",
        "flask-cors>=3",
        "flask-sqlalchemy>=3",
        "google-cloud-logging",
        "gunicorn",
        "policyengine_canada==0.87.0",
        "policyengine-ng==0.5.1",
        "policyengine-il==0.1.0",
        "policyengine_uk==0.62.0",
        "policyengine_us==0.571.2",
        "pyjwt",
        "Flask-Caching==2.0.2",
        "urllib3<1.27,>=1.21.1",
        "python-dotenv",
        "pymysql",
        "black==22.12.0",  # This is because policyengine_canada uses black<23
    ],
    extras_require={
        "dev": [
            "pytest-timeout",
        ],
    },
)
