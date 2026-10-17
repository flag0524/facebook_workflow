# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 개요

페이스북 페이지에 이미지 카드와 릴스를 **예약 게시**로 자동 등록하는 Python 스크립트 모음이다. 매일 게시하지 않는다. 계획(JSON)에 적힌 건을 미리 렌더링해서 Graph API의 `scheduled_publish_time`으로 페이스북에 예약을 맡긴다. 실제 운영은 GitHub Actions(`flag0524/facebook_workflow`)에서 돈다.

## 명령어

로컬은 Windows이고 `venv`를 쓴다. 테스트는 pytest가 아니라 파일마다 `__main__` 블록이 있는 단순 스크립트다.

```powershell
.\venv\Scripts\python.exe test_fb.py        # 각 파일이 test_* 함수를 모두 실행하고 OK를 찍는다
.\venv\Scripts\python.exe test_plan.py
.\venv\Scripts\python.exe test_publish.py
.\venv\Scripts\python.exe test_render.py    # Chromium(playwright) + ffmpeg 필요

# 테스트 하나만
.\venv\Scripts\python.exe -c "import test_fb as t; t.test_to_unix_respects_timezone()"

# 렌더링만 하고 API는 부르지 않는다 (out/에 png·mp4 생성)
.\venv\Scripts\python.exe publish.py --plan plans/vibe_coding.json --cycle VIBE-2026-10 --dry-run

# 토큰 확인
.\venv\Scripts\python.exe -c "import fb; print(fb.verify_token())"
```

의존성은 `requests`, `python-dotenv`, `playwright`다. 시스템에 `ffmpeg`가 있어야 하고 `python -m playwright install chromium`도 필요하다. 린터나 빌드 단계는 없다.

## 구조

모듈 경계가 엄격하다.
- `fb.py`는 Graph API(v25.0 고정)만 안다.
- `render.py`는 렌더링만 안다.
- `publish.py`가 둘을 엮는다.

- **`render.py`** — `templates/card.html`(1080 정사각 카드)과 `templates/scene.html`(1080×1920 장면)의 `__PLACEHOLDER__`를 치환한 뒤 Playwright로 스크린샷을 찍는다. 릴스는 장면 PNG를 ffmpeg concat으로 이어 MP4를 만든다. 배경 이미지는 base64 data URI로 HTML에 인라인한다.
- **`fb.py`** — 사진은 `published=false`로 올린 뒤 `/feed`에 예약한다. 릴스는 `video_reels` 3단계(start → rupload 바이너리 → finish)로 올린다. `video_state`는 `SCHEDULED`가 기본이고, 실패하면 `DRAFT`로 우회할 수 있다.
- **`publish.py`** — 계획 항목 중 **예약 창(지금+10분 ~ 지금+28일)** 안에 있는 미등록 건만 처리한다.
  - 창보다 먼 건은 다음 실행으로 미룬다.
  - 이미 지난 건은 경고만 남기고 건너뛴다. 재시도하지 않는다.
  - 등록에 성공하면 그 즉시 건별로 `state.json`에 기록한다.
- **`plan.py`** — 초기 설계인 반달 사이클(`2026-10A`/`B`, 이미지와 릴스 혼합)의 골격을 `topics.json`에서 만든다. 원고 필드는 비워 둔다. 현재 운영 중인 매일 릴스 계획은 이 스크립트로 만들지 않았다.

### 계획 파일과 실행 경로 (`.github/workflows/publish-page.yml`)

| 트리거 | 처리하는 계획 |
|---|---|
| `content_plan.json`을 main에 push | `content_plan.json`. **사람 검수 없이 바로 실제 예약된다** |
| 매일 06:00 KST cron | `content_plan.json`과 `plans/*.json` 전부(롤링 예약) |
| `workflow_dispatch` | 입력한 `plan`·`cycle`. `dry_run` 기본값은 true |

실행이 끝나면 Actions 봇이 `state.json`을 커밋하고 push한다(`chore: save Facebook publishing state`).

계획 JSON의 형태는 `{"cycle": ..., "items": [...]}`다.
- 각 항목에는 `id`, `kind`(`image`|`reel`), `publish_at`(KST ISO), `message`가 있다.
- 이미지 항목은 `card`를, 릴스 항목은 `scenes[{text, sec}]`를 가진다. 릴스 총 길이는 20~60초여야 한다.
- 배경 이미지는 선택 사항이고 `visual.image_path`에 넣는다.
- `plans/*.json`처럼 `warn_days_left`가 있는 계획은 "콘텐츠 뱅크"다. 원고가 그 일수 아래로 남으면 경고를 낸다. 뱅크는 항목을 이어 붙이는 식으로 운영한다.
- 원고(`message`, `scenes`)는 LLM API로 만들지 않는다. Claude Code 세션에서 직접 쓴다.

## 주의 사항

- **`state.json`이 중복 게시를 막는 유일한 장치다.** Actions 봇이 계속 커밋하므로 작업 전에 항상 `git pull`하고, 이 파일을 옛 버전으로 덮어쓰지 마라. 항목이 사라지면 같은 글이 다시 예약된다.
- 항목 `id`는 한 번 등록되면 바꾸지 마라. 바꾸면 새 건으로 인식된다.
- `content_plan.json`을 main에 push하면 곧바로 실게재가 된다. 시험할 때는 `--dry-run`이나 `workflow_dispatch`의 `dry_run=true`를 쓴다.
- **토큰**: `FB_PAGE_TOKEN`은 반드시 **페이지 토큰**이어야 한다.
  - `verify_token()`은 공개 필드인 페이지 이름만 읽기 때문에 사용자 토큰도 통과시킨다. 토큰 종류는 `debug_token`의 `type`이 `PAGE`인지로 확인한다.
  - 토큰은 비밀번호 변경이나 로그아웃(오류 코드 190, subcode 460/467)으로 무효화된다.
  - 운영 토큰은 GitHub Secrets에 있다. 로컬 `.env`의 토큰과 같지 않을 수 있다.
- 실행 로그는 `publish.log`에 남는다(gitignore 대상). Windows 콘솔(cp949)에서 깨지지 않도록 `main()`이 stdout을 UTF-8로 다시 설정한다.
- 설계 배경은 `context-notes.md`와 `docs/superpowers/specs/`에 있다. 토큰 발급 절차는 설계 문서 7절에 있다.
