#!/usr/bin/env python3
"""Experimental, attended Instagram desktop Reel uploader for Mity Clipping Studio.

The script uses the visible Instagram website through Playwright. It does not use
private APIs, stealth plugins, CAPTCHA bypasses, or login-challenge workarounds.
The account owner must sign in manually and explicitly authorize the schedule.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VIDEO_ROOT = ROOT / "video-processing"
OUTPUT_DIR = VIDEO_ROOT / "output"
REJECTED_DIR = VIDEO_ROOT / "input" / "rejected"
ASSETS_DIR = VIDEO_ROOT / "input" / "assets"
COVER_FILE = ASSETS_DIR / "cover.jpg"
STATE_DIR = Path(__file__).resolve().parent
STATE_FILE = STATE_DIR / "upload_state.json"
CHROME_PROFILE_DIR = (
    Path.home() / ".local" / "share" / "instagram-dm" / "chrome-profile"
)
INSTAGRAM_URL = "https://www.instagram.com/"
VIDEO_EXTENSIONS = {".mp4"}
MIN_OUTPUT = 120
MIN_REJECTED = 38
SECONDS_BETWEEN_POSTS = 30
UI_TIMEOUT_MS = 30_000
POST_CONFIRM_TIMEOUT_MS = 90_000

# Exact sequence supplied by the project owner.
# The output batches total 99 videos (19 + 20 + 20 + 20 + 20), not 120.
BATCH_PLAN: list[dict[str, Any]] = [
    {"label": "Rejected batch 1", "folder": "rejected", "count": 19, "wait_after": 2 * 60 * 60},
    {"label": "Rejected batch 2", "folder": "rejected", "count": 19, "wait_after": 4 * 60 * 60},
    {"label": "Output batch 1", "folder": "output", "count": 19, "wait_after": 3 * 60 * 60},
    {"label": "Output batch 2", "folder": "output", "count": 20, "wait_after": 4 * 60 * 60},
    {"label": "Output batch 3", "folder": "output", "count": 20, "wait_after": 2 * 60 * 60},
    {"label": "Output batch 4", "folder": "output", "count": 20, "wait_after": 2 * 60 * 60},
    {"label": "Output batch 5", "folder": "output", "count": 20, "wait_after": 0},
]


class UploadError(RuntimeError):
    pass


class StopForInstagramChallenge(UploadError):
    pass


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def natural_key(path: Path) -> tuple[Any, ...]:
    """Sort numbered files numerically, then fall back to natural filename order."""
    if path.stem.isdigit():
        return (0, int(path.stem), path.name.casefold())
    pieces = re.split(r"(\d+)", path.name.casefold())
    return (1, *(int(part) if part.isdigit() else part for part in pieces))


def list_videos(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS),
        key=natural_key,
    )


def new_state() -> dict[str, Any]:
    return {
        "version": 1,
        "created_at": stamp(),
        "completed": [],
        "pending": None,
        "next_batch_index": 0,
        "next_batch_at": None,
    }


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return new_state()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("unsupported upload state format")
        data.setdefault("completed", [])
        data.setdefault("pending", None)
        data.setdefault("next_batch_index", 0)
        data.setdefault("next_batch_at", None)
        return data
    except Exception as exc:
        raise UploadError(
            f"Cannot read upload progress file {STATE_FILE}: {exc}. "
            "Do not delete it until you confirm which Reels were published."
        ) from exc


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(STATE_FILE)


def file_key(folder_name: str, path: Path) -> str:
    return f"{folder_name}/{path.name}"


def ask_caption() -> str:
    print("MITY REEL UPLOADER — caption is requested before inventory checks.")
    print("Paste the complete caption below. Blank lines are allowed.")
    print("When finished, enter END on a line by itself, then press Enter:")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            raise UploadError("Caption input ended before END was received.")
        if line.strip() == "END":
            break
        lines.append(line)
    caption = "\n".join(lines).strip()
    if not caption:
        raise UploadError("Caption cannot be empty. Nothing was opened or uploaded.")
    if len(caption) > 2200:
        raise UploadError(f"Caption is {len(caption)} characters; Instagram caption field limit is 2,200.")
    return caption


def print_plan(output_count: int, rejected_count: int) -> None:
    print("\n=== INVENTORY CHECK ===")
    print(f"Output videos:  {output_count} (minimum required: {MIN_OUTPUT})")
    print(f"Rejected videos:{rejected_count:>4} (minimum required: {MIN_REJECTED})")
    print("\n=== SCHEDULE ===")
    for index, batch in enumerate(BATCH_PLAN, start=1):
        wait = int(batch["wait_after"])
        wait_text = f"{wait // 3600}h {(wait % 3600) // 60}m" if wait else "No further wait"
        print(
            f"Batch {index}: {batch['label']:<17} "
            f"{batch['count']:>2} videos | wait after batch: {wait_text}"
        )
    output_scheduled = sum(int(b["count"]) for b in BATCH_PLAN if b["folder"] == "output")
    rejected_scheduled = sum(int(b["count"]) for b in BATCH_PLAN if b["folder"] == "rejected")
    print("\n=== TOTALS ===")
    print(f"Scheduled from rejected: {rejected_scheduled}")
    print(f"Scheduled from output:   {output_scheduled}")
    print(f"Total scheduled:          {output_scheduled + rejected_scheduled}")
    print(
        f"Output reserve at minimum inventory: {MIN_OUTPUT - output_scheduled} videos "
        "(the supplied schedule does not use all 120 output videos)."
    )
    print("Total inter-batch waiting time: 17 hours.")


def preflight() -> tuple[list[Path], list[Path]]:
    rejected = list_videos(REJECTED_DIR)
    output = list_videos(OUTPUT_DIR)
    print_plan(len(output), len(rejected))
    if len(output) < MIN_OUTPUT or len(rejected) < MIN_REJECTED:
        raise UploadError(
            "Inventory requirements are not met. Need at least 120 MP4 files in output/ "
            "and 38 MP4 files in input/rejected/. Chrome was not launched."
        )
    if not COVER_FILE.is_file():
        raise UploadError(f"Required cover for rejected videos was not found: {COVER_FILE}")
    # The requested schedule uses exactly 38 rejected and 99 output videos.
    if len(rejected) < 38 or len(output) < 99:
        raise UploadError("Not enough videos for the exact batch schedule.")
    return rejected, output


def select_batch_files(rejected: list[Path], output: list[Path], batch_index: int) -> list[Path]:
    batch = BATCH_PLAN[batch_index]
    folder_name = str(batch["folder"])
    source = rejected if folder_name == "rejected" else output
    offset = sum(
        int(item["count"])
        for item in BATCH_PLAN[:batch_index]
        if item["folder"] == folder_name
    )
    count = int(batch["count"])
    selected = source[offset : offset + count]
    if len(selected) != count:
        raise UploadError(f"{batch['label']} expected {count} files but found {len(selected)}.")
    return selected


def human_duration(seconds: int) -> str:
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def countdown(seconds: int, label: str) -> None:
    end_at = time.time() + seconds
    print(f"\n{label}")
    try:
        while True:
            remaining = int(end_at - time.time() + 0.999)
            if remaining <= 0:
                break
            print(f"\rTime remaining: {human_duration(remaining)}", end="", flush=True)
            time.sleep(min(1, remaining))
        print("\rTime remaining: 00:00:00 — continuing.             ")
    except KeyboardInterrupt:
        print("\nTimer interrupted. Schedule progress is saved; restart and choose RESUME.")
        raise


def challenge_check(page: Any) -> None:
    url = (page.url or "").lower()
    if any(part in url for part in ("/challenge/", "/checkpoint/", "/accounts/suspended")):
        raise StopForInstagramChallenge(
            f"Instagram security/checkpoint page detected ({page.url}). Stopping without attempting to bypass it."
        )
    try:
        body = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        body = ""
    warning_phrases = (
        "try again later",
        "confirm it's you",
        "confirm your identity",
        "suspicious login",
        "unusual activity",
        "automated behavior",
    )
    if any(phrase in body for phrase in warning_phrases):
        raise StopForInstagramChallenge(
            "Instagram displayed a security or activity warning. The uploader stopped; handle it manually in Chrome."
        )


def visible_text_locator(page: Any, text: str, *, last: bool = False) -> Any:
    """Find a visible exact-text element; avoid relying on unstable CSS classes."""
    candidates = []
    for role in ("button", "link"):
        try:
            locator = page.get_by_role(role, name=text, exact=True)
            for index in range(locator.count()):
                item = locator.nth(index)
                if item.is_visible():
                    candidates.append(item)
        except Exception:
            pass
    try:
        locator = page.get_by_text(text, exact=True)
        for index in range(locator.count()):
            item = locator.nth(index)
            if item.is_visible():
                candidates.append(item)
    except Exception:
        pass
    if not candidates:
        raise UploadError(f"Could not find a visible Instagram control labelled '{text}'.")
    return candidates[-1] if last else candidates[0]


def click_text(page: Any, text: str, *, last: bool = False) -> None:
    locator = visible_text_locator(page, text, last=last)
    locator.click(timeout=UI_TIMEOUT_MS)



def reveal_create_control(page: Any, *, click: bool) -> None:
    """Hover Instagram's collapsed left navigation, then reveal/click Create.

    Instagram may render the left rail as icons only until the pointer enters it.
    We first hover semantic navigation containers, then use conservative points
    inside the left rail as a fallback. No click is made until Create is visible.
    """
    challenge_check(page)
    print("[UI] Revealing Instagram's left navigation to locate Create...")

    # Prefer the actual left navigation element when it is identifiable.
    for selector in ("nav", '[role="navigation"]', "aside"):
        try:
            containers = page.locator(selector)
            for index in range(containers.count()):
                container = containers.nth(index)
                if not container.is_visible():
                    continue
                box = container.bounding_box()
                if not box:
                    continue
                # Ignore full-width/top navigation containers; this is the
                # collapsed vertical rail we want to expand.
                if box["x"] > 120 or box["width"] > 420:
                    continue
                container.hover(timeout=2500)
                page.wait_for_timeout(450)
                try:
                    create = visible_text_locator(page, "Create")
                    create.hover(timeout=2500)
                    page.wait_for_timeout(250)
                    create = visible_text_locator(page, "Create")
                    if click:
                        create.click(timeout=UI_TIMEOUT_MS)
                        print("[UI] Clicked Create after hovering the left navigation.")
                    else:
                        print("[UI] Create is visible after hovering the left navigation.")
                    return
                except Exception:
                    continue
        except Exception:
            continue

    # Fallback for Instagram layouts where the nav has no stable semantic
    # container. Hover several safe points along the left icon rail.
    try:
        viewport = page.evaluate(
            "() => ({ width: window.innerWidth, height: window.innerHeight })"
        )
        height = int(viewport.get("height") or 900)
        width = int(viewport.get("width") or 1440)
    except Exception:
        height, width = 900, 1440

    x_points = sorted({max(12, min(35, width - 1)), max(12, min(58, width - 1))})
    y_points = []
    for fraction in (0.43, 0.50, 0.57, 0.64, 0.71):
        y = max(80, min(height - 30, int(height * fraction)))
        if y not in y_points:
            y_points.append(y)

    for y in y_points:
        for x in x_points:
            page.mouse.move(x, y)
            page.wait_for_timeout(400)
            try:
                create = visible_text_locator(page, "Create")
                create.hover(timeout=2500)
                page.wait_for_timeout(250)
                create = visible_text_locator(page, "Create")
                if click:
                    create.click(timeout=UI_TIMEOUT_MS)
                    print(f"[UI] Clicked Create after sidebar hover at ({x}, {y}).")
                else:
                    print(f"[UI] Create is visible after sidebar hover at ({x}, {y}).")
                return
            except Exception:
                continue

    screenshot = Path("/tmp/mity-create-hover-not-found.png")
    try:
        page.screenshot(path=str(screenshot), full_page=True)
        print(f"[UI] Diagnostic screenshot saved to: {screenshot}")
    except Exception:
        pass
    raise UploadError(
        "Could not reveal Instagram's Create control after hovering the left sidebar. "
        "Check that the Home page is fully loaded and the left navigation is visible."
    )


def click_next(page: Any) -> None:
    """Prefer the Next control inside the active Crop dialog; otherwise use the current step's Next."""
    dialogs = page.locator('[role="dialog"][aria-label="Crop"]')
    crop_dialog = None
    for index in range(dialogs.count()):
        candidate = dialogs.nth(index)
        try:
            if candidate.is_visible():
                crop_dialog = candidate
        except Exception:
            continue

    clicked = False
    if crop_dialog is not None:
        controls = crop_dialog.locator('[role="button"]')
        for index in range(controls.count()):
            control = controls.nth(index)
            try:
                label = " ".join(control.inner_text(timeout=2000).split()).casefold()
                if label == "next" and control.is_visible() and control.is_enabled():
                    control.click(timeout=UI_TIMEOUT_MS)
                    clicked = True
                    break
            except Exception:
                continue

    if not clicked:
        click_text(page, "Next", last=True)

    page.wait_for_timeout(1200)
    challenge_check(page)


