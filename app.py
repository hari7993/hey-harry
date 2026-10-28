"""Entry point for the shortcut: same as `python siri.py --ui`, with output saved to %LOCALAPPDATA%\\Hey Harry\\Logs\\Hey Harry.log."""
import os
import sys

# Her modules' compiled code is kept in __pycache__ even with PYTHONDONTWRITEBYTECODE set or python -B: the cached
# files here were found stale, so each start compiled her 24k lines again (import siri 0.84 s against 0.6 s)
sys.dont_write_bytecode = False
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import winplatform  # noqa: E402

winplatform.move_home()  # Hey Jev's folders as Hey Harry's, the first time, before her log or anything else is open
log = open(winplatform.log_path("Hey Harry.log"), "a", buffering=1, encoding="utf-8", errors="backslashreplace")
sys.stdout = sys.stderr = log
if winplatform.MOVED:
    print(f"moved from Hey Jev: {', '.join(winplatform.MOVED)}")

from assistant_ui import run_app  # noqa: E402

run_app()
