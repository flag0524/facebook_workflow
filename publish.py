# 사이클 계획을 읽어 건별로 렌더링하고 페이스북 예약 게시로 등록하는 엔트리포인트
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

import requests

import fb
import render

ROOT = Path(__file__).parent
PLAN = ROOT / "content_plan.json"
STATE = ROOT / "state.json"
OUT = ROOT / "out"
LOG = ROOT / "publish.log"

load_dotenv(ROOT / ".env")

KST = dt.timezone(dt.timedelta(hours=9))


def log(msg):
    """스케줄러로 돌리면 표준출력이 사라지므로 파일에도 남긴다."""
    line = f"[{dt.datetime.now(KST):%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def notify(msg):
    """실패를 텔레그램으로 알린다. 설정이 없으면 조용히 넘어간다."""
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat, "text": msg},
            timeout=15,
        )
    except Exception as e:
        log(f"텔레그램 알림 실패: {e}")


def load_state():
    if not STATE.exists():
        return {}
    return json.loads(STATE.read_text(encoding="utf-8"))


def save_item(item_id, record):
    """건별로 즉시 기록한다. 중간에 죽어도 앞선 성공은 남는다."""
    state = load_state()
    state[item_id] = record
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATE)


def _publish_image(item, when, dry_run):
    png = OUT / f"{item['id']}.png"
    render.render_card(item["card"], png)
    if dry_run:
        log(f"  [dry-run] 사진 업로드 + 예약 등록 생략 ({png.name})")
        return None
    photo_id = fb.upload_photo(png)
    return fb.schedule_photo_post(item["message"], photo_id, when)


BGM_DIR = ROOT / "assets" / "bgm"


def _pick_bgm():
    """BGM 폴더에 파일이 있으면 첫 번째를 쓴다. 없으면 무음으로 간다."""
    if not BGM_DIR.exists():
        return None
    files = sorted(BGM_DIR.glob("*.mp3"))
    return files[0] if files else None


REEL_MIN_SEC, REEL_MAX_SEC = 20, 50


def _publish_reel(item, when, dry_run, video_state="SCHEDULED"):
    total = sum(s["sec"] for s in item["scenes"])
    if not REEL_MIN_SEC <= total <= REEL_MAX_SEC:
        raise ValueError(
            f"릴스 길이가 {total}초다. {REEL_MIN_SEC}~{REEL_MAX_SEC}초로 맞춰라"
        )
    mp4 = OUT / f"{item['id']}.mp4"
    render.render_reel(item["scenes"], mp4, bgm=_pick_bgm())
    if dry_run:
        log(f"  [dry-run] 릴스 업로드 + 예약 등록 생략 ({mp4.name})")
        return None
    return fb.schedule_reel(mp4, item["message"], when, video_state=video_state)


def run(plan_data, dry_run=False, video_state="SCHEDULED"):
    """계획의 모든 항목을 처리하고 (성공, 실패) 건수를 돌려준다."""
    ids = [item["id"] for item in plan_data["items"]]
    dupes = [i for i in ids if ids.count(i) > 1]
    assert not dupes, f"content_plan.json에 중복 id가 있다: {sorted(set(dupes))}"

    state = load_state()
    ok = fail = 0

    for item in plan_data["items"]:
        item_id = item["id"]
        if item_id in state:
            log(f"{item_id} 건너뜀 (이미 등록됨)")
            continue

        try:
            if not item.get("message"):
                raise ValueError("message가 비어있다. 원고를 채워라")
            when = dt.datetime.fromisoformat(item["publish_at"])

            if item["kind"] == "image":
                post_id = _publish_image(item, when, dry_run)
            elif item["kind"] == "reel":
                post_id = _publish_reel(item, when, dry_run, video_state=video_state)
            else:
                raise ValueError(f"알 수 없는 kind: {item['kind']}")

            if not dry_run:
                save_item(item_id, {
                    "kind": item["kind"],
                    "fb_post_id": post_id,
                    "scheduled_at": item["publish_at"],
                    "registered_at": dt.datetime.now(KST).isoformat(),
                })
            log(f"{item_id} 성공 → {post_id}")
            ok += 1
        except Exception as e:
            log(f"{item_id} 실패: {e}")
            fail += 1

    return ok, fail


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # ponytail: Windows cp949 콘솔이 em dash 등을 못 찍고 죽는 문제 회피
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--video-state",
        choices=("SCHEDULED", "DRAFT"),
        default="SCHEDULED",
        help="릴스 업로드 완료 상태. SCHEDULED 실패 시 DRAFT로 대체할 수 있다.",
    )
    args = ap.parse_args()

    plan_data = json.loads(PLAN.read_text(encoding="utf-8"))
    if plan_data["cycle"] != args.cycle:
        raise SystemExit(
            f"content_plan.json은 {plan_data['cycle']} 사이클이다. --cycle과 다르다"
        )

    if not args.dry_run:
        log(f"토큰 확인: {fb.verify_token()}")

    ok, fail = run(plan_data, dry_run=args.dry_run, video_state=args.video_state)
    summary = f"{args.cycle} 완료 — {ok}건 성공 / {fail}건 실패"
    log(summary)
    if fail and not args.dry_run:
        notify(summary + "\n실패한 건은 같은 명령을 다시 돌리면 재시도된다")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
