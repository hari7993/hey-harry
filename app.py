"""Entry point for the shortcut: same as `python siri.py --ui`, with output saved to %LOCALAPPDATA%\\Hey Harry\\Logs\\Hey Harry.log.

Started plainly, this is her keeper (selfwork.keep, 29 October 2026): a dozen MB of the standard library that runs
her as `app.py --child` and starts her again when she asks to (a build of hers is in) or when she crashes, taking out
a build she won't start with. Quit from her window, or stop her yourself, and she stays stopped.
--after <pid>: wait for that one to go first (a restart of hers, started without a keeper)."""
import os
import sys

# Her modules' compiled code is kept in __pycache__ even with PYTHONDONTWRITEBYTECODE set or python -B: the cached
# files here were found stale, so each start compiled her 24k lines again (import siri 0.84 s against 0.6 s)
sys.dont_write_bytecode = False
os.chdir(os.path.dirname(os.path.abspath(__file__)))

if "--after" in sys.argv:
    i = sys.argv.index("--after")
    pid = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    del sys.argv[i:i + 2]
    if pid.isdigit():
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, int(pid))  # SYNCHRONIZE
        if handle:
            ctypes.windll.kernel32.WaitForSingleObject(handle, 30000)
            ctypes.windll.kernel32.CloseHandle(handle)

if "--child" not in sys.argv:
    import selfwork

    sys.exit(selfwork.keep(sys.argv[1:]))

import winplatform  # noqa: E402

winplatform.move_home()  # Hey Jev's folders as Hey Harry's, the first time, before her log or anything else is open
log = open(winplatform.log_path("Hey Harry.log"), "a", buffering=1, encoding="utf-8", errors="backslashreplace")
sys.stdout = sys.stderr = log
if winplatform.MOVED:
    print(f"moved from Hey Jev: {', '.join(winplatform.MOVED)}")

from assistant_ui import run_app  # noqa: E402

run_app()
