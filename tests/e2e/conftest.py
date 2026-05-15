import subprocess
import time
import pytest


@pytest.fixture(scope="session")
def streamlit_server():
    """Start Streamlit server for E2E tests."""
    proc = subprocess.Popen(
        ["python", "-m", "streamlit", "run", "apps/dashboard/app.py", "--server.port", "8502", "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for server to start
    time.sleep(5)
    yield "http://localhost:8502"
    proc.terminate()
    proc.wait(timeout=10)
