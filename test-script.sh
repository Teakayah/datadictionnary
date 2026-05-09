docker run --rm -d --name test-app -p 8501:8501 --read-only --tmpfs /tmp --tmpfs /run --tmpfs /home/appuser/.streamlit --user 1000:1000 test-app
