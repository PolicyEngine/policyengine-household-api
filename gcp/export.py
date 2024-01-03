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

# Export GAE to to .gac.json

with open(".gac.json", "w") as f:
    f.write(GAE)

# in gcp/policyengine_api_light/Dockerfile, replace env variables
for dockerfile_location in [
    "gcp/policyengine_api_light/Dockerfile",
]:
    with open(dockerfile_location, "r") as f:
        dockerfile = f.read()
        dockerfile = dockerfile.replace(
            ".address", ADDRESS
        )
        dockerfile = dockerfile.replace(
            ".audience", AUDIENCE
        )
      
    with open(dockerfile_location, "w") as f:
        f.write(dockerfile)
