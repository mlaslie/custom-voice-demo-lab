import pytest


@pytest.fixture(autouse=True)
def no_keychain(monkeypatch):
    """Tests never read or write the real OS keychain: secrets fall back to the test's secrets.json."""
    from demolab import config

    def blocked():
        raise RuntimeError("keychain disabled in tests")
    monkeypatch.setattr(config, "_kr", blocked)
