# 콘텐츠 계획 항목을 PNG나 MP4로 뽑는 렌더러. 페이스북 API를 알지 못한다
import html
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
TEMPLATES = ROOT / "templates"

IMG_W, IMG_H = 1080, 1350
VID_W, VID_H, FPS = 1080, 1920, 30


def _shoot(html_text, out_path, width, height):
    """HTML 문자열을 지정 크기 PNG로 찍는다."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_content(html_text, wait_until="networkidle")
            page.screenshot(path=str(out_path))
        finally:
            browser.close()
    return out_path


def _build_card_html(card):
    """카드를 HTML 문자열로 렌더링한다. 이스케이핑을 포함하지만 브라우저를 쓰지 않는다."""
    tpl = (TEMPLATES / "card.html").read_text(encoding="utf-8")
    body = "".join(f"<li>{html.escape(line)}</li>" for line in card["body"])
    filled = (
        tpl.replace("__TEMPLATE__", str(card.get("template", 1)))
        .replace("__HEADLINE__", html.escape(card["headline"]))
        .replace("__BODY__", body)
    )
    return filled


def render_card(card, out_path):
    """이미지 게시물 카드 1장을 PNG로 만든다."""
    filled = _build_card_html(card)
    return _shoot(filled, Path(out_path), IMG_W, IMG_H)


def render_reel(scenes, out_path, bgm=None):
    """장면 목록을 PNG로 찍고 ffmpeg로 이어붙여 MP4를 만든다."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tpl = (TEMPLATES / "scene.html").read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        lines = []
        for idx, scene in enumerate(scenes):
            png = tmp / f"{idx:02d}.png"
            _shoot(tpl.replace("__TEXT__", html.escape(scene["text"])),
                   png, VID_W, VID_H)
            lines.append(f"file '{png.as_posix()}'")
            lines.append(f"duration {scene['sec']}")
        # ffmpeg 8은 마지막 duration을 존중한다. 옛 버전 우회로 마지막 파일을 반복하면
        # 그 장면이 한 번 더 붙어 길이가 늘어난다 (8.1.2에서 10초 → 12.97초 실측)

        listfile = tmp / "list.txt"
        listfile.write_text("\n".join(lines), encoding="utf-8")

        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
               "-i", str(listfile)]
        if bgm:
            cmd += ["-stream_loop", "-1", "-i", str(bgm)]
        cmd += ["-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-vf", f"scale={VID_W}:{VID_H}"]
        if bgm:
            cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
        cmd.append(str(out_path))

        # ffmpeg는 stderr에 UTF-8로 출력하지만, cp949 콘솔에서 text=True만 쓰면
        # 한글 경로(예: 이 프로젝트 자체 폴더명)가 포함된 배너에서 디코딩이 깨져
        # res.stderr가 None이 되고 아래 슬라이싱이 TypeError를 낸다. 인코딩을 못 박는다
        res = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg 실패:\n{res.stderr[-2000:]}")

    return out_path
