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


def _reel_at(item_id, when):
    return {
        "id": item_id, "kind": "reel", "message": "본문",
        "publish_at": when.isoformat(),
        "scenes": [{"text": "한 컷", "sec": 12}, {"text": "두 컷", "sec": 12}],
    }


def test_past_item_is_skipped_not_failed():
    if STATE.exists():
        STATE.unlink()
    past = dt.datetime.now(KST) - dt.timedelta(hours=1)
    data = {"cycle": "TEST", "items": [_reel_at("TEST-PAST", past)]}
    calls = []
    original = publish.render.render_reel
    publish.render.render_reel = lambda *a, **k: calls.append(a)
    try:
        ok, fail = publish.run(data, dry_run=True)
    finally:
        publish.render.render_reel = original
    assert (ok, fail) == (0, 0), "이미 지난 항목은 실패가 아니라 건너뛰어야 한다"
    assert calls == [], "지난 항목을 렌더링하면 안 된다"


def test_item_beyond_window_is_deferred():
    if STATE.exists():
        STATE.unlink()
    far = dt.datetime.now(KST) + dt.timedelta(days=publish.WINDOW_MAX_DAYS + 2)
    data = {"cycle": "TEST", "items": [_reel_at("TEST-FAR", far)]}
    calls = []
    original = publish.render.render_reel
    publish.render.render_reel = lambda *a, **k: calls.append(a)
    try:
        ok, fail = publish.run(data, dry_run=True)
    finally:
        publish.render.render_reel = original
    assert (ok, fail) == (0, 0), "예약 창 밖 항목은 다음 실행으로 미뤄야 한다"
    assert calls == [], "예약 창 밖 항목을 렌더링하면 안 된다"


def test_window_moves_with_now():
    """매일 cron이 돌면 창이 하루씩 밀리며 다음 항목이 들어온다."""
    if STATE.exists():
        STATE.unlink()
    now = dt.datetime(2026, 10, 2, 6, 0, tzinfo=KST)
    target = now + dt.timedelta(days=publish.WINDOW_MAX_DAYS, hours=6)
    data = {"cycle": "TEST", "items": [_reel_at("TEST-ROLL", target)]}
    calls = []
    original = publish.render.render_reel
    publish.render.render_reel = lambda *a, **k: calls.append(a)
    try:
        assert publish.run(data, dry_run=True, now=now) == (0, 0)
        assert publish.run(data, dry_run=True, now=now + dt.timedelta(days=1)) == (1, 0)
    finally:
        publish.render.render_reel = original
    assert len(calls) == 1


def test_bank_days_left():
    now = dt.datetime(2026, 10, 2, 6, 0, tzinfo=KST)
    data = {"cycle": "TEST", "items": [
        _reel_at("A", now + dt.timedelta(days=3)),
        _reel_at("B", now + dt.timedelta(days=10)),
    ]}
    assert round(publish.bank_days_left(data, now)) == 10
    assert publish.bank_days_left({"cycle": "TEST", "items": []}, now) == 0


if __name__ == "__main__":
    test_dry_run_makes_no_state()
    test_already_published_is_skipped()
    test_empty_message_is_failure()
    test_reel_item_is_handled()
    test_duplicate_id_raises_before_any_api_call()
    test_save_item_writes_atomically_no_tmp_left()
    test_reel_length_out_of_range_is_failure()
    test_past_item_is_skipped_not_failed()
    test_item_beyond_window_is_deferred()
    test_window_moves_with_now()
    test_bank_days_left()
    print("OK")
