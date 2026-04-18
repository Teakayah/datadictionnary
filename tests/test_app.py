import sys
from unittest.mock import MagicMock, patch
import os
import pytest

# Mock modules that are missing in the environment
mock_st = MagicMock()

# session_state in streamlit acts like an object with attribute access
class MockSessionState(dict):
    def __getattr__(self, item):
        return self.get(item)
    def __setattr__(self, key, value):
        self[key] = value

mock_st.session_state = MockSessionState()
mock_st.query_params = {}
sys.modules["streamlit"] = mock_st
sys.modules["databricks"] = MagicMock()
sys.modules["databricks.sql"] = MagicMock()

class DummyConfidentialClientApplication:
    def __init__(self, *args, **kwargs):
        pass
    def get_authorization_request_url(self, *args, **kwargs):
        return "mock_url"

class MockMsalModule:
    ConfidentialClientApplication = DummyConfidentialClientApplication

sys.modules["msal"] = MockMsalModule()
sys.modules["dotenv"] = MagicMock()
sys.modules["pandas"] = MagicMock()

def test_get_msal_app():
    """
    Test that get_msal_app correctly initializes the msal ConfidentialClientApplication
    with the expected environment variables.
    """
    env_vars = {
        "TENANT_ID": "test-tenant",
        "CLIENT_ID": "test-client",
        "CLIENT_SECRET": "test-secret",
        "DATABRICKS_HOST": "test-host",
        "DATABRICKS_HTTP_PATH": "test-path",
        "DATABRICKS_TOKEN": "test-token"
    }

    with patch.dict(os.environ, env_vars):
        # Remove app from sys.modules if it's already there to force a reload with new env vars
        if "app" in sys.modules:
            del sys.modules["app"]

        # Now we can patch msal.ConfidentialClientApplication because we mocked msal
        import msal
        with patch.object(msal, "ConfidentialClientApplication", autospec=True) as mock_cca:
            mock_instance = DummyConfidentialClientApplication()
            mock_cca.return_value = mock_instance

            # We need to import app here so it picks up the patched os.environ
            import app

            # Clear any calls that might have happened during module import (e.g. from check_auth)
            mock_cca.reset_mock()

            # Call the function we are testing
            result = app.get_msal_app()

            # Verify ConfidentialClientApplication was called with correct arguments
            mock_cca.assert_called_once_with(
                "test-client",
                authority="https://login.microsoftonline.com/test-tenant",
                client_credential="test-secret"
            )

            # Verify it returns the instance created
            assert result == mock_cca.return_value
            assert isinstance(result, DummyConfidentialClientApplication)
