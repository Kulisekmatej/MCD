"""Update check against GitHub Releases.

On startup the application asks GitHub for the latest release of this
repository and compares its tag with the running version. Only the pure
logic lives here (no tkinter), so it can be unit-tested headless; the GUI
wires the result to a Czech dialog.

Release tags may carry prefixes (``v1.2.0``, ``Beta_v1.1.1``); only the
numeric part is compared.
"""

from __future__ import annotations

import json
import queue
import re
import threading
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from . import __version__

GITHUB_LATEST_RELEASE_URL = (
    "https://api.github.com/repos/Kulisekmatej/MCD/releases/latest"
)
RELEASES_PAGE_URL = "https://github.com/Kulisekmatej/MCD/releases/latest"
REQUEST_TIMEOUT_S = 6


@dataclass(frozen=True)
class UpdateInfo:
    """A newer release found on GitHub."""

    version: str  # normalized version of the latest release, e.g. "1.2.0"
    tag: str      # raw tag name, e.g. "Beta_v1.2.0"
    url: str      # release page where the build can be downloaded


def parse_version(text: str) -> Optional[Tuple[int, ...]]:
    """Extract a numeric version tuple from a tag or version string.

    Returns None when the string contains no number at all.
    """
    match = re.search(r"(\d+(?:\.\d+)*)", text)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(candidate: str, current: str) -> bool:
    """True when *candidate* denotes a strictly newer version than *current*.

    Unparsable versions are never reported as newer, so a malformed tag on
    GitHub cannot spam users with false update prompts.
    """
    cand = parse_version(candidate)
    curr = parse_version(current)
    if cand is None or curr is None:
        return False
    size = max(len(cand), len(curr))
    return cand + (0,) * (size - len(cand)) > curr + (0,) * (size - len(curr))


def fetch_latest_release(url: str = GITHUB_LATEST_RELEASE_URL) -> dict:
    """Return the GitHub API payload for the repository's latest release."""
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"PocitadloHodin/{__version__}",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
        return json.load(response)


def check_for_update(current_version: str = __version__) -> Optional[UpdateInfo]:
    """Return info about a newer release, or None.

    The check must never break application startup, so every failure
    (offline, API limit, no release published yet) silently returns None.
    """
    try:
        payload = fetch_latest_release()
        tag = payload.get("tag_name") or ""
        if is_newer(tag, current_version):
            numbers = parse_version(tag)
            assert numbers is not None  # guaranteed by is_newer above
            return UpdateInfo(
                version=".".join(str(n) for n in numbers),
                tag=tag,
                url=payload.get("html_url") or RELEASES_PAGE_URL,
            )
    except Exception:
        pass
    return None


def start_update_check(
    root,
    on_update_available: Callable[[UpdateInfo], None],
    poll_ms: int = 500,
) -> None:
    """Check for updates in the background and report on the Tk main loop.

    ``root`` only needs an ``after`` method. The network call runs in a
    daemon thread; the result is handed over via a queue polled with
    ``after``, so *on_update_available* always runs on the GUI thread and
    may open dialogs. Nothing happens when the app is up to date or the
    check fails.
    """
    result: "queue.Queue[Optional[UpdateInfo]]" = queue.Queue(maxsize=1)

    def worker() -> None:
        result.put(check_for_update())

    def poll() -> None:
        try:
            info = result.get_nowait()
        except queue.Empty:
            root.after(poll_ms, poll)
            return
        if info is not None:
            on_update_available(info)

    threading.Thread(target=worker, daemon=True).start()
    root.after(poll_ms, poll)
