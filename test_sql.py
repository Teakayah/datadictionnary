from src.sync.push import _push_to_databricks

# Mock Databricks SQL connection
import os
os.environ["DATABRICKS_HOST"] = "test"
os.environ["DATABRICKS_HTTP_PATH"] = "test"
os.environ["DATABRICKS_TOKEN"] = "test"

# Let's see what happens...
# Oh wait, databricks.sql is imported inside the function, which might not be installed. Let's check:
