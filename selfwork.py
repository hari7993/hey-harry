"""How she knows herself, builds into herself and heals herself (29 October 2026, the owner's ask: "when I need a new
feature I tell her and she builds it herself, with the good model I choose; she knows her parts, what she does and
what she can do; and if anything fails she heals herself, without asking me to run anything").

Knowing herself (knowledge): read from her own code each time she's asked, so it's never out of date: each file and
what it's for (the first paragraph of its docstring), her steps (toolbox), what's switched on, the models she thinks,
speaks and builds with, what she's built into herself and fixed, and the faults she's had lately. The about_me step
answers from it ("what can you do?", "how do you see me?", "what have you built for yourself?").

Building into herself (Build): the coding agent coding jobs use (coder.Job: the OpenCode CLI), on the model picked in
Settings > Builder model (the answer model's to start with), in a copy of her code made with git worktree in
%LOCALAPPDATA%\\Hey Harry\\builds, never in the code that's running. AGENTS.md tells it how she's put together and the
rules. Then her whole test suite runs there, and what fails that didn't fail before the change goes back to the agent,
twice at most. A change that passes is checked once more (none of PROTECTED touched, no test taken away, nothing
that looks like a key, not too big), its files are copied into her code, only where they're still as they were when
it began, and she restarts to use it. If she won't start with it, her keeper (keep, which app.py runs) puts the files
back as they were and starts her again, and she says so and tries to fix what stopped her.

Healing herself (fault): an error in her own code, a TypeError or a KeyError raised from one of her files, is kept in
faults.jsonl, and the first time each one's seen she builds a fix for it the same way, at most HEALS_A_DAY a day, and
says so once it's in. A crash is the keeper's: it starts her again, and she fixes what crashed her.

Light: nothing here is imported until she starts, and nothing heavy at all. Her keeper is this file and the standard
library, a dozen MB, waiting on her."""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Hey Harry")
BUILDS = os.path.join(LOCAL, "builds")  # copies of her code being built on
BUILT = os.path.join(LOCAL, "built.jsonl")  # what she's built into herself and fixed, newest last
FAULTS = os.path.join(LOCAL, "faults.jsonl")  # errors in her own code, one row each, with how often it's come
PENDING = os.path.join(LOCAL, "pending.json")  # a build that's in, until she's run TRIAL seconds with it
TAKEN_OUT = os.path.join(LOCAL, "taken_out.json")  # a build the keeper took out as she wouldn't start with it
LOG = os.path.join(LOCAL, "Logs", "Hey Harry.log")
RESTART = 75  # her exit code for "start me again": a build of hers is in
TRIAL = 90.0  # seconds she runs with a new build before it counts as started
TEST_TIMEOUT = 20 * 60
ROUNDS = 3  # goes at a change: the first, and two more with what still fails
HEALS_A_DAY = 4
MOST_LINES = 3000  # lines changed in one build, past which it isn't taken
# What puts her back if a build goes wrong, what the tests stand on, and what changes the PC's packages: a build
# never touches them (AGENTS.md says so too). The owner changes them, with Claude Code or by hand
PROTECTED = ("app.py", "selfwork.py", "tests/support.py", "tests/test_selfwork.py", "AGENTS.md", ".gitignore",
             "requirements.txt", "setup.ps1")
CREATE_NO_WINDOW = 0x08000000
# what counts as a fault of her own: her code doing what it shouldn't. RuntimeError is what she raises to say why
# she can't, and OSError and the network's are the world's, so neither is a fault of hers
BUG_TYPES = (AttributeError, NameError, TypeError, KeyError, IndexError, ValueError, ZeroDivisionError,
             ImportError, AssertionError, RecursionError)
NOT_BUGS = ("requests.", "urllib3.", "json.decoder.", "comtypes.", "_ctypes.")

_lock = threading.RLock()
STATE = {"heal": None, "building": None, "say": None, "restart": None}  # siri's hooks: heal(sig, trace, where,
# doing), say(line), restart(), and the build going on now


# --------------------------------------------------------------------------- small pieces
def git(*args, cwd=None, timeout=120, check=True, binary=False, env=None):
    """What git printed (bytes if binary), raising RuntimeError if it failed and check."""
    done = subprocess.run(["git", "-C", cwd or HERE, *args], capture_output=True, timeout=timeout, env=env,
                          creationflags=CREATE_NO_WINDOW)
    if check and done.returncode:
        why = (done.stderr or done.stdout).decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {args[0]} failed: {why[:300]}")
    return done.stdout if binary else done.stdout.decode("utf-8", "replace").strip()


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(value, f, indent=1, ensure_ascii=False)
    os.replace(path + ".tmp", path)


