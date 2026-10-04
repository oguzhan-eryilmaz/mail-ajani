import builtins
import fcntl

import pytest

from mail_ajani import config, db
from mail_ajani.gmail import GmailAuthError
from mail_ajani.telegram import TelegramError
from tests.helpers import FakeGmail, FakeTg, make_mail
from tests.test_dinleyici import cb, OWNER, NOW

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


def test_overlapping_forced_tur_exits_cleanly_before_loading_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('MAIL_AJANI_HOME', str(tmp_path))
    def forbidden():
        raise AssertionError('second tur must not reach config or services')
    monkeypatch.setattr(config, 'load_config', forbidden)
    with (tmp_path / 'tur.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert cli.cmd_tur(force=True) == 0
    assert 'Başka bir tur çalışıyor' in capsys.readouterr().out


def test_lock_spans_whole_run_and_is_released_after_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('MAIL_AJANI_HOME', str(tmp_path))
    monkeypatch.setattr(config, 'load_config', lambda: {'accounts': [], 'chat_id': OWNER})
    monkeypatch.setattr(cli, '_telegram', lambda cfg: FakeTg())
    calls = []
    def running(*args, **kwargs):
        calls.append(1)
        assert cli.cmd_tur(force=True) == 0  # independent open cannot acquire flock
        raise TelegramError('SECRET')
    monkeypatch.setattr(cli.tur, 'run_tur', running)
    assert cli.cmd_tur(force=False) == 1
    assert cli.cmd_tur(force=True) == 1  # lock was released even on exception
    assert len(calls) == 2


def test_cmd_tur_returns_retry_status_when_work_incomplete(tmp_path, monkeypatch):
    monkeypatch.setenv('MAIL_AJANI_HOME', str(tmp_path))
    monkeypatch.setattr(config, 'load_config', lambda: {'accounts': [], 'chat_id': OWNER})
    monkeypatch.setattr(cli, '_telegram', lambda cfg: FakeTg())
    monkeypatch.setattr(cli.tur, 'run_tur', lambda *a, **kw: {'incomplete': True})
    assert cli.cmd_tur(force=False) == 1


def test_listener_reloads_accounts_and_rebuilds_client_after_auth_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('MAIL_AJANI_HOME', str(tmp_path))
    config.save_config({'accounts': ['a'], 'chat_id': OWNER})
    tg = FakeTg()
    monkeypatch.setattr(cli, '_telegram', lambda cfg: tg)
    a1, a2, b = FakeGmail('a'), FakeGmail('a'), FakeGmail('b')
    def denied(gid, action):
        raise GmailAuthError('invalid token')
    a1.apply = denied
    builds = []
    def build(accounts):
        builds.append(accounts[:])
        if accounts == ['a']:
            return {'a': a1 if builds.count(['a']) == 1 else a2}, []
        assert accounts == ['b']
        return {'b': b}, []
    monkeypatch.setattr(cli, 'build_clients', build)
    def listener(conn, get_clients, tg, owner):
        first = get_clients()
        assert first == {'a': a1}
        config.save_config({'accounts': ['a', 'b'], 'chat_id': OWNER})
        assert get_clients() == {'a': a1, 'b': b}
        mid = make_mail(conn, account='b')
        cli.dinleyici.handle_update(conn, cb(f'a:cop:{mid}'), get_clients(), tg, owner, NOW)
        assert len(b.applied) == 1
        mid = make_mail(conn, account='a')
        cli.dinleyici.handle_update(conn, cb(f'a:cop:{mid}'), get_clients(), tg, owner, NOW)
        assert db.active_decision(conn, mid) is None
        cli.dinleyici.handle_update(conn, cb(f'a:cop:{mid}'), get_clients(), tg, owner, NOW)
        assert db.active_decision(conn, mid)['action'] == 'cop' and len(a2.applied) == 1
        config.save_config({'accounts': ['b'], 'chat_id': OWNER})
        assert get_clients() == {'b': b}
    monkeypatch.setattr(cli.dinleyici, 'run_listener', listener)
    assert cli.cmd_dinle() == 0
    assert builds == [['a'], ['b'], ['a']]


@pytest.mark.parametrize('confirmation', ['', 'hayır', 'yes', 'evet'])
def test_bot_setup_shows_start_chat_and_requires_explicit_confirmation(tmp_path, monkeypatch, capsys, confirmation):
    monkeypatch.setenv('MAIL_AJANI_HOME', str(tmp_path))
    monkeypatch.setattr(cli.getpass, 'getpass', lambda prompt: 'SECRET')
    inputs = iter(['', confirmation])
    monkeypatch.setattr(builtins, 'input', lambda prompt: next(inputs))
    updates = [
        {'message': {'text': '/start', 'chat': {'id': OWNER, 'first_name': 'Sahip', 'username': 'sahip'}}},
        {'message': {'text': 'merhaba', 'chat': {'id': 999, 'first_name': 'Başka'}}},
    ]
    probe = FakeTg()
    probe.updates = lambda *a, **kw: updates
    monkeypatch.setattr(cli, 'TelegramClient', lambda *a, **kw: probe)
    saved = []
    monkeypatch.setattr(cli.sirlar, 'set_secret', lambda *args: saved.append(args))
    result = cli.cmd_bot_kur()
    output = capsys.readouterr().out
    assert 'Sahip' in output and '@sahip' in output and str(OWNER) in output
    assert 'SECRET' not in output
    if confirmation == 'evet':
        assert result == 0 and config.load_config()['chat_id'] == OWNER
        assert saved == [('telegram_token', 'SECRET')] and len(probe.sent) == 1
    else:
        assert result == 1 and config.load_config()['chat_id'] is None
        assert not (tmp_path / 'config.json').exists()
        assert saved == [] and probe.sent == []


def test_bot_setup_ignores_non_start_messages(tmp_path, monkeypatch):
    monkeypatch.setenv('MAIL_AJANI_HOME', str(tmp_path))
    monkeypatch.setattr(cli.getpass, 'getpass', lambda prompt: 'SECRET')
    monkeypatch.setattr(builtins, 'input', lambda prompt: '')
    probe = FakeTg()
    probe.updates = lambda *a, **kw: [{'message': {'text': 'hi', 'chat': {'id': 999}}}]
    monkeypatch.setattr(cli, 'TelegramClient', lambda *a, **kw: probe)
    monkeypatch.setattr(cli.sirlar, 'set_secret', lambda *a: pytest.fail('must not save token'))
    assert cli.cmd_bot_kur() == 1
    assert config.load_config()['chat_id'] is None and probe.sent == []


@pytest.mark.parametrize('deferred', [False, True])
def test_tur_skips_before_keychain_or_gmail_client_build(tmp_path, monkeypatch, deferred):
    from datetime import datetime, timedelta
    monkeypatch.setenv('MAIL_AJANI_HOME', str(tmp_path))
    now = datetime.now(config.TZ)
    conn = db.connect(config.db_path())
    if deferred:
        db.set_meta(conn, 'tur_incomplete', '1')
        db.set_meta(conn, 'telegram_retry_at', (now + timedelta(hours=1)).isoformat())
    else:
        db.set_meta(conn, 'last_run', now.isoformat())
    conn.close()
    def forbidden(*a, **kw):
        pytest.fail('skipped tur must not read secrets or build/refresh clients')
    monkeypatch.setattr(cli.sirlar, 'get_secret', forbidden)
    monkeypatch.setattr(cli, '_telegram', forbidden)
    monkeypatch.setattr(cli, 'build_clients', forbidden)
    monkeypatch.setattr(config, 'load_config', forbidden)
    assert cli.cmd_tur(force=False) == (1 if deferred else 0)


@pytest.mark.parametrize('work', ['force', 'pending', 'warning', 'incomplete', 'new_slot'])
def test_tur_preflight_allows_due_or_pending_work(tmp_path, monkeypatch, work):
    from datetime import datetime, timedelta
    monkeypatch.setenv('MAIL_AJANI_HOME', str(tmp_path))
    now = datetime.now(config.TZ)
    conn = db.connect(config.db_path())
    db.set_meta(conn, 'last_run', (now - timedelta(hours=6) if work == 'new_slot' else now).isoformat())
    if work == 'pending':
        make_mail(conn)
    elif work == 'warning':
        db.set_meta(conn, 'pending_warnings', '["uyarı"]')
    elif work == 'incomplete':
        db.set_meta(conn, 'tur_incomplete', '1')
    conn.close()
    calls = []
    monkeypatch.setattr(config, 'load_config', lambda: {'accounts': ['a'], 'chat_id': OWNER})
    monkeypatch.setattr(cli, '_telegram', lambda cfg: (calls.append('telegram'), FakeTg())[1])
    monkeypatch.setattr(cli, 'build_clients', lambda accounts: (calls.append('gmail'), ({}, []))[1])
    monkeypatch.setattr(cli.tur, 'run_tur', lambda *a, **kw: (calls.append('run'), {})[1])
    assert cli.cmd_tur(force=(work == 'force')) == 0
    assert calls == ['telegram', 'gmail', 'run']


@pytest.mark.parametrize('code,phrase', [(401, 'tanımadı'), (404, 'tanımadı'), (409, 'başka bir yerden'),
                                         (None, 'bağlantı hatası'), (502, 'kod 502')])
def test_bot_setup_explains_telegram_failure_without_traceback_or_token(tmp_path, monkeypatch, capsys, code, phrase):
    monkeypatch.setenv('MAIL_AJANI_HOME', str(tmp_path))
    monkeypatch.setattr(cli.getpass, 'getpass', lambda prompt: 'SECRET')
    monkeypatch.setattr(builtins, 'input', lambda prompt: '')
    probe = FakeTg()
    def fail(*a, **kw):
        raise TelegramError('getUpdates: Telegram isteği başarısız', status_code=code)
    probe.updates = fail
    monkeypatch.setattr(cli, 'TelegramClient', lambda *a, **kw: probe)
    monkeypatch.setattr(cli.sirlar, 'set_secret', lambda *a: pytest.fail('must not save token'))
    assert cli.cmd_bot_kur() == 1
    out = capsys.readouterr().out
    assert phrase in out and 'SECRET' not in out and 'Traceback' not in out
    assert config.load_config()['chat_id'] is None


class _ProfileSvc:
    def __init__(self, address):
        self.address = address

    def users(self):
        return self

    def getProfile(self, userId):
        return self

    def execute(self, num_retries=0):
        return {'emailAddress': self.address}


def _hesap_ekle_env(tmp_path, monkeypatch, granted):
    monkeypatch.setenv('MAIL_AJANI_HOME', str(tmp_path))
    (tmp_path / 'client_secret-sirket.com.json').write_text('{}')
    store = {}
    monkeypatch.setattr(cli.sirlar, 'set_secret', lambda n, v: store.__setitem__(n, v))
    monkeypatch.setattr(cli.sirlar, 'get_secret', lambda n: store.get(n))
    monkeypatch.setattr(cli.sirlar, 'delete_secret', lambda n: store.pop(n, None))
    monkeypatch.setattr(cli.gmail, 'authorize', lambda email: store.__setitem__(f'gmail:{email}', 'TOKEN'))
    def build(account):
        assert f'gmail:{account}' in store
        c = FakeGmail(account)
        c.svc = _ProfileSvc(granted)
        return c
    monkeypatch.setattr(cli.gmail, 'build_client', build)
    return store


def test_hesap_ekle_saves_the_address_that_actually_granted_access(tmp_path, monkeypatch, capsys):
    # Canlı kurulum, 5 Ekim: komut yer tutucu adresle çalıştırıldı, hesap yanlış adla kaydoldu.
    store = _hesap_ekle_env(tmp_path, monkeypatch, 'Gercek@sirket.com')
    assert cli.cmd_hesap_ekle('ADRESIN@sirket.com') == 0
    assert config.load_config()['accounts'] == ['gercek@sirket.com']
    assert store == {'gmail:gercek@sirket.com': 'TOKEN'}
    out = capsys.readouterr().out
    assert 'gercek@sirket.com' in out and 'TOKEN' not in out


def test_hesap_ekle_matching_address_is_unchanged(tmp_path, monkeypatch):
    store = _hesap_ekle_env(tmp_path, monkeypatch, 'ben@sirket.com')
    assert cli.cmd_hesap_ekle('ben@sirket.com') == 0
    assert config.load_config()['accounts'] == ['ben@sirket.com']
    assert store == {'gmail:ben@sirket.com': 'TOKEN'}


def test_hesap_ekle_refuses_token_from_another_domain(tmp_path, monkeypatch, capsys):
    (tmp_path / 'client_secret.json').write_text('{}')
    store = _hesap_ekle_env(tmp_path, monkeypatch, 'kisisel@gmail.com')
    assert cli.cmd_hesap_ekle('ben@sirket.com') == 1
    assert config.load_config()['accounts'] == [] and store == {}
    assert 'hesap-ekle kisisel@gmail.com' in capsys.readouterr().out


@pytest.mark.parametrize('count,onayla,runs', [(50, False, True), (201, False, False), (201, True, True)])
def test_backlog_scan_counts_first_and_never_floods(tmp_path, monkeypatch, capsys, count, onayla, runs):
    monkeypatch.setenv('MAIL_AJANI_HOME', str(tmp_path))
    monkeypatch.setattr(config, 'load_config', lambda: {'accounts': ['a'], 'chat_id': OWNER})
    monkeypatch.setattr(cli, '_telegram', lambda cfg: FakeTg())
    g = FakeGmail('a')
    g.count_since = lambda since, limit: count
    monkeypatch.setattr(cli, 'build_clients', lambda accounts: ({'a': g}, []))
    seen = []
    def fake_run(conn, clients, tg, classify, now, force=False, warnings=None, lookback=None):
        seen.append((force, lookback))
        return {'new': 0}
    monkeypatch.setattr(cli.tur, 'run_tur', fake_run)
    assert cli.main(['tur', '--geri', '30'] + (['--onayla'] if onayla else [])) == 0
    out = capsys.readouterr().out
    if runs:
        from datetime import timedelta
        assert seen == [(True, timedelta(days=30))]
    else:
        assert seen == [] and 'Hiçbir şey gönderilmedi' in out
