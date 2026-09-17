# fb.py의 자격증명 로딩과 토큰 검증을 확인하는 테스트
import datetime as dt
import os
import tempfile
from pathlib import Path

import fb

KST = dt.timezone(dt.timedelta(hours=9))


def test_graph_version_is_pinned():
    assert fb.GRAPH == "https://graph.facebook.com/v25.0"


def test_creds_raises_without_env():
    old_id = os.environ.pop("FB_PAGE_ID", None)
    try:
        raised = False
        try:
            fb.creds()
        except RuntimeError:
            raised = True
        assert raised, "FB_PAGE_ID가 없으면 RuntimeError여야 한다"
    finally:
        if old_id is not None:
            os.environ["FB_PAGE_ID"] = old_id


def test_to_unix_respects_timezone():
    when = dt.datetime(2026, 10, 1, 9, 0, tzinfo=KST)
    assert fb.to_unix(when) == 1790812800


def test_rupload_base_is_pinned():
    assert fb.RUPLOAD == "https://rupload.facebook.com/video-upload/v25.0"


def test_schedule_reel_exists():
    assert callable(fb.schedule_reel)


class _FakeResponse:
    def __init__(self, body):
        self.ok = True
        self.status_code = 200
        self._body = body

    def json(self):
        return self._body


def _run_schedule_reel_with_fake_start_response(start_body, **schedule_kwargs):
    """1단계 응답을 start_body로 고정하고 schedule_reel을 실행한 뒤
    실제로 호출된 URL 목록과 마지막 finish 단계 data를 돌려준다.
    env·requests.post를 모두 복원한다.
    """
    old_id = os.environ.get("FB_PAGE_ID")
    old_token = os.environ.get("FB_PAGE_TOKEN")
    os.environ["FB_PAGE_ID"] = "pid"
    os.environ["FB_PAGE_TOKEN"] = "tok"
    calls = []
    finish_calls = []

    def fake_post(url, data=None, headers=None, timeout=None):
        calls.append(url)
        if url.endswith("/video_reels") and data.get("upload_phase") == "start":
            return _FakeResponse(start_body)
        if url.endswith("/video_reels") and data.get("upload_phase") == "finish":
            finish_calls.append(data)
        return _FakeResponse({"video_id": "vid123"})

    real_post = fb.requests.post
    fb.requests.post = fake_post
    try:
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "dummy.mp4"
            video.write_bytes(b"x")
            fb.schedule_reel(video, "설명", dt.datetime.now(dt.timezone.utc), **schedule_kwargs)
    finally:
        fb.requests.post = real_post
        for key, old in (("FB_PAGE_ID", old_id), ("FB_PAGE_TOKEN", old_token)):
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old

    return calls, finish_calls


def test_schedule_reel_prefers_server_upload_url():
    """1단계 응답에 upload_url이 있으면 그 값을 쓰는지 확인한다.
    schedule_reel은 실제 토큰이 생기기 전까진 검증 불가능한 구간이라,
    서버 응답을 신뢰하는 분기 자체는 requests를 가짜로 바꿔서라도 확인해 둔다.
    """
    calls, _ = _run_schedule_reel_with_fake_start_response(
        {"video_id": "vid123", "upload_url": "https://server-given/upload"}
    )
    assert "https://server-given/upload" in calls, \
        f"서버가 준 upload_url을 쓰지 않았다: {calls}"


def test_schedule_reel_falls_back_without_upload_url():
    """1단계 응답에 upload_url이 없으면 RUPLOAD/video_id로 구성한
    URL로 업로드하는지 확인한다."""
    calls, _ = _run_schedule_reel_with_fake_start_response({"video_id": "vid123"})
    expected = f"{fb.RUPLOAD}/vid123"
    assert expected in calls, f"폴백 URL을 쓰지 않았다: {calls}"


def test_schedule_reel_threads_video_state_into_finish_call():
    """video_state 파라미터를 finish 단계 요청에 그대로 전달하는지 확인한다.
    DRAFT 폴백을 코드 수정 없이 쓸 수 있어야 하므로 이 배선이 중요하다."""
    _, finish_calls = _run_schedule_reel_with_fake_start_response(
        {"video_id": "vid123"}, video_state="DRAFT"
    )
    assert finish_calls and finish_calls[0]["video_state"] == "DRAFT", \
        f"video_state가 finish 요청에 전달되지 않았다: {finish_calls}"


if __name__ == "__main__":
    test_graph_version_is_pinned()
    test_creds_raises_without_env()
    test_to_unix_respects_timezone()
    test_rupload_base_is_pinned()
    test_schedule_reel_exists()
    test_schedule_reel_prefers_server_upload_url()
    test_schedule_reel_falls_back_without_upload_url()
    test_schedule_reel_threads_video_state_into_finish_call()
    print("OK")
