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
sys.modules["msal"] = MagicMock()
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
        with patch.object(msal, "ConfidentialClientApplication") as mock_cca:
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

@patch("app.logging.error")
def test_error_logging_not_exposed(mock_logging_error):
    """
    Test that when an exception occurs during query execution, the exception is logged
    but only a generic error message is shown to the user via st.error.
    """
    # Fix the mock of st.cache_data so the decorated run_query is a normal function
    def mock_cache_data(**kwargs):
        def decorator(func):
            return func
        return decorator
    mock_st.cache_data = mock_cache_data

    # Ensure that databricks connect raises our Exception
    import sys
    test_exception = Exception("Secret Database Error")
    sys.modules["databricks"].sql.connect.side_effect = test_exception

    # Simulate search input to trigger the try-except block
    mock_st.text_input.return_value = "test search"
    mock_st.session_state.user_groups = ["test-group"]

    # Clear previous error calls
    mock_st.error.reset_mock()

    # Import or reload app to execute the UI flow
    import app
    import importlib
    importlib.reload(app)

    # Check that logging.error was called with the actual exception
    mock_logging_error.assert_called_once_with(f"Error querying data: {test_exception}", exc_info=True)

    # Check that st.error was called with the generic message
    mock_st.error.assert_any_call("An error occurred while querying the data. Please try again later or contact support.")

    # Verify the actual exception text is not passed to st.error
    for call in mock_st.error.call_args_list:
        assert "Secret Database Error" not in str(call)
