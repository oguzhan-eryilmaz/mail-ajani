import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_both_launchd_agents_have_explicit_home_after_install_substitution():
    for path in (ROOT / 'launchd').glob('*.plist'):
        source = path.read_text()
        text = source.replace('__HOME__', '/tmp/mail-ajani-owner').replace('__REPO__', '/tmp/repo').replace(
            '__PY__', '/tmp/repo/.venv/bin/python')
        data = plistlib.loads(text.encode())
        assert data['EnvironmentVariables']['HOME'] == '/tmp/mail-ajani-owner'
        assert data['EnvironmentVariables']['PATH'].startswith('/tmp/mail-ajani-owner/.local/bin:')


def test_scheduled_tur_retries_in_same_slot_and_keeps_calendar():
    data = plistlib.loads((ROOT / 'launchd/com.oguzhan.mail-ajani.tur.plist').read_bytes())
    assert data['StartInterval'] == 900
    assert data['StartCalendarInterval'] == [{'Hour': h, 'Minute': 0} for h in (0, 6, 12, 18)]
    assert data['RunAtLoad'] is True
