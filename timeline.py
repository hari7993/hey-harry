"""What you did on this PC, day by day (7 November 2026, the owner's ask: "it needs to tell me what I've done
previously"): each window you were in, when and for how long, its app, its title and its site, a few of its words and
what you clicked in it, as her screen watch read them through agent-desktop (screen_watch.Watcher). Never a
screenshot, and never what you typed. Kept on this PC only, a file a day in %LOCALAPPDATA%\\Hey Harry\\timeline, for
the days in Settings (timeline_days, 7 by the owner's choice) before today: a password, payment or private window
only as one that was open, never its title, site or words. It goes to the model only with words that ask about what
you did (ASKED), in Hermes' untrusted wrapper, as what's on a screen is someone else's words."""
import datetime
import json
import os
import re
import threading
import time

import agent
import settings
import winplatform as win

FOLDER = os.path.join(win.home("LOCALAPPDATA"), "timeline")
SHORTEST = 3.0  # seconds: a window passed through on the way to another (Alt+Tab) isn't kept
WORDS_KEPT = 240  # characters of a window's words kept with its visit
CLICKS_KEPT = 12  # of what was clicked in a window, the first ones
BLOCK_CHARS = 5000  # of a day's visits, at most, for the model: the latest, when there are more
WITH_WORDS = 8  # the latest visits whose words go with them
MERGE_GAP = 90.0  # seconds: the same window again this soon after is one visit, not two
_lock = threading.Lock()
_pruned = [None]  # the day old files were last let go

# Words that ask about what you did, lower case: "what was I doing", "what did I do today", "where was I", "which site
# was I on", "that video I watched", "how long was I on YouTube", "when did I open the report", "my timeline"
_I = r"(?:i|we)"
_THING = r"(?:site|website|page|video|file|document|doc|app|tab|window|link|article|song|mail|email|sheet|" \
         r"spreadsheet|folder|project|chat|thing)"
ASKED = re.compile(
    r"\bwhat (?:was|were) " + _I + r" (?:doing|working on|looking at|reading|watching|listening to|on|up to)\b|"
    r"\bwhat (?:did|have|had) " + _I + r" (?:do|done|been|work(?:ed)? on|open(?:ed)?|watch(?:ed)?|read|"
    r"click(?:ed)?|look(?:ed)? at|visit(?:ed)?|search(?:ed)?|use[d]?|play(?:ed)?|see|seen)\b|"
    r"\bwhat (?:i've|i'd|i have|i had|i was|i did)\b|"
    r"\bwhere (?:was|were) " + _I + r"\b|\bwhere did " + _I + r" (?:leave off|stop|get to|go)\b|"
    r"\b(?:which|what) " + _THING + r" (?:was|were|did|had|have) " + _I + r"\b|"
    r"\b(?:that|the) " + _THING + r" (?:that )?" + _I + r" (?:had|was|opened|watched|read|saw|looked at|visited|"
    r"used|played|closed)\b|"
    r"\bhow long (?:was|were|did|have|had) " + _I + r"\b|"
    r"\bwhen did " + _I + r" (?:open|watch|read|visit|use|start|stop|last|close|leave|see|play|go)\b|"
    r"\b(?:my|the) (?:activity|timeline|screen time)\b|\bwhat was on (?:my|the) screen\b|"
    r"\b(?:remind|tell) me what " + _I + r"\b")
DAYS_OF_WEEK = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WEEK = re.compile(r"\b(?:this|last|past|whole|all) week\b|\bpast (?:few|couple of|\d+) days\b|\bthese days\b")
NOTE = ("# What they did on this PC\n"
        "Read by you from their screen through agent-desktop as they worked, and kept on this PC only: window by "
        "window, when, for how long, the app, its title and site, a few of its words and what they clicked. Never "
        "what they typed, never a picture, and a password, payment or private window only as one that was open. "
        "Answer what they asked from it in a sentence or two, the way a friend who'd been beside them would: what, "
        "when, for how long. If it isn't here, say you didn't see it. Times are theirs (local).")


def days():
    """How many days before today are kept (Settings' timeline_days)."""
    try:
        return max(0, int(settings.get("timeline_days")))
    except (TypeError, ValueError):
        return 7


