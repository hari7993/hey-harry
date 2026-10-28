"""Finding your files by what's in them (28 October 2026, after Atticus): "find my notes about the Tokyo trip", "which
document mentions invoice 4521?", "search my files for 'quarterly targets'". It asks the same Windows Search index as
filesearch.py, for the words inside documents, PDFs, slides and mail it has indexed, in your own folders only
(filesearch.scopes). It reads nothing off the disk itself, so it answers in about a second.

What it finds is kept as filesearch's finds are, so "open the first one" and "show me where it is" work after it. The
model is only ever told names, folders and dates, never what's in a file."""
import re
import time

import filesearch

# words that say "by what's in it", and what goes before the words to look for
INSIDE = re.compile(r"\b(?:about|mentioning|mentions|mention|containing|contains|contain|that says?|which says?|"
                    r"saying|with the words?|with the text|has the words?|have the words?|talks? about|talking about|"
                    r"refers? to|regarding|on the topic of|inside|in them|in it)\b", re.I)
LEAD = re.compile(r"^(?:please )?(?:can you |could you )?(?:find|search|look|locate|get|show)(?: me)?(?: for| through| "
                  r"in| inside)?(?: (?:all|any|my|the|a|an|some))*\s*", re.I)
SAYS = re.compile(r"[\"\u201c\u2018']([^\"\u201d\u2019']{2,80})[\"\u201d\u2019']")  # 'quarterly targets', said quoted
KIND_WORDS = {"note": (".txt", ".md", ".docx", ".doc", ".rtf", ".odt", ".one", ".pdf"),
              "notes": (".txt", ".md", ".docx", ".doc", ".rtf", ".odt", ".one", ".pdf")}
DROP = filesearch.STOP | set(filesearch.KINDS) | {"file", "files", "folder", "folders", "document", "documents", "doc",
                                                  "docs", "note", "notes", "anything", "something", "everything",
                                                  "stuff", "things", "thing", "word", "words", "text", "inside",
                                                  "about", "mention", "mentions", "mentioning", "containing",
                                                  "contains", "says", "say", "saying", "talks", "talking", "refers",
                                                  "regarding", "topic", "which", "that", "with", "has", "have",
                                                  "pc", "computer", "laptop", "them", "it"}
TOP, MOST = 300, 8
# what a program wrote, not you: build and test output, logs, dumps. They mention everything, so they go last
MACHINE_MADE = re.compile(r"(?:^|[\W_\d])(?:errors?|logs?|debug|trace|output|stdout|stderr|compile|build|tests?|run|"
                          r"dump|tmp|temp|cache|crash|report|results?|lint|coverage|backup)(?:$|[\W_\d])", re.I)
CODE_PLACES = re.compile(r"\\(?:backend|frontend|src|server|client|api|dist|build|out|logs?|tests?|scripts?|"
                         r"node_modules|\.next|venv|\.venv|target|bin|obj)\\", re.I)


def wanted(said):
    """(the words to look for inside files, the extensions it may be, the words as said for her answer), or None if
    these words don't ask for files by what's in them."""
    text = " ".join(str(said or "").split())
    quoted = SAYS.search(text)
    if not (INSIDE.search(text) or quoted):
        return None
    if quoted:
        phrase = quoted[1].strip()
        words = [w.lower() for w in re.findall(r"[\w'.+-]+", phrase)]
    else:
        at = INSIDE.search(text)
        before, after = text[:at.start()], text[at.end():]
        phrase = after.strip(" .?!") or before
        words = [w.lower().strip(".'") for w in re.findall(r"[\w'.+-]+", phrase)]
        words = [w for w in words if w and w not in DROP and len(w) > 1]
    phrase = re.sub(r"^(?:the|my|a|an|our|your|some)\s+", "", phrase.strip(), flags=re.I)
    exts = []
    for w in re.findall(r"[a-z]+", text.lower()):
        for e in KIND_WORDS.get(w, ()) or filesearch.KINDS.get(w if w in filesearch.KINDS else w.rstrip("s"), ()) or ():
            if e not in exts:
                exts.append(e)
    words = list(dict.fromkeys(words))[:6]
    if not words:
        return None
    return words, tuple(exts), " ".join(phrase.split()).strip(" .?!") or " ".join(words)


def _term(word):
    """One word for CONTAINS, as a prefix: "tokyo*", quoted, with anything but letters, digits and a few marks out."""
    word = re.sub(r"[^\w.+-]", "", word)
    return f'"{word}*"' if word else ""


