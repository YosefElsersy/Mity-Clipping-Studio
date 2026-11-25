#!/usr/bin/env python3
"""Instagram DM shared-Reel monitor with automatic card opening.

Uses a dedicated, persistent Google Chrome profile and Playwright. The user
signs in manually. It observes newly inserted DM cards that contain Instagram's
visible `clip` icon and applies a left-side/incoming layout heuristic. To keep
the monitored DM tab untouched, it opens a temporary second tab on the same
thread, clicks the corresponding card there, captures the permalink, downloads
it with yt-dlp, and closes only the temporary tab.

Limitations:
- Instagram's web UI is undocumented and may change at any time.
- The incoming-message check is a geometry heuristic, not verified sender ID.
- It only monitors the one DM surface left open in the dedicated Chrome tab.
- It does not bypass CAPTCHA, login challenges, private-content restrictions,
  or other security controls.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

HOME = Path.home()
PROJECT_DIR = HOME / "Mity-Clipping-Studio" / "instagram-dm"
CHROME_PROFILE_DIR = HOME / ".local" / "share" / "instagram-dm" / "chrome-profile"
REELS_DIR = HOME / "Mity-Clipping-Studio" / "video-processing" / "input" / "reels"
LINKS_FILE = PROJECT_DIR / "reel_links.txt"
STATE_FILE = PROJECT_DIR / "monitor_state.json"
LOG_FILE = PROJECT_DIR / "monitor.log"
ARCHIVE_FILE = PROJECT_DIR / "yt_dlp_archive.txt"
INBOX_URL = "https://www.instagram.com/direct/inbox/"
POLL_SECONDS = 0.5
BUILD_VERSION = "8.5.1-temporary-tab-fix-structural-dedupe"

CONTENT_PATH_RE = re.compile(r"^/(p|reel|reels)/([A-Za-z0-9_-]+)/?$")
DM_PATH_RE = re.compile(r"^/direct/(?:inbox|t/[^/]+)$")


def stamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    line = f"[{stamp()}] {message}"
    print(line, flush=True)
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def debug(message: str) -> None:
    line = f"[{stamp()}] {message}"
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    with (PROJECT_DIR / "dm_network_debug.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"seen_urls": [], "successful_downloads": []}
    try:
        obj = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("state must be a JSON object")
        obj.setdefault("seen_urls", [])
        obj.setdefault("successful_downloads", [])
        return obj
    except Exception as exc:
        log(f"Could not read state file ({type(exc).__name__}); starting fresh.")
        return {"seen_urls": [], "successful_downloads": []}


def save_state(state: dict) -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def canonical_content_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in {"instagram.com", "www.instagram.com", "m.instagram.com"}:
        return None
    match = CONTENT_PATH_RE.fullmatch(parsed.path or "")
    if not match:
        return None
    kind, code = match.groups()
    if kind == "reels":
        kind = "reel"
    return f"https://www.instagram.com/{kind}/{code}/"


def is_dm_url(url: str) -> bool:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    path = re.sub(r"/+", "/", p.path or "/").rstrip("/") or "/"
    return host in {"instagram.com", "www.instagram.com", "m.instagram.com"} and bool(DM_PATH_RE.fullmatch(path))

def is_dm_thread_url(url: str) -> bool:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    path = re.sub(r"/+", "/", p.path or "/").rstrip("/") or "/"
    return host in {"instagram.com", "www.instagram.com", "m.instagram.com"} and re.fullmatch(r"/direct/t/[^/]+", path) is not None


def append_link(url: str) -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    old = set()
    if LINKS_FILE.exists():
        old = {x.strip() for x in LINKS_FILE.read_text(encoding="utf-8").splitlines() if x.strip()}
    if url not in old:
        with LINKS_FILE.open("a", encoding="utf-8") as f:
            f.write(url + "\n")


def find_ytdlp() -> list[str] | None:
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    local = HOME / ".local" / "bin" / "yt-dlp"
    return [str(local)] if local.is_file() else None


def download_content(url: str, ytdlp: list[str]) -> bool:
    REELS_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        *ytdlp,
        "--no-playlist",
        "--no-overwrites",
        "--download-archive", str(ARCHIVE_FILE),
        "--cookies-from-browser", f"chrome:{CHROME_PROFILE_DIR}",
        "-P", str(REELS_DIR),
        "-o", "%(id)s.%(ext)s",
        url,
    ]
    log(f"Starting yt-dlp download: {url}")
    try:
        result = subprocess.run(cmd, check=False)
    except OSError as exc:
        log(f"Could not start yt-dlp: {exc}")
        return False
    if result.returncode == 0:
        log(f"Download completed or already present: {url}")
        return True
    log(f"yt-dlp returned exit code {result.returncode}; URL remains in reel_links.txt")
    return False


# This observer deliberately records only card geometry and semantic markers.
# It never reads message text, account names, cookies, or message payloads.
INSTALL_CARD_OBSERVER = r"""() => {
  if (window.__igAutoReelV85 && window.__igAutoReelV85.installed) {
    return {installed:true, alreadyInstalled:true, path:location.pathname,
            href:location.href, viewport:{w:innerWidth,h:innerHeight}};
  }
  const state = {installed:true, seq:0, queue:[], seen:new WeakSet()};
  window.__igAutoReelV85 = state;

  const ICONS = 'svg[aria-label="clip" i], [role="img"][aria-label="clip" i]';
  function hasClip(el) {
    if (!(el instanceof Element)) return false;
    return el.matches(ICONS) || !!el.querySelector(ICONS);
  }
  function pickCard(icon) {
    let node = icon;
    for (let i=0; node && i<12; i++, node=node.parentElement) {
      if (!(node instanceof HTMLElement) || !hasClip(node)) continue;
      const r = node.getBoundingClientRect();
      if ((node.getAttribute('role') || '').toLowerCase() === 'button' && r.width >= 140 && r.height >= 160) return node;
    }
    node = icon;
    for (let i=0; node && i<12; i++, node=node.parentElement) {
      if (!(node instanceof HTMLElement) || !hasClip(node)) continue;
      const r = node.getBoundingClientRect();
      if ((node.getAttribute('role') || '').toLowerCase() === 'article' && r.width >= 140 && r.height >= 160) return node;
    }
    return null;
  }
  function listCards() {
    const unique = new Set();
    for (const icon of document.querySelectorAll(ICONS)) {
      const card = pickCard(icon);
      if (card) unique.add(card);
    }
    return [...unique]; // querySelectorAll order is document order
  }
  // A hash of structural attributes only: no message text, names, or URLs.
  function structuralSignature(card) {
    const bits = [];
    let el = card;
    for (let i=0; el && i<5; i++, el=el.parentElement) {
      const cls = typeof el.className === 'string' ? el.className.split(/\s+/).slice(0,4).join('.') : '';
      bits.push([el.tagName, el.getAttribute('role') || '', el.getAttribute('data-testid') || '', cls].join(':'));
    }
    const str = bits.join('>');
    let h = 2166136261;
    for (let i=0; i<str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    return (h >>> 0).toString(16);
  }
  function consider(icon) {
    const card = pickCard(icon);
    if (!card || state.seen.has(card) || card.dataset.igAutoReelQueued === '1') return;
    const r = card.getBoundingClientRect();
    if (r.width < 140 || r.height < 160 || r.bottom <= 0 || r.top >= innerHeight) return;
    const visibleHeight = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
    if (visibleHeight / r.height < 0.80) return;

    state.seen.add(card);
    card.dataset.igAutoReelQueued = '1';
    const centerX = r.left + r.width/2;
    const incoming = centerX < innerWidth * 0.60;
    if (!incoming) return;

    const allCards = listCards();
    const index = allCards.indexOf(card);
    const ordinalFromEnd = index >= 0 ? allCards.length - 1 - index : 0;
    const signature = structuralSignature(card);
    // Do not deduplicate using a structural signature: different newly received
    // Reels can have identical DOM geometry and the same ordinal position.
    // The WeakSet prevents repeated processing of the same DOM node. Actual
    // Reel URLs are deduplicated later, after the permalink is captured.
    const id = String(++state.seq);
    card.dataset.igAutoReelCard = id;
    state.queue.push({id, signature, ordinalFromEnd, candidateCount:allCards.length,
      x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height),
      centerX:Math.round(centerX), viewportW:innerWidth, side:'left/incoming-heuristic'});
    if (state.queue.length > 30) state.queue.shift();
  }
  function inspectAdded(root) {
    if (!(root instanceof Element)) return;
    if (root.matches(ICONS)) consider(root);
    for (const icon of root.querySelectorAll(ICONS)) consider(icon);
  }
  const observer = new MutationObserver(records => {
    for (const rec of records) {
      if (rec.type === 'childList') {
        for (const node of rec.addedNodes) inspectAdded(node);
      } else if (rec.type === 'attributes' && rec.target instanceof Element && rec.target.matches(ICONS)) {
        consider(rec.target);
      }
    }
  });
  observer.observe(document.body, {childList:true, subtree:true, attributes:true, attributeFilter:['aria-label']});
  state.observer = observer;
  state.drain = () => state.queue.splice(0, state.queue.length);
  return {installed:true, path:location.pathname, viewport:{w:innerWidth,h:innerHeight}};
}"""

# The following selector runs only in the temporary tab. It selects the same
# clip card by its DOM-order offset from the end and validates its structural
# signature before clicking it.
SELECT_TEMP_CARD_JS = r"""event => {
  const ICONS = 'svg[aria-label="clip" i], [role="img"][aria-label="clip" i]';
  function hasClip(el) { return el instanceof Element && (el.matches(ICONS) || !!el.querySelector(ICONS)); }
  function pickCard(icon) {
    let node = icon;
    for (let i=0; node && i<12; i++, node=node.parentElement) {
      if (!(node instanceof HTMLElement) || !hasClip(node)) continue;
      const r = node.getBoundingClientRect();
      if ((node.getAttribute('role') || '').toLowerCase() === 'button' && r.width >= 140 && r.height >= 160) return node;
    }
    node = icon;
    for (let i=0; node && i<12; i++, node=node.parentElement) {
      if (!(node instanceof HTMLElement) || !hasClip(node)) continue;
      const r = node.getBoundingClientRect();
      if ((node.getAttribute('role') || '').toLowerCase() === 'article' && r.width >= 140 && r.height >= 160) return node;
    }
    return null;
  }
  function signature(card) {
    const bits = []; let el = card;
    for (let i=0; el && i<5; i++, el=el.parentElement) {
      const cls = typeof el.className === 'string' ? el.className.split(/\s+/).slice(0,4).join('.') : '';
      bits.push([el.tagName, el.getAttribute('role') || '', el.getAttribute('data-testid') || '', cls].join(':'));
    }
    const str = bits.join('>'); let h = 2166136261;
    for (let i=0; i<str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    return (h >>> 0).toString(16);
  }
  const unique = new Set();
  for (const icon of document.querySelectorAll(ICONS)) { const c = pickCard(icon); if (c) unique.add(c); }
  const cards = [...unique];
  const ordinal = Math.max(0, Number(event.ordinalFromEnd) || 0);
  if (cards.length <= ordinal) return {found:false, count:cards.length, reason:'not-enough-cards'};
  let card = cards[cards.length - 1 - ordinal];
  const expectedSig = String(event.signature || '');
  if (expectedSig && signature(card) !== expectedSig) {
    const matches = cards.filter(c => signature(c) === expectedSig);
    if (matches.length === 1) card = matches[0];
    else return {found:false, count:cards.length, reason:'signature-mismatch', matches:matches.length};
  }
  const r = card.getBoundingClientRect();
  const centerX = r.left + r.width/2;
  if (r.width < 140 || r.height < 160 || centerX >= innerWidth*0.60) {
    return {found:false, count:cards.length, reason:'geometry-or-side-mismatch'};
  }
  card.scrollIntoView({block:'center', inline:'nearest'});
  card.setAttribute('data-ig-temp-target', '1');
  return {found:true, count:cards.length, index:cards.indexOf(card), x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)};
}"""


def install_observer(page) -> None:
    result = page.evaluate(INSTALL_CARD_OBSERVER)
    if not isinstance(result, dict):
        result = {"installed": False, "path": None, "viewport": None}
    debug(
        "Card observer status="
        f"{result.get('installed')} already_installed={result.get('alreadyInstalled', False)} "
        f"path={result.get('path')} viewport={result.get('viewport')}"
    )


def drain_cards(page) -> list[dict]:
    return page.evaluate("() => window.__igAutoReelV85 && window.__igAutoReelV85.drain ? window.__igAutoReelV85.drain() : []") or []


def click_and_capture_in_temporary_tab(context, dm_url: str, event: dict,
                                       main_page, timeout_seconds: float = 18.0) -> str | None:
    """Open the selected message in a disposable tab; never navigate the DM tab."""
    temp_page = None
    try:
        temp_page = context.new_page()
        try:
            temp_page.goto(dm_url, wait_until="domcontentloaded", timeout=25000)
        except PlaywrightTimeoutError:
            log("Temporary tab navigation timed out; checking whether the DM thread loaded anyway.")

        expected_path = urlparse(dm_url).path.rstrip("/")
        load_deadline = time.time() + 12
        selected = None
        last_result = None
        while time.time() < load_deadline:
            live = _live_url(temp_page)
            if is_dm_thread_url(live) and urlparse(live).path.rstrip("/") == expected_path:
                try:
                    last_result = temp_page.evaluate(SELECT_TEMP_CARD_JS, event)
                except PlaywrightError:
                    last_result = None
                if isinstance(last_result, dict) and last_result.get("found"):
                    selected = last_result
                    break
            time.sleep(0.35)

        if not selected:
            reason = last_result.get("reason") if isinstance(last_result, dict) else "thread-or-card-not-loaded"
            count = last_result.get("count") if isinstance(last_result, dict) else "unknown"
            log(f"Temporary tab could not safely identify the matching Reel card (reason={reason}, cards={count}); original DM tab was not touched.")
            return None

        locator = temp_page.locator('[data-ig-temp-target="1"]').first
        if locator.count() == 0:
            log("Temporary Reel target disappeared before click; original DM tab was not touched.")
            return None

        log(f"Opening Reel in temporary tab only (matching card index={selected.get('index')}, cards={selected.get('count')}).")
        before = _live_url(temp_page)
        try:
            locator.click(timeout=8000)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            log(f"Could not click Reel in temporary tab ({type(exc).__name__}); original DM tab was not touched.")
            return None

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                current = _live_url(temp_page)
                permalink = canonical_content_url(current)
                if permalink and permalink != canonical_content_url(before):
                    return permalink
                hrefs = temp_page.locator('a[href*="/p/"], a[href*="/reel/"], a[href*="/reels/"]').evaluate_all(
                    "els => els.map(a => a.href).filter(Boolean)"
                )
                for href in hrefs:
                    permalink = canonical_content_url(href)
                    if permalink and permalink != canonical_content_url(before):
                        return permalink
            except PlaywrightError:
                pass
            time.sleep(0.25)

        log("Temporary tab opened the card but no /p/ or /reel/ permalink became visible; original DM tab remains open.")
        return None
    except PlaywrightError as exc:
        log(f"Temporary-tab processing failed safely ({type(exc).__name__}); original DM tab was not touched.")
        return None
    finally:
        if temp_page is not None:
            try:
                if not temp_page.is_closed():
                    temp_page.close()
            except PlaywrightError:
                pass
        try:
            if not main_page.is_closed():
                main_page.bring_to_front()
        except PlaywrightError:
            pass


def _live_url(page) -> str:
    try:
        return str(page.evaluate("() => window.location.href") or page.url)
    except PlaywrightError:
        return str(page.url)


def find_thread_url_by_label(page, label: str) -> str | None:
    """Resolve one exact visible inbox row to its /direct/t/<thread-id> URL."""
    try:
        matches = page.evaluate(r"""needle => {
          const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLocaleLowerCase();
          const wanted = norm(needle);
          if (!wanted) return [];
          const found = new Set();
          for (const a of document.querySelectorAll('a[href]')) {
            let u;
            try { u = new URL(a.href, location.href); } catch { continue; }
            if (!/^\/direct\/t\/[^/]+\/?$/.test(u.pathname)) continue;
            const raw = a.innerText || a.getAttribute('aria-label') || a.getAttribute('title') || '';
            const lines = raw.split(/\n+/).map(norm).filter(Boolean);
            if (lines.includes(wanted)) found.add(u.href);
          }
          return [...found];
        }""", label)
    except PlaywrightError:
        return None
    if isinstance(matches, list) and len(matches) == 1 and is_dm_thread_url(str(matches[0])):
        return str(matches[0])
    return None


def return_to_chat(page, expected_dm_url: str) -> bool:
    """Restore the exact selected thread; never count the inbox shell as success."""
    if not is_dm_thread_url(expected_dm_url):
        log("Cannot safely restore the selected conversation: no exact thread URL was captured.")
        return False

    expected_path = urlparse(expected_dm_url).path.rstrip("/")
    current = _live_url(page)
    if is_dm_thread_url(current) and urlparse(current).path.rstrip("/") == expected_path:
        return True

    log("Returning to the exact monitored DM thread.")
    try:
        page.go_back(wait_until="domcontentloaded", timeout=12000)
    except (PlaywrightError, PlaywrightTimeoutError):
        try:
            page.keyboard.press("Escape")
        except PlaywrightError:
            pass

    deadline = time.time() + 4
    while time.time() < deadline:
        current = _live_url(page)
        if is_dm_thread_url(current) and urlparse(current).path.rstrip("/") == expected_path:
            log("Returned to the exact monitored DM thread.")
            return True
        time.sleep(0.25)

    # Browser history may land on /direct/inbox/. That is only the inbox shell,
    # so explicitly navigate to the saved thread route instead of declaring success.
    try:
        page.goto(expected_dm_url, wait_until="domcontentloaded", timeout=15000)
        deadline = time.time() + 8
        while time.time() < deadline:
            current = _live_url(page)
            if is_dm_thread_url(current) and urlparse(current).path.rstrip("/") == expected_path:
                log("Restored the exact monitored DM thread URL.")
                return True
            time.sleep(0.25)
    except (PlaywrightError, PlaywrightTimeoutError):
        pass

    log(f"CRITICAL: exact DM thread was not restored. Current URL: {_live_url(page)}")
    return False


def main() -> int:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    REELS_DIR.mkdir(parents=True, exist_ok=True)
    CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(CHROME_PROFILE_DIR, 0o700)
    except OSError:
        pass

    ytdlp = find_ytdlp()
    if not ytdlp:
        print("yt-dlp is missing. Install it in this virtualenv: python -m pip install yt-dlp")
        return 2

    print("\nInstagram DM Reel Monitor")
    print("-------------------------")
    print(f"Build {BUILD_VERSION}: lets you select the tab with the visible DM conversation (including Instagram's /direct/inbox/ shell), then watches newly inserted clip cards and opens incoming-looking cards automatically.")
    print("Chrome uses a dedicated profile. Sign in manually; never share passwords, cookies, or the profile.")
    print("Keep the intended DM conversation open. Sender-side detection is based on chat layout, not verified sender identity.")
    print("The monitor does not bypass CAPTCHA, login challenges, or other security checks.\n")
    label = input("Exact conversation name as shown in the DM inbox list (used to restore this chat): ").strip()

    state = load_state()
    # Older builds persisted structural card keys. Those keys are not unique Reel
    # identities and could suppress newly received cards with the same layout.
    if state.pop("handled_card_keys", None) is not None:
        save_state(state)
        log("Removed obsolete structural card-deduplication keys; URL download history was preserved.")
    seen_urls = set(str(x) for x in state.get("seen_urls", []))
    successful = set(str(x) for x in state.get("successful_downloads", []))
    def handle_url(url: str, source: str) -> None:
        if url in successful:
            log(f"Already downloaded successfully; skipping duplicate: {url}")
            return
        if url in seen_urls:
            log(f"Previously seen but not recorded as successfully downloaded; retrying: {url}")
        else:
            seen_urls.add(url)
            append_link(url)
            state["seen_urls"] = sorted(seen_urls)
            save_state(state)
            log(f"New Reel/post URL detected via {source}: {url}")
        if download_content(url, ytdlp):
            successful.add(url)
            state["successful_downloads"] = sorted(successful)
            save_state(state)

    try:
        with sync_playwright() as p:
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(CHROME_PROFILE_DIR),
                    channel="chrome",
                    headless=False,
                    no_viewport=True,
                    accept_downloads=False,
                    chromium_sandbox=True,
                    args=["--start-maximized"],
                )
            except PlaywrightError as exc:
                print("\nCould not safely start Chrome with its sandbox enabled.")
                print("Close other Chrome processes using this dedicated profile and retry.")
                print(f"Details: {exc}")
                return 3

            pages = [pg for pg in context.pages if not pg.is_closed()]
            page = next((pg for pg in pages if "instagram.com" in pg.url), None)
            if page is None:
                page = pages[0] if pages else context.new_page()
            try:
                if "instagram.com" not in page.url:
                    page.goto(INBOX_URL, wait_until="domcontentloaded", timeout=90000)
            except PlaywrightTimeoutError:
                log("Instagram did not finish loading; continue if the inbox is usable.")

            print("\nIn the dedicated Chrome window opened by this script:")
            print("  1) Sign in manually if needed.")
            print("  2) Open the intended person's conversation in the main pane.")
            print("  3) Leave it visible. Do NOT use Brave or another Chrome window.")
            print("\nIf Instagram keeps /direct/inbox/, enter the exact chat name so the script can save that thread's /direct/t/ link before monitoring.")
            print("Instagram tabs currently open:")
            live_pages = [pg for pg in context.pages if not pg.is_closed() and "instagram.com" in pg.url]
            if not live_pages:
                print("  No Instagram tab is open. Log in and open Instagram in the dedicated Chrome window first.")
                return 4
            for idx, pg in enumerate(live_pages, 1):
                print(f"  Tab {idx}: {pg.url}")
            while True:
                raw_choice = input(f"Choose the tab showing the target conversation [1-{len(live_pages)}]: ").strip() or "1"
                if raw_choice.isdigit() and 1 <= int(raw_choice) <= len(live_pages):
                    page = live_pages[int(raw_choice) - 1]
                    break
                print("Invalid tab number. Try again.")
            confirmation = input("Is the target person's conversation visibly open in the main pane (not just the inbox list)? Type YES: ").strip()
            if confirmation != "YES":
                print("Not confirmed. Open the target conversation in the dedicated Chrome window and run the monitor again.")
                return 4
            if not is_dm_url(page.url):
                print(f"Selected tab is not an Instagram Direct page: {page.url}")
                return 4

            # Capture the live browser URL after the user confirms the visible
            # conversation. In Instagram's SPA, Playwright's cached page.url can
            # briefly remain /direct/inbox/ while location.pathname is /direct/t/<id>/.
            try:
                live_href = str(page.evaluate("() => window.location.href") or page.url)
            except PlaywrightError:
                live_href = page.url
            # This is a user-confirmed scope, not a verified sender identity.
            # Record only structural counts, never message text or message payloads.
            try:
                stats = page.evaluate("""() => ({path:location.pathname, href:location.href, messageGroups:document.querySelectorAll('[aria-label=\"message\"], [role=\"article\"]').length, clipIcons:document.querySelectorAll('svg[aria-label=\"clip\" i], [role=\"img\"][aria-label=\"clip\" i]').length, anchors:document.querySelectorAll('a').length})""") or {}
            except PlaywrightError:
                stats = {}
            selected_dm_url = live_href
            if isinstance(stats, dict):
                live_path = str(stats.get("path") or "")
                if re.fullmatch(r"/direct/t/[^/]+/?", live_path):
                    parsed_live = urlparse(live_href)
                    selected_dm_url = f"{parsed_live.scheme or 'https'}://{parsed_live.netloc or 'www.instagram.com'}{live_path}"
            if not is_dm_thread_url(selected_dm_url):
                if not label:
                    print("A conversation name is required because Instagram is showing only /direct/inbox/.")
                    return 4
                restored_candidate = find_thread_url_by_label(page, label)
                if not restored_candidate:
                    print("Could not identify exactly one matching /direct/t/ link for that conversation name.")
                    print("For safety, automatic Reel opening is disabled so the private chat is not lost.")
                    print("Use the exact name shown on the inbox row, then run the monitor again.")
                    return 4
                selected_dm_url = restored_candidate
                print("Captured the exact conversation thread route from its inbox row.")
            print(f"Selected conversation scope: {selected_dm_url}")
            print(f"Initial structural DOM counts (no message text captured): {stats}")
            print("Only newly inserted clip cards will be processed; existing chat history is ignored.")
            print("Reels open in a temporary tab; the selected DM tab is kept on the conversation.")
            install_observer(page)

            log(f"Monitoring started for '{label}'. New incoming-looking Reel cards will be opened automatically.")
            log(f"Download folder: {REELS_DIR}")
            log("Detection is limited to newly inserted, visible clip cards on the one open DM page.")
            print("\nMonitoring is running. New incoming-looking Reel cards will download via a temporary tab.")
            print("Keep the target DM open. Press Ctrl+C to stop.\n")

            while True:
                time.sleep(POLL_SECONDS)
                if page.is_closed():
                    log("Monitored Chrome tab was closed; stopping.")
                    break
                live_current_url = _live_url(page)
                if not is_dm_url(live_current_url):
                    # During an intentional opened-card navigation, the code below
                    # is synchronous and handles the return before reaching here.
                    log(f"Not on the monitored DM route; waiting without interaction ({live_current_url}).")
                    continue
                try:
                    cards = drain_cards(page)
                except PlaywrightError as exc:
                    debug(f"Could not drain DOM observer ({type(exc).__name__})")
                    continue
                for event in cards:
                    if not isinstance(event, dict):
                        debug(f"Ignored malformed observer event type={type(event).__name__}")
                        continue
                    try:
                        permalink = click_and_capture_in_temporary_tab(context, selected_dm_url, event, page)
                        if permalink:
                            log(f"Automatically captured shared Reel/post permalink: {permalink}")
                            handle_url(permalink, "temporary-tab shared clip card")
                        else:
                            log("No permalink captured from temporary tab; monitored DM tab remains on the conversation.")
                    except Exception as exc:
                        log(f"Card processing skipped ({type(exc).__name__}: {exc}); monitored DM tab was not navigated.")

    except KeyboardInterrupt:
        log("Stopped by user (Ctrl+C).")
        return 0
    except Exception as exc:
        log(f"Unexpected error: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