def path_for(when):
    """Its day's file, for a time."""
    return os.path.join(FOLDER, time.strftime("%Y-%m-%d", time.localtime(when)) + ".jsonl")


def kept(visit):
    """What's kept of a visit: a private one's app and times only, else its title, site, words and what was clicked,
    codes and numbers masked (agent._masked)."""
    row = {"from": round(float(visit["from"]), 1), "to": round(float(visit["to"]), 1),
           "app": str(visit.get("app") or "")[:40]}
    if visit.get("private"):
        return {**row, "private": True}
    words = agent._masked(" ".join(str(visit.get("words") or "").split()))[:WORDS_KEPT]
    clicks = [agent._masked(" ".join(str(c).split()))[:80] for c in visit.get("clicks") or () if c][:CLICKS_KEPT]
    return {**row, "title": agent._masked(" ".join(str(visit.get("title") or "").split()))[:160],
            "site": visit.get("site") or None, **({"words": words} if words else {}),
            **({"clicks": clicks} if clicks else {})}


def add(visit):
    """Keeps a visit of the screen watch's in its day's file, unless it was too short to be one (SHORTEST). True if
    kept. Never raises: a full disk is no reason for her to stop watching."""
    try:
        if float(visit["to"]) - float(visit["from"]) < SHORTEST:
            return False
        row = kept(visit)
        with _lock:
            os.makedirs(FOLDER, exist_ok=True)
            with open(path_for(row["from"]), "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        prune()
        return True
    except Exception as exc:
        print(f"  timeline: couldn't keep it ({exc!r})")
        return False


def prune(today=None):
    """Lets go of the days older than days() before today, once a day."""
    today = today or datetime.date.today()
    if _pruned[0] == today:
        return
    _pruned[0] = today
    oldest = today - datetime.timedelta(days=days())
    try:
        names = os.listdir(FOLDER)
    except OSError:
        return
    for name in names:
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})\.jsonl", name)
        try:
            if m and datetime.date(int(m[1]), int(m[2]), int(m[3])) < oldest:
                os.remove(os.path.join(FOLDER, name))
        except (ValueError, OSError) as exc:
            print(f"  timeline: couldn't let {name} go ({exc!r})")