def set_file_from_computer(page: Any, file_path: Path, *, last_button: bool = False) -> None:
    # Prefer the native file chooser, matching the user-visible desktop workflow.
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        button = visible_text_locator(page, "Select from computer", last=last_button)
        with page.expect_file_chooser(timeout=12_000) as chooser_info:
            button.click(timeout=UI_TIMEOUT_MS)
        chooser_info.value.set_files(str(file_path))
        return
    except PlaywrightTimeoutError:
        pass
    except UploadError:
        pass
    # UI variants sometimes route the click to a hidden file input without emitting
    # a Playwright file-chooser event; use the corresponding accept filter as fallback.
    inputs = page.locator('input[type="file"]')
    expected = "image" if file_path.suffix.lower() in {".jpg", ".jpeg", ".png"} else "video"
    matches = []
    for index in range(inputs.count()):
        item = inputs.nth(index)
        accept = (item.get_attribute("accept") or "").lower()
        if expected in accept or (expected == "image" and any(x in accept for x in (".jpg", ".png", "image/"))) or (expected == "video" and any(x in accept for x in (".mp4", "video/"))):
            matches.append(item)
    if matches:
        matches[-1].set_input_files(str(file_path), timeout=UI_TIMEOUT_MS)
        return
    raise UploadError(f"Could not attach file through Instagram's visible file picker: {file_path.name}")


