import sys
from unittest.mock import patch

def test_sync_daemon_main():
    with patch.object(sys, "argv", ["daemon.py", "--once"]), \
         patch("src.sync.daemon.run", return_value=0) as mock_run:
        from src.sync.daemon import main
        assert main() == 0
        mock_run.assert_called_once_with(once=True, healthz_port=8765)