from pathlib import Path

from runtime_config import browser_args, browser_headless, env_flag, env_path


def test_env_flag_reads_truthy_values(monkeypatch):
    monkeypatch.setenv("XIANYU_TEST_FLAG", "yes")

    assert env_flag("XIANYU_TEST_FLAG") is True


def test_env_flag_uses_default_when_missing(monkeypatch):
    monkeypatch.delenv("XIANYU_MISSING_FLAG", raising=False)

    assert env_flag("XIANYU_MISSING_FLAG", True) is True


def test_env_path_reads_custom_path(monkeypatch):
    monkeypatch.setenv("XIANYU_TEST_PATH", "~/xianyu-data")

    assert env_path("XIANYU_TEST_PATH", Path("/tmp/default")).name == "xianyu-data"


def test_browser_server_flags(monkeypatch):
    monkeypatch.setenv("XIANYU_HEADLESS", "1")
    monkeypatch.setenv("XIANYU_NO_SANDBOX", "1")

    assert browser_headless() is True
    assert "--no-sandbox" in browser_args()