def set_portrait_9_16(page: Any) -> None:
    """Open Select crop, choose 9:16 from its portal menu, and verify Next."""
    dialogs = page.locator('[role="dialog"][aria-label="Crop"]')
    dialog = None
    for index in range(dialogs.count()):
        candidate = dialogs.nth(index)
        try:
            if candidate.is_visible():
                dialog = candidate
                break
        except Exception:
            continue

    if dialog is None:
        screenshot = Path("/tmp/mity-crop-dialog-not-found.png")
        try:
            page.screenshot(path=str(screenshot), full_page=True)
            print(f"[UI] Diagnostic screenshot saved to: {screenshot}")
        except Exception:
            pass
        raise UploadError("Instagram's visible Crop dialog was not found; stopped before changing the ratio.")

    def find_visible_ratio_button() -> Any | None:
        # Instagram renders the ratio popup in a separate visible layer/portal,
        # not necessarily as a descendant of the Crop dialog. Search page-wide.
        controls = page.locator('[role="button"]')
        for control_index in range(controls.count()):
            control = controls.nth(control_index)
            try:
                if not control.is_visible():
                    continue
                label = " ".join(control.inner_text(timeout=1200).split())
                if label == "9:16":
                    return control
            except Exception:
                continue
        return None

    # If the ratio menu is already open, do not toggle it closed.
    ratio_button = find_visible_ratio_button()
    if ratio_button is None:
        crop_icon = dialog.locator('svg[aria-label="Select crop"]')
        crop_button = None
        for icon_index in range(crop_icon.count()):
            icon = crop_icon.nth(icon_index)
            try:
                if not icon.is_visible():
                    continue
                # Supplied Inspector DOM: SVG is nested inside a real HTML button.
                ancestor = icon.locator("xpath=ancestor::button[1]")
                if ancestor.count() and ancestor.is_visible():
                    crop_button = ancestor
                    break
            except Exception:
                continue

        if crop_button is None:
            screenshot = Path("/tmp/mity-select-crop-parent-not-found.png")
            try:
                page.screenshot(path=str(screenshot), full_page=True)
                print(f"[UI] Diagnostic screenshot saved to: {screenshot}")
            except Exception:
                pass
            raise UploadError("Found no visible button parent for svg[aria-label='Select crop'].")

        print('[UI] Clicking the HTML button containing svg[aria-label="Select crop"]...')
        try:
            crop_button.scroll_into_view_if_needed(timeout=UI_TIMEOUT_MS)
            crop_button.hover(timeout=UI_TIMEOUT_MS)
            crop_button.click(timeout=UI_TIMEOUT_MS)
        except Exception as exc:
            screenshot = Path("/tmp/mity-select-crop-button-click-failed.png")
            try:
                page.screenshot(path=str(screenshot), full_page=True)
                print(f"[UI] Diagnostic screenshot saved to: {screenshot}")
            except Exception:
                pass
            raise UploadError(f"Could not open the crop ratio menu using the Select crop button: {exc}") from exc

        # The popup is rendered outside the Crop dialog. Wait for its global
        # role=button option to become visible instead of searching inside dialog.
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            challenge_check(page)
            ratio_button = find_visible_ratio_button()
            if ratio_button is not None:
                break
            page.wait_for_timeout(200)

    if ratio_button is None:
        screenshot = Path("/tmp/mity-crop-916-portal-option-not-found.png")
        try:
            page.screenshot(path=str(screenshot), full_page=True)
            print(f"[UI] Diagnostic screenshot saved to: {screenshot}")
        except Exception:
            pass
        visible_labels: list[str] = []
        controls = page.locator('[role="button"]')
        for index in range(controls.count()):
            control = controls.nth(index)
            try:
                if control.is_visible():
                    label = " ".join(control.inner_text(timeout=1000).split())
                    if label:
                        visible_labels.append(label)
            except Exception:
                continue
        labels = ", ".join(repr(label) for label in visible_labels[:25]) or "none"
        raise UploadError(
            "Clicked Select crop, but the page-wide visible 9:16 option did not appear. "
            f"Visible role=button labels: {labels}. No Next action was taken."
        )

    try:
        ratio_button.scroll_into_view_if_needed(timeout=UI_TIMEOUT_MS)
        ratio_button.hover(timeout=UI_TIMEOUT_MS)
        ratio_button.click(timeout=UI_TIMEOUT_MS)
    except Exception as exc:
        screenshot = Path("/tmp/mity-crop-916-option-click-failed.png")
        try:
            page.screenshot(path=str(screenshot), full_page=True)
            print(f"[UI] Diagnostic screenshot saved to: {screenshot}")
        except Exception:
            pass
        raise UploadError(f"Could not select Instagram's visible 9:16 ratio option: {exc}") from exc

    page.wait_for_timeout(600)
    challenge_check(page)

    # Instagram's Crop dialog is expected to remain open. Next belongs to the
    # dialog; the ratio choice is in the separate popup layer.
    next_button = None
    controls = dialog.locator('[role="button"]')
    for index in range(controls.count()):
        control = controls.nth(index)
        try:
            label = " ".join(control.inner_text(timeout=1500).split()).casefold()
            if label == "next" and control.is_visible() and control.is_enabled():
                next_button = control
                break
        except Exception:
            continue

    if next_button is None:
        screenshot = Path("/tmp/mity-crop-next-not-ready.png")
        try:
            page.screenshot(path=str(screenshot), full_page=True)
            print(f"[UI] Diagnostic screenshot saved to: {screenshot}")
        except Exception:
            pass
        raise UploadError("Selected 9:16, but no enabled Next control was found inside the Crop dialog.")

    print("[UI] Selected 9:16 from Instagram's page-level crop menu.")
    print("[UI] Crop dialog remains open as expected; its Next control is ready.")


