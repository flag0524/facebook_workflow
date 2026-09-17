# 주제 큐에서 사이클 골격을 만들어 content_plan.json으로 내보내는 스크립트
import argparse
import calendar
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).parent
TOPICS = ROOT / "topics.json"
PLAN = ROOT / "content_plan.json"

KST = dt.timezone(dt.timedelta(hours=9))
WINDOW_MIN_MINUTES = 10
WINDOW_MAX_DAYS = 29
SLOTS = [(8, 0), (12, 30), (20, 30)]


def cycle_dates(cycle, now):
    """사이클 ID를 예약 시각 목록으로 바꾼다. 창을 벗어나는 슬롯은 버린다."""
    year, rest = cycle.split("-")
    month, half = int(rest[:2]), rest[2].upper()
    year = int(year)

    if half == "A":
        days = range(1, 16)
    else:
        days = range(16, calendar.monthrange(year, month)[1] + 1)

    floor = now + dt.timedelta(minutes=WINDOW_MIN_MINUTES)
    ceil = now + dt.timedelta(days=WINDOW_MAX_DAYS)

    out = []
    for idx, day in enumerate(days):
        hour, minute = SLOTS[idx % len(SLOTS)]
        when = dt.datetime(year, month, day, hour, minute, tzinfo=KST)
        if floor < when <= ceil:
            out.append(when)
    return out


def build(cycle, topics, now):
    """사이클 골격을 만든다. 원고 필드는 비워두고 사람이 채운다."""
    dates = cycle_dates(cycle, now)
    unused = [t for t in topics if t["used_in"] is None]
    if len(unused) < len(dates):
        raise RuntimeError(
            f"주제가 모자란다. 필요 {len(dates)}건, 남은 {len(unused)}건. topics.json을 채워라"
        )

    items = []
    image_count = 0
    for idx, when in enumerate(dates):
        topic = unused[idx]
        topic["used_in"] = cycle
        kind = "reel" if idx % 3 == 2 else "image"
        item = {
            "id": f"{cycle}-{idx + 1:02d}",
            "kind": kind,
            "topic_id": topic["id"],
            "topic_title": topic["title"],
            "message": "",
            "publish_at": when.isoformat(),
        }
        if kind == "image":
            item["card"] = {"headline": "", "body": [], "template": image_count % 3 + 1}
            image_count += 1
        else:
            item["scenes"] = []
        items.append(item)

    return {"cycle": cycle, "items": items}


def guard_before_write(result, cycle, plan_path):
    """빈 계획으로 덮어쓰거나 이미 같은 사이클인 계획을 지우는 사고를 막는다."""
    if not result["items"]:
        raise SystemExit(f"{cycle}의 예약 가능한 슬롯이 0건이다. 사이클 ID를 확인해라")
    if plan_path.exists():
        existing = json.loads(plan_path.read_text(encoding="utf-8"))
        if existing.get("cycle") == cycle:
            raise SystemExit(
                f"content_plan.json이 이미 {cycle} 사이클이다. 덮어쓰려면 먼저 지워라"
            )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle", required=True, help="예: 2026-10A")
    args = ap.parse_args()

    topics = json.loads(TOPICS.read_text(encoding="utf-8"))
    now = dt.datetime.now(KST)
    result = build(args.cycle, topics, now)
    guard_before_write(result, args.cycle, PLAN)

    PLAN.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    TOPICS.write_text(
        json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    left = len([t for t in topics if t["used_in"] is None])
    print(f"{args.cycle}: {len(result['items'])}건 골격 생성. 남은 주제 {left}건")
    if left < 15:
        print("경고: 다음 사이클 주제가 모자란다. topics.json을 채워라")


if __name__ == "__main__":
    main()
