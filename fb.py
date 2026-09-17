# 페이스북 그래프 API 호출만 담당하는 얇은 래퍼. 콘텐츠 계획 구조를 알지 못한다
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent
GRAPH = "https://graph.facebook.com/v25.0"
RUPLOAD = "https://rupload.facebook.com/video-upload/v25.0"

load_dotenv(ROOT / ".env")


def creds():
    """페이지 ID와 토큰을 돌려준다. 없으면 즉시 죽는다."""
    page_id = os.getenv("FB_PAGE_ID")
    token = os.getenv("FB_PAGE_TOKEN")
    if not page_id or not token:
        raise RuntimeError("FB_PAGE_ID / FB_PAGE_TOKEN이 .env에 없다")
    return page_id, token


def _check(res):
    """그래프 API 응답을 검사한다. 에러 본문을 그대로 노출해야 원인이 보인다."""
    if not res.ok:
        raise RuntimeError(f"{res.status_code} {res.text}")
    return res.json()


def verify_token():
    """토큰이 살아있는지 확인하고 페이지 이름을 돌려준다."""
    page_id, token = creds()
    res = requests.get(
        f"{GRAPH}/{page_id}",
        params={"fields": "name", "access_token": token},
        timeout=30,
    )
    return _check(res)["name"]


def to_unix(when):
    """예약 시각을 그래프 API가 받는 유닉스 정수로 바꾼다."""
    return int(when.timestamp())


def upload_photo(path):
    """사진을 게시하지 않은 상태로 올리고 photo_id를 돌려준다."""
    page_id, token = creds()
    with open(path, "rb") as f:
        res = requests.post(
            f"{GRAPH}/{page_id}/photos",
            data={"published": "false", "access_token": token},
            files={"source": f},
            timeout=120,
        )
    return _check(res)["id"]


def schedule_photo_post(message, photo_id, when):
    """올려둔 사진을 본문과 묶어 예약 게시로 등록하고 post_id를 돌려준다."""
    import json as _json

    page_id, token = creds()
    res = requests.post(
        f"{GRAPH}/{page_id}/feed",
        data={
            "message": message,
            "attached_media[0]": _json.dumps({"media_fbid": photo_id}),
            "published": "false",
            "scheduled_publish_time": to_unix(when),
            "access_token": token,
        },
        timeout=60,
    )
    return _check(res)["id"]


def schedule_reel(path, description, when, video_state="SCHEDULED"):
    """릴스를 3단계로 업로드하고 예약 상태로 등록한 뒤 video_id를 돌려준다."""
    page_id, token = creds()
    path = Path(path)

    # 1단계: 업로드 세션 시작
    res = requests.post(
        f"{GRAPH}/{page_id}/video_reels",
        data={"upload_phase": "start", "access_token": token},
        timeout=60,
    )
    started = _check(res)
    video_id = started["video_id"]
    # 문서상 rupload.facebook.com/video-upload/{video_id}는 안정적으로 구성 가능하다고
    # 명시되어 있지만, 응답이 upload_url을 함께 주면 그 값을 우선한다. 이 함수는 실제
    # 토큰이 생기기 전까진 검증할 수 없는 구간이라 서버 값을 신뢰하는 쪽이 더 안전하다
    upload_url = started.get("upload_url") or f"{RUPLOAD}/{video_id}"

    # 2단계: 바이너리 업로드
    size = path.stat().st_size
    with open(path, "rb") as f:
        res = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(size),
            },
            data=f.read(),
            timeout=600,
        )
    _check(res)

    # 3단계: 예약 상태로 확정
    res = requests.post(
        f"{GRAPH}/{page_id}/video_reels",
        data={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": video_state,
            "scheduled_publish_time": to_unix(when),
            "description": description,
            "access_token": token,
        },
        timeout=120,
    )
    _check(res)
    return video_id