def fill_caption(page: Any, caption: str) -> None:
    candidates = [
        page.get_by_placeholder(re.compile(r"Add a caption", re.I)),
        page.locator("textarea"),
        page.locator('[contenteditable="true"][role="textbox"]'),
    ]
    for locator in candidates:
        try:
            for index in range(locator.count()):
                item = locator.nth(index)
                if item.is_visible() and item.is_enabled():
                    item.fill(caption, timeout=UI_TIMEOUT_MS)
                    return
        except Exception:
            continue
    raise UploadError("Could not find Instagram's caption field on the final sharing screen.")


def wait_for_publish_confirmation(page: Any, video_path: Path) -> bool:
    messages = (
        "Your reel has been shared",
        "Your post has been shared",
        "Reel shared",
        "Post shared",
    )
    deadline = time.time() + POST_CONFIRM_TIMEOUT_MS / 1000
    while time.time() < deadline:
        challenge_check(page)
        for message in messages:
            try:
                locator = page.get_by_text(re.compile(re.escape(message), re.I))
                if locator.count() and locator.last.is_visible():
                    return True
            except Exception:
                pass
        page.wait_for_timeout(1000)
    print(f"\nNo clear success message was detected for {video_path.name}.")
    print("Inspect the open Chrome tab. Do not assume it posted just because Share was clicked.")
    answer = input("Did Instagram confirm that this Reel was published? Type YES or NO: ").strip().upper()
    if answer == "YES":
        return True
    if answer == "NO":
        return False
    raise UploadError("Confirmation was ambiguous. Progress is saved as pending; stopping to avoid duplicates.")


