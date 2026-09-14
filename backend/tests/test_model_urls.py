import socket

import pytest


@pytest.fixture(autouse=True)
def services(monkeypatch):
    from app import services
    monkeypatch.setattr(services.settings, "app_env", "development")
    monkeypatch.setattr(services.settings, "ai_allow_private_hosts", False)
    monkeypatch.setattr(services.settings, "ai_allowed_hosts", "")
    monkeypatch.setattr(services.settings, "ai_fake_ip_hosts", "api.deepseek.com")
    return services


def dns(monkeypatch, addresses):
    from app import services
    monkeypatch.setattr(services.socket, "getaddrinfo", lambda *_: [
        (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
        for address in addresses
    ])


@pytest.mark.parametrize("addresses", [
    ["198.18.0.212"], ["fdfe:dcba:9876::3f"],
    ["198.18.0.212", "fdfe:dcba:9876::3f"], ["93.184.216.34", "198.18.0.212"],
])
def test_trusted_https_domain_accepts_fake_dns(monkeypatch, addresses, services):
    dns(monkeypatch, addresses)
    assert services.valid_url("https://api.deepseek.com/v1/") == "https://api.deepseek.com/v1"
    assert services.valid_url("https://API.DeepSeek.com:443/v1") == "https://API.DeepSeek.com:443/v1"
    monkeypatch.setattr(services.settings, "ai_fake_ip_hosts", "")
    with pytest.raises(services.ApiError):
        services.valid_url("https://api.deepseek.com/v1")


@pytest.mark.parametrize("url", [
    "http://api.deepseek.com/v1", "https://api.deepseek.com:8443/v1",
    "https://api.deepseek.com.evil.test/v1", "https://other.test/v1",
    "https://198.18.0.212/v1", "https://[fdfe:dcba:9876::3f]/v1",
])
def test_fake_dns_exception_is_scoped_to_https_domain(monkeypatch, url, services):
    dns(monkeypatch, ["198.18.0.212", "fdfe:dcba:9876::3f"])
    monkeypatch.setattr(services.settings, "ai_fake_ip_hosts", "api.deepseek.com,198.18.0.212,fdfe:dcba:9876::3f")
    with pytest.raises(services.ApiError):
        services.valid_url(url)


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254",
    "::1", "fe80::1", "fd00::1", "198.19.0.1", "fdfe:dcba:9876:1::1",
])
def test_private_dns_still_blocks_trusted_domain(monkeypatch, address, services):
    dns(monkeypatch, ["198.18.0.212", address])
    with pytest.raises(services.ApiError):
        services.valid_url("https://api.deepseek.com/v1")


def test_failed_or_empty_dns_is_rejected(monkeypatch, services):
    dns(monkeypatch, [])
    with pytest.raises(services.ApiError):
        services.valid_url("https://api.deepseek.com/v1")
    def fail(*_):
        raise socket.gaierror()
    monkeypatch.setattr(services.socket, "getaddrinfo", fail)
    with pytest.raises(services.ApiError):
        services.valid_url("https://api.deepseek.com/v1")


def test_public_dns_and_explicit_policies(monkeypatch, services):
    dns(monkeypatch, ["93.184.216.34"])
    assert services.valid_url("https://other.test/v1") == "https://other.test/v1"
    dns(monkeypatch, ["198.18.0.212"])
    monkeypatch.setattr(services.settings, "ai_allowed_hosts", "other.test")
    with pytest.raises(services.ApiError, match="AI_ALLOWED_HOSTS"):
        services.valid_url("https://api.deepseek.com/v1")
    monkeypatch.setattr(services.settings, "ai_allowed_hosts", "")
    monkeypatch.setattr(services.settings, "ai_allow_private_hosts", True)
    assert services.valid_url("https://127.0.0.1/v1") == "https://127.0.0.1/v1"


def test_server_fake_ip_compatibility_defaults_off(monkeypatch):
    from app.config import Settings
    monkeypatch.delenv("AI_FAKE_IP_HOSTS", raising=False)
    assert Settings(_env_file=None).ai_fake_ip_hosts == ""
