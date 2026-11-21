"""Screenshots of a running demo (see demo.sh), signed in, the way the teacher sees it.

    uv run --with playwright==1.58.0 python shoot.py OUT_DIR / /students /reports/monthly \
        [--base http://127.0.0.1:5174] [--size phone,desktop] [--theme light,dark] [--lang fr] [--full]

One PNG per path × size × theme: `<path-slug>-<size>-<theme>.png` (e.g. `students-phone-dark.png`).
Phone is 390×844 at 2×, touch, like an iPhone; desktop is 1280×800. Motion is reduced so nothing is
caught mid-animation.

For a flow (open a sheet, tap a tile), import it instead:

    from shoot import app
    with app(theme="dark") as page:
        page.goto("/students/1")
        page.get_by_role("button", name="Encaisser").first.click()
        page.screenshot(path="out/sheet.png")
"""

import argparse
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

SIZES = {
    "phone": {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2,
              "is_mobile": True, "has_touch": True},
    "desktop": {"viewport": {"width": 1280, "height": 800}},
}  # fmt: skip
USER, PASSWORD = "aymen", "demo-pass-123"


@contextmanager
def app(
    base: str = "http://127.0.0.1:5174",
    size: str = "phone",
    theme: str = "light",
    lang: str = "fr",
) -> Iterator[Page]:
    """A signed-in page on the demo; `page.goto("/path")` is relative to `base`."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            base_url=base,
            color_scheme="dark" if theme == "dark" else "light",  # the app follows the device
            reduced_motion="reduce",
            locale="fr-FR" if lang == "fr" else "en-GB",
            **SIZES[size],
        )
        # The app opens in French unless told otherwise; this is what Réglages › Langue stores.
        context.add_init_script(f"localStorage.setItem('ardoise.locale', '{lang}')")
        page = context.new_page()
        page.goto("/")
        page.locator("input[autocomplete=username]").fill(USER)
        page.locator("input[type=password]").fill(PASSWORD)
        page.locator("button[type=submit]").click()
        page.locator("input[type=password]").wait_for(state="detached")
        try:
            yield page
        finally:
            browser.close()


def settle(page: Page) -> None:
    """Wait for the data and the fonts, and move the pointer off anything it would highlight."""
    page.wait_for_load_state("networkidle")
    page.evaluate("document.fonts.ready")
    page.mouse.move(1, 1)
    page.wait_for_timeout(300)


def slug(path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-") or "home"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--base", default="http://127.0.0.1:5174")
    parser.add_argument("--size", default="phone")
    parser.add_argument("--theme", default="light")
    parser.add_argument("--lang", default="fr")
    parser.add_argument("--full", action="store_true", help="the whole page, not just the screen")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    for size in args.size.split(","):
        for theme in args.theme.split(","):
            with app(args.base, size, theme, args.lang) as page:
                for path in args.paths:
                    page.goto(path)
                    settle(page)
                    target = args.out / f"{slug(path)}-{size}-{theme}.png"
                    page.screenshot(path=str(target), full_page=args.full)
                    print(target)


if __name__ == "__main__":
    main()
