"""Platform-specific system integrations."""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from typing import Optional


class SleepInhibitor:
    """Prevent the system from sleeping while active."""

    def __init__(self) -> None:
        self._caffeinate_proc: Optional[subprocess.Popen] = None
        self._active = False

    def __enter__(self) -> "SleepInhibitor":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def start(self) -> None:
        if self._active:
            return
        if sys.platform == "darwin":
            self._start_macos()
        elif sys.platform.startswith("win"):
            self._start_windows()
        self._active = True

    def stop(self) -> None:
        if not self._active:
            return
        if sys.platform == "darwin":
            self._stop_macos()
        elif sys.platform.startswith("win"):
            self._stop_windows()
        self._active = False

    def _start_macos(self) -> None:
        try:
            self._caffeinate_proc = subprocess.Popen(
                ["caffeinate", "-dimsu", "-w", str(os.getpid())],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            self._caffeinate_proc = None

    def _stop_macos(self) -> None:
        if self._caffeinate_proc is None:
            return
        with contextlib.suppress(Exception):
            self._caffeinate_proc.terminate()
        self._caffeinate_proc = None

    def _start_windows(self) -> None:
        try:
            import ctypes

            flags = 0x80000000 | 0x00000001 | 0x00000002
            windll = getattr(ctypes, "windll", None)
            if windll is None:
                return
            windll.kernel32.SetThreadExecutionState(flags)
        except Exception:
            pass

    def _stop_windows(self) -> None:
        try:
            import ctypes

            windll = getattr(ctypes, "windll", None)
            if windll is None:
                return
            windll.kernel32.SetThreadExecutionState(0x80000000)
        except Exception:
            pass


def send_notification(title: str, message: str) -> None:
    """Send a best-effort desktop notification."""
    if sys.platform == "darwin":
        _send_macos_notification(title, message)
    elif sys.platform.startswith("win"):
        _send_windows_notification(title, message)


def _send_macos_notification(title: str, message: str) -> None:
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{_escape_applescript(message)}" '
                f'with title "{_escape_applescript(title)}"',
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _send_windows_notification(title: str, message: str) -> None:
    script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textNodes = $template.GetElementsByTagName("text")
$textNodes.Item(0).AppendChild($template.CreateTextNode("{_escape_powershell(title)}")) > $null
$textNodes.Item(1).AppendChild($template.CreateTextNode("{_escape_powershell(message)}")) > $null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Discord Storage Bot")
$notifier.Show($toast)
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _escape_powershell(value: str) -> str:
    return value.replace("`", "``").replace('"', '`"')


def open_folder_in_explorer(path: str) -> None:
    """Open a folder in the system file explorer."""
    if sys.platform == "darwin":
        # macOS - open in Finder
        subprocess.run(
            ["open", path],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif sys.platform.startswith("win"):
        # Windows - open in Explorer
        subprocess.run(
            ["explorer", path],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif sys.platform.startswith("linux"):
        # Linux - try xdg-open
        subprocess.run(
            ["xdg-open", path],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
