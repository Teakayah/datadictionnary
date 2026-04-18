import sys
from unittest.mock import MagicMock, patch
import os
import pytest

# Custom exceptions to mock Streamlit's flow control
class StopException(BaseException):
    pass

class RerunException(BaseException):
    pass

# Mock modules that are missing in the environment
mock_st = MagicMock()

# Configure specific mock behaviors
mock_st.stop.side_effect = StopException()
mock_st.rerun.side_effect = RerunException()

# mock cache_data decorator to just return the original function
def mock_cache_data(*args, **kwargs):
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0] # Used without parens: @st.cache_data
    def decorator(func):
        return func # Used with parens: @st.cache_data(...)
    return decorator

mock_st.cache_data = mock_cache_data

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
        import sys
        if "app" in sys.modules:
            del sys.modules["app"]

        # Mock st.stop and st.rerun so app imports successfully without exceptions
        with patch("streamlit.stop"), patch("streamlit.rerun"):
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

def test_check_auth_redirects_when_no_token():
    """
    Test that check_auth redirects to login when there is no token in session state
    and no authorization code in the query parameters.
    """
    # Clean up the module to ensure fresh import
    import sys
    if "app" in sys.modules:
        del sys.modules["app"]

    mock_st.session_state.clear()
    mock_st.query_params.clear()

    # First get app module without mocked exception side effects
    # to avoid StopException terminating the import prematurely
    with patch("streamlit.stop"), patch("streamlit.rerun"):
        import app

    with patch.object(app, "get_msal_app") as mock_get_msal_app:
        mock_msal_instance = MagicMock()
        mock_get_msal_app.return_value = mock_msal_instance
        mock_msal_instance.get_authorization_request_url.return_value = "https://auth-url"

        # call check_auth and assert it raises StopException
        with pytest.raises(StopException):
            app.check_auth()

        mock_get_msal_app.assert_called_once()
        mock_msal_instance.get_authorization_request_url.assert_called_once_with(
            app.SCOPE, redirect_uri=app.REDIRECT_URI
        )
        assert mock_st.session_state.auth_token is None

def test_check_auth_processes_code():
    """
    Test that check_auth processes the authorization code, sets session state,
    and forces a rerun.
    """
    import sys
    if "app" in sys.modules:
        del sys.modules["app"]

    mock_st.session_state.clear()
    mock_st.query_params.clear()
    mock_st.query_params["code"] = "auth-code-123"

    with patch("streamlit.stop"), patch("streamlit.rerun"):
        import app

    with patch.object(app, "get_msal_app") as mock_get_msal_app:
        mock_msal_instance = MagicMock()
        mock_get_msal_app.return_value = mock_msal_instance

        # Setup mock to return an access token
        mock_token_result = {
            "access_token": "token-123",
            "id_token_claims": {
                "groups": ["group1", "group2"],
                "name": "Test User"
            }
        }
        mock_msal_instance.acquire_token_by_authorization_code.return_value = mock_token_result

        # call check_auth and assert it raises RerunException
        with pytest.raises(RerunException):
            app.check_auth()

        mock_get_msal_app.assert_called_once()
        mock_msal_instance.acquire_token_by_authorization_code.assert_called_once_with(
            "auth-code-123", scopes=app.SCOPE, redirect_uri=app.REDIRECT_URI
        )

        # Verify session state was updated
        assert mock_st.session_state.auth_token == mock_token_result
        assert mock_st.session_state.user_groups == ["group1", "group2"]
        assert mock_st.session_state.user_name == "Test User"

def test_run_query():
    """
    Test that run_query correctly connects to Databricks SQL and executes a query,
    returning a pandas DataFrame.
    """
    import sys
    if "app" in sys.modules:
        del sys.modules["app"]

    env_vars = {
        "DATABRICKS_HOST": "query-host",
        "DATABRICKS_HTTP_PATH": "query-path",
        "DATABRICKS_TOKEN": "query-token"
    }

    with patch("streamlit.stop"), patch("streamlit.rerun"), patch.dict(os.environ, env_vars):
        import app

        # Reset the mock to clear calls made during import execution of app.py
        app.sql.connect.reset_mock()

        # Databricks sql is mocked at the module level in this file
        # We need to configure the context manager behavior for connect and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # Setup context managers
        app.sql.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Setup return value for fetchall_as_pandas
        mock_df = MagicMock()
        mock_cursor.fetchall_as_pandas.return_value = mock_df

        # Execute
        query = "SELECT * FROM test WHERE id = %s"
        params = (1,)
        result = app.run_query(query, params)

        # Assertions
        app.sql.connect.assert_called_once_with(
            server_hostname="query-host",
            http_path="query-path",
            access_token="query-token"
        )
        mock_conn.cursor.assert_called_once()
        mock_cursor.execute.assert_called_once_with(query, params)
        mock_cursor.fetchall_as_pandas.assert_called_once()

        assert result == mock_df
