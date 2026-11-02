"""Capture three contest screenshots from shots.html (phone-sized)."""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
SHOTS = ROOT.parent / "screenshots"
HTML = ROOT / "shots.html"
OUT = [
    ("shot-home", "小程序-小红书-01-首页三门课.png"),
    ("shot-quiz", "小程序-小红书-02-判错进错题本.png"),
    ("shot-wrong", "小程序-小红书-03-错题本列表.png"),
]


def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    uri = HTML.as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
        )
        page.goto(uri, wait_until="networkidle")
        page.wait_for_timeout(800)
        for elem_id, name in OUT:
            path = SHOTS / name
            page.locator(f"#{elem_id}").screenshot(path=str(path))
            print("WROTE", path, path.stat().st_size)
        browser.close()


if __name__ == "__main__":
    main()
