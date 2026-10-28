"""Named helpers (28 October 2026, after Atticus's named agents): "make a helper called Researcher to find the best
budget laptops under 50,000", then "Researcher, look at battery life too" or "tell Researcher to stick to Lenovo",
"how's Researcher doing?", "stop Researcher", "what are my helpers doing?".

A helper is one of her jobs in the background (siri.queue_job, agent.Job) with a name you gave it, kept here by its
task id. What you tell a running one reaches it in its next round (agent.messages reads Job.steer), as Atticus steers
its agents by voice; what it's doing now comes from her activity, as the island shows it. When it's done she says so
by its name (siri._task_result_line)."""
import json
import os
import re
import threading
import time

import activity
import agent
from winplatform import APPDATA_DIR

host = None
PATH = os.path.join(APPDATA_DIR, "helpers.json")
LIVE = ("queued", "running", "waiting_approval")
# words that can't be a helper's name: "make a helper called it", "tell him to ...", her own name
NOT_NAMES = {"it", "this", "that", "him", "her", "them", "me", "my", "the", "a", "an", "one", "someone", "somebody",
             "everyone", "harry", "jev", "jarvis", "you", "yourself", "mum", "mom", "dad", "amma", "appa", "task",
             "job", "helper", "agent", "assistant", "everybody", "all", "who", "what", "us", "we", "i", "and", "or",
             "spotify", "chrome", "youtube", "google", "whatsapp", "telegram", "windows", "notepad"}
_lock = threading.Lock()


def bind(module):
    global host
    host = module


def _load():
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def good_name(name):
    name = str(name or "").strip(" .,!?'\"")
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{1,19}", name)) and name.lower() not in NOT_NAMES


def _row(entry):
    try:
        return host.TASK_STORE.get(entry["task"])
    except Exception:
        return None


def find(name):
    """The helper by that name, alive or finished lately: {"name", "task", "goal", "started"}, or None."""
    with _lock:
        return _load().get(str(name or "").strip().lower())


def names():
    """Every helper's name, the finished ones too, for her to hear them in what you say."""
    with _lock:
        return [e["name"] for e in _load().values()]


def live():
    out = []
    with _lock:
        entries = list(_load().values())
    for e in entries:
        row = _row(e)
        if row and row.get("status") in LIVE:
            out.append((e, row))
    return out


def name_of(task_id):
    """The name of the helper doing task task_id, or None."""
    with _lock:
        for e in _load().values():
            if int(e.get("task") or 0) == int(task_id):
                return e["name"]
    return None


def start(name, goal):
    """A new helper on a job of its own. What she says."""
    name = str(name).strip(" .,!?'\"")
    name = name[:1].upper() + name[1:]
    goal = " ".join(str(goal or "").split()).strip(" .")
    if not good_name(name):
        raise ValueError("That isn't a name I can give a helper")
    if not goal:
        raise ValueError(f"What should {name} do?")
    old = find(name)
    if old:
        row = _row(old)
        if row and row.get("status") in LIVE:
            return f"{name} is still on {old['goal']}. Say stop {name} first, or pick another name."
    task_id = host.queue_job(goal, description=f"{name}: {agent.task_words(goal) or goal}"[:150])
    with _lock:
        data = _load()
        data[name.lower()] = {"name": name, "task": int(task_id), "goal": goal, "started": time.time()}
        # the ones done a day or more ago go
        data = {k: v for k, v in data.items() if time.time() - float(v.get("started") or 0) < 86400 or k == name.lower()}
        _save(data)
    return f"{name}'s on it. Ask me how {name}'s doing any time."


def tell(name, words, named=True):
    """What you said to a helper, for it to follow from its next round. What she says."""
    e = find(name)
    if not e:
        return None
    words = " ".join(str(words or "").split()).strip(" .")
    row = _row(e)
    status = (row or {}).get("status")
    if status not in LIVE:
        result = " ".join(str((row or {}).get("result") or "").split())[:200]
        return f"{e['name']} has finished already." + (f" {result}" if result else "")
    if not words:
        return f"What should I tell {e['name']}?"
    payload = (row or {}).get("payload") or {}  # a job that hasn't started yet is made as run_job would make it
    job = agent.job_for(e["task"], payload.get("goal") or e["goal"], payload.get("words") or e["goal"],
                        payload.get("named", True), payload.get("origin"))
    steer = getattr(job, "steer", None)
    if steer is None:
        steer = job.steer = []
    steer.append(words[:300])
    if named:  # asked of her plainly: what it may type or send widens with your words, as if you'd said them first
        job.words = f"{job.words} {words}"[:1200]
    return f"Okay, I've told {e['name']}."


def doing(e, row):
    """What a helper's doing now, in a few words: its row on the island, else tasks.db's progress."""
    item = next((i for i in activity.snapshot() if i["key"] == f"task:{e['task']}"), None)
    status = row.get("status")
    if status == "waiting_approval":
        return "waiting for your yes" + (f": {item['note']}" if item and item.get("note") and
                                         not item["note"].startswith("Or say") else "")
    if status == "queued":
        return "waiting its turn"
    note = (item or {}).get("note") or row.get("progress") or ""
    if item and item.get("total"):
        note = f"{note}, step {item['step']} of {item['total']}".strip(", ")
    return note.strip() or "working on it"


def status(name):
    e = find(name)
    if not e:
        return None
    row = _row(e) or {}
    if row.get("status") in LIVE:
        return f"{e['name']} is {doing(e, row)}."
    if row.get("status") == "done":
        result = " ".join(str(row.get("result") or "").split())[:240]
        return f"{e['name']} is done." + (f" {result}" if result else "")
    if row.get("status") == "cancelled":
        return f"{e['name']} was stopped."
    return f"{e['name']} didn't finish." + (f" {row.get('error')}" if row.get("error") else "")


def stop(name):
    e = find(name)
    if not e:
        return None
    row = _row(e) or {}
    if row.get("status") not in LIVE:
        return f"{e['name']} isn't working on anything."
    host.stop_task(e["task"])
    return f"Stopped {e['name']}."


def listing():
    going = live()
    if not going:
        return "None of your helpers are working right now."
    parts = [f"{e['name']} is {doing(e, row)}" for e, row in going[:4]]
    return (parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]) + "."
