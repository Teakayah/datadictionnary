import pytest
from src.auth import is_pipeline_user, is_admin

class TestIsPipelineUser:
    def test_is_pipeline_user_no_env_var(self, monkeypatch):
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["some-group"]})
        monkeypatch.setenv("PIPELINE_GROUPS", "")
        assert is_pipeline_user() is False

    def test_is_pipeline_user_no_matching_groups(self, monkeypatch):
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["some-group", "another-group"]})
        monkeypatch.setenv("PIPELINE_GROUPS", "pipeline-group1,pipeline-group2")
        assert is_pipeline_user() is False

    def test_is_pipeline_user_matching_groups(self, monkeypatch):
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["some-group", "pipeline-group2"]})
        monkeypatch.setenv("PIPELINE_GROUPS", "pipeline-group1,pipeline-group2")
        assert is_pipeline_user() is True

    def test_is_pipeline_user_empty_session_state(self, monkeypatch):
        monkeypatch.setattr("src.auth.st.session_state", {})
        monkeypatch.setenv("PIPELINE_GROUPS", "pipeline-group1")
        assert is_pipeline_user() is False

    def test_is_pipeline_user_handles_whitespace(self, monkeypatch):
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["pipeline-group1"]})
        monkeypatch.setenv("PIPELINE_GROUPS", "  pipeline-group1  ,  pipeline-group2  ")
        assert is_pipeline_user() is True

class TestIsAdmin:
    def test_is_admin_no_env_var(self, monkeypatch):
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["some-group"]})
        monkeypatch.setenv("ADMIN_GROUPS", "")
        assert is_admin() is False

    def test_is_admin_no_matching_groups(self, monkeypatch):
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["some-group", "another-group"]})
        monkeypatch.setenv("ADMIN_GROUPS", "admin-group1,admin-group2")
        assert is_admin() is False

    def test_is_admin_matching_groups(self, monkeypatch):
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["some-group", "admin-group2"]})
        monkeypatch.setenv("ADMIN_GROUPS", "admin-group1,admin-group2")
        assert is_admin() is True

    def test_is_admin_empty_session_state(self, monkeypatch):
        monkeypatch.setattr("src.auth.st.session_state", {})
        monkeypatch.setenv("ADMIN_GROUPS", "admin-group1")
        assert is_admin() is False

    def test_is_admin_handles_whitespace(self, monkeypatch):
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["admin-group1"]})
        monkeypatch.setenv("ADMIN_GROUPS", "  admin-group1  ,  admin-group2  ")
        assert is_admin() is True
