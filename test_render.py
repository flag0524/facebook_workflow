# render.py가 규격에 맞는 이미지를 뽑는지 확인하는 테스트
import subprocess
from pathlib import Path

import render

OUT = Path(__file__).parent / "out"


def _probe(path, stream_key):
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", stream_key, "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return res.stdout.strip()


def test_card_has_exact_dimensions():
    OUT.mkdir(exist_ok=True)
    path = OUT / "test_card.png"
    card = {"headline": "자동화가 실패하는 진짜 이유",
            "body": ["소재가 먼저 마른다", "코드는 두 번째 문제다"],
            "template": 1}
    render.render_card(card, path)
    assert path.exists(), "PNG가 생성되지 않았다"
    size = _probe(path, "stream=width,height")
    assert size == f"{render.IMG_W},{render.IMG_H}", f"규격이 다르다: {size}"


def test_card_escapes_html():
    """HTML 이스케이핑이 실제로 작동하는지 확인한다."""
    # headline의 <script> 태그가 &lt;script&gt;로 변환되어야 한다
    html_text = render._build_card_html(
        {"headline": "<script>alert(1)</script>", "body": ["a & b"], "template": 2}
    )
    assert "&lt;script&gt;" in html_text, "헤드라인의 < 기호가 이스케이프되지 않았다"
    assert "<script>" not in html_text, "헤드라인에 raw <script> 태그가 남아있다"
    assert "&amp;" in html_text, "바디의 & 기호가 이스케이프되지 않았다"

    # 렌더링도 성공하는지 스모크 테스트
    OUT.mkdir(exist_ok=True)
    path = OUT / "test_escape.png"
    render.render_card(
        {"headline": "<script>alert(1)</script>", "body": ["a & b"], "template": 2},
        path
    )
    assert path.exists(), "PNG가 생성되지 않았다"


def test_reel_has_exact_spec():
    OUT.mkdir(exist_ok=True)
    path = OUT / "test_reel.mp4"
    scenes = [
        {"text": "자동화가 실패하는 이유", "sec": 3},
        {"text": "코드가 아니라 소재다", "sec": 4},
        {"text": "주제 큐부터 만들어라", "sec": 3},
    ]
    render.render_reel(scenes, path, bgm=None)
    assert path.exists(), "MP4가 생성되지 않았다"

    size = _probe(path, "stream=width,height")
    assert size == f"{render.VID_W},{render.VID_H}", f"규격이 다르다: {size}"

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip())
    assert 9.5 <= dur <= 10.5, f"길이가 예상과 다르다: {dur}"


def test_reel_ffmpeg_failure_raises_runtime_error():
    """ffmpeg가 실제로 실패하면 RuntimeError로 이어지는지 확인한다."""
    OUT.mkdir(exist_ok=True)
    # sec에 정수가 아닌 값을 넣어 concat 리스트 파일 파싱을 ffmpeg가 거부하게 만든다
    scenes = [{"text": "장애 유발용 장면", "sec": "not-a-number"}]
    path = OUT / "test_reel_fail.mp4"
    try:
        render.render_reel(scenes, path, bgm=None)
        assert False, "ffmpeg가 실패해야 하는데 성공했다"
    except RuntimeError as e:
        assert "ffmpeg 실패" in str(e), f"에러 메시지가 예상과 다르다: {e}"


def test_ffmpeg_call_pins_utf8_encoding():
    """한글 경로(이 저장소 폴더명 자체가 한글)가 낀 ffmpeg 출력 배너는 UTF-8로
    찍히는데, subprocess.run에 encoding을 못 박지 않으면 cp949 콘솔에서 디코딩이
    깨져 res.stderr가 None이 되고, 실패 시 res.stderr[-2000:]가 RuntimeError
    대신 TypeError를 낸다 (실측 완료, ffmpeg 8.1.2 / Windows cp949).

    실제 ffmpeg로 이 디코딩 실패 자체를 안정적으로 재현하려면 출력 배너가
    찍힌 뒤에 실패하는 조건이 필요한데, 그런 조건을 인위적으로 만들기가
    불안정해 subprocess.run을 가짜로 바꿔 두 가지를 직접 확인한다.
    (1) render_reel이 실제로 subprocess.run을 encoding="utf-8",
    errors="replace"로 호출하는지 — 이 인자가 없으면 위 결함이 재발한다.
    (2) stderr 문자열이 정상적으로 들어왔을 때 RuntimeError 메시지에
    그대로 실리는지.
    """
    OUT.mkdir(exist_ok=True)
    scenes = [{"text": "정상 장면", "sec": 1}]
    path = OUT / "test_reel_encoding.mp4"

    captured_kwargs = {}
    real_run = render.subprocess.run

    def fake_run(cmd, **kwargs):
        captured_kwargs.update(kwargs)

        class _Result:
            returncode = 1
            stderr = "Output #0, mp4, to '한글_경로.mp4': 가짜 실패"
        return _Result()

    render.subprocess.run = fake_run
    try:
        try:
            render.render_reel(scenes, path, bgm=None)
            assert False, "가짜 ffmpeg 실패인데 RuntimeError가 나지 않았다"
        except RuntimeError as e:
            assert "가짜 실패" in str(e), f"stderr 내용이 에러 메시지에 없다: {e}"
        except TypeError as e:
            assert False, f"stderr 처리가 깨져 RuntimeError 대신 TypeError가 발생했다: {e}"
    finally:
        render.subprocess.run = real_run

    assert captured_kwargs.get("encoding") == "utf-8", \
        f"subprocess.run에 encoding='utf-8'이 전달되지 않았다: {captured_kwargs}"
    assert captured_kwargs.get("errors") == "replace", \
        f"subprocess.run에 errors='replace'가 전달되지 않았다: {captured_kwargs}"


if __name__ == "__main__":
    test_card_has_exact_dimensions()
    test_card_escapes_html()
    test_reel_has_exact_spec()
    test_reel_ffmpeg_failure_raises_runtime_error()
    test_ffmpeg_call_pins_utf8_encoding()
    print("OK")
