import subprocess
import sys


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "apps.cli.main", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "daily" in result.stdout


def test_cli_validate():
    result = subprocess.run(
        [sys.executable, "-m", "apps.cli.main", "validate"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
