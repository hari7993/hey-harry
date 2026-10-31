"""Coding agents in her island (31 October 2026, the owner's ask, after Glance's notch, which has Claude Code, Codex and
Cursor in it): through each one's own hooks, Claude Code and Codex ask her island before something they need your OK
for, Approve or Deny there; they say when they're waiting on you and when they're done, and show the command they're
running, as Glance's Terminal does. Cursor and Kiro say when they're done (Kiro its commands too), never ask: Cursor's
one hook for that comes for every command, not only those it would ask about, and its "ask" was found to let them
run (its forum, 2026); Kiro's says nothing of allowing.

Each runs this file for a hook (python coding_agents.py <agent>, its words on stdin). A question is a small file in
%LOCALAPPDATA%\\Hey Harry\\agents, and the answer another beside it, written by the island's Agents plugin
(island_plugins.Agents); with her not running (no "alive" touched in the last ALIVE_FOR seconds), or no answer in
WAIT seconds, it says nothing, and the agent asks you itself, as it would without her. Nothing leaves the PC.

Off until you turn Coding agents on in the Island tab, which adds the hooks to the settings of each of these that's on
this PC (AGENTS: Claude Code's settings.json, Codex's hooks.json, Cursor's hooks.json, a file of Kiro's own), a copy
of each kept first as .harry-backup; off again takes them out. Codex runs a new hook only once you've trusted it
(/hooks in Codex). Only the standard library here: the agents wait on it."""
import json
import os
import sys
import threading
import time
import uuid

ALIVE_FOR, WAIT = 5.0, 110.0  # seconds: how fresh her island's mark must be, and how long a question waits
HERE = os.path.abspath(__file__)
NAMES = {"claude": "Claude", "codex": "Codex", "cursor": "Cursor", "kiro": "Kiro"}
# each agent: its folder in your home (only an agent that has one is connected), its hooks file in it, how that file's
# laid out, and the hooks put in it
AGENTS = {
    "claude": (".claude", "settings.json", "claude", ("PermissionRequest", "Notification", "Stop", "PreToolUse",
                                                       "PostToolUse")),
    "codex": (".codex", "hooks.json", "claude", ("PermissionRequest", "Stop", "PreToolUse", "PostToolUse")),
    "cursor": (".cursor", "hooks.json", "cursor", ("stop", "afterShellExecution")),
    "kiro": (".kiro", os.path.join("hooks", "harry-island.json"), "kiro", ("PreToolUse", "Stop")),
}
SHELL_TOOLS = ("Bash", "execute_bash", "shell", "executeBash")  # what each calls running a command


def folder():
    """Where the questions and answers go, made if it isn't there."""
    path = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Hey Harry", "agents")
    os.makedirs(path, exist_ok=True)
    return path


def _write(path, data, tries=10):
    """data written whole: a file of its own first, then moved over path, again a moment later while the other side
    has it open (Windows won't replace a file being read: the hook and the island read and write these at once)."""
    tmp = f"{path}.{os.getpid()}-{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    for i in range(tries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.02)
    try:
        os.remove(tmp)
    except OSError:
        pass


def _read(path, tries=1):
    """What's in the JSON file at path, or None. tries: for a file that's there, read again a moment later when it
    couldn't be read, as alive.json can't be for an instant while the island replaces it (_write), and a hook took
    her for not running (31 October 2026, one test run in three)."""
    for i in range(tries):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            if i + 1 < tries:
                time.sleep(0.02)
    return None


def touch():
    """Her island's mark that it's there to answer (the Agents plugin, each look)."""
    _write(os.path.join(folder(), "alive.json"), {"at": time.time()})


def alive(now=None):
    got = _read(os.path.join(folder(), "alive.json"), tries=5)
    return bool(got) and (now or time.time()) - float(got.get("at") or 0) < ALIVE_FOR


def what_of(event, agent="claude"):
    """A hook's words as the island says them: {"agent", "project", "tool", "command"}."""
    tool = str(event.get("tool_name") or "")
    given = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    command = event.get("command") or given.get("command") or given.get("file_path") or given.get("url") or \
        given.get("pattern") or ""
    if not command and given:
        command = json.dumps(given)[:200]
    roots = event.get("workspace_roots") if isinstance(event.get("workspace_roots"), list) else []
    where = str(event.get("cwd") or (roots[0] if roots else "")).rstrip("\\/")
    name = NAMES.get(agent, "Claude")
    return {"agent": name, "project": os.path.basename(where) or name, "tool": tool or "Shell",
            "command": " ".join(str(command).split())[:300]}


