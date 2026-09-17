# 중복 방지와 건별 커밋 동작을 검증하는 테스트
import datetime as dt
import json
import tempfile
from pathlib import Path

import publish

KST = dt.timezone(dt.timedelta(hours=9))

# 운영 파일을 건드리면 발행 기록이 날아가고 중복 방지가 무력화되며 테스트 노이즈가 섞인다.
# 테스트는 임시 디렉토리 안의 모든 파일만 쓴다.
TMPDIR = Path(tempfile.mkdtemp())
STATE = TMPDIR / "state.json"
LOG = TMPDIR / "publish.log"
OUT = TMPDIR / "out"
OUT.mkdir(exist_ok=True)
publish.STATE = STATE
publish.LOG = LOG
publish.OUT = OUT


def _plan():
    when = (dt.datetime.now(KST) + dt.timedelta(days=1)).isoformat()
    return {
        "cycle": "TEST",
        "items": [
            {"id": "TEST-01", "kind": "image", "message": "본문",
             "publish_at": when,
             "card": {"headline": "제목", "body": ["줄1"], "template": 1}},
        ],
    }


def test_dry_run_makes_no_state():
    if STATE.exists():
        STATE.unlink()
    ok, fail = publish.run(_plan(), dry_run=True)
    assert (ok, fail) == (1, 0)
    assert not STATE.exists(), "dry-run이 state.json을 만들면 안 된다"


def test_already_published_is_skipped():
    STATE.write_text(json.dumps({"TEST-01": {"fb_post_id": "x"}}), encoding="utf-8")
    calls = []
    original = publish.fb.upload_photo
    publish.fb.upload_photo = lambda p: calls.append(p)
    try:
        ok, fail = publish.run(_plan(), dry_run=False)
    finally:
        publish.fb.upload_photo = original
        STATE.unlink()
    assert calls == [], "이미 발행된 항목은 API를 호출하면 안 된다"
    assert (ok, fail) == (0, 0)


def test_empty_message_is_failure():
    if STATE.exists():
        STATE.unlink()
    data = _plan()
    data["items"][0]["message"] = ""
    ok, fail = publish.run(data, dry_run=True)
    assert (ok, fail) == (0, 1), "원고가 비면 실패로 잡아야 한다"


def test_reel_item_is_handled():
    if STATE.exists():
        STATE.unlink()
    when = (dt.datetime.now(KST) + dt.timedelta(days=1)).isoformat()
    data = {
        "cycle": "TEST",
        "items": [{
            "id": "TEST-02", "kind": "reel", "message": "본문",
            "publish_at": when,
            "scenes": [{"text": "한 컷", "sec": 12}, {"text": "두 컷", "sec": 12}],
        }],
    }
    ok, fail = publish.run(data, dry_run=True)
    assert (ok, fail) == (1, 0), "릴스 항목이 처리되지 않았다"


def test_duplicate_id_raises_before_any_api_call():
    if STATE.exists():
        STATE.unlink()
    when = (dt.datetime.now(KST) + dt.timedelta(days=1)).isoformat()
    data = {
        "cycle": "TEST",
        "items": [
            {"id": "TEST-DUP", "kind": "image", "message": "본문1",
             "publish_at": when,
             "card": {"headline": "제목", "body": ["줄1"], "template": 1}},
            {"id": "TEST-DUP", "kind": "image", "message": "본문2",
             "publish_at": when,
             "card": {"headline": "제목", "body": ["줄1"], "template": 1}},
        ],
    }
    calls = []
    original = publish.fb.upload_photo
    publish.fb.upload_photo = lambda p: calls.append(p)
    try:
        raised = False
        try:
            publish.run(data, dry_run=False)
        except AssertionError:
            raised = True
        assert raised, "중복 id는 AssertionError로 잡아야 한다"
    finally:
        publish.fb.upload_photo = original
    assert calls == [], "중복 id를 잡기 전에 API를 호출하면 안 된다"


def test_save_item_writes_atomically_no_tmp_left():
    if STATE.exists():
        STATE.unlink()
    tmp = STATE.with_suffix(".json.tmp")
    if tmp.exists():
        tmp.unlink()
    publish.save_item("TEST-ATOMIC", {"fb_post_id": "x"})
    assert json.loads(STATE.read_text(encoding="utf-8"))["TEST-ATOMIC"] == {"fb_post_id": "x"}
    assert not tmp.exists(), "성공 후 .tmp 파일이 남으면 안 된다"
    STATE.unlink()


def test_reel_length_out_of_range_is_failure():
    if STATE.exists():
        STATE.unlink()
    when = (dt.datetime.now(KST) + dt.timedelta(days=1)).isoformat()
    data = {
        "cycle": "TEST",
        "items": [{
            "id": "TEST-03", "kind": "reel", "message": "본문",
            "publish_at": when,
            "scenes": [{"text": "너무 짧다", "sec": 3}],
        }],
    }
    ok, fail = publish.run(data, dry_run=True)
    assert (ok, fail) == (0, 1), "20초 미만 릴스를 실패로 잡아야 한다"


if __name__ == "__main__":
    test_dry_run_makes_no_state()
    test_already_published_is_skipped()
    test_empty_message_is_failure()
    test_reel_item_is_handled()
    test_duplicate_id_raises_before_any_api_call()
    test_save_item_writes_atomically_no_tmp_left()
    test_reel_length_out_of_range_is_failure()
    print("OK")