def launch_chrome() -> tuple[Any, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise UploadError(
            "Playwright is missing from instagram-dm/.venv. Install it with: "
            "instagram-dm/.venv/bin/python -m pip install playwright"
        ) from exc
    playwright = sync_playwright().start()
    try:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_PROFILE_DIR),
            channel="chrome",
            headless=False,
            no_viewport=True,
            args=["--start-maximized"],
        )
    except Exception:
        playwright.stop()
        raise
    return playwright, context


def prepare_login(context: Any) -> Any:
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(INSTAGRAM_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(3000)
    print("\nA dedicated Chrome profile has opened for the uploader.")
    print("Sign in manually if needed. Do not paste passwords or cookies into the terminal.")
    login_required = "/accounts/login" in (page.url or "").lower()
    login_inputs = page.locator('input[name="username"], input[name="password"], input[autocomplete="username"], input[type="password"]')
    for index in range(login_inputs.count()):
        try:
            if login_inputs.nth(index).is_visible():
                login_required = True
                break
        except Exception:
            continue
    if login_required:
        print("[LOGIN] Instagram requires manual sign-in in the Chrome window.")
        input("After signing in successfully, press Enter here: ")
        page.wait_for_timeout(2500)
    else:
        print("[LOGIN] Existing Instagram session detected; skipping the READY prompt.")
    challenge_check(page)
    # The left navigation is collapsed until hovered on some Instagram layouts.
    reveal_create_control(page, click=False)
    return page


def upload_one(context: Any, login_page: Any, video_path: Path, folder_name: str, caption: str, state: dict[str, Any]) -> None:
    key = file_key(folder_name, video_path)
    if key in state.get("completed", []):
        print(f"[ALREADY POSTED — SKIP] {key}")
        return
    state["pending"] = key
    save_state(state)
    page = context.new_page()  # a fresh tab for each Reel; the login tab stays untouched
    try:
        page.goto(INSTAGRAM_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1800)
        challenge_check(page)

        reveal_create_control(page, click=True)
        page.wait_for_timeout(700)
        click_text(page, "Post")
        page.wait_for_timeout(1000)

        set_file_from_computer(page, video_path)
        page.wait_for_timeout(2500)
        challenge_check(page)

        # Crop stage: explicitly select Portrait 9:16 as requested.
        set_portrait_9_16(page)
        click_next(page)

        # Edit stage: only unprocessed/rejected files need the external cover.
        if folder_name == "rejected":
            visible_text_locator(page, "Cover photo")
            set_file_from_computer(page, COVER_FILE, last_button=True)
            page.wait_for_timeout(1500)

        click_next(page)
        fill_caption(page, caption)
        page.wait_for_timeout(1000)
        challenge_check(page)

        # The user authorized the whole schedule with the PUBLISH confirmation.
        click_text(page, "Share", last=True)
        print(f"[SHARE CLICKED] {key}")

        if not wait_for_publish_confirmation(page, video_path):
            raise UploadError(
                f"Instagram did not confirm publication of {key}. The uploader stopped; inspect the post before retrying."
            )
        completed = set(state.get("completed", []))
        completed.add(key)
        state["completed"] = sorted(completed)
        state["pending"] = None
        state["last_published_at"] = stamp()
        save_state(state)
        print(f"[PUBLISHED CONFIRMED] {key}")
    except Exception as exc:
        screenshot = Path("/tmp") / f"mity-upload-error-{int(time.time())}.png"
        try:
            page.screenshot(path=str(screenshot), full_page=True)
            print(f"Diagnostic screenshot: {screenshot}")
        except Exception:
            pass
        print(f"[STOPPED] {key}: {exc}")
        print("No automatic retry will be attempted. Check Instagram manually to avoid duplicate posts.")
        raise
    else:
        page.close()


def resolve_pending(state: dict[str, Any]) -> None:
    pending = state.get("pending")
    if not pending:
        return
    print(f"\nA previous run stopped while processing: {pending}")
    answer = input("Did that Reel finish publishing on Instagram? Type YES or NO: ").strip().upper()
    if answer == "YES":
        completed = set(state.get("completed", []))
        completed.add(pending)
        state["completed"] = sorted(completed)
        state["pending"] = None
        save_state(state)
        print("Recorded as published; it will not be uploaded again.")
    elif answer == "NO":
        state["pending"] = None
        save_state(state)
        print("Recorded as not published; it may be attempted again.")
    else:
        raise UploadError("Please resolve the pending Reel with an exact YES or NO answer.")


def choose_campaign_state(state: dict[str, Any]) -> dict[str, Any]:
    next_batch = int(state.get("next_batch_index", 0))
    completed_count = len(state.get("completed", []))
    if completed_count == 0 and next_batch == 0 and not state.get("pending"):
        return state
    print(f"\nSaved upload progress: {completed_count} confirmed Reel(s); next batch index: {next_batch + 1}.")
    choice = input("Type RESUME to continue this schedule, or NEW to start a fresh schedule: ").strip().upper()
    if choice == "RESUME":
        return state
    if choice == "NEW":
        if input("This clears only the local upload history. Type RESET to confirm: ").strip().upper() != "RESET":
            raise UploadError("Fresh schedule cancelled.")
        state = new_state()
        save_state(state)
        return state
    raise UploadError("Type RESUME or NEW. Nothing was published.")


def run_test_one(context: Any, login_page: Any, rejected: list[Path], caption: str, state: dict[str, Any]) -> None:
    if not rejected:
        raise UploadError("No rejected video is available for a one-Reel test.")
    video = next((p for p in rejected if file_key("rejected", p) not in set(state.get("completed", []))), None)
    if video is None:
        raise UploadError("All rejected videos in the current inventory are already marked as published.")
    print(f"\nOne-Reel REJECTED test: {video.name}")
    print(f"External cover: {COVER_FILE}")
    if input("Type POST ONE to publish this single test Reel: ").strip() != "POST ONE":
        raise UploadError("One-Reel test cancelled.")
    upload_one(context, login_page, video, "rejected", caption, state)


def run_test_output(context: Any, login_page: Any, output: list[Path], caption: str, state: dict[str, Any]) -> None:
    if not output:
        raise UploadError("No processed video is available in output/ for a one-Reel test.")
    video = next((p for p in output if file_key("output", p) not in set(state.get("completed", []))), None)
    if video is None:
        raise UploadError("All output videos in the current inventory are already marked as published.")
    print(f"\nOne-Reel OUTPUT test: {video.name}")
    print("External cover: SKIPPED — this processed video already contains its cover.")
    if input("Type POST ONE to publish this single test Reel: ").strip() != "POST ONE":
        raise UploadError("One-Reel test cancelled.")
    upload_one(context, login_page, video, "output", caption, state)


def run_full_schedule(context: Any, login_page: Any, rejected: list[Path], output: list[Path], caption: str, state: dict[str, Any]) -> None:
    resolve_pending(state)
    start_index = int(state.get("next_batch_index", 0))
    if start_index >= len(BATCH_PLAN):
        print("The saved schedule is already complete. No new posts were started.")
        return

    # If the process was stopped during an inter-batch countdown, honor the
    # saved wall-clock deadline instead of starting the next batch immediately.
    saved_deadline = state.get("next_batch_at")
    if saved_deadline:
        target_time = datetime.fromisoformat(str(saved_deadline))
        remaining = max(0, int((target_time - datetime.now().astimezone()).total_seconds()))
        countdown(remaining, f"Resuming saved inter-batch timer. Next batch local time: {target_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        state["next_batch_at"] = None
        save_state(state)

    for batch_index in range(start_index, len(BATCH_PLAN)):
        batch = BATCH_PLAN[batch_index]
        batch_files = select_batch_files(rejected, output, batch_index)
        folder_name = str(batch["folder"])
        pending_files = [p for p in batch_files if file_key(folder_name, p) not in set(state.get("completed", []))]
        print(f"\n=== BATCH {batch_index + 1}/7: {batch['label']} ===")
        print(f"Target count: {batch['count']} | Remaining in this batch: {len(pending_files)}")
        for index, video in enumerate(pending_files, start=1):
            print(f"\nUploading {index}/{len(pending_files)} in this batch: {video.name}")
            upload_one(context, login_page, video, folder_name, caption, state)
            if index < len(pending_files):
                countdown(SECONDS_BETWEEN_POSTS, "Short interval before the next upload (not a bypass or rate-limit workaround).")

        next_index = batch_index + 1
        wait_after = int(batch["wait_after"])
        state["next_batch_index"] = next_index
        if wait_after and next_index < len(BATCH_PLAN):
            next_at = datetime.now().astimezone() + timedelta(seconds=wait_after)
            state["next_batch_at"] = next_at.isoformat(timespec="seconds")
        else:
            state["next_batch_at"] = None
        save_state(state)

        print(f"\n[ BATCH COMPLETE ] {batch['label']}")
        if wait_after and next_index < len(BATCH_PLAN):
            target_time = datetime.fromisoformat(str(state["next_batch_at"]))
            remaining = max(0, int((target_time - datetime.now().astimezone()).total_seconds()))
            countdown(remaining, f"Waiting for the next batch. Scheduled local time: {target_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            state["next_batch_at"] = None
            save_state(state)

    print("\nALL SCHEDULED BATCHES FINISHED.")
    print("The schedule used 38 rejected videos and 99 output videos.")
    print("The output folder's remaining videos were intentionally left untouched.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Attended Instagram desktop Reel upload schedule.")
    parser.add_argument("--plan-only", action="store_true", help="Ask for caption, verify inventory, and show the exact schedule without opening Chrome.")
    parser.add_argument("--test-one", action="store_true", help="Publish one rejected Reel as a controlled workflow test.")
    parser.add_argument("--test-output", action="store_true", help="Publish one processed output Reel without uploading an external cover.")
    args = parser.parse_args()

    print("\nIMPORTANT: This is experimental browser UI automation, not an official Instagram publishing integration.")
    print("Instagram's Terms restrict automated access without express permission. Account restrictions are possible.")
    print("The script will not bypass CAPTCHA, login challenges, checkpoints, or activity warnings.")
    caption = ask_caption()  # user's requested first interaction

    rejected, output = preflight()
    if args.plan_only:
        print("\nPLAN ONLY: no Chrome window opened and no content published.")
        return 0

    state = load_state()
    if not (args.test_one or args.test_output):
        state = choose_campaign_state(state)
    # The risk notice is displayed above. A single action-specific confirmation
    # (POST ONE for test mode or PUBLISH for the full schedule) authorizes posting.

    if not (args.test_one or args.test_output):
        print("\nThis run will publish up to 137 Reels in 7 batches over the supplied schedule.")
        print("The repeated caption will be used for every Reel in this run.")
        if input("Type PUBLISH to authorize the full schedule: ").strip() != "PUBLISH":
            print("Cancelled. No browser was opened.")
            return 0

    playwright = None
    context = None
    try:
        playwright, context = launch_chrome()
        login_page = prepare_login(context)
        if args.test_one and args.test_output:
            raise UploadError("Choose only one test mode: --test-one or --test-output.")
        if args.test_one or args.test_output:
            resolve_pending(state)
            if args.test_output:
                run_test_output(context, login_page, output, caption, state)
            else:
                run_test_one(context, login_page, rejected, caption, state)
        else:
            run_full_schedule(context, login_page, rejected, output, caption, state)
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted by user. Confirm any in-progress post in Instagram before resuming.")
        return 130
    except Exception as exc:
        print(f"\nUPLOAD STOPPED: {exc}", file=sys.stderr)
        if context is not None:
            try:
                input("Chrome will remain open for manual inspection. Press Enter when you are ready to close it: ")
            except EOFError:
                pass
        return 1
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
