from backend.reliability_graph.config import Settings


def test_default_cors_regex_allows_vite_fallback_ports(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)

    settings = Settings.from_env()

    assert settings.cors_origin_regex == r"http://(localhost|127\.0\.0\.1):[0-9]+"
