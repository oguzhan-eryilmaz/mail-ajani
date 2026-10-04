from mail_ajani import cli


def test_build_clients_collects_failures():
    def builder(account):
        if account == "bad@x.com":
            raise RuntimeError("no token")
        return f"client-{account}"

    clients, warnings = cli.build_clients(["ok@x.com", "bad@x.com"], builder=builder)
    assert clients == {"ok@x.com": "client-ok@x.com"}
    assert len(warnings) == 1 and "hesap-ekle bad@x.com" in warnings[0]


def test_tur_requires_setup(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MAIL_AJANI_HOME", str(tmp_path))
    monkeypatch.setenv("MAIL_AJANI_LOGS", str(tmp_path / "logs"))
    monkeypatch.setattr(cli.sirlar, "get_secret", lambda name: None)
    assert cli.main(["tur"]) == 2
    assert "bot-kur" in capsys.readouterr().out
