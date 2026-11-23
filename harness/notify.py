"""Sound and desktop notification when the run needs the human (spec 5.7, step 1).

macOS only, no dependencies: `afplay` on a system sound and `osascript`.
HARNESS_NO_NOTIFY=1 disables both (tests, headless machines).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess

SOUND = "/System/Library/Sounds/Glass.aiff"


def notify(title: str, message: str) -> None:
    print(f"\a🔔 {title}: {message}")
    if os.environ.get("HARNESS_NO_NOTIFY"):
        return
    if platform.system() != "Darwin":
        return
    if shutil.which("afplay") and os.path.exists(SOUND):
        subprocess.Popen(["afplay", SOUND], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if shutil.which("osascript"):
        safe_title = title.replace('"', "'")
        safe_msg = message.replace('"', "'")
        script = f'display notification "{safe_msg}" with title "{safe_title}"'
        subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
