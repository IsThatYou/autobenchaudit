"""Minimal progress tracking for long-running audit loops."""

from __future__ import annotations

import sys
import threading
import time


class ProgressTracker:
    """Thread-safe progress bar and per-item status printed to stderr."""

    def __init__(
        self,
        total: int,
        label: str = "Processing",
        info: dict[str, str] | None = None,
    ) -> None:
        self.total = total
        self.label = label
        self._completed = 0
        self._errors = 0
        self._start = time.monotonic()
        self._bar_width = 30
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self._print_header(info)

    def _print_header(self, info: dict[str, str] | None) -> None:
        sys.stderr.write(f"\n{'─' * 60}\n")
        sys.stderr.write(f"  {self.label}\n")
        if info:
            max_key = max(len(k) for k in info)
            for key, value in info.items():
                sys.stderr.write(f"  {key:<{max_key}}  {value}\n")
        sys.stderr.write(f"  {'tasks':<10}  {self.total}\n")
        sys.stderr.write(f"{'─' * 60}\n")
        sys.stderr.flush()

    def _format_elapsed(self) -> str:
        elapsed = time.monotonic() - self._start
        minutes, seconds = divmod(int(elapsed), 60)
        if minutes:
            return f"{minutes}m{seconds:02d}s"
        return f"{seconds}s"

    def _render_bar(self) -> str:
        if self.total == 0:
            return ""
        filled = int(self._bar_width * self._completed / self.total)
        bar = "█" * filled + "░" * (self._bar_width - filled)
        pct = 100 * self._completed / self.total
        return f"[{bar}] {pct:5.1f}%"

    def _active_summary(self) -> str:
        if not self._active:
            return ""
        items = sorted(self._active)
        if len(items) <= 3:
            return ", ".join(items)
        return ", ".join(items[:3]) + f" +{len(items) - 3}"

    def _write_status_line(self) -> None:
        bar = self._render_bar()
        active = self._active_summary()
        status = f"  {bar}  ({self._completed}/{self.total})  [{self._format_elapsed()}]"
        if active:
            status += f"  ▸ {active}"
        # Clear line and write status
        sys.stderr.write(f"\r\033[K{status}")
        sys.stderr.flush()

    def skip(self, item_id: str) -> None:
        with self._lock:
            self._completed += 1
            # Print skip on its own line, then redraw status
            sys.stderr.write(f"\r\033[K  {item_id} — skipped (cached)\n")
            self._write_status_line()

    def start(self, item_id: str) -> None:
        with self._lock:
            self._active.add(item_id)
            self._write_status_line()

    def done(self, item_id: str, *, error: bool = False) -> None:
        with self._lock:
            self._active.discard(item_id)
            self._completed += 1
            if error:
                self._errors += 1
            status = "error" if error else "done"
            # Print completion on its own line, then redraw status
            sys.stderr.write(f"\r\033[K  {item_id} — {status}  [{self._format_elapsed()}]\n")
            self._write_status_line()

    def finish(self) -> None:
        with self._lock:
            elapsed = self._format_elapsed()
            err_suffix = f" ({self._errors} errors)" if self._errors else ""
            sys.stderr.write(f"\r\033[K  ✓ Completed {self._completed}/{self.total} in {elapsed}{err_suffix}\n\n")
            sys.stderr.flush()
