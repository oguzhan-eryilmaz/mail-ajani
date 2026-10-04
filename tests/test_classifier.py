import json
import subprocess
from pathlib import Path

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
        {"items": [{"id": 2, "karar": "cop", "ozet": "reklam"}, {"id": 3, "karar": "uydurma", "ozet": ""},
                   {"id": 99, "karar": "cop", "ozet": ""}]})})
    assert classifier.parse_output(stdout, {2, 3}) == {2: ("cop", "reklam")}


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
    assert len(errors) == 1 and "rate limit" in errors[0]
    cmd = calls[0]
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert "--bare" not in cmd
    assert cmd[cmd.index("--tools") + 1] == ""


def test_classify_timeout_is_error():
    def runner(cmd, input, **kw):
        raise subprocess.TimeoutExpired(cmd, 300)

    preds, errors = classifier.classify([mail(1)], [], runner=runner)
    assert preds == {} and len(errors) == 1
