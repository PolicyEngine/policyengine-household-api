import os
from pathlib import Path

GAE = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
# If it's a filepath, read the file. Otherwise, it'll be text
try:
    Path(GAE).resolve(strict=True)
    with open(GAE, "r") as f:
        GAE = f.read()
except Exception as e:
    pass
ADDRESS = os.environ["AUTH0_ADDRESS_NO_DOMAIN"]
AUDIENCE = os.environ["AUTH0_AUDIENCE_NO_DOMAIN"]
TEST_TOKEN = os.environ["AUTH0_TEST_TOKEN_NO_DOMAIN"]
DB_USER = os.environ["USER_ANALYTICS_DB_USERNAME"]
DBPW = os.environ["USER_ANALYTICS_DB_PASSWORD"]
DB_CONN = os.environ["USER_ANALYTICS_DB_CONNECTION_NAME"]

# Export GAE to to .gac.json

with open(".gac.json", "w") as f:
    f.write(GAE)

# in gcp/policyengine_household_api/Dockerfile, replace env variables
for dockerfile_location in [
    "gcp/policyengine_household_api/Dockerfile",
]:
    with open(dockerfile_location, "r") as f:
        dockerfile = f.read()
        dockerfile = dockerfile.replace(".address", ADDRESS)
        dockerfile = dockerfile.replace(".audience", AUDIENCE)
        dockerfile = dockerfile.replace(".test-token", TEST_TOKEN)
        dockerfile = dockerfile.replace(".dbuser", DB_USER)
        dockerfile = dockerfile.replace(".dbpw", DBPW)
        dockerfile = dockerfile.replace(".dbconn", DB_CONN)

    with open(dockerfile_location, "w") as f:
        f.write(dockerfile)
