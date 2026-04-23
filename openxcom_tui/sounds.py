"""Sound effects — stub.

Following SKILL.md Phase D, we ship a no-op implementation by default.
If the vendor OXC tree is present and ``SOUND/`` contains the original
.WAV files, we can wire them up later. For MVP the game is silent.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional


class SoundBoard:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self._player: Optional[str] = None
        self._last_played: dict[str, float] = {}
        self._debounce_sec = 0.15
        if enabled:
            for cand in ("paplay", "aplay", "afplay"):
                if shutil.which(cand):
                    self._player = cand
                    return
            # No player found — silently disable.
            self.enabled = False

    def play(self, name: str, asset: Optional[Path] = None) -> None:
        if not self.enabled or self._player is None:
            return
        now = time.monotonic()
        if now - self._last_played.get(name, 0) < self._debounce_sec:
            return
        self._last_played[name] = now
        if asset is None or not asset.exists():
            return
        try:
            subprocess.Popen(
                [self._player, str(asset)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass
