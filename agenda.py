"""Her calendar (28 October 2026): "what's on my calendar tomorrow?", "add lunch with Sam on Friday at
1", "move my 3 PM to 4", "cancel the dentist", "am I free at 5?", "what's my next meeting?", and a word from her before
each thing starts.

Your events are kept on this PC, in %APPDATA%\\Hey Harry\\calendar.json. A Google or Outlook calendar can be read too,
by its private iCal address (in Google Calendar: Settings, your calendar, "Secret address in iCal format"), typed in her
box or sent from your phone as "add my calendar https://...": read only, fetched every 10 minutes and kept for when
you're offline, the address never shown to a model or put in her log. Windows' own calendar store is only open to
packaged apps and Outlook's to classic Outlook, so the iCal address is the way in for both. One of those events is
changed where it lives: she opens that day in Google Calendar, or a new event filled in ("put it in my Google
calendar"), for you to save.

Moving or cancelling an event of hers is read back and asked about first."""
import calendar as _cal
import datetime as dt
import hashlib
import json
import os
import re
import threading
import time
from urllib.parse import quote, urlsplit

from winplatform import APPDATA_DIR

PATH = os.path.join(APPDATA_DIR, "calendar.json")
FEED_DIR = os.path.join(APPDATA_DIR, "calendar_feeds")
FEED_EVERY = 600.0  # seconds a fetched feed counts
FEED_MOST = 16 * 1024 * 1024  # characters of a feed read at most: years of a busy calendar are a few MB
REMIND = 10  # minutes before a timed event she says it's coming
DEFAULT_MINUTES = 60
_lock = threading.RLock()
_feeds = {}  # url: (when fetched, parsed events)
_failed = set()  # the feeds that couldn't be read last time, with nothing kept from before
LAST = {"event": None, "at": 0.0}  # the event she last spoke of, for "move it to 4"

MONTHS = {m: i for i, names in enumerate(((), ("january", "jan"), ("february", "feb"), ("march", "mar"),
                                          ("april", "apr"), ("may",), ("june", "jun"), ("july", "jul"),
                                          ("august", "aug"), ("september", "sep", "sept"), ("october", "oct"),
                                          ("november", "nov"), ("december", "dec"))) for m in names}
WEEKDAYS = {w: i for i, names in enumerate((("monday", "mon"), ("tuesday", "tue", "tues"), ("wednesday", "wed"),
                                            ("thursday", "thu", "thur", "thurs"), ("friday", "fri"),
                                            ("saturday", "sat"), ("sunday", "sun"))) for w in names}
HOURS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12}
MINUTE_WORDS = {"fifteen": 15, "thirty": 30, "forty five": 45, "forty-five": 45, "o five": 5, "ten": 10, "twenty": 20}
PARTS = {"morning": 9, "afternoon": 14, "evening": 18, "tonight": 20, "night": 20, "lunchtime": 13, "lunch time": 13}
_H = r"(?:\d{1,2}|" + "|".join(HOURS) + r")"
_M = r"(?:[0-5]\d|" + "|".join(sorted(MINUTE_WORDS, key=len, reverse=True)) + r")"
AMPM = r"(?:a\.?\s?m\.?|p\.?\s?m\.?)"
# whole names only: "sat" and "wed" are words too ("I sat down")
WD = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
MON = r"(?:" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")"
ORD = r"(?:\d{1,2})(?:st|nd|rd|th)?"
# A time: "at 3", "3 pm", "15:30", "at half past 4", "quarter to 5", "noon"; a range: "from 2 to 3", "2-3 pm"
CLOCK = (rf"(?:(?:half|quarter) past {_H}|quarter to {_H}|noon|midday|midnight|"
         rf"{_H}(?:[:.]{_M}| {_M}(?= ?{AMPM}))? ?{AMPM}|\d{{1,2}}[:.][0-5]\d)")
TIME = re.compile(rf"\b(?:(?:at|@|around|by|from|for|starting at) )?(?P<t>{CLOCK})\b|"
                  rf"\b(?:at|@|around|by|starting at) (?P<b>{_H}(?:[:. ]{_M})?)\b(?! ?(?:{MON}|days?|weeks?|hours?|"
                  rf"minutes?|mins?|people|of)\b)")
SPAN = re.compile(rf"\b(?:from |between )?(?P<a>{_H}(?:[:.]{_M})?) ?(?P<ap1>{AMPM})? ?(?:-|to|till|until|and|–) "
                  rf"?(?P<z>{_H}(?:[:.]{_M})?) ?(?P<ap2>{AMPM})?\b")
LENGTH = re.compile(r"\bfor (?:(?P<n>\d+(?:\.\d+)?|an?|one|two|three|half an?)(?: and a half)? ?(?P<u>hours?|hrs?|h|"
                    r"minutes?|mins?|m)\b|(?P<half>half an hour)|(?P<hr>an hour and a half))")
DAY = re.compile(rf"\b(?:(?P<rel>today|tonight|tomorrow|day after tomorrow|yesterday)|"
                 rf"(?:on )?(?:(?P<which>this|next|coming) )?(?P<wd>{WD})(?: (?:the )?(?P<wdd>{ORD}))?|"
                 rf"(?:on )?(?:the )?(?P<d1>{ORD})(?: of)? (?P<m1>{MON})(?: (?P<y1>\d{{4}}))?|"
                 rf"(?:on )?(?P<m2>{MON}) (?:the )?(?P<d2>{ORD})(?:,? (?P<y2>\d{{4}}))?|"
                 rf"(?:on )?the (?P<d3>\d{{1,2}}(?:st|nd|rd|th))|"
                 rf"(?:on )?(?P<dd>\d{{1,2}})[/-](?P<mm>\d{{1,2}})(?:[/-](?P<yy>\d{{2,4}}))?|"
                 rf"in (?P<n>\d+|a|one|two|three) (?P<u>days?|weeks?))\b")