def ask(event, wait=WAIT, step=0.2, agent="claude"):
    """A question for her island, and its answer: True to allow, False to deny, None for none (the agent asks)."""
    qid = uuid.uuid4().hex[:12]
    base = os.path.join(folder(), qid)
    _write(base + ".ask.json", dict(what_of(event, agent), id=qid, at=time.time()))
    end = time.time() + wait
    try:
        while time.time() < end:
            got = _read(base + ".answer.json")
            if got is not None:
                return bool(got.get("allow"))
            if not alive():
                return None
            time.sleep(step)
        return None
    finally:
        for tail in (".ask.json", ".answer.json"):
            try:
                os.remove(base + tail)
            except OSError:
                pass


def questions():
    """The questions waiting on her island, oldest first."""
    out = []
    for name in sorted(os.listdir(folder())):
        if name.endswith(".ask.json"):
            got = _read(os.path.join(folder(), name))
            if isinstance(got, dict) and got.get("id"):
                out.append(got)
    return sorted(out, key=lambda q: q.get("at") or 0)


def answer(qid, allow):
    """Her island's answer to question qid."""
    if qid and all(c.isalnum() for c in str(qid)):
        _write(os.path.join(folder(), f"{qid}.answer.json"), {"allow": bool(allow)})


def note(kind, event, agent="claude"):
    """Something to say for a moment, or what's running: kind "waiting", "done", "running" or "ran"."""
    _write(os.path.join(folder(), f"{time.time():.6f}-{uuid.uuid4().hex[:6]}.note.json"),
           dict(what_of(event, agent), kind=kind, message=str(event.get("message") or "")[:200], at=time.time(),
                session=f"{agent}:{str(event.get('session_id') or event.get('conversation_id') or '')[:40]}"))


def notes():
    """What the hooks said since the last look, oldest first, each taken once."""
    out = []
    for name in sorted(os.listdir(folder())):
        if name.endswith(".note.json"):
            path = os.path.join(folder(), name)
            got = _read(path)
            try:
                os.remove(path)
            except OSError:
                pass
            if isinstance(got, dict):
                out.append(got)
    return out


def main(stdin=None, stdout=None, argv=None):
    """An agent's hook: its words in, an answer out only for a question her island answered. A stop says {} to
    Codex and Cursor, which want JSON from it; Cursor's other hooks are only told of."""
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    argv = sys.argv[1:] if argv is None else argv
    agent = argv[0] if argv and argv[0] in AGENTS else "claude"
    try:
        event = json.loads(stdin.read() or "{}")
    except ValueError:
        return 0
    name = str(event.get("hook_event_name") or "")
    if name.lower() == "stop" and agent in ("codex", "cursor"):
        stdout.write("{}")
    if not alive():  # she isn't running: the agent goes on as it would without her
        return 0
    shell = event.get("tool_name") in SHELL_TOOLS
    if name == "PermissionRequest" and agent in ("claude", "codex"):
        allow = ask(event, agent=agent)
        if allow is not None:
            decision = {"behavior": "allow"} if allow else {"behavior": "deny",
                                                            "message": "Denied from Harry's island."}
            stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                                            "decision": decision}}))
    elif name == "Notification":
        note("waiting", event, agent)
    elif name.lower() == "stop":
        note("done", event, agent)
    elif name == "PreToolUse" and shell:
        note("running", event, agent)
    elif (name == "PostToolUse" and shell) or name == "afterShellExecution":
        note("ran", event, agent)
    return 0


# --------------------------------------------------------------------------- each agent's settings
def settings_path(agent):
    """The file agent's hooks go in; under her tests (HEYHARRY_TESTING) one in their own temp folder, never yours."""
    home, name = AGENTS[agent][:2]
    if os.getenv("HEYHARRY_TESTING"):
        return os.path.join(folder(), f"{agent}-settings-test.json")
    return os.path.join(os.path.expanduser("~"), home, name)


def installed(agent):
    """True if agent is on this PC: its folder in your home is there (always, under the tests)."""
    return bool(os.getenv("HEYHARRY_TESTING")) or os.path.isdir(os.path.join(os.path.expanduser("~"), AGENTS[agent][0]))


