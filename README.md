# facebook_workflow

페이스북 페이지에 릴스와 이미지 카드를 자동으로 **예약 게시**하는 도구입니다.

원고를 JSON 계획 파일에 적어 두면 GitHub Actions가 매일 아침 영상과 이미지를 만듭니다. 그리고 Graph API로 페이스북에 예약을 걸어 둡니다. 실제 게시는 페이스북이 예약 시각에 합니다. 그래서 PC를 켜 둘 필요가 없습니다.

## 동작 방식

```
plans/*.json, content_plan.json   ← 원고 (사람 또는 Claude Code가 작성)
        │
        ▼  매일 06:00 KST (GitHub Actions)
  publish.py ─ 예약 창(지금+10분 ~ +28일) 안의 미등록 건만 골라
        │      render.py로 PNG/MP4 렌더링 → fb.py로 예약 등록
        ▼
  state.json   ← 등록 기록. Actions 봇이 자동 커밋
```

- 페이스북은 약 29일 뒤까지만 예약을 받습니다. 그래서 먼 날짜의 원고는 날짜가 가까워질 때까지 기다렸다가 매일 실행에서 차례로 등록됩니다.
- `state.json`에 이미 기록된 건은 다시 등록하지 않습니다. 같은 워크플로우를 여러 번 돌려도 중복 게시는 생기지 않습니다.
- 예약 시각이 이미 지났는데 등록되지 못한 건은 건너뜁니다. 이런 건은 Actions 화면에 경고로 표시됩니다.

## 콘텐츠 추가하기

계획 파일은 두 종류입니다.

| 파일 | 용도 |
|---|---|
| `plans/*.json` | **콘텐츠 뱅크.** 원고를 계속 이어 붙이는 방식입니다. 남은 원고가 `warn_days_left`일보다 적어지면 경고합니다. |
| `content_plan.json` | 한 사이클 단위 계획입니다. main에 push하면 **검수 없이 즉시 예약 등록**됩니다. |

릴스 항목 예시입니다.

```json
{
  "id": "VIBE-20261003",
  "kind": "reel",
  "publish_at": "2026-10-03T12:30:00+09:00",
  "message": "게시글 본문 #해시태그",
  "scenes": [
    {"text": "첫 장면 문구", "sec": 5},
    {"text": "두 번째 장면\n줄바꿈 가능", "sec": 8}
  ]
}
```

- `id`는 계획 전체에서 유일해야 합니다. 한 번 등록된 뒤에는 바꾸면 안 됩니다. 바꾸면 새 글로 인식돼 다시 올라갑니다.
- 릴스 장면 길이의 합은 20~60초여야 합니다.
- 이미지 카드는 `"kind": "image"`로 쓰고 `scenes` 대신 `"card": {"headline", "body": [...], "template": 1~3}`를 넣습니다.
- 배경 이미지를 쓰려면 경로를 넣습니다. 릴스는 `"visual": {"image_path": "assets/..."}`에, 이미지 카드는 `card.image`에 넣습니다. 없으면 단색 배경으로 렌더링됩니다.
- 배경 음악은 `assets/bgm/`에 mp3를 넣으면 첫 파일을 씁니다.

## GitHub Actions 설정

저장소 **Settings → Secrets and variables → Actions**에 다음 값을 등록합니다.

| Secret | 설명 |
|---|---|
| `FB_PAGE_ID` | 페이스북 페이지 ID |
| `FB_PAGE_TOKEN` | **페이지** 액세스 토큰 (사용자 토큰이면 안 됩니다) |
| `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | 선택 사항. 실패하거나 원고가 바닥나면 텔레그램으로 알립니다 |

워크플로우는 세 가지 경우에 실행됩니다.
- **매일 06:00 KST 자동 실행**: 모든 계획 파일을 처리합니다.
- **`content_plan.json`을 push할 때**: 그 파일만 즉시 처리합니다.
- **수동 실행**: Actions 탭에서 *Publish reviewed Facebook Page cycle* → *Run workflow*를 누릅니다. `dry_run`의 기본값은 true라서 렌더링만 하고 등록하지 않습니다.

## 페이지 토큰 발급

1. [Graph API 탐색기](https://developers.facebook.com/tools/explorer/)에서 앱을 고르고 다음 권한을 줍니다.
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
2. 로그인 동의 화면의 페이지 선택 단계에서 **게시할 페이지를 반드시 체크**합니다. 체크하지 않으면 페이지 토큰을 받을 수 없습니다.
3. 단기 사용자 토큰을 장기 토큰(60일)으로 바꿉니다.
   `GET /oauth/access_token?grant_type=fb_exchange_token&client_id={앱ID}&client_secret={앱시크릿}&fb_exchange_token={단기토큰}`
4. 장기 토큰으로 `GET /me/accounts`를 호출해 해당 페이지의 `access_token`을 받습니다. 이것이 만료되지 않는 페이지 토큰입니다.
5. [액세스 토큰 디버거](https://developers.facebook.com/tools/debug/accesstoken/)에서 **Type이 Page**인지 확인한 뒤 Secret에 등록합니다.

토큰은 페이스북 비밀번호를 바꾸거나 보안 조치로 세션이 끊기면 무효화됩니다. 이때 Actions 로그에 `OAuthException 190`이 찍히고, 위 절차로 다시 발급해야 합니다.

## 로컬에서 실행하기

Python 3.11 이상과 [ffmpeg](https://ffmpeg.org/)가 필요합니다.

```powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
.\venv\Scripts\python -m playwright install chromium
copy .env.example .env    # FB_PAGE_ID, FB_PAGE_TOKEN 입력
```

```powershell
# 렌더링만 해서 out/에 결과물 확인 (페이스북 호출 없음)
.\venv\Scripts\python publish.py --plan plans/vibe_coding.json --cycle VIBE-2026-10 --dry-run

# 테스트
.\venv\Scripts\python test_fb.py
.\venv\Scripts\python test_plan.py
.\venv\Scripts\python test_publish.py
.\venv\Scripts\python test_render.py
```

`--cycle`에는 계획 파일 안의 `cycle` 값을 그대로 적어야 합니다. 다르면 실행을 거부합니다.

## 문제 해결

| 증상 | 원인과 조치 |
|---|---|
| `OAuthException 190` (subcode 460/467) | 토큰이 무효화됐습니다. 페이지 토큰을 다시 발급해 Secret을 갱신하세요. |
| 토큰 확인은 통과했는데 등록이 실패 | 사용자 토큰을 넣었을 가능성이 큽니다. 디버거에서 Type이 Page인지 확인하세요. |
| 릴스 예약이 계속 실패 | 수동 실행에서 `video_state`를 `DRAFT`로 바꾸세요. 초안으로 올라가므로 비즈니스 스위트에서 직접 예약하면 됩니다. |
| "콘텐츠 뱅크 원고가 N일치만 남았다" 경고 | 해당 `plans/*.json`에 다음 원고를 이어 붙이세요. |
| 같은 글을 다시 올리고 싶음 | `state.json`에서 해당 `id` 항목을 지우고 push하세요. 다음 실행 때 다시 등록됩니다. |

`state.json`은 Actions 봇이 계속 커밋합니다. 수정하기 전에는 반드시 `git pull`부터 하세요.
