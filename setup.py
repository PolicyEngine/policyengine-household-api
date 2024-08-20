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
        "Authlib>=1.3.1",
        "cloud-sql-python-connector",
        "flask>=2.2",
        "flask-cors>=3",
        "flask-sqlalchemy>=3",
        "google-cloud-logging",
        "gunicorn",
        "policyengine_canada==0.95.0",
        "policyengine-ng==0.5.1",
        "policyengine-il==0.1.0",
        "policyengine_uk==1.7.0",
        "policyengine_us==1.56.1",
        "pyjwt",
        "Flask-Caching==2.0.2",
        "urllib3<1.27,>=1.21.1",
        "python-dotenv",
        "pymysql",
        "black==24.3.0",
        "ratelimiter",
    ],
    extras_require={
        "dev": [
            "pytest-timeout",
        ],
    },
)