def command(agent="claude"):
    """How agent runs this file: her own Python (python.exe, as pythonw.exe may have no stdout to answer on)."""
    return f'"{os.path.join(os.path.dirname(HERE), ".venv", "Scripts", "python.exe")}" "{HERE}" {agent}'


def _ours(hook):
    if not isinstance(hook, dict):
        return False
    action = hook.get("action") if isinstance(hook.get("action"), dict) else hook
    return "coding_agents.py" in str(action.get("command") or "")


def connected(agent="claude", path=None):
    got = _read(path or settings_path(agent)) or {}
    hooks = got.get("hooks")
    if AGENTS[agent][2] == "kiro":
        return any(_ours(h) for h in hooks or [])
    entries = [e for groups in (hooks or {}).values() if isinstance(groups, list) for e in groups]
    if AGENTS[agent][2] == "cursor":
        return any(_ours(e) for e in entries)
    return any(_ours(h) for g in entries if isinstance(g, dict) for h in g.get("hooks") or [])


def _hooks(agent, on, got):
    """got, the agent's settings, with her hooks taken out and, if on, put in again: (it, True if it changed)."""
    style, events = AGENTS[agent][2:]
    changed = False
    if style == "kiro":  # a file of her own: only hers in it
        if not on:
            return None, any(_ours(h) for h in got.get("hooks") or [])
        entries = [{"name": f"harry-island-{e.lower()}", "trigger": e, "action": {"type": "command",
                                                                                 "command": command(agent)},
                    "timeout": 10, "enabled": True} for e in events]
        return {"version": "v1", "hooks": entries}, True
    hooks = got.setdefault("hooks", {})
    if style == "cursor":
        got.setdefault("version", 1)
    for name in events:
        groups = [g for g in hooks.get(name) or [] if isinstance(g, dict)]
        if style == "cursor":
            kept = [g for g in groups if not _ours(g)]
            changed |= len(kept) != len(groups)
            if on:
                kept.append({"command": command(agent)})
                changed = True
        else:
            kept = []
            for g in groups:
                mine = [h for h in g.get("hooks") or [] if _ours(h)]
                if mine:
                    changed = True
                    rest = [h for h in g.get("hooks") or [] if not _ours(h)]
                    if rest:
                        kept.append(dict(g, hooks=rest))
                else:
                    kept.append(g)
            if on:
                entry = {"type": "command", "command": command(agent),
                         "timeout": int(WAIT) + 10 if name == "PermissionRequest" else 10}
                kept.append({"matcher": "Bash", "hooks": [entry]} if name in ("PreToolUse", "PostToolUse") else
                            {"matcher": "", "hooks": [entry]} if name == "PermissionRequest" else {"hooks": [entry]})
                changed = True
        if kept:
            hooks[name] = kept
        else:
            hooks.pop(name, None)
    if not hooks:
        got.pop("hooks", None)
    return got, changed


def connect(on, path=None, agent="claude"):
    """Her hooks put in agent's settings (on), or taken out, keeping everything else there as it was and a copy of it
    from before. True if it changed."""
    path = path or settings_path(agent)
    got = _read(path)
    if got is None and os.path.exists(path):
        raise ValueError(f"{NAMES[agent]}'s {os.path.basename(path)} couldn't be read; left as it is")
    got, changed = _hooks(agent, on, got or {})
    if not changed:
        return False
    if got is None:  # Kiro's file of hers, gone
        try:
            os.remove(path)
        except OSError:
            pass
        return True
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and not os.path.exists(path + ".harry-backup"):
        with open(path, encoding="utf-8") as f, open(path + ".harry-backup", "w", encoding="utf-8") as b:
            b.write(f.read())
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(got, f, indent=2)
    os.replace(tmp, path)
    return True


def connect_all(on):
    """Her hooks in, or out of, each agent on this PC: the names of those it was done for."""
    done = []
    for agent in AGENTS:
        if not installed(agent) and on:
            continue
        try:
            if connect(on, agent=agent) or (on and connected(agent)):
                done.append(agent)
        except Exception as exc:
            print(f"  agents: {NAMES[agent]}'s hooks not {'put in' if on else 'taken out'} ({exc!r})")
    return done


if __name__ == "__main__":
    sys.exit(main())