# a part of the day: "night" only with words round it, or "movie night" would lose its night
PART = re.compile(r"\b(?:(?:in the|this|tomorrow|at|on \w+day) (?P<p>morning|afternoon|evening|night|lunch ?time)|"
                  r"(?P<q>tonight)|(?P<r>morning|afternoon|evening|lunchtime))\b")
LEAD = re.compile(r"^(?:please |can you |could you |hey |ok |okay )*(?:add|put|create|make|schedule|book|set up|"
                  r"plan|pencil in|note|save|block(?: out)?|mark|log)(?: me)?(?: (?:a|an|the|my))?"
                  r"(?: (?:new )?(?:event|entry|calendar event|item)(?: (?:called|named|for|about))?)?[: ]+", re.I)
TRAIL = re.compile(r"(?:,? ?(?:to|on|in|into|onto|for) (?:my |the )?(?:google |outlook |harry's |own )?"
                   r"(?:calendar|diary|schedule|agenda)(?: please)?|,? please)$", re.I)
WORDS_GOOGLE = re.compile(r"\bgoogle\b", re.I)


# --------------------------------------------------------------------------- her store
def _load():
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("events", [])
            data.setdefault("feeds", [])
            data.setdefault("told", {})
            return data
    except (OSError, ValueError):
        pass
    return {"events": [], "feeds": [], "told": {}}


def _save(data):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%M")


def _dt(text):
    try:
        return dt.datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None


def add(title, start, end=None, all_day=False, where="", remind=REMIND):
    """A new event of hers. start and end are local datetimes; all-day events run from midnight to midnight."""
    title = " ".join(str(title or "").split())[:120]
    if not title:
        raise ValueError("I didn't catch what to call it")
    if all_day:
        start = dt.datetime.combine(start.date(), dt.time())
        end = end if end and end > start else start + dt.timedelta(days=1)
    else:
        end = end if end and end > start else start + dt.timedelta(minutes=DEFAULT_MINUTES)
    event = {"id": os.urandom(4).hex(), "title": title, "start": _iso(start), "end": _iso(end),
             "all_day": bool(all_day), "where": " ".join(str(where or "").split())[:120],
             "remind": int(remind), "created": time.time()}
    with _lock:
        data = _load()
        data["events"].append(event)
        _save(data)
    LAST.update(event=_occurrence(event), at=time.time())
    return _occurrence(event)


def change(event_id, start=None, end=None, title=None):
    """One of her events moved or renamed. The occurrence as it is now; LookupError if it's gone."""
    with _lock:
        data = _load()
        for e in data["events"]:
            if e["id"] == event_id:
                old_s, old_e = _dt(e["start"]), _dt(e["end"])
                if start is not None:
                    length = (old_e - old_s) if old_s and old_e else dt.timedelta(minutes=DEFAULT_MINUTES)
                    e["start"], e["end"] = _iso(start), _iso(end or start + length)
                if title:
                    e["title"] = " ".join(str(title).split())[:120]
                data["told"] = {k: v for k, v in data["told"].items() if not k.startswith(event_id)}
                _save(data)
                LAST.update(event=_occurrence(e), at=time.time())
                return _occurrence(e)
    raise LookupError("That event isn't in your calendar any more")


def remove(event_id):
    with _lock:
        data = _load()
        kept = [e for e in data["events"] if e["id"] != event_id]
        if len(kept) == len(data["events"]):
            raise LookupError("That event isn't in your calendar any more")
        data["events"] = kept
        _save(data)
    LAST.update(event=None, at=0.0)


def _occurrence(e, source="harry"):
    start, end = _dt(e.get("start")), _dt(e.get("end"))
    return {"id": e.get("id"), "title": e.get("title") or "(no title)", "start": start, "end": end or start,
            "all_day": bool(e.get("all_day")), "where": e.get("where") or "", "source": source,
            "remind": int(e.get("remind", REMIND) if e.get("remind") is not None else REMIND),
            "key": f"{e.get('id')}@{e.get('start')}"}


# --------------------------------------------------------------------------- calendars from elsewhere (iCal)
def feeds():
    with _lock:
        return [dict(f) for f in _load()["feeds"]]


def clean_url(url):
    """An iCal address as https, or None if it isn't one: webcal:// is how calendars hand them out."""
    url = str(url or "").strip().strip("<>\"'")
    url = re.sub(r"^webcals?://", "https://", url, flags=re.I)
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("https", "http") or not parts.netloc:
        return None
    return url


def feed_name(url):
    host = urlsplit(url).netloc.lower()
    return "Google" if "google" in host else "Outlook" if ("outlook" in host or "office" in host or "live" in host) \
        else "iCloud" if "icloud" in host else host.split(":")[0]


def add_feed(url, fetch=None):
    """Reads a calendar at an iCal address, then keeps the address. The calendar's name, or ValueError."""
    url = clean_url(url)
    if not url:
        raise ValueError("That isn't a calendar address")
    events = _fetch(url, fetch, force=True)
    name = feed_name(url)
    with _lock:
        data = _load()
        if not any(f["url"] == url for f in data["feeds"]):
            data["feeds"].append({"url": url, "name": name})
            _save(data)
    return name, len(events)


def remove_feeds():
    with _lock:
        data = _load()
        n = len(data["feeds"])
        data["feeds"] = []
        _save(data)
    _feeds.clear()
    return n