def load(day):
    """A day's visits (a datetime.date), oldest first; [] for a day with none."""
    try:
        with open(os.path.join(FOLDER, day.isoformat() + ".jsonl"), encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
            float(row["from"]), float(row["to"])
            rows.append(row)
        except (ValueError, KeyError, TypeError):
            continue  # a line cut short when the PC went off
    return sorted(rows, key=lambda r: r["from"])


def which_day(t, now):
    """The day words mean (lower case): a date, or "week" for the days kept. Today unless they say otherwise."""
    today = datetime.date.fromtimestamp(now)
    if WEEK.search(t):
        return "week"
    if re.search(r"\bday before yesterday\b", t):
        return today - datetime.timedelta(days=2)
    if re.search(r"\byesterday\b|\blast night\b", t):
        return today - datetime.timedelta(days=1)
    for i, name in enumerate(DAYS_OF_WEEK):
        if re.search(rf"\b{name}\b", t):
            back = (today.weekday() - i) % 7 or (7 if re.search(rf"\blast {name}\b", t) else 0)
            return today - datetime.timedelta(days=back)
    return today


def merged(rows):
    """Visits in a row to the same window (its app, title and site) within MERGE_GAP of each other, as one."""
    out = []
    for row in rows:
        last = out[-1] if out else None
        if last is not None and row["from"] - last["to"] <= MERGE_GAP and \
                all(last.get(k) == row.get(k) for k in ("app", "title", "site", "private")):
            clicks = (last.get("clicks") or []) + [c for c in row.get("clicks") or () if c not in (last.get("clicks") or [])]
            out[-1] = {**last, "to": max(last["to"], row["to"]), "words": row.get("words") or last.get("words"),
                       **({"clicks": clicks[:CLICKS_KEPT]} if clicks else {})}
        else:
            out.append(dict(row))
    return out


def hour(when):
    """A time as she says it: "9:05 AM"."""
    lt = time.localtime(when)
    return f"{lt.tm_hour % 12 or 12}:{lt.tm_min:02d} {'AM' if lt.tm_hour < 12 else 'PM'}"


def lasted(secs):
    """"40 s", "12 min", "1 h 5 min"."""
    secs = int(secs)
    if secs < 60:
        return f"{secs} s"
    h, m = divmod(secs // 60, 60)
    return f"{h} h {m} min" if h and m else f"{h} h" if h else f"{m} min"


def where(row):
    """A visit's window in a few words: "Chrome: Inbox - Gmail (mail.google.com)", "a private window in Chrome"."""
    if row.get("private"):
        return f"a private window in {row.get('app') or 'an app'}"
    title, site = row.get("title") or "", f" ({row['site']})" if row.get("site") else ""
    return f"{row.get('app') or 'an app'}: {title}{site}" if title else f"{row.get('app') or 'an app'}{site}"


def told(row, words=False):
    """One visit as a line: when, how long, where, and what was clicked (and its words, with words)."""
    line = f"{hour(row['from'])}-{hour(row['to'])} ({lasted(row['to'] - row['from'])}): {where(row)}"
    if row.get("clicks"):
        line += "; clicked " + ", ".join(f'"{c}"' for c in row["clicks"])
    if words and row.get("words"):
        line += f"; on it: {row['words']}"
    return line


def totals(rows):
    """Where the time went in a day: each app's, its sites' with it, most first, as one line."""
    apps, sites = {}, {}
    for row in rows:
        app, spent = row.get("app") or "an app", row["to"] - row["from"]
        apps[app] = apps.get(app, 0) + spent
        if row.get("site"):
            sites.setdefault(app, {})
            sites[app][row["site"]] = sites[app].get(row["site"], 0) + spent
    out = []
    for app, spent in sorted(apps.items(), key=lambda kv: -kv[1])[:8]:
        top = sorted((sites.get(app) or {}).items(), key=lambda kv: -kv[1])[:3]
        out.append(f"{app} {lasted(spent)}" + (" (" + ", ".join(f"{s} {lasted(t)}" for s, t in top) + ")"
                                               if top else ""))
    return ", ".join(out)


def day_lines(rows):
    """A day's visits as lines for the model, the latest ones when they don't all fit BLOCK_CHARS, the last
    WITH_WORDS with their words."""
    rows = merged(rows)
    lines, size = [], 0
    for i, row in enumerate(reversed(rows)):
        line = told(row, words=i < WITH_WORDS)
        if size + len(line) > BLOCK_CHARS:
            lines.append(f"(and {len(rows) - i} earlier)")
            break
        lines.append(line)
        size += len(line) + 1
    return list(reversed(lines))


def prompt_block(text, current=None, now=None):
    """What they did, for the planner, only when the words ask about it (ASKED): the day they mean (which_day) visit
    by visit, with the time, how long, the window and what was clicked, and the window they're in now (current, the
    screen watch's open visit, for today). "" for most requests."""
    t = " ".join(re.sub(r"[^\w' ]+", " ", str(text or "").lower()).split())
    if not ASKED.search(t):
        return ""
    now = time.time() if now is None else now
    day, today = which_day(t, now), datetime.date.fromtimestamp(now)
    if day == "week":
        parts = []
        for back in range(min(days(), 7), -1, -1):
            date = today - datetime.timedelta(days=back)
            rows = load(date)
            if rows:
                parts.append(f"{date.strftime('%A %d %B')}, {hour(rows[0]['from'])} to {hour(rows[-1]['to'])}: "
                             f"{totals(rows)}")
        body = "\n".join(parts) or "Nothing kept for these days."
    else:
        rows = load(day)
        if day == today and current and float(current.get("to", now)) - float(current["from"]) >= SHORTEST:
            rows = rows + [{**kept({**current, "to": now}), "now": True}]
        name = "Today" if day == today else "Yesterday" if day == today - datetime.timedelta(days=1) else \
            day.strftime("%A %d %B")
        if not rows:
            body = f"{name}: nothing kept" + ("" if day >= today - datetime.timedelta(days=days()) else
                                              f" (only the last {days()} days are kept)") + "."
        else:
            body = f"{name} ({day.isoformat()}), where the time went: {totals(rows)}\n" + "\n".join(day_lines(rows))
            if rows[-1].get("now"):
                body += "\n(The last one is the window in front now.)"
    return "\n\n" + NOTE + "\n" + agent.wrapped("screen", body)