def query(words, exts, phone=False, loose=False, top=TOP):
    """The Windows Search SQL: in your own folders, files whose text has every word (or, loose, the words as a phrase
    the index ranks by meaning), best first."""
    def text(s):
        return str(s).replace("'", "''")
    scopes = " OR ".join(f"SCOPE='file:{text(p.replace(chr(92), '/'))}'" for p in filesearch.scopes(phone))
    if loose:
        cond = "FREETEXT(*, '" + text(" ".join(re.sub(r"[^\w.+-]", "", w) for w in words)) + "')"
    else:
        cond = "CONTAINS(*, '" + text(" AND ".join(t for t in map(_term, words) if t)) + "')"
    where = [f"({scopes})", cond, "System.Kind <> 'folder'"]
    if exts:
        where.append("(" + " OR ".join(f"System.FileExtension = '{text(e)}'" for e in exts) + ")")
    return (f"SELECT TOP {int(top)} System.ItemPathDisplay, System.DateModified, System.Size, System.Search.Rank "
            f"FROM SystemIndex WHERE {' AND '.join(where)} ORDER BY System.Search.Rank DESC")


def _rows(sql):
    """[(path, modified, size, rank)] from Windows Search's index."""
    filesearch.win._com()
    import comtypes.client
    con = comtypes.client.CreateObject("ADODB.Connection")
    con.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
    try:
        rs = comtypes.client.CreateObject("ADODB.Recordset")
        rs.Open(sql, con)
        try:
            if rs.EOF:
                return []
            paths, modified, sizes, ranks = rs.GetRows()
        finally:
            rs.Close()
        return [(str(p), m.timestamp() if hasattr(m, "timestamp") else 0.0, int(s or 0), int(r or 0))
                for p, m, s, r in zip(paths, modified, sizes, ranks)]
    finally:
        con.Close()


def search(said, limit=MOST, remember=True, ask=None):
    """Files whose text matches what was said, best first, as filesearch.search has them (named and exact False).
    ValueError if the words don't say what to look for, RuntimeError if Windows Search can't be asked."""
    got = wanted(said)
    if got is None:
        raise ValueError("I didn't catch what to look for inside your files")
    words, exts, _ = got
    ask = ask or _rows
    rows = []
    for loose in (False, True):  # every word first; else the index's own ranking of the words together
        sql = query(words, exts, loose=loose)
        for attempt in (1, 2):  # its first connection in a while now and then fails, and the next one works
            try:
                rows = ask(sql)
                break
            except Exception as exc:
                if attempt == 2:
                    raise RuntimeError("Windows Search isn't answering, so I can't look inside your files") from exc
                time.sleep(0.3)
        if rows:
            break
    found = []
    for path, when, size, rank in rows:
        if filesearch.SKIP.search(path) or path.lower().startswith(filesearch.PHONE.lower()):
            continue
        score = rank / 1000 * 2 + filesearch._yours(path)
        base = filesearch.os.path.splitext(filesearch.os.path.basename(path))[0]
        if MACHINE_MADE.search(base):
            score -= 1.2
        if CODE_PLACES.search(path):
            score -= 0.6
        found.append({"path": path, "name": filesearch.os.path.basename(path),
                      "folder": filesearch.os.path.dirname(path), "modified": when, "size": size, "is_dir": False,
                      "score": round(score, 3), "named": False, "exact": False})
    found.sort(key=lambda f: (-f["score"], -f["modified"]))
    found = found[:limit]
    if remember:
        filesearch.keep_found(found)
    return found


def said(found, about):
    """What she says about what she found by its contents: the best one, where it is, and two more."""
    about = " ".join(str(about or "").split())
    if not found:
        return (f"Nothing in your files mentions \u201c{about}\u201d. Windows only looks inside files in the folders it "
                f"indexes, like Documents and Desktop.")
    top = found[0]
    when = f", changed {filesearch.ago(top['modified'])}" if top["modified"] else ""
    if len(found) == 1:
        return f"One file mentions it: {filesearch.spoken(top)} {filesearch.where(top['folder'])}{when}. Want me to " \
               f"open it?"
    others = " and ".join(filesearch.spoken(f) for f in found[1:3])
    return (f"{len(found)} files mention \u201c{about}\u201d. The best match is {filesearch.spoken(top)} "
            f"{filesearch.where(top['folder'])}{when}. Also {others}. Want me to open the first one?")