def _feed_file(url):
    return os.path.join(FEED_DIR, hashlib.sha1(url.encode()).hexdigest()[:16] + ".ics")


def _fetch(url, fetch=None, force=False):
    """A feed's events, from memory if it was read in the last FEED_EVERY seconds, else fetched, else as last kept."""
    now = time.time()
    got = _feeds.get(url)
    if got and not force and now - got[0] < FEED_EVERY:
        return got[1]
    text = None
    try:
        if fetch is None:
            import requests
            r = requests.get(url, timeout=10, headers={"User-Agent": "HeyHarry/1.0"})
            r.raise_for_status()
            text = r.text
        else:
            text = fetch(url)
        if len(text) > FEED_MOST:
            raise ValueError("That calendar is too big to read")
        if "BEGIN:VCALENDAR" not in text[:2000].upper():
            raise ValueError("That address didn't give a calendar")
        os.makedirs(FEED_DIR, exist_ok=True)
        with open(_feed_file(url), "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as exc:
        print(f"  calendar {feed_name(url)}: {exc.__class__.__name__}")  # never the address: it's a password
        if force:
            raise ValueError("I couldn't read that calendar") from exc
        try:
            with open(_feed_file(url), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            _feeds[url] = (now - FEED_EVERY + 60, [])  # try again in a minute
            _failed.add(url)
            return []
    events = parse_ics(text)
    _feeds[url] = (now, events)
    _failed.discard(url)
    return events


def _unfold(text):
    out = []
    for line in re.split(r"\r?\n", text):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        elif line:
            out.append(line)
    return out


def _prop(line):
    """(NAME, {PARAM: value}, value) of one iCal line."""
    quoted, cut = False, None
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == ":" and not quoted:
            cut = i
            break
    if cut is None:
        return line.upper(), {}, ""
    head, value = line[:cut], line[cut + 1:]
    parts = head.split(";")
    params = {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        params[k.upper()] = v.strip('"')
    return parts[0].upper(), params, value


def _text(value):
    return re.sub(r"\\([\\,;nN])", lambda m: "\n" if m[1] in "nN" else m[1], value).strip()


def _offset(text):
    m = re.fullmatch(r"([+-])(\d\d)(\d\d)(\d\d)?", str(text or "").strip())
    if not m:
        return None
    minutes = int(m[2]) * 60 + int(m[3])
    return -minutes if m[1] == "-" else minutes


FIXED_ZONES = {"asia/kolkata": 330, "asia/calcutta": 330, "india standard time": 330, "utc": 0, "etc/utc": 0,
               "gmt": 0, "z": 0, "asia/dubai": 240, "asia/singapore": 480, "asia/tokyo": 540, "asia/shanghai": 480}


def _onset(comp, year):
    """When a zone's STANDARD or DAYLIGHT part starts in a year, as local wall time."""
    start, rule = comp["start"], comp.get("rrule") or {}
    if not rule or rule.get("FREQ") != "YEARLY" or start is None:
        return start
    month = int((rule.get("BYMONTH") or [start.month])[0])
    days = rule.get("BYDAY") or []
    if days:
        m = re.fullmatch(r"([+-]?\d+)?([A-Z]{2})", days[0])
        if m:
            return _nth_weekday(year, month, int(m[1] or 1), "MOTUWETHFRSASU".index(m[2]) // 2,
                                start.hour, start.minute)
    try:
        return start.replace(year=year, month=month)
    except ValueError:
        return None


_NO_ZONEINFO = set()  # zones Python's own database doesn't have here (Windows has none without the tzdata package)


def _zone_minutes(tzid, local, zones):
    """The zone's offset from UTC at a local time, in minutes, or None if it isn't known."""
    if tzid not in _NO_ZONEINFO:
        try:
            import zoneinfo
            off = local.replace(tzinfo=zoneinfo.ZoneInfo(tzid)).utcoffset()
            return int(off.total_seconds() // 60)
        except Exception:
            _NO_ZONEINFO.add(tzid)
    comps = zones.get(tzid)
    if comps:
        best, value = None, None
        for comp in comps:
            for year in (local.year - 1, local.year):
                at = _onset(comp, year)
                if at is not None and at <= local and (best is None or at > best):
                    best, value = at, comp["to"]
        if value is not None:
            return value
        return comps[0]["to"]
    return FIXED_ZONES.get(str(tzid or "").lower())


def _wall(value, params):
    """(an iCal date or date-time as written, all day, how it's read: "date", "utc", "zone" or "floating", the zone)."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        try:
            return dt.datetime.strptime(value[:8], "%Y%m%d"), True, "date", None
        except ValueError:
            return None, True, "date", None
    m = re.fullmatch(r"(\d{8})T(\d{4})(\d\d)?(Z)?", value)
    if not m:
        return None, False, "floating", None
    try:
        wall = dt.datetime.strptime(m[1] + m[2] + (m[3] or "00"), "%Y%m%d%H%M%S")
    except ValueError:
        return None, False, "floating", None
    if m[4]:
        return wall, False, "utc", None
    tzid = params.get("TZID")
    return wall, False, "zone" if tzid else "floating", tzid


def _local(wall, mode, tzid, zones):
    """A wall time in its own zone as this PC's local time: a meeting at 9 in New York is 6:30 PM here in summer,
    7:30 PM in winter, as New York's clocks change."""
    if wall is None:
        return None
    if mode == "utc":
        return wall.replace(tzinfo=dt.timezone.utc).astimezone().replace(tzinfo=None)
    if mode == "zone":
        minutes = _zone_minutes(tzid, wall, zones)
        if minutes is not None:
            return wall.replace(tzinfo=dt.timezone(dt.timedelta(minutes=minutes))).astimezone().replace(tzinfo=None)
    return wall  # floating, or a date: the time where you are


def _when(value, params, zones):
    """(local datetime, all day) for an iCal date or date-time, in this PC's own time zone."""
    wall, all_day, mode, tzid = _wall(value, params)
    return _local(wall, mode, tzid, zones), all_day


def _rrule(value):
    rule = {}
    for part in value.split(";"):
        k, _, v = part.partition("=")
        k = k.upper()
        if k in ("BYDAY", "BYMONTHDAY", "BYMONTH"):
            rule[k] = [x for x in v.upper().split(",") if x]
        elif k:
            rule[k] = v.upper()
    return rule


def parse_ics(text):
    """The events in an iCal file: [{"uid", "title", "start", "end", "all_day", "where", "rrule", "exdates",
    "recurrence_id", "cancelled"}], times as local datetimes."""
    zones, events, stack, cur, comp, tzid = {}, [], [], None, None, None
    raw_events = []
    for line in _unfold(text):
        name, params, value = _prop(line)
        if name == "BEGIN":
            stack.append(value.upper())
            if value.upper() == "VEVENT":
                cur = []
            elif value.upper() in ("STANDARD", "DAYLIGHT") and "VTIMEZONE" in stack:
                comp = {"kind": value.upper(), "start": None, "to": 0, "rrule": None}
            continue
        if name == "END":
            kind = stack.pop() if stack else ""
            if kind == "VEVENT" and cur is not None:
                raw_events.append(cur)
                cur = None
            elif kind in ("STANDARD", "DAYLIGHT") and comp is not None and tzid:
                zones.setdefault(tzid, []).append(comp)
                comp = None
            elif kind == "VTIMEZONE":
                tzid = None
            continue
        top = stack[-1] if stack else ""
        if top == "VTIMEZONE" and name == "TZID":
            tzid = value
        elif top in ("STANDARD", "DAYLIGHT") and comp is not None:
            if name == "DTSTART":
                try:
                    comp["start"] = dt.datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
                except ValueError:
                    pass
            elif name == "TZOFFSETTO":
                comp["to"] = _offset(value) or 0
            elif name == "RRULE":
                comp["rrule"] = _rrule(value)
        elif top == "VEVENT" and cur is not None:
            cur.append((name, params, value))
    for props in raw_events:
        e = {"uid": "", "title": "(no title)", "start": None, "end": None, "all_day": False, "where": "",
             "rrule": None, "exdates": set(), "recurrence_id": None, "cancelled": False, "duration": None,
             "wall": None, "mode": "floating", "tzid": None, "zones": zones}
        for name, params, value in props:
            if name == "UID":
                e["uid"] = value.strip()
            elif name == "SUMMARY":
                e["title"] = _text(value)[:160] or "(no title)"
            elif name == "LOCATION":
                e["where"] = _text(value)[:160]
            elif name == "DTSTART":
                e["wall"], e["all_day"], e["mode"], e["tzid"] = _wall(value, params)
                e["start"] = _local(e["wall"], e["mode"], e["tzid"], zones)
            elif name == "DTEND":
                e["end"], _ = _when(value, params, zones)
            elif name == "DURATION":
                e["duration"] = _duration(value)
            elif name == "RRULE":
                e["rrule"] = _rrule(value)
            elif name == "EXDATE":
                for v in value.split(","):
                    when, _ = _when(v, params, zones)
                    if when is not None:
                        e["exdates"].add(when)
            elif name == "RECURRENCE-ID":
                e["recurrence_id"], _ = _when(value, params, zones)
            elif name == "STATUS" and value.strip().upper() == "CANCELLED":
                e["cancelled"] = True
        if e["start"] is None:
            continue
        if e["end"] is None:
            e["end"] = e["start"] + (e["duration"] or (dt.timedelta(days=1) if e["all_day"] else dt.timedelta(0)))
        events.append(e)
    return events


def _duration(value):
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value.strip())
    if not m:
        return None
    w, d, h, mi, s = (int(x or 0) for x in m.groups()[1:])
    return dt.timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)


def _nth_weekday(year, month, n, weekday, hour=0, minute=0):
    """The nth weekday (0 Monday) of a month, -1 the last; None if there's no such day."""
    days = [d for d in range(1, _cal.monthrange(year, month)[1] + 1) if dt.date(year, month, d).weekday() == weekday]
    try:
        day = days[n - 1] if n > 0 else days[n]
    except IndexError:
        return None
    return dt.datetime(year, month, day, hour, minute)


def _rule_end(rule):
    """An RRULE's UNTIL as local time, a day's UNTIL to the end of that day; None if it has none."""
    if not rule.get("UNTIL"):
        return None
    end, _ = _when(rule["UNTIL"], {}, {})
    if end is not None and len(rule["UNTIL"]) == 8:
        end = end + dt.timedelta(days=1) - dt.timedelta(seconds=1)
    return end


def _starts(e, until):
    """Every start of a repeating event as its own zone's wall time, in order, from its first, up to about until
    (RRULE's common parts: DAILY, WEEKLY, MONTHLY and YEARLY, INTERVAL, COUNT, UNTIL, BYDAY, BYMONTHDAY, BYMONTH).
    Worked out on the wall clock, then made local one by one (expand), so a zone's clocks changing moves them."""
    start, rule = e["wall"] or e["start"], e["rrule"]
    freq, step = rule.get("FREQ"), max(1, int(rule.get("INTERVAL") or 1))
    count = int(rule["COUNT"]) if str(rule.get("COUNT") or "").isdigit() else None
    end = _rule_end(rule)
    until = until + dt.timedelta(days=1)  # wall and local differ by under a day; expand keeps only what's in range
    last = min(until, end + dt.timedelta(days=1)) if end else until
    days = rule.get("BYDAY") or []
    plain_days = sorted({"MOTUWETHFRSASU".index(d[-2:]) // 2 for d in days if d[-2:] in "MOTUWETHFRSASU"})
    months = [int(m) for m in rule.get("BYMONTH") or [] if m.lstrip("-").isdigit()]
    monthdays = [int(m) for m in rule.get("BYMONTHDAY") or [] if m.lstrip("-").isdigit()]
    made, guard = 0, 0

    def take(when):
        nonlocal made
        made += 1
        return when

    if freq == "DAILY":
        k = 0
        if count is None and start < until - dt.timedelta(days=400):  # far in the past: straight to the last year
            k = max(0, ((until - dt.timedelta(days=400)) - start).days // step)
        while guard < 3000:
            guard += 1
            when = start + dt.timedelta(days=k * step)
            k += 1
            if when > last or (count is not None and made >= count):
                return
            if plain_days and when.weekday() not in plain_days:
                continue
            if months and when.month not in months:
                continue
            yield take(when)
    elif freq == "WEEKLY":
        week0 = start - dt.timedelta(days=start.weekday())
        k = 0
        if count is None and start < until - dt.timedelta(days=400):
            k = max(0, ((until - dt.timedelta(days=400)) - start).days // (7 * step))
        wanted = plain_days or [start.weekday()]
        while guard < 3000:
            guard += 1
            week = week0 + dt.timedelta(weeks=k * step)
            k += 1
            if week > last:
                return
            for wd in wanted:
                when = week + dt.timedelta(days=wd)
                if when < start:
                    continue
                if when > last or (count is not None and made >= count):
                    return
                yield take(when)
    elif freq in ("MONTHLY", "YEARLY"):
        k = 0
        while guard < 3000:
            guard += 1
            if freq == "MONTHLY":
                total = start.month - 1 + k * step
                year, mons = start.year + total // 12, [total % 12 + 1]
            else:
                year, mons = start.year + k * step, months or [start.month]
            k += 1
            if dt.datetime(year, mons[0], 1) > last:
                return
            found = []
            for month in mons:
                length = _cal.monthrange(year, month)[1]
                if monthdays:
                    for d in monthdays:
                        d = d if d > 0 else length + 1 + d
                        if 1 <= d <= length:
                            found.append(dt.datetime(year, month, d, start.hour, start.minute))
                elif days:
                    for spec in days:
                        m = re.fullmatch(r"([+-]?\d+)?([A-Z]{2})", spec)
                        if not m:
                            continue
                        wd = "MOTUWETHFRSASU".index(m[2]) // 2
                        if m[1]:
                            got = _nth_weekday(year, month, int(m[1]), wd, start.hour, start.minute)
                            if got:
                                found.append(got)
                        else:
                            found += [dt.datetime(year, month, d, start.hour, start.minute)
                                      for d in range(1, length + 1) if dt.date(year, month, d).weekday() == wd]
                elif start.day <= length:
                    found.append(dt.datetime(year, month, start.day, start.hour, start.minute))
            for when in sorted(found):
                if when < start:
                    continue
                if when > last or (count is not None and made >= count):
                    return
                yield take(when)
    else:
        yield start


def expand(events, a, b):
    """The occurrences of iCal events overlapping a to b, repeats worked out, moved ones in their new place."""
    moved = {(e["uid"], e["recurrence_id"]) for e in events if e["recurrence_id"] is not None}
    out = []
    for e in events:
        if e["cancelled"] and e["recurrence_id"] is None:
            continue
        length = e["end"] - e["start"]
        repeats = bool(e["rrule"]) and e["recurrence_id"] is None
        stop = _rule_end(e["rrule"]) if repeats else None
        if repeats:
            starts = (_local(w, e["mode"], e["tzid"], e["zones"]) for w in _starts(e, b))
        else:
            starts = [e["start"]]
        for s in starts:
            if s is None or (stop is not None and s > stop):
                continue
            if repeats and ((e["uid"], s) in moved or s in e["exdates"]):
                continue
            if e["cancelled"]:
                continue
            if s < b and s + max(length, dt.timedelta(minutes=1)) > a:
                out.append({"id": None, "uid": e["uid"], "title": e["title"], "start": s, "end": s + length,
                            "all_day": e["all_day"], "where": e["where"], "remind": REMIND,
                            "key": f"{e['uid']}@{s.isoformat()}"})
    return out


# --------------------------------------------------------------------------- what's on
def between(a, b, fetch=None):
    """Everything on your calendars from a to b, soonest first: (occurrences, the calendars that couldn't be read)."""
    with _lock:
        data = _load()
    out = []
    for e in data["events"]:
        o = _occurrence(e)
        if o["start"] and o["start"] < b and (o["end"] or o["start"]) > a:
            out.append(o)
    missing = []
    for f in data["feeds"]:
        try:
            events = _fetch(f["url"], fetch)
        except Exception:
            events = []
            _failed.add(f["url"])
        if f["url"] in _failed:
            missing.append(f.get("name") or "a calendar")
        for o in expand(events, a, b):
            o["source"] = f.get("name") or "Google"
            out.append(o)
    out.sort(key=lambda o: (o["start"], not o["all_day"], o["title"].lower()))
    return out, missing


def next_up(now=None, days=30, fetch=None):
    now = now or dt.datetime.now()
    found, _ = between(now, now + dt.timedelta(days=days), fetch)
    later = [o for o in found if not o["all_day"] and o["start"] >= now - dt.timedelta(minutes=5)]
    return later[0] if later else (found[0] if found else None)


# --------------------------------------------------------------------------- words to times
def _hour(h, m, ap, text, default_pm=True):
    """A clock time as 24-hour (hour, minute): "1" alone for an event is 1 PM, "8" is 8 AM, unless the words say
    morning or evening."""
    raw = str(h)
    h = HOURS.get(raw, None) if not raw.isdigit() else int(raw)
    if h is None or h > 23:
        return None
    ap = (ap or "").replace(".", "").replace(" ", "").lower()
    if not ap and raw.isdigit() and len(raw) == 2 and raw.startswith("0"):
        return h, m  # "06:15" is written the 24-hour way: the morning
    if ap:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if ap == "pm" else 0)
    elif h <= 12:
        if re.search(r"\bmorning\b", text):
            h = 0 if h == 12 else h
        elif re.search(r"\b(?:afternoon|evening|tonight|night)\b", text):
            h = h if h == 12 else h + 12
        elif default_pm and 1 <= h <= 7:
            h += 12
    return h, m


def _minutes(m):
    if m is None:
        return 0
    m = str(m).strip()
    return int(m) if m.isdigit() else MINUTE_WORDS.get(m, 0)


def _clock(found, text):
    """(hour, minute) for a TIME match."""
    groups = found.groupdict()
    t = (groups.get("t") or groups.get("b") or "").lower()
    if t in ("noon", "midday"):
        return 12, 0
    if t == "midnight":
        return 0, 0
    m = re.fullmatch(rf"(?P<k>half|quarter) past (?P<h>{_H})", t)
    if m:
        got = _hour(m["h"], 0, "", text)
        return (got[0], 30 if m["k"] == "half" else 15) if got else None
    m = re.fullmatch(rf"quarter to (?P<h>{_H})", t)
    if m:
        got = _hour(m["h"], 0, "", text)
        return ((got[0] - 1) % 24, 45) if got else None
    m = re.fullmatch(rf"(?P<h>{_H})(?:[:. ](?P<m>{_M}))? ?(?P<ap>{AMPM})?", t)
    if not m:
        return None
    return _hour(m["h"], _minutes(m["m"]), m["ap"], text)


def _day(found, now):
    """The date a DAY match means, or None."""
    today = now.date()
    if found["rel"]:
        rel = found["rel"]
        return today + dt.timedelta(days={"today": 0, "tonight": 0, "tomorrow": 1, "day after tomorrow": 2,
                                          "yesterday": -1}[rel])
    if found["wd"]:
        wd = WEEKDAYS[found["wd"]]
        ahead = (wd - today.weekday()) % 7
        if found["which"] == "next":
            monday_next = today + dt.timedelta(days=7 - today.weekday())
            return monday_next + dt.timedelta(days=wd)
        if ahead == 0 and found["which"] != "this":
            ahead = 7
        return today + dt.timedelta(days=ahead)
    for d, m, y in (("d1", "m1", "y1"), ("d2", "m2", "y2")):
        if found[d] and found[m]:
            return _date(int(re.match(r"\d+", found[d])[0]), MONTHS[found[m]], found[y], today)
    if found["d3"]:
        day = int(re.match(r"\d+", found["d3"])[0])
        month, year = today.month, today.year
        if day < today.day:
            month, year = (1, year + 1) if month == 12 else (month + 1, year)
        return _date(day, month, str(year), today)
    if found["dd"]:  # 5/11: the 5th of November, as dates are written here
        return _date(int(found["dd"]), int(found["mm"]), found["yy"], today)
    if found["n"]:
        n = {"a": 1, "one": 1, "two": 2, "three": 3}.get(found["n"], None) or int(found["n"])
        return today + dt.timedelta(days=n * (7 if found["u"].startswith("week") else 1))
    return None


def _date(day, month, year, today):
    try:
        if year:
            y = int(year)
            y = y + 2000 if y < 100 else y
            return dt.date(y, month, day)
        got = dt.date(today.year, month, day)
        return got if got >= today else dt.date(today.year + 1, month, day)
    except ValueError:
        return None


def when(text, now=None, default_pm=True):
    """What a request says about time: {"start", "end", "all_day", "date", "clock", "spans"}, spans being where those
    words are in text, or None if it says neither a day nor a time."""
    now = now or dt.datetime.now()
    low = re.sub(r"o'?\s?clock", lambda m: " " * len(m[0]), text.lower())  # "3 o'clock" is 3, same length kept
    spans, day, clock, end_clock, length = [], None, None, None, None

    def free(span):  # not inside words already taken: "2-3 pm" isn't the 2nd of March too
        return all(span[1] <= a or span[0] >= b for a, b in spans)
    m = SPAN.search(low)
    if m and (m["ap1"] or m["ap2"] or re.search(r"\b(?:from|between)\b", low[max(0, m.start() - 8):m.start() + 8])):
        a = _hour(re.match(rf"{_H}", m["a"])[0], _minutes((re.split(r"[:.]", m["a"]) + [None])[1]),
                  m["ap1"] or m["ap2"], low, default_pm)
        z = _hour(re.match(rf"{_H}", m["z"])[0], _minutes((re.split(r"[:.]", m["z"]) + [None])[1]), m["ap2"], low,
                  default_pm)
        if a and z:
            if not m["ap1"] and m["ap2"] and a[0] > z[0]:  # "11 to 1 pm" is 11 AM to 1 PM
                a = (a[0] - 12, a[1]) if a[0] >= 12 else a
            clock, end_clock = a, z
            spans.append(m.span())
    if clock is None:
        for m in TIME.finditer(low):
            got = _clock(m, low) if free(m.span()) else None
            if got:
                clock = got
                spans.append(m.span())
                break
    m = LENGTH.search(low)
    if m and free(m.span()):
        if m["half"]:
            length = 30
        elif m["hr"]:
            length = 90
        else:
            n = m["n"] or "1"
            n = 0.5 if n.startswith("half") else 1 if n in ("a", "an", "one") else 2 if n == "two" else \
                3 if n == "three" else float(n)
            if re.search(r"and a half", m[0]):
                n += 0.5
            length = int(n * (60 if m["u"][0] == "h" else 1))
        spans.append(m.span())
    for m in DAY.finditer(low):
        got = _day(m, now) if free(m.span()) else None
        if got:
            day = got
            spans.append(m.span())
            break
    part = PART.search(low)
    if part and clock is None:
        name = (part["p"] or part["q"] or part["r"]).replace(" ", "")
        clock = (PARTS.get(name, 9), 0)
    if part and free(part.span()):  # "at 7 in the evening": its words go from the title either way
        spans.append(part.span())
    if day is None and clock is None:
        return None
    all_day = clock is None
    if day is None:  # a time alone is today's, or tomorrow's once it's gone
        day = now.date()
        if dt.datetime.combine(day, dt.time(*clock)) < now - dt.timedelta(minutes=5):
            day += dt.timedelta(days=1)
    start = dt.datetime.combine(day, dt.time(*(clock or (0, 0))))
    end = None
    if end_clock:
        end = dt.datetime.combine(day, dt.time(*end_clock))
        if end <= start:
            end += dt.timedelta(days=1)
    elif length:
        end = start + dt.timedelta(minutes=length)
    return {"start": start, "end": end, "all_day": all_day, "date": day, "clock": clock, "spans": spans}


def title_of(text, spans):
    """What an event's called: the words left once its time and the asking are taken out."""
    keep = list(text)
    for a, b in spans:
        for i in range(a, min(b, len(keep))):
            keep[i] = " "
    t = " ".join("".join(keep).split())
    for _ in range(3):
        t = LEAD.sub("", t).strip(" ,.")
        t = TRAIL.sub("", t).strip(" ,.")
    t = re.sub(r"\b(?:on|at|for|from|by|this|in the|the|to)$", "", t.strip(" ,.")).strip(" ,.")
    t = re.sub(r"^(?:for|to|about|called|named)\b", "", t).strip(" ,.")
    return (t[:1].upper() + t[1:]) if t else ""


def parse_event(text, now=None):
    """{"title", "start", "end", "all_day"} for "add lunch with Sam tomorrow at 1", or None."""
    got = when(text, now)
    if got is None:
        return None
    title = title_of(text, got["spans"])
    if not title or len(title) > 120:
        return None
    return {"title": title, "start": got["start"], "end": got["end"], "all_day": got["all_day"]}


def day_range(text, now=None):
    """(start, end, how she says it) for the day or days a question is about: "tomorrow", "on Friday", "this week",
    "next week", "this weekend"; today by default."""
    now = now or dt.datetime.now()
    low = text.lower()
    today = dt.datetime.combine(now.date(), dt.time())
    if re.search(r"\bnext week\b", low):
        a = today + dt.timedelta(days=7 - today.weekday())
        return a, a + dt.timedelta(days=7), "next week"
    if re.search(r"\b(?:this|the rest of the) week\b", low):
        return now, today + dt.timedelta(days=7 - today.weekday()), "this week"
    if re.search(r"\b(?:this |the )?weekend\b", low):
        sat = today + dt.timedelta(days=(5 - today.weekday()) % 7)
        return max(now, sat), sat + dt.timedelta(days=2), "this weekend"
    m = DAY.search(low)
    if m:
        d = _day(m, now)
        if d:
            a = dt.datetime.combine(d, dt.time())
            return (max(now, a) if d == now.date() else a), a + dt.timedelta(days=1), _day_said(a, now)
    if re.search(r"\btonight\b", low):
        return now, today + dt.timedelta(days=1), "tonight"
    return now, today + dt.timedelta(days=1), "today"


# --------------------------------------------------------------------------- as she says it
def _clock_said(d):
    h = d.hour % 12 or 12
    ap = "AM" if d.hour < 12 else "PM"
    if d.hour == 12 and d.minute == 0:
        return "noon"
    if d.hour == 0 and d.minute == 0:
        return "midnight"
    return f"{h}:{d.minute:02d} {ap}" if d.minute else f"{h} {ap}"


def _day_said(d, now):
    days = (d.date() - now.date()).days
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days == -1:
        return "yesterday"
    if 1 < days < 7:
        return d.strftime("%A")
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')}"


def said(o, now=None, day=True):
    """One occurrence as she says it: "Lunch with Sam tomorrow at 1 PM", "the team offsite on Friday (all day)"."""
    now = now or dt.datetime.now()
    when_ = ("" if not day else _day_said(o["start"], now) + " ") + \
        ("all day" if o["all_day"] else f"at {_clock_said(o['start'])}")
    where = f", at {o['where']}" if o.get("where") and len(o["where"]) < 50 else ""
    return f"{o['title']} {when_.strip()}{where}"


def listing(found, label, missing=(), now=None):
    """What's on, said: "Tomorrow you have 2 things: Lunch with Sam at 1 PM, and the dentist at 4:30 PM."."""
    now = now or dt.datetime.now()
    tail = f" I couldn't reach your {' and '.join(missing)} calendar." if missing else ""
    if not found:
        return f"Nothing on your calendar {label}.{tail}"
    one_day = len({o["start"].date() for o in found}) == 1
    items = [said(o, now, day=not one_day) if not one_day else
             (f"{o['title']} all day" if o["all_day"] else f"{o['title']} at {_clock_said(o['start'])}")
             for o in found[:6]]
    more = f", and {len(found) - 6} more" if len(found) > 6 else ""
    things = items[0] if len(items) == 1 else ", ".join(items[:-1]) + (", and " if not more else ", ") + items[-1]
    count = "one thing" if len(found) == 1 else f"{len(found)} things"
    lead = label[:1].upper() + label[1:]
    LAST.update(event=found[0], at=time.time())
    return f"{lead} you have {count}: {things}{more}.{tail}"


def google_link(title, start, end=None, all_day=False, where=""):
    """Google Calendar's own new-event page with it filled in, for you to save."""
    if all_day:
        a, z = start.strftime("%Y%m%d"), ((end or start + dt.timedelta(days=1))).strftime("%Y%m%d")
    else:
        a = start.strftime("%Y%m%dT%H%M00")
        z = (end or start + dt.timedelta(minutes=DEFAULT_MINUTES)).strftime("%Y%m%dT%H%M00")
    url = (f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={quote(title)}&dates={a}/{z}")
    return url + (f"&location={quote(where)}" if where else "")


def google_day(d):
    return f"https://calendar.google.com/calendar/r/day/{d.year}/{d.month}/{d.day}"


# --------------------------------------------------------------------------- finding the one meant
def find(words, now=None, days=30, fetch=None):
    """The upcoming occurrence words point at: "my 3 PM", "lunch with Sam", "it" (the one she last spoke of), or None."""
    now = now or dt.datetime.now()
    text = " ".join(str(words or "").lower().split())
    text = re.sub(r"^(?:my|the|that|this|our)\s+", "", text)
    if text in ("it", "that", "this", "that one", "this one", "the event", "the meeting", "my meeting", "meeting") and \
            LAST["event"] and time.time() - LAST["at"] < 600:
        return LAST["event"]
    found, _ = between(now - dt.timedelta(hours=1), now + dt.timedelta(days=days), fetch)
    if not found:
        return None
    clock = None
    plain = re.sub(r"o'?\s?clock", "", text)
    m = TIME.search(plain) or re.search(rf"\b(?P<t>\d{{1,2}}(?:[:.][0-5]\d)? ?{AMPM}?)\b", plain)
    if m:
        try:
            clock = _clock(m, plain)
        except Exception:
            clock = None
    if clock is not None:
        at = [o for o in found if not o["all_day"] and (o["start"].hour, o["start"].minute) == clock]
        if at:
            return at[0]
    words_ = {w for w in re.findall(r"[a-z0-9']+", text) if len(w) > 2 and w not in
              {"the", "my", "with", "and", "for", "meeting", "event", "appointment", "call", "on", "at"}}
    best, score = None, 0
    for o in found:
        have = set(re.findall(r"[a-z0-9']+", o["title"].lower()))
        hit = len(words_ & have) + sum(1 for w in words_ for h in have if len(w) > 3 and (w in h or h in w)) * 0.5
        if hit > score:
            best, score = o, hit
    if best is None and re.search(r"\b(?:meeting|event|appointment|call)\b", text):
        timed = [o for o in found if not o["all_day"] and o["start"] >= now - dt.timedelta(minutes=10)]
        return timed[0] if timed else None
    return best


def free_at(start, end, fetch=None):
    """What's on between start and end, as a list (empty if you're free)."""
    found, _ = between(start, end, fetch)
    return [o for o in found if not o["all_day"]]


# --------------------------------------------------------------------------- a word before each thing starts
def due(now=None, fetch=None):
    """(key, what to say) for each event starting within its reminder time, said once each: "Lunch with Sam starts in
    10 minutes."; all-day ones once at 9 in the morning."""
    now = now or dt.datetime.now()
    found, _ = between(now - dt.timedelta(minutes=1), now + dt.timedelta(minutes=max(REMIND, 30) + 1), fetch)
    found += [o for o in between(now - dt.timedelta(hours=10), now + dt.timedelta(hours=1), fetch)[0]
              if o["all_day"] and o["start"].date() == now.date()]
    with _lock:
        data = _load()
        told = data["told"]
        out = []
        for o in found:
            key = o["key"]
            if key in told:
                continue
            if o["all_day"]:
                if o["start"].date() == now.date() and now.hour >= 9:
                    out.append((key, f"Today: {o['title']}."))
                continue
            left = (o["start"] - now).total_seconds() / 60
            if -1 <= left <= o.get("remind", REMIND):
                mins = max(0, round(left))
                out.append((key, f"{o['title']} starts {'now' if mins <= 1 else f'in {mins} minutes'}."))
        if out:
            for key, _ in out:
                told[key] = time.time()
            cutoff = time.time() - 3 * 86400  # what was said days ago is forgotten
            data["told"] = {k: v for k, v in told.items() if v > cutoff}
            _save(data)
    return out


def today_line(now=None, fetch=None):
    """For her briefing: "On your calendar today: lunch with Sam at 1 PM." "" when nothing's on."""
    now = now or dt.datetime.now()
    a, b, _ = day_range("today", now)
    try:
        found, _ = between(a, b, fetch)
    except Exception:
        return ""
    if not found:
        return ""
    items = [(f"{o['title']} all day" if o["all_day"] else f"{o['title']} at {_clock_said(o['start'])}")
             for o in found[:4]]
    return "On your calendar today: " + (items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " +
                                         items[-1]) + "."
