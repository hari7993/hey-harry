# Working on Hey Harry's code

This is for a coding agent changing Hey Harry: Harry herself, when the owner asks her to build something into herself or she fixes a fault of her own (`selfwork.py`), or anyone else. Read it before you change anything.

Hey Harry is a voice assistant for Windows 10 and 11, in Python 3.14, run from `.venv`. The README says what she does for the owner; this says how the code fits together and the rules for changing it.

## How she's put together

- `app.py` starts her, under her keeper: it runs her, restarts her when she asks or crashes, and puts back a change of hers that won't start. `assistant_ui.py` is her window (Tk) and Settings, `island.py` the drop at the top of the screen.
- `siri.py` is the voice loop and every turn: hearing (`speech.py`, `hearing.py`), the fast path with no model (`_quick`, then each module's `quick()`), planning with the model (`think`, its prompt built from `prompt()`, `soul()` and gated blocks), doing the plan's steps (`do_step`, `run_info`) and her voice (`Line`, `voices.py`).
- `toolbox.py` is the one registry of steps. A step is registered once, with what it changes (`effect`), the words it needs without her name (`asks_for`) and how she asks about it (`confirm`). siri's gate sets are worked out from it, and `tests/test_toolbox.py` holds each set to its literal, so a new step is added there too.
- A feature of its own usually lives in a module of its own, the way `dream.py`, `cues.py` and `extras.py` do: a `quick(words, plain, gate)` for what's said plainly, a step registered with `toolbox.register(...)` and a handler, a `prompt_block(text)` that gives the planner its line only when the words may ask for it, a setting in `settings.py`'s `DEFAULTS`, a row in Settings (`assistant_ui.py`), and tests in `tests/test_<module>.py`.
- `agent.py` does tasks in apps on the screen and learns them as procedures; `tasks.py` keeps background tasks and decides which commands may run (`command_policy`); `coder.py` runs coding jobs through the OpenCode CLI.
- `selfwork.py` is how she knows herself (her parts, steps, settings and what she's built) and how she builds into and fixes herself.

Her own data lives in `%APPDATA%\Hey Harry` and `%LOCALAPPDATA%\Hey Harry` (`winplatform.APPDATA_DIR`, `winplatform.home`), never next to the code. Keys are in Windows Credential Manager (`secrets_store.py`), never in files.

## How things are written here

- Match the code round what you change: its names, its comments and how many of them, and its plain way of saying things. Comments say why, in plain words, often with the day something was found ("on 29 October ..."). Docstrings say what a function gives back, in a sentence or two.
- Keep her light and fast: the owner's hard rule. No new dependency without the owner, no heavy import at the top of `siri.py` (import inside the function that needs it), and nothing slow on a turn's path.
- Files have Windows line endings (CRLF, `core.autocrlf=true`).
- Safety stays: she asks before sending, deleting, paying, installing, shutting down or restarting the PC, and never types passwords. Never take a gate away or around one.

## Testing

From the repo root:

```
.venv\Scripts\python.exe -m unittest discover -s tests -t .
```

About 1,700 tests in about 3 minutes. Every test file imports `tests.support` first: it points `%APPDATA%` and `%LOCALAPPDATA%` at a temp folder and replaces everything that acts on the PC or goes online with a tripwire. A test that needs one patches it itself (`unittest.mock.patch.object`). Tests never touch the real PC, the network, the mic or the camera. A few tests may already fail before your change; only failures your change brings matter, and the build checks that.

## Rules for a change she makes to herself

- Do what was asked, and no more. Keep the change as small as it can be.
- Add or update tests for it, and run the suite.
- Never delete or weaken a test to make it pass, and never change `tests/support.py`.
- Never change `app.py`, `selfwork.py` or `tests/test_selfwork.py`: they're what puts her back if a change goes wrong. The build refuses a change to them.
- No installs, no new packages, no network, nothing outside this folder, and no git commands that change history. The build turns them down.
- No keys, passwords, names, numbers or anything personal in the code.
- When you're done, say in one or two plain sentences what you changed, to be read out loud.
