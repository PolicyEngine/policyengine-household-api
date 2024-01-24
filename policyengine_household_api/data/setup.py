import os
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector, IPTypes

load_dotenv()

# Much of this configuration is taken from https://pypi.org/project/cloud-sql-python-connector/
# Initialize connector object
connector = Connector()

# Configure connector
def getconn():

  conn = connector.connect(
    "policyengine-household-api:us-central1:household-api-user-analytics", # Cloud SQL Instance Connection Name
    "pymysql",
    user="policyengine",
    password=os.getenv("USER_ANALYTICS_DB_PASSWORD"),
    db="user_analytics",
    ip_type= IPTypes.PUBLIC  # IPTypes.PRIVATE for private IP
  )

  return conn