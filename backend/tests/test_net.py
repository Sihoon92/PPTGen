import os

from app.config import Settings
from app.net import apply_proxy_bypass


def test_apply_proxy_bypass_disabled_keeps_env(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://corp:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://corp:8080")
    cleared = apply_proxy_bypass(Settings(_env_file=None, bypass_proxy=False))
    assert cleared == []
    assert os.environ.get("HTTP_PROXY") == "http://corp:8080"
    assert os.environ.get("HTTPS_PROXY") == "http://corp:8080"


def test_apply_proxy_bypass_clears_proxy_vars(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://corp:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://corp:8080")
    cleared = apply_proxy_bypass(Settings(_env_file=None, bypass_proxy=True))
    assert "HTTP_PROXY" in cleared
    assert "HTTPS_PROXY" in cleared
    assert os.environ.get("HTTP_PROXY") is None
    assert os.environ.get("HTTPS_PROXY") is None


def test_apply_proxy_bypass_noop_when_no_proxy_set(monkeypatch):
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    cleared = apply_proxy_bypass(Settings(_env_file=None, bypass_proxy=True))
    assert cleared == []


def test_bypass_proxy_defaults_false():
    assert Settings(_env_file=None).bypass_proxy is False
