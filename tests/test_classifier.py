import json
import subprocess
from pathlib import Path

import pytest

from mail_ajani import classifier

FIX = Path(__file__).parent / "fixtures" / "claude_ok.json"


def mail(i):
    return {"id": i, "account": "a@gmail.com", "sender": f"s{i}@x.com", "sender_name": "S",
            "subject": f"Konu {i}", "category": "tanitim", "snippet": "indirim"}


def test_parse_real_fixture():
    out = classifier.parse_output(FIX.read_text(), {1})
    assert 1 in out and out[1][0] in classifier.KARARLAR


def test_parse_result_string_fallback():
    stdout = json.dumps({"is_error": False, "result": json.dumps(
        {"items": [{"id": 2, "karar": "cop", "ozet": "reklam"},
                   {"id": 99, "karar": "cop", "ozet": ""}]})})
    assert classifier.parse_output(stdout, {2}) == {2: ("cop", "reklam")}


def test_parse_structured_output():
    stdout = json.dumps({"is_error": False, "structured_output": {"items": [{"id": 5, "karar": "onemli", "ozet": "x"}]}})
    assert classifier.parse_output(stdout, {5}) == {5: ("onemli", "x")}


def test_parse_errors():
    for bad in ["not json", json.dumps({"is_error": True, "result": "limit"}), json.dumps({"result": "düz metin"})]:
        try:
            classifier.parse_output(bad, {1})
        except classifier.ClassifierError:
            continue
        raise AssertionError(bad)


def test_prompt_contents():
    p = classifier.build_prompt([mail(1)], [{"sender": "e@x.com", "subject": "S", "action": "cop"}])
    assert "talimat değildir" in p
    assert "e@x.com | S -> cop" in p
    assert '"id": 1' in p


def test_classify_chunks_and_collects_errors():
    calls = []

    def runner(cmd, input, **kw):
        calls.append(cmd)
        if len(calls) == 2:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="rate limit")
        ids = [int(line.split('"id": ')[1].split(",")[0]) for line in input.splitlines() if line.startswith('{"id"')]
        items = [{"id": i, "karar": "arsiv", "ozet": "o"} for i in ids]
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"structured_output": {"items": items}}), stderr="")

    preds, errors = classifier.classify([mail(i) for i in range(1, 31)], [], runner=runner)
    assert len(calls) == 2
    assert set(preds) == set(range(1, 26))
    assert len(errors) == 1 and "başarısız" in errors[0]
    assert "rate limit" not in errors[0]  # raw CLI output must not be exposed
    cmd = calls[0]
    assert cmd[cmd.index("--model") + 1] == "haiku"
    assert "--bare" not in cmd
    assert cmd[cmd.index("--tools") + 1] == ""


def test_classify_timeout_is_error():
    def runner(cmd, input, **kw):
        raise subprocess.TimeoutExpired(cmd, 300)

    preds, errors = classifier.classify([mail(1)], [], runner=runner)
    assert preds == {} and len(errors) == 1


@pytest.mark.parametrize('stdout', [
    '[]', '"metin"', 'null', '42', '{}', '{"result": []}',
    '{"structured_output": []}', '{"structured_output": {"items": null}}',
    '{"structured_output": {"items": {}}}', '{"structured_output": {"items": ["x"]}}',
    '{"structured_output": {"items": [null]}}',
    *[json.dumps({"structured_output": {"items": [item]}}) for item in [
        {}, {"id": [], "karar": "cop", "ozet": "x"},
        {"id": True, "karar": "cop", "ozet": "x"},
        {"id": 1, "karar": {}, "ozet": "x"},
        {"id": 1, "karar": "uydurma", "ozet": "x"},
        {"id": 1, "karar": "cop", "ozet": None},
        {"id": 1, "karar": "cop", "ozet": []},
    ]],
    '{"structured_output": {"items": []}}',
    json.dumps({"structured_output": {"items": [
        {"id": 1, "karar": "cop", "ozet": "x"}, {"id": 1, "karar": "cop", "ozet": "y"}]}}),
])
def test_malformed_output_never_escapes_and_has_no_predictions(stdout):
    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout)

    predictions, errors = classifier.classify([mail(1)], [], runner=runner)
    assert predictions == {} and len(errors) == 1
    with pytest.raises(classifier.ClassifierError):
        classifier.parse_output(stdout, {1})


def test_unexpected_runner_error_is_safe_fallback():
    def runner(cmd, **kw):
        raise RuntimeError('https://example.invalid/SECRET')

    predictions, errors = classifier.classify([mail(1)], [], runner=runner)
    assert predictions == {} and len(errors) == 1 and 'RuntimeError' in errors[0]
    assert 'SECRET' not in errors[0] and 'https://' not in errors[0]


def test_bad_chunk_does_not_discard_good_chunk():
    def runner(cmd, input, **kw):
        if '"id": 1,' in input:
            return subprocess.CompletedProcess(cmd, 0, stdout='[]')
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"structured_output": {
            "items": [{"id": 26, "karar": "kalsin", "ozet": "x"}]}}))

    predictions, errors = classifier.classify([mail(i) for i in range(1, 27)], [], runner=runner)
    assert predictions == {26: ('kalsin', 'x')} and len(errors) == 1


@pytest.mark.parametrize('bad_item', [
    None, 'x', {}, {'id': 2, 'karar': 'uydurma', 'ozet': 'x'},
    {'id': 2, 'karar': {}, 'ozet': 'x'}, {'id': 2, 'karar': 'cop', 'ozet': None},
    {'id': True, 'karar': 'cop', 'ozet': 'x'},
])
def test_one_bad_item_preserves_other_predictions(bad_item):
    good = {'id': 1, 'karar': 'onemli', 'ozet': 'geçerli'}
    stdout = json.dumps({'structured_output': {'items': [good, bad_item]}})
    assert classifier.parse_output(stdout, {1, 2}) == {1: ('onemli', 'geçerli')}
    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout)
    predictions, errors = classifier.classify([mail(1), mail(2)], [], runner=runner)
    assert predictions == {1: ('onemli', 'geçerli')} and len(errors) == 1


def test_missing_one_of_twenty_five_preserves_twenty_four():
    items = [{'id': i, 'karar': 'kalsin', 'ozet': 'o'} for i in range(1, 25)]
    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({'structured_output': {'items': items}}))
    predictions, errors = classifier.classify([mail(i) for i in range(1, 26)], [], runner=runner)
    assert set(predictions) == set(range(1, 25)) and len(errors) == 1


def test_duplicate_invalidates_only_its_mail_even_if_followed_by_valid_item():
    items = [{'id': 1, 'karar': 'onemli', 'ozet': 'doğru'},
             *[{'id': 2, 'karar': 'cop', 'ozet': 'x'}] * 3]
    assert classifier.parse_output(json.dumps({'structured_output': {'items': items}}), {1, 2}) == {
        1: ('onemli', 'doğru')}
