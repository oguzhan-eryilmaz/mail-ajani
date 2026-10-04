from mail_ajani import config, sirlar


def test_home_uses_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MAIL_AJANI_HOME", str(tmp_path / "h"))
    assert config.home() == tmp_path / "h"
    assert (tmp_path / "h").is_dir()
    assert config.db_path() == tmp_path / "h" / "ajan.db"


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MAIL_AJANI_HOME", str(tmp_path))
    assert config.load_config() == {"accounts": [], "chat_id": None}
    config.save_config({"accounts": ["a@gmail.com"], "chat_id": 42})
    assert config.load_config() == {"accounts": ["a@gmail.com"], "chat_id": 42}


def test_client_secret_per_domain(tmp_path, monkeypatch):
    monkeypatch.setenv("MAIL_AJANI_HOME", str(tmp_path))
    assert config.client_secret_path("a@gmail.com") == tmp_path / "client_secret.json"
    (tmp_path / "client_secret-eryondigital.com.json").write_text("{}")
    assert config.client_secret_path("x@eryondigital.com") == tmp_path / "client_secret-eryondigital.com.json"


def test_secrets_use_service_name(monkeypatch):
    store = {}
    monkeypatch.setattr(sirlar.keyring, "set_password", lambda s, n, v: store.__setitem__((s, n), v))
    monkeypatch.setattr(sirlar.keyring, "get_password", lambda s, n: store.get((s, n)))
    sirlar.set_secret("telegram_token", "x")
    assert store == {("mail-ajani", "telegram_token"): "x"}
    assert sirlar.get_secret("telegram_token") == "x"
    assert sirlar.get_secret("missing") is None
