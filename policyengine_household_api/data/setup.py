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
        os.getenv("USER_ANALYTICS_CONNECTION_NAME"),
        "pymysql",
        user=os.getenv("USER_ANALYTICS_DB_USERNAME"),
        password=os.getenv("USER_ANALYTICS_DB_PASSWORD"),
        db="user_analytics",
        ip_type=IPTypes.PUBLIC,  # IPTypes.PRIVATE for private IP
    )

    return conn
