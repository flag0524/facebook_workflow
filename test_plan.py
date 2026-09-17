# plan.py의 날짜 배치와 29일 창 제약을 검증하는 테스트
import datetime as dt
import json
import tempfile
from pathlib import Path

import plan

KST = dt.timezone(dt.timedelta(hours=9))


def _topics(n):
    tracks = ["trend", "stack", "workflow"]
    return [
        {"id": f"t{i:03d}", "track": tracks[i % 3], "title": f"주제 {i}", "used_in": None}
        for i in range(1, n + 1)
    ]


def test_a_cycle_covers_first_half():
    now = dt.datetime(2026, 9, 30, 10, 0, tzinfo=KST)
    dates = plan.cycle_dates("2026-10A", now)
    assert dates[0].day == 1
    assert dates[-1].day == 15
    assert len(dates) == 15


def test_b_cycle_covers_second_half():
    now = dt.datetime(2026, 10, 15, 10, 0, tzinfo=KST)
    dates = plan.cycle_dates("2026-10B", now)
    assert dates[0].day == 16
    assert dates[-1].day == 31
    assert len(dates) == 16


def test_past_slots_are_dropped():
    """1일 오후에 A사이클을 돌리면 1일 08:00 슬롯은 이미 지났으므로 빠진다."""
    now = dt.datetime(2026, 10, 1, 14, 0, tzinfo=KST)
    dates = plan.cycle_dates("2026-10A", now)
    assert all(d > now + dt.timedelta(minutes=10) for d in dates)


def test_all_slots_within_29_day_window():
    now = dt.datetime(2026, 10, 1, 9, 0, tzinfo=KST)
    dates = plan.cycle_dates("2026-10A", now)
    limit = now + dt.timedelta(days=plan.WINDOW_MAX_DAYS)
    assert all(d <= limit for d in dates)


def test_build_assigns_two_images_per_reel():
    now = dt.datetime(2026, 9, 30, 10, 0, tzinfo=KST)
    result = plan.build("2026-10A", _topics(20), now)
    kinds = [i["kind"] for i in result["items"]]
    assert kinds.count("reel") == 5
    assert kinds.count("image") == 10


def test_build_marks_topics_used():
    now = dt.datetime(2026, 9, 30, 10, 0, tzinfo=KST)
    topics = _topics(20)
    plan.build("2026-10A", topics, now)
    used = [t for t in topics if t["used_in"] == "2026-10A"]
    assert len(used) == 15


def test_build_refuses_when_topics_short():
    now = dt.datetime(2026, 9, 30, 10, 0, tzinfo=KST)
    raised = False
    try:
        plan.build("2026-10A", _topics(5), now)
    except RuntimeError as e:
        raised = "주제" in str(e)
    assert raised, "주제가 모자라면 RuntimeError여야 한다"


def test_build_image_templates_cycle_1_2_3():
    """이미지 템플릿이 전역 인덱스가 아니라 이미지별로 1,2,3 로테이션해야 한다."""
    now = dt.datetime(2026, 9, 30, 10, 0, tzinfo=KST)
    result = plan.build("2026-10A", _topics(20), now)
    images = [i for i in result["items"] if i["kind"] == "image"]
    templates = [i["card"]["template"] for i in images]
    expected = [1, 2, 3, 1, 2, 3, 1, 2, 3, 1]
    assert templates == expected, f"이미지 템플릿이 1,2,3 로테이션이어야 한다. 현재: {templates}"


def test_guard_raises_when_zero_items():
    raised = False
    try:
        plan.guard_before_write({"items": []}, "2020-01A", Path(tempfile.mkdtemp()) / "content_plan.json")
    except SystemExit:
        raised = True
    assert raised, "슬롯이 0건이면 SystemExit이어야 한다"


def test_guard_raises_when_plan_already_same_cycle():
    tmpdir = Path(tempfile.mkdtemp())
    plan_path = tmpdir / "content_plan.json"
    existing = {"cycle": "2026-10A", "items": [{"id": "2026-10A-01"}]}
    plan_path.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")

    raised = False
    try:
        plan.guard_before_write({"items": [{"id": "2026-10A-99"}]}, "2026-10A", plan_path)
    except SystemExit:
        raised = True
    assert raised, "같은 사이클의 content_plan.json이 이미 있으면 SystemExit이어야 한다"
    assert json.loads(plan_path.read_text(encoding="utf-8")) == existing, \
        "가드가 파일을 건드리면 안 된다"


if __name__ == "__main__":
    test_a_cycle_covers_first_half()
    test_b_cycle_covers_second_half()
    test_past_slots_are_dropped()
    test_all_slots_within_29_day_window()
    test_build_assigns_two_images_per_reel()
    test_build_marks_topics_used()
    test_build_refuses_when_topics_short()
    test_build_image_templates_cycle_1_2_3()
    test_guard_raises_when_zero_items()
    test_guard_raises_when_plan_already_same_cycle()
    print("OK")