def _rows(path, most=500):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()[-most:]
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def _add_row(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _log(line):
    print(line, flush=True)


# --------------------------------------------------------------------------- knowing herself
_DOCS = {}  # path: (mtime, the first paragraph of its docstring)


def docline(path):
    """The first paragraph of a Python file's docstring, as one line, or ""."""
    try:
        mtime = os.path.getmtime(path)
        if _DOCS.get(path, (None,))[0] == mtime:
            return _DOCS[path][1]
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(12000)
    except OSError:
        return ""
    m = re.match(r'\s*(?:#[^\n]*\n\s*)*[rRbBuU]?("""|\'\'\')(.*?)(?:\1|$)', head, re.S)
    text = " ".join(m.group(2).strip().split("\n\n")[0].split()) if m else ""
    _DOCS[path] = (mtime, text)
    return text


def parts(folder=None):
    """[(file, what it's for)] for each of her own Python files, from its docstring, tests left out."""
    folder = folder or HERE
    return [(name, docline(os.path.join(folder, name))) for name in sorted(os.listdir(folder))
            if name.endswith(".py") and not name.startswith(("_", "test"))]


def tests_count(folder=None):
    """How many tests she has."""
    n, tests = 0, os.path.join(folder or HERE, "tests")
    for name in os.listdir(tests) if os.path.isdir(tests) else []:
        if name.startswith("test") and name.endswith(".py"):
            with open(os.path.join(tests, name), encoding="utf-8", errors="replace") as f:
                n += len(re.findall(r"^\s+def test_", f.read(), re.M))
    return n


def builds():
    """Each build's latest row, in the order they were built: [{id, at, kind, what, files, state, ...}]."""
    latest = {}
    for row in _rows(BUILT, 2000):
        latest[row.get("id")] = row  # the first time an id's seen sets its place
    return list(latest.values())


def built(most=15):
    """What she's built into herself and fixed lately, newest last."""
    return builds()[-most:]


def faults(most=10):
    """The faults kept lately, newest last: [{sig, count, first, last, state, where, doing}]."""
    latest = {}
    for row in _rows(FAULTS, 2000):
        latest[row.get("sig")] = row
    return sorted(latest.values(), key=lambda r: r.get("last", 0))[-most:]


def _ago(t):
    return time.strftime("%d %b %H:%M", time.localtime(t)) if t else "?"


def knowledge(question=""):
    """What she knows of herself, as text for the model to answer from: her parts, steps, what's switched on, her
    models, what she's built and fixed, and her faults lately. The parts a question names come in full."""
    import settings
    import toolbox
    words = {w for w in re.findall(r"[a-z]{4,}", str(question).lower())} - {"what", "your", "have", "with", "does",
                                                                          "that", "this", "about", "yourself"}
    lines = [f"Your code: {HERE}, {tests_count()} tests. Your parts (each file, and what it's for):"]
    for name, doc in parts():
        full = words and (name[:-3] in words or any(w in doc.lower() for w in words))
        lines.append(f"- {name}: {doc if full else doc[:170]}")
    steps = [n for n, t in toolbox.TOOLS.items() if t.known and t.gated_by is not None]
    lines.append("Your steps (what you can plan): " + ", ".join(steps))
    on = [k for k, v in settings.DEFAULTS.items() if isinstance(v, bool) and settings.get(k)]
    off = [k for k, v in settings.DEFAULTS.items() if isinstance(v, bool) and not settings.get(k)]
    lines.append("Switched on: " + ", ".join(on) + ". Off: " + ", ".join(off))
    lines.append(f"Models: answers {settings.get('llm_model')}; building yourself {builder_model() or 'none'}; "
                 f"voice {settings.get('voice') or 'Fish'}; hearing {settings.get('ears') or settings.get('stt_engine')}")
    done = built()
    lines.append("Built into yourself and fixed: " + ("; ".join(
        f"{_ago(b.get('at'))} {b.get('kind')} '{b.get('what', '')[:90]}' ({b.get('state')})" for b in done)
        if done else "nothing yet"))
    kept = faults()
    lines.append("Faults lately: " + ("; ".join(
        f"{f['sig']} x{f.get('count', 1)}, last {_ago(f.get('last'))} ({f.get('state')})" for f in kept)
        if kept else "none"))
    return "\n".join(lines)


# --------------------------------------------------------------------------- the model a build thinks with
OPENCODE_IDS = {"opencode": "opencode", "anthropic": "anthropic", "openai": "openai", "openrouter": "openrouter",
                "google": "google", "xai": "xai", "groq": "groq", "deepseek": "deepseek", "mistral": "mistral",
                "cerebras": "cerebras", "together": "togetherai", "moonshot": "moonshotai"}
KEY_ENV = {"opencode": "OPENCODE_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
           "openrouter": "OPENROUTER_API_KEY", "google": "GOOGLE_GENERATIVE_AI_API_KEY", "xai": "XAI_API_KEY",
           "groq": "GROQ_API_KEY", "deepseek": "DEEPSEEK_API_KEY", "mistral": "MISTRAL_API_KEY",
           "cerebras": "CEREBRAS_API_KEY", "together": "TOGETHER_AI_API_KEY", "moonshot": "MOONSHOT_API_KEY"}


def builder_model():
    """The model she builds herself with: Settings > Builder model, or the answer model's."""
    import settings
    return settings.get("builder_model") or settings.get("llm_model") or ""


def for_opencode(model):
    """(OpenCode's name for a model picked in Settings, the environment giving OpenCode its key), or (None, {}) for
    a provider OpenCode doesn't have (Kilo, this PC's)."""
    import providers
    p, model_id = providers.split(model)
    if p.id not in OPENCODE_IDS or not model_id:
        return None, {}
    key = providers.key(p) if p.key else ""
    return f"{OPENCODE_IDS[p.id]}/{model_id}", ({KEY_ENV[p.id]: key} if key and p.id in KEY_ENV else {})


def opencode_config(model):
    """OpenCode's setting for the key of model's provider, from her own keys: it outranks a key OpenCode keeps itself,
    which on 29 October was an OpenCode Zen key that had run out, while hers worked. {} with no key."""
    import providers
    p, _ = providers.split(model)
    key = providers.key(p) if p.key and p.id in OPENCODE_IDS else ""
    return {"provider": {OPENCODE_IDS[p.id]: {"options": {"apiKey": key}}}} if key else {}


def offered(model, env=None):
    """True if OpenCode offers model (its name for it, like "anthropic/claude-opus-5-5") given env's key, False if
    it doesn't, None if OpenCode couldn't be asked. Its list only: no model is asked anything."""
    import coder
    exe = coder.opencode_exe()
    if not exe or not model:
        return None
    try:
        done = subprocess.run([exe, "models", model.split("/")[0]], capture_output=True, timeout=90,
                              env=dict(os.environ, **(env or {})), creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode:
        return None
    return model in {line.strip() for line in done.stdout.decode("utf-8", "replace").splitlines()}


# --------------------------------------------------------------------------- her tests
def python_exe():
    """Her venv's python, which has everything her tests need."""
    for exe in (os.path.join(HERE, ".venv", "Scripts", "python.exe"), sys.executable):
        if exe and os.path.isfile(exe):
            return exe
    return "python"


TEST_LINE = re.compile(r"^(?:FAIL|ERROR): \S+ \(([^)]+)\)", re.M)


def run_tests(folder, only=(), timeout=TEST_TIMEOUT):
    """The tests that fail in folder: a set of their names. "the tests didn't finish" in it if they didn't run
    through. only: just these names (a rerun)."""
    args = [python_exe(), "-m", "unittest"] + (list(only) if only else ["discover", "-s", "tests", "-t", "."])
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("HEYHARRY_TESTING", None)
    try:
        done = subprocess.run(args, cwd=folder, capture_output=True, timeout=timeout, env=env,
                              creationflags=CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {"the tests didn't finish"}
    out = (done.stdout + done.stderr).decode("utf-8", "replace")
    failing = set(TEST_LINE.findall(out))
    if not re.search(r"^Ran \d+ tests?", out, re.M):
        failing.add("the tests didn't finish")
    return failing


# Looking round the copy: on 29 October a build's agent tried "ls" first, was turned down, and stopped there
LOOKING = re.compile(r"(?:ls|dir|cat|type|head|tail|wc|grep|rg|findstr|tree|pwd|echo|sed -n(?![^\n]* -i)|"
                     r"find(?![^\n]* -(?:exec|execdir|delete|ok|fprint|fls))|"
                     r"get-childitem|gci|get-content|gc|select-string|sls|get-location|"
                     r"git (?:status|diff|log|show|ls-files|grep|blame)(?![^\n]*--output))(?: [^\n]*)?", re.I)


def _pieces(command):
    """A command cut into what it runs, where it's piped (|) or chained (&&, ||, ;), but not inside quotes:
    grep -E "cues|dream" is one. None if anything else in it is outside quotes: a lone & (run in the background),
    > or < (a file written or read in), ` or $( (a command inside it)."""
    pieces, now, quote, i = [], "", None, 0
    while i < len(command):
        ch, two = command[i], command[i:i + 2]
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif two in ("&&", "||"):
            pieces.append(now)
            now, i = "", i + 2
            continue
        elif ch in "|;":
            pieces.append(now)
            now, i = "", i + 1
            continue
        elif ch in "&<>`" or two == "$(":
            return None
        now += ch
        i += 1
    return [p.strip() for p in pieces + [now]]


def may_run(command):
    """True for a command a build's agent may run without asking anyone: her own tests and compile checks, in her
    venv's python, and looking round the copy (LOOKING), piped or chained, its errors put with what it prints
    (2>&1) or nowhere: on 29 October an agent's "...unittest tests.test_routing 2>&1 | tail -20" and "git status &&
    git diff" were turned down, and it never saw why its test failed. Never a file written, or anything else."""
    command = re.sub(r"\s*2>(?:&1|/dev/null|nul)(?=\s|$|\|)", "", " ".join(str(command or "").split()), flags=re.I)
    pieces = _pieces(command)
    return bool(pieces) and all(piece and (LOOKING.fullmatch(piece) or _tests(piece)) for piece in pieces)


def _tests(command):
    """True for her tests or a compile check, in her venv's python or plain python."""
    m = re.fullmatch(r'"?(?P<exe>[^"]*?python(?:\.exe)?)"? -m (?P<mod>unittest|py_compile|compileall)(?: (?P<rest>.*))?',
                     command, re.I)
    if not m:
        return False
    exe = m["exe"].lower().replace("/", "\\")
    return exe in ("python", "python.exe", "py") or exe.endswith(("\\.venv\\scripts\\python.exe",
                                                                     "\\.venv\\scripts\\python"))


# --------------------------------------------------------------------------- building into herself
GUIDE = ("You're changing Hey Harry's own code: a copy of it, in {folder}, made for this change. Read AGENTS.md there "
         "first: how she's put together, how things are written, and the rules. {ask}\n\n"
         "Run her tests with: \"{python}\" -m unittest discover -s tests -t .  (a single file: \"{python}\" -m unittest "
         "tests.test_cues). Look round with your own read, list and search tools; of shell commands only her tests "
         "and read-only looks (ls, cat, grep, git status or diff) are let through. Some tests may fail before your "
         "change; leave those. Make the change with your edit tools, keep it small, and when you're done say in one "
         "or two plain sentences what you changed, to be read out loud.")
ASKS = {"build": "The owner asked for this, in their words: \"{what}\". Build it into her, with tests.",
        "fix": "She hit this error in her own code{doing}. Find why and fix it, with a test that fails without the "
               "fix:\n{trace}",
        "again": "Your change makes these tests fail, which passed before it:\n{failing}\nFix the change so they pass, "
                 "without weakening or deleting any test.",
        "nudge": "Last time you looked round and stopped without changing anything. Make the change now: edit the "
                 "files with your edit tools, add its test, then run the tests."}


class Build:
    """One change to her own code, built and checked in a copy of it, then put in. kind: "build" (asked for) or
    "fix" (a fault of hers, trace its traceback). progress(note): how it's going, for her task's row."""

    def __init__(self, what, kind="build", trace="", doing="", model=None, cancelled=lambda: False, progress=None,
                 job=None, tests=None):
        self.what, self.kind, self.trace, self.doing = " ".join(str(what).split())[:2000], kind, trace, doing
        self.model = builder_model() if model is None else model
        self.cancelled, self.progress = cancelled, progress or (lambda note: None)
        self.job = job  # coder.Job, or a stand-in in the tests
        self.tests = tests or run_tests
        self.id = time.strftime("%Y%m%d-%H%M%S")
        self.folder = os.path.join(BUILDS, self.id)
        self.before = os.path.join(BUILDS, self.id + "-before")
        self.files, self.said, self.used = [], "", None
        self.again = str(doing).startswith("again")  # a build tried once more, after it stopped her starting

    def run(self):
        """(it's in, what to say about it)."""
        import coder
        with _lock:
            if STATE["building"]:
                return False, "I'm already building something into myself. I'll do this after."
            STATE["building"] = self
        try:
            os.makedirs(BUILDS, exist_ok=True)
            _tidy()
            self.progress("copying my code")
            base = coder.snapshot(HERE).partition(":")[2]  # her code as it is now, with what's not committed
            git("worktree", "add", "--detach", self.folder, base, timeout=180)
            git("worktree", "add", "--detach", self.before, base, timeout=180)
            baseline = {}
            first = threading.Thread(target=lambda: baseline.update(failing=self.tests(self.before)), daemon=True)
            first.start()  # her tests as they are, while the agent works
            ok, said = self._rounds(baseline, first)
            if not ok:
                return False, said + self._fell_back(" Pick a stronger one in Settings > Build herself.")
            problem = self._checks(base)
            if problem:
                return False, problem + " Nothing in me changed."
            if self.cancelled():
                return False, "Stopped. Nothing in me changed."
            self.progress("putting it in")
            commit = self._commit()
            self.files = put_in(base, commit, self.folder)
            entry = {"id": self.id, "at": time.time(), "kind": self.kind, "what": self.what, "base": base,
                     "commit": commit, "files": self.files, "model": self.used or self.model, "said": self.said[:600],
                     "state": "in", "again": self.again}
            _write_json(PENDING, entry)
            _add_row(BUILT, entry)
            return True, self._summary() + self._fell_back()
        except Exception as exc:  # whatever happened, nothing of hers changed unless put_in finished
            _log(f"  build {self.id}: {exc!r}")
            if self.cancelled():
                return False, "Stopped. Nothing in me changed."
            return False, f"I couldn't build it: {exc}. Nothing in me changed."
        finally:
            for folder in (self.folder, self.before):
                git("worktree", "remove", "--force", folder, check=False)
                shutil.rmtree(folder, ignore_errors=True)
            git("worktree", "prune", check=False)
            with _lock:
                STATE["building"] = None

    def _summary(self):
        """What the agent said it did, or, when that's missing or cut off ("Now the whole suite:", a free model's last
        words on 29 October), the files it changed."""
        said = " ".join(self.said.split())
        if len(said) >= 12 and not said.endswith(":"):
            return said
        names = [os.path.basename(f) for f in self.files]
        return f"I changed {len(names)} file{'' if len(names) == 1 else 's'}: {', '.join(names[:4])}."

    def _fell_back(self, then=""):
        """What to say when OpenCode didn't have the model picked and a free one built it, or ""."""
        wanted = for_opencode(self.model)[0] if self.model else None
        if not self.used or self.used == wanted:
            return ""
        return (f" OpenCode doesn't have {wanted}, so {self.used.split('/')[-1]} built it." if wanted else
                f" {self.used.split('/')[-1]} built it.") + then

    def _rounds(self, baseline, first):
        """The agent's goes at it, each followed by her tests: (passing, what to say)."""
        failing, new, nudged = set(), set(), False
        for n in range(ROUNDS):
            if self.cancelled():
                return False, "Stopped. Nothing in me changed."
            ask = ASKS["again"].format(failing="\n".join(sorted(new))) if n else \
                ASKS[self.kind].format(what=self.what, trace=self.trace[-6000:],
                                       doing=f", while {self.doing}" if self.doing else "")
            if not n and self.kind == "build" and self.trace:  # built before, and it stopped her starting
                ask += f"\n\nThe last time this was built, she wouldn't start with it:\n{self.trace[-4000:]}\nMind that."
            self.progress("building" if not n else f"fixing what fails, go {n + 1}")
            finished, said = self._agent(GUIDE.format(folder=self.folder, ask=ask, python=python_exe()))
            self.said = said or self.said
            if self.cancelled():
                return False, "Stopped. Nothing in me changed."
            if not changed_files(self.folder):
                if n + 1 < ROUNDS and not nudged:  # a model that looked round and stopped: once more, told to
                    nudged = True
                    new = set()
                    ask = ASKS["nudge"]
                    finished, said = self._agent(GUIDE.format(folder=self.folder, ask=ASKS[self.kind].format(
                        what=self.what, trace=self.trace[-6000:], doing=f", while {self.doing}" if self.doing
                        else "") + "\n\n" + ask, python=python_exe()))
                    self.said = said or self.said
                if not changed_files(self.folder):
                    return False, "It didn't change anything" + (f": {said}" if said else ".")
            self.progress("running my tests")
            failing = self.tests(self.folder)
            first.join(TEST_TIMEOUT)
            before = baseline.get("failing", set())
            new = failing - before
            if new and "the tests didn't finish" not in new:  # one more run of those alone, here and before: a test
                # that only fails some of the time, or only while music plays, isn't this change's
                again = self.tests(self.folder, sorted(new))
                was = self.tests(self.before, sorted(new))
                new = {t for t in new if t in again and t not in was}
            if not new:
                return True, said
            _log(f"  build {self.id}: {len(new)} tests fail that didn't: {', '.join(sorted(new)[:5])}")
        return False, (f"I couldn't get it working: {len(new)} of my tests still fail with it, like "
                       f"{sorted(new)[0]}. Nothing in me changed.")

    def _agent(self, prompt):
        """The coding agent's go at prompt, in the copy: (it finished, what it says it did)."""
        if self.job is not None:
            return self.job(self.folder, prompt)
        import coder
        model, env = for_opencode(self.model)
        venv = os.path.dirname(python_exe())
        env = {**env, "PATH": venv + os.pathsep + os.environ.get("PATH", "")}  # "python" is hers, with her packages
        job = coder.Job(self.folder, self.what, ask=None, cancelled=self.cancelled, model=model, env=env,
                        may_run=may_run, may_edit=lambda path: not protected(path, self.folder), guide=prompt,
                        config=opencode_config(self.model),
                        progress=lambda n: self.progress(f"building, {coder.edited(n)}"))
        finished, said = job.run()
        self.used = job.model_used
        _log(f"  build {self.id}: {job.model_used} {'finished' if finished else 'stopped'}, {len(job.edited)} edits, "
             f"ran {len(job.ran)}" + (f", didn't let it run {'; '.join(job.refused[:3])}" if job.refused else ""))
        return finished, said

    def _checks(self, base):
        """Why the change can't go in, or None."""
        names = changed_files(self.folder)
        touched = [n for n in names if protected(n)]
        if touched:
            return f"It changed {touched[0]}, which is what puts me back if a change goes wrong, so it's not taken."
        if tests_count(self.folder) < tests_count(self.before):
            return "It took some of my tests away, so it's not taken."
        diff = git("diff", "--numstat", "HEAD", cwd=self.folder) + "\n" + "\n".join(
            f"{len(_lines(os.path.join(self.folder, n)))}\t0\t{n}" for n in untracked(self.folder))
        total = sum(int(a) + int(b) for a, b, _ in re.findall(r"^(\d+)\t(\d+)\t(.+)$", diff, re.M))
        if total > MOST_LINES:
            return f"It changed {total} lines, too much to take in one go."
        added = "".join(line[1:] + "\n" for line in git("diff", "HEAD", "-U0", cwd=self.folder).splitlines()
                        if line.startswith("+") and not line.startswith("+++")) + "".join(
            "".join(_lines(os.path.join(self.folder, n))) for n in untracked(self.folder))
        if _secret_in(added):
            return "It put in something that looks like a key or a password, so it's not taken."
        return None

    def _commit(self):
        git("add", "-A", cwd=self.folder)
        git("-c", "user.name=Hey Harry", "-c", "user.email=hey-harry@localhost", "commit", "-q", "-m",
            f"Harry {'fixed' if self.kind == 'fix' else 'built'}: {self.what[:200]}", cwd=self.folder)
        commit = git("rev-parse", "HEAD", cwd=self.folder)
        git("update-ref", f"refs/heyharry/builds/{self.id}", commit)
        return commit


def protected(path, folder=None):
    """True for a file a build mustn't change (PROTECTED), or one outside its copy, named as OpenCode or git names
    it."""
    p = str(path or "").strip().strip('"')
    if folder and os.path.isabs(p):
        try:
            p = os.path.relpath(p, folder)
        except ValueError:  # another drive
            return True
    p = re.sub(r"^(?:\./)+", "", p.replace("\\", "/"))
    return p.startswith("../") or p in PROTECTED


def _tidy(keep_refs=30):
    """Copies of her code left from a build that stopped part-way (she crashed, the PC went off), and all but the
    last keep_refs builds' commits."""
    for name in os.listdir(BUILDS) if os.path.isdir(BUILDS) else []:
        path = os.path.join(BUILDS, name)
        if os.path.isdir(path):
            git("worktree", "remove", "--force", path, check=False)
            shutil.rmtree(path, ignore_errors=True)
    git("worktree", "prune", check=False)
    refs = git("for-each-ref", "--sort=-refname", "--format=%(refname)", "refs/heyharry/builds", check=False).split()
    for old in refs[keep_refs:]:
        git("update-ref", "-d", old, check=False)


def changed_files(folder):
    """The files a build's copy has changed, added or deleted, as git names them. Read NUL-separated and untrimmed:
    trimmed, " M app.py" lost its first space, the name came out "pp.py", and a change to app.py went past the
    check on what a build mustn't touch."""
    out = git("status", "--porcelain", "-z", "--untracked-files=all", cwd=folder, binary=True).decode("utf-8", "replace")
    names, entries = [], out.split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        if len(entry) > 3:
            names.append(entry[3:])
            if entry[0] in "RC":  # a rename: the name it had comes next
                i += 1
        i += 1
    return names


def untracked(folder):
    out = git("ls-files", "--others", "--exclude-standard", cwd=folder)
    return [n for n in out.splitlines() if n.strip()]


def _lines(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except OSError:
        return []


# what a real key looks like written into code: the kinds providers hand out, a JWT, a private key. Not "token =
# ...", which her code has all over
KEY_LIKE = re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{20,}|\b(?:sk|pk|ghp|gho|github_pat|xox[abp])_[A-Za-z0-9_-]{16,}|"
                      r"\bAKIA[A-Z0-9]{16}\b|\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|"
                      r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


def _secret_in(text):
    """True if text has what looks like a key in it, or one of her own keys (checked, never said)."""
    if KEY_LIKE.search(text):
        return True
    try:
        import secrets_store
        for name in secrets_store.KEY_NAMES + secrets_store.MODEL_KEYS + secrets_store.VOICE_KEYS:
            value = secrets_store.get_secret(name) or ""
            if len(value) >= 12 and value in text:
                return True
    except Exception:
        pass
    return False


def _blob(commit, path):
    """The bytes of path in commit, or None if it isn't there."""
    done = subprocess.run(["git", "-C", HERE, "cat-file", "blob", f"{commit}:{path}"], capture_output=True,
                          timeout=60, creationflags=CREATE_NO_WINDOW)
    return done.stdout if done.returncode == 0 else None


def _file(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def _same(a, b):
    """The same file, line endings aside (git keeps them as LF, Windows as CRLF)."""
    if a is None or b is None:
        return a is b
    return a.replace(b"\r\n", b"\n") == b.replace(b"\r\n", b"\n")


def put_in(base, commit, folder):
    """Copies a build's files from its copy into her code: only if each is still as it was when the build began
    (base), else RuntimeError and nothing changed. The files, as git names them."""
    changes = []
    for line in git("diff", "--name-status", "--no-renames", base, commit).splitlines():
        status, _, path = line.partition("\t")
        if not path:
            continue
        if not _same(_blob(base, path), _file(os.path.join(HERE, path))):
            raise RuntimeError(f"{path} changed while I was building, so I've left it")
        changes.append((status, path))
    for status, path in changes:
        live = os.path.join(HERE, path)
        if status.startswith("D"):
            if os.path.exists(live):
                os.remove(live)
            continue
        os.makedirs(os.path.dirname(live), exist_ok=True)
        shutil.copyfile(os.path.join(folder, path), live + ".new")
        os.replace(live + ".new", live)
    return [path for _, path in changes]


def take_out(entry):
    """Puts the files a build changed back as they were before it. The files put back."""
    back = []
    for path in entry.get("files") or []:
        before, live = _blob(entry["base"], path), os.path.join(HERE, path)
        if before is None:
            if os.path.exists(live):
                os.remove(live)
        else:
            if b"\0" not in before:  # text: as Windows keeps it, as git checks it out here
                before = before.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            os.makedirs(os.path.dirname(live), exist_ok=True)
            with open(live + ".old", "wb") as f:
                f.write(before)
            os.replace(live + ".old", live)
        back.append(path)
    return back


def undo_last():
    """Takes her last build out, if what it changed is still as it left it: (it's out, what to say)."""
    done = [b for b in builds() if b.get("state") == "in"]
    if not done:
        return False, "I haven't built anything into myself to undo."
    last = done[-1]
    for path in last.get("files") or []:
        if not _same(_blob(last["commit"], path), _file(os.path.join(HERE, path))):
            return False, f"{path} has changed since I built that, so I can't just take it out."
    take_out(last)
    _add_row(BUILT, {**last, "at": time.time(), "state": "taken out"})
    if os.path.exists(PENDING):
        os.remove(PENDING)
    return True, f"Okay, I've taken out \"{last['what'][:100]}\"."


# --------------------------------------------------------------------------- healing herself
def bug_in_me(exc):
    """(its signature, where in her code) if exc is a fault of her own code, else None."""
    if not isinstance(exc, BUG_TYPES) or type(exc).__module__.startswith(NOT_BUGS):
        return None
    frames = [f for f in traceback.extract_tb(exc.__traceback__)
              if os.path.normcase(os.path.dirname(os.path.abspath(f.filename))) == os.path.normcase(HERE)]
    if not frames:
        return None
    last = frames[-1]
    return f"{type(exc).__name__} in {os.path.basename(last.filename)} {last.name}()", f"{last.filename}:{last.lineno}"


def fault(exc, where="", doing=""):
    """An error caught somewhere in her. A fault of her own code is kept, and fixed the first time it's seen (heal)
    unless Settings > Heal herself is off or she's fixed HEALS_A_DAY today. True if it was hers."""
    found = bug_in_me(exc)
    if not found:
        return False
    sig, at = found
    trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-6000:]
    _note(sig, trace, where or at, doing)
    return True


NOTED = {}  # sig: when it was last written down, so one that comes every couple of seconds isn't a line each time
NOTE_EVERY = 60.0
FAULTS_MOST = 2 * 1024 * 1024  # bytes of faults.jsonl, past which it's cut to each fault's latest row


def _note(sig, trace, where, doing, crash=False, heal_now=True):
    """Keeps a fault, and starts its fix if heal_now and it's new. The keeper only keeps one (heal_now False): she
    fixes it once she's up (started)."""
    with _lock:
        now = time.time()
        if now - NOTED.get(sig, 0.0) < NOTE_EVERY:
            return False
        NOTED[sig] = now
        rows = {r.get("sig"): r for r in _rows(FAULTS, 2000)}
        try:
            if os.path.getsize(FAULTS) > FAULTS_MOST:
                with open(FAULTS + ".tmp", "w", encoding="utf-8") as f:
                    f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows.values())
                os.replace(FAULTS + ".tmp", FAULTS)
        except OSError:
            pass
        row = rows.get(sig) or {"sig": sig, "first": now, "count": 0, "state": "new"}
        row.update(last=now, count=row.get("count", 0) + 1, where=where, doing=str(doing)[:200], crash=crash,
                   trace=trace[-6000:])
        fixing = heal_now and row["state"] == "new" and _may_heal(rows.values(), now)
        if fixing:
            row["state"] = "fixing"
        _add_row(FAULTS, row)
    _log(f"  (fault in me: {sig}{', fixing it' if fixing else ''})")
    if fixing and STATE["heal"] is not None:
        STATE["heal"](sig, trace, where, doing)
    return fixing


def _may_heal(rows, now):
    import settings
    if settings.get("self_heal") is False:
        return False
    today = sum(1 for r in rows if r.get("state") in ("fixing", "fixed", "not fixed") and now - r.get("last", 0) < 86400)
    return today < HEALS_A_DAY


def healed(sig, ok):
    """How a fix for a fault went."""
    rows = {r.get("sig"): r for r in _rows(FAULTS, 2000)}
    if sig in rows:
        _add_row(FAULTS, {**rows[sig], "state": "fixed" if ok else "not fixed", "last": time.time()})


def watch(heal, say):
    """From her start: every error no one caught, on any thread, is looked at as a fault (fault), and heal(sig,
    trace, where, doing) is how a fix is started; say(line) is how she tells you."""
    STATE["heal"], STATE["say"] = heal, say
    old_main, old_thread = sys.excepthook, threading.excepthook

    def main(kind, exc, tb):
        try:
            fault(exc, "her main thread")
        except Exception:
            pass
        old_main(kind, exc, tb)

    def thread(args):
        try:
            if args.exc_value is not None:
                fault(args.exc_value, f"thread {getattr(args.thread, 'name', '?')}")
        except Exception:
            pass
        old_thread(args)
    sys.excepthook, threading.excepthook = main, thread


# --------------------------------------------------------------------------- starting with a build, or after one
def started(say, heal, queue=None):
    """As she starts: says if a build came in, or was taken out because she wouldn't start with it (and tries it
    once more, told what stopped it), or if she crashed and started again (and fixes that, heal); a build counts as
    started after TRIAL. queue(kind, what, trace, doing): siri.queue_self."""
    out = _read_json(TAKEN_OUT)
    if out:
        os.remove(TAKEN_OUT)
        again = queue is not None and out.get("kind") == "build" and not out.get("again")
        say(f"My new build, \"{out.get('what', '')[:80]}\", stopped me starting, so I've put myself back as I was."
            + (" I'll build it again, minding what went wrong." if again else ""))
        if again:
            queue("build", out.get("what", ""), out.get("trace", ""), "again: the last try stopped her starting")
    pending = _read_json(PENDING)
    if pending:
        say(f"I'm back, and {'the fix' if pending.get('kind') == 'fix' else 'it'}'s in: {pending.get('what', '')[:100]}.")

        def settle():
            time.sleep(TRIAL)
            if _read_json(PENDING, {}).get("id") == pending.get("id"):
                os.remove(PENDING)
                _log(f"  (build {pending.get('id')} started fine)")
        threading.Thread(target=settle, name="build-trial", daemon=True).start()
    crashes = [f for f in faults(20) if f.get("crash") and f.get("state") == "new"]
    rows = {r.get("sig"): r for r in _rows(FAULTS, 2000)}
    for crash in crashes[-1:]:
        if not _may_heal(rows.values(), time.time()):
            say("I stopped by myself a moment ago and started again.")
            break
        say("I stopped by myself a moment ago and started again. I'm fixing what did it.")
        _add_row(FAULTS, {**rows[crash["sig"]], "state": "fixing"})
        heal(crash["sig"], crash.get("trace", ""), "a crash", crash.get("doing", ""))


def restart_soon(say, idle, why, wait=600):
    """Starts her again with what's been built, once she's not busy (idle()), or after wait seconds: by her keeper
    (RESTART), or, started without one, by starting her keeper first."""
    def go():
        end = time.time() + wait
        while time.time() < end and not idle():
            time.sleep(2)
        try:
            if why:
                say(why)
        except Exception:
            pass
        time.sleep(4)  # her line said before she goes
        sys.stdout.flush()
        if "--child" not in sys.argv:  # no keeper: one is started, which waits for this one to go
            subprocess.Popen([python_exe().replace("python.exe", "pythonw.exe"), os.path.join(HERE, "app.py"),
                              "--after", str(os.getpid())], cwd=HERE, creationflags=CREATE_NO_WINDOW,
                             close_fds=True)
            os._exit(0)
        os._exit(RESTART)
    threading.Thread(target=go, name="restart", daemon=True).start()


# --------------------------------------------------------------------------- her keeper
def _log_size():
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


def last_trace(most=40, since=None):
    """The last traceback in her log (written after since, a size it had), or her last lines if there's none."""
    try:
        with open(LOG, "rb") as f:
            f.seek(0, 2)
            end = f.tell()
            f.seek(max(0, end - 60000, since if since is not None and since <= end else 0))
            tail = f.read().decode("utf-8", "replace").replace("\r\n", "\n")
    except OSError:
        return ""
    i = tail.rfind("Traceback (most recent call last)")
    return "\n".join(tail[i:].splitlines()[:most]) if i >= 0 else "\n".join(tail.splitlines()[-8:])


def _say_in_log(line):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[keeper {time.strftime('%H:%M:%S')}] {line}\n")
    except OSError:
        pass


def _tell(text):
    """A box on the screen, for when she can't say it herself."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "Hey Harry", 0x40 | 0x40000)  # information, top-most
    except Exception:
        pass


def keep(args, run=None, clock=time.time, sleep=time.sleep, tell=_tell):
    """Runs her (app.py --child) and keeps her running, which app.py does: when she quits, so does this; when she
    asks to start again (RESTART, a build's in), she's started again; when she crashes, she's started again too,
    with the build she'd just started taken out if it's what stopped her (TAKEN_OUT), and the crash kept as a fault
    she fixes once she's up. Four crashes in ten minutes and it stops, and says so on the screen."""
    run = run or (lambda cmd: subprocess.call(cmd, cwd=HERE))
    exe = sys.executable
    crashes = []
    while True:
        began, size = clock(), _log_size()
        code = run([exe, os.path.join(HERE, "app.py"), "--child", *args])
        args = [a for a in args if a != "--startup"]  # only the first start is as you signed in
        if code == 0:
            return 0
        if code == RESTART:
            _say_in_log("starting her again, with what she's built")
            continue
        trace = last_trace(since=size)
        if code == 1 and "Traceback" not in trace:  # stopped from outside (Task Manager, taskkill), or she said
            # why she couldn't go on (no key): starting her again wouldn't help, and you meant it
            _say_in_log("she was stopped, so she stays stopped")
            return code
        why = (trace.strip().splitlines() or [f"exit code {code}"])[-1][:200]
        _say_in_log(f"she stopped after {clock() - began:.0f} s (exit code {code}): {why}")
        pending = _read_json(PENDING)
        if pending and clock() - began < TRIAL + 30:
            take_out(pending)
            _add_row(BUILT, {**pending, "at": clock(), "state": "taken out: she wouldn't start with it"})
            _write_json(TAKEN_OUT, {**pending, "trace": trace})
            os.remove(PENDING)
            _say_in_log(f"took out build {pending.get('id')}, she wouldn't start with it")
            continue
        _note(f"crash: {why[:120]}", trace, "her start" if clock() - began < 60 else "while running", "", crash=True,
              heal_now=False)
        crashes = [t for t in crashes if clock() - t < 600] + [clock()]
        if len(crashes) >= 4:
            tell(f"Hey Harry keeps stopping by herself, so I've stopped starting her again:\n\n{why}\n\nStart her "
                 f"from the Start menu once it's sorted.")
            return code
        sleep(min(30, 3 * len(crashes)))


# --------------------------------------------------------------------------- what's said about it
# Only plain asks to build into her: "make yourself quieter" is her volume, "teach yourself to..." a task she learns
# by doing it (agent.py), so neither is here
SELF = r"(?:yourself|your ?self|your own code|your code)"
_KIND = r"(?:feature|function|ability|option|mode|command|setting|skill)s?"
_LINK = r"(?: (?:to|that|which|for|so|so that|where|called|named|like))?:?"
BUILD_SAID = re.compile(r"(?:i want you to |go (?:and )?)?(?:build|code|develop|program|implement)(?: (?:into|in|for|"
                        r"to))? " + SELF + r"(?: (?:a|an|the|some))?(?: new)?(?: " + _KIND + ")?" + _LINK +
                        r" (?P<what>.{6,600})|"
                        r"(?:i want you to )?add (?:a |an |the )?(?:new )?" + _KIND + r"(?: (?:to|into|in) " + SELF +
                        ")?" + _LINK + r" (?P<what3>.{6,600})|"
                        r"(?:improve|upgrade|extend) " + SELF + r"(?: (?:so|to|so that|by|with|and|for|in))? "
                        r"(?P<what2>.{6,600})|"
                        r"give yourself (?:the ability|a way|an? (?:new )?" + _KIND + r")(?: to| for| that)? "
                        r"(?P<what4>.{4,600})")
WHAT_BUILT = re.compile(r"what (?:have|did) you (?:built|build|made|make|fixed|fix|changed|change|improved|improve)"
                        r"(?: (?:for|in|into|on|to|about))?(?: yourself| your code)?(?: (?:lately|today|so far|"
                        r"recently))?|(?:show|tell) me (?:your|what you'?ve) (?:builds|built|fixes|fixed)")
HEALTH = re.compile(r"(?:are you (?:ok|okay|alright|healthy|working (?:ok|okay|fine|properly))(?: inside)?|"
                    r"(?:any|have you had any|did you have any) (?:errors|faults|bugs|crashes|problems)(?: (?:lately|"
                    r"today|in you|inside))?|how(?:'s| is| are) your (?:health|code|system)|(?:your|check your) "
                    r"(?:health|faults|errors))")
FIX_SAID = re.compile(r"(?:(?:can|could|will) you |please |go )?(?:fix|heal|repair|debug) (?:yourself|your ?self|your "
                      r"(?:code|bugs?|errors?|faults?|system))(?: (?:now|please))?")
UNDO_SAID = re.compile(r"(?:undo|remove|take out|roll ?back|revert|reverse)(?: (?:your|that|the))? (?:last |latest "
                       r")?(?:build|change|update|upgrade|feature|fix)(?: (?:you|to yourself|you made|you built))?|"
                       r"put yourself back(?: (?:how|as) you were)?")


def quick(words, plain, gate=False, queue=None, health_check=None):
    """A plan for what's said about her building into and healing herself, or None. queue(kind, what, trace,
    doing): her task for a build. With her name only: never from across the room."""
    if gate == "cold":
        return None
    t = plain(str(words or ""))
    if WHAT_BUILT.fullmatch(t):
        done = [b for b in built(30) if b.get("state")]
        if not done:
            return {"steps": [], "say": "Nothing yet. Ask me for a feature, like: build yourself a way to read my "
                                        "battery out every hour, and I will."}
        latest = done[-5:]
        return {"steps": [], "say": "Lately: " + "; ".join(
            f"{'fixed' if b.get('kind') == 'fix' else 'built'} {b.get('what', '')[:80]} on "
            f"{time.strftime('%d %B', time.localtime(b.get('at') or 0))}, {b.get('state')}" for b in latest) + "."}
    if HEALTH.fullmatch(t):
        kept = [f for f in faults(20) if time.time() - f.get("last", 0) < 86400 * 7]
        if not kept:
            return {"steps": [], "say": "All good: no faults in my code this week."}
        open_ = [f for f in kept if f.get("state") in ("new", "not fixed")]
        return {"steps": [], "say": f"{len(kept)} fault{'s' if len(kept) != 1 else ''} this week, "
                                    f"{len(kept) - len(open_)} fixed or being fixed"
                                    + (f", and {len(open_)} not yet: {open_[-1]['sig']}." if open_ else ".")}
    if FIX_SAID.fullmatch(t):
        open_ = [f for f in faults(20) if f.get("state") in ("new", "not fixed")]
        if not open_:
            return {"steps": [], "say": "There's nothing wrong in me that I know of. If something didn't work, tell me "
                                        "what, and I'll build a fix for it."}
        f = open_[-1]
        if queue:
            queue("fix", f"Fix: {f['sig']}", f.get("trace", ""), f.get("doing", ""))
        return {"steps": [], "say": f"I'm on it: fixing {f['sig']}. I'll tell you once it's in."}
    if UNDO_SAID.fullmatch(t):
        ok, line = undo_last()
        if ok and STATE.get("restart"):
            STATE["restart"]()  # once this turn's said
        return {"steps": [], "say": line + (" Restarting to be as I was, back in a moment." if ok else "")}
    m = BUILD_SAID.fullmatch(t)
    if m:
        what = (m["what"] or m["what2"] or m["what3"] or m["what4"] or "").strip(" .")
        if queue:
            queue("build", str(words).strip(), "", "")
        model = builder_model()
        return {"steps": [], "say": f"Okay, I'll build that into myself: {what[:120]}. It takes a few minutes, "
                                    f"with {model.split('/')[-1] or 'my model'}; I'll tell you when it's in."}
    return None


# --------------------------------------------------------------------------- her steps for the planner
LINE = ('{"do":"improve","what":"..."}  build a new feature into yourself or change how you work, when they ask you '
        'to ("build yourself...", "add a feature...", "improve yourself so..."): what, in their words. Coded, tested and '
        'put in in the background, then you restart\n'
        '{"do":"about_me","ask":"..."}  what you know of yourself, to answer a question about you: your parts and code, '
        'what you can do and how, your settings and models, what you have built into yourself, your faults')
WORDS = re.compile(r"\b(?:yourself|your (?:own )?(?:code|parts|features?|abilities|capabilities|skills|components|"
                   r"modules|settings|system|models?|health|faults|errors|bugs)|what can you do|what do you do|"
                   r"how do you (?:work|know|see|hear)|are you able|feature|improve|upgrade|build|rebuild|heal|crash\w*|"
                   r"what have you (?:built|made|fixed|changed))\b", re.I)


def register():
    """Her steps for it, in the registry: improve queues a build (siri.prepare_task_steps); about_me is a look-up."""
    import toolbox
    if toolbox.get("improve") is None:
        # asked about when it's planned without her name or after reading a page: what a page says never builds her
        toolbox.register("improve", effect="acts", asks_for=None, confirm="Should I build that into myself?",
                         line=LINE.split("\n")[0], background="never", gated_by="SELF_STEPS")
    if toolbox.get("about_me") is None:
        toolbox.register("about_me", effect="info", asks_for=None, confirm=None, line=LINE.split("\n")[1],
                         handler=lambda step: {"about_me": knowledge(step.get("ask") or "")}, parallel_ok=True,
                         gated_by="SELF_STEPS")


def prompt_block(text):
    """Her lines for these, for the planner, only when the words may be about her: "" for most."""
    return "\n\n" + LINE if WORDS.search(str(text or "")) else ""
