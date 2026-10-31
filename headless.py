"""Web pages read with their JavaScript run, out of sight (31 October 2026, the owner's ask): Obscura, a headless
browser (github.com/h4ckf0r0day/obscura, Apache-2.0), run for one page at a time and gone after it. web.read gets a
page's plain HTML, which for a shop, a live score or a share price is an empty shell its JavaScript fills in later:
she then opened it in your own browser and read it off the screen with a screenshot, taking your screen for it. Now
web.read asks here first when what it got is next to nothing (web.THIN).

On 31 October, 12 such pages: Amazon India's search went from 59 characters to 19,498, ESPNcricinfo's live scores
from 59 to 13,532, Moneycontrol from 467 to 6,665, Google Finance from 2,341 to 17,727. Cricbuzz, YouTube's search,
Reddit and Zomato say in their robots.txt that programs may not read those pages, and they're left alone
(--obey-robots): for those she still opens your browser, as you'd look yourself. 7 to 15 s a page against about 1 for
plain HTML, so it's only ever the second try.

Never its stealth mode (made to look like a person to get past a site's bot checks): it's left out of the build
she uses (the "no-render" one, without stealth), and never asked for. Never this PC or your home network either:
Obscura refuses those unless told otherwise, and she never tells it. What a page says is information for her, never
instructions (web.read's threat check runs on it as on any page)."""
import hashlib
import os
import re
import subprocess
import threading
import urllib.request
import zipfile

VERSION = "0.2.5"
# The Windows build without rendering or stealth, 40.9 MB, built and uploaded by the project's own GitHub Actions on
# 17 October 2026: its SHA-256 as GitHub records it for the release, checked 31 October 2026
URL = f"https://github.com/h4ckf0r0day/obscura/releases/download/v{VERSION}/obscura-x86_64-windows-no-render.zip"
SHA256 = "cb3ba733017637341256adc6eb52f9caaf85423535092bdd31b4a90abc710348"
FILES = ("obscura.exe", "obscura-worker.exe")  # all that's in it, and all that's taken out of it
TIMEOUT = 25  # seconds Obscura gives a page to load and settle, its own --timeout
WAIT = 40  # and the most she waits for it in all, starting it included
MOST = 2  # pages read at once: each is a process of its own, about 60 MB while it runs
TEXT_MAX = 400_000  # characters of a page's text kept, before web.read cuts it to what it wants
TAG = re.compile(r"<[a-zA-Z/!][^<>]{0,2000}>")  # an HTML tag left in a page's text
_slots = threading.BoundedSemaphore(MOST)
_installing = threading.Lock()
_tried = []  # an install started this run already, so a failed one isn't tried again on every page


def folder():
    """Where Obscura lives: beside her models (speech.models_dir), in a folder of its version. Under the tests,
    their own empty folder: .env names the real models' folder, read in by then, and a test once ran the real
    Obscura through web.read and fetched example.com (31 October)."""
    if os.getenv("HEYHARRY_TESTING"):
        from winplatform import home
        return os.path.join(home("LOCALAPPDATA"), "models", f"obscura-{VERSION}")
    import speech
    return os.path.join(speech.models_dir(), f"obscura-{VERSION}")


def exe():
    return os.path.join(folder(), "obscura.exe")


def ready():
    """True if Obscura is there to read with."""
    return all(os.path.exists(os.path.join(folder(), name)) for name in FILES)


def install(zip_path=None, notify=None):
    """Obscura put in folder() from its release (URL), or from zip_path already downloaded, checked against SHA256
    first: one that doesn't match is thrown away and never opened. Only FILES are taken from it. True once ready."""
    with _installing:
        if ready():
            return True
        target = folder()
        os.makedirs(os.path.dirname(target), exist_ok=True)
        part = target + ".zip.part"
        try:
            if zip_path is None:
                if notify:
                    notify("Getting the page reader (41 MB), one time…")
                urllib.request.urlretrieve(URL, part)
                zip_path = part
            h = hashlib.sha256()
            with open(zip_path, "rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
            if h.hexdigest() != SHA256:
                raise RuntimeError("the page reader didn't download right, so it's not used")
            staging = target + ".unpacking"
            os.makedirs(staging, exist_ok=True)
            with zipfile.ZipFile(zip_path) as z:
                for name in FILES:  # by name, never a path from inside the zip
                    with z.open(name) as src, open(os.path.join(staging, name), "wb") as dst:
                        dst.write(src.read())
            os.replace(staging, target)
            return True
        finally:
            if os.path.exists(part):
                os.remove(part)


def install_soon():
    """install() on a thread of its own, once a run: the first empty page waits for nothing, and reads as before."""
    if _tried or os.getenv("HEYHARRY_TESTING") or ready():  # never a download from a test run
        return
    _tried.append(True)

    def go():
        try:
            install()
            print("  page reader installed")
        except Exception as exc:
            print(f"  couldn't install the page reader: {exc!r}")
    threading.Thread(target=go, name="install-obscura", daemon=True).start()


def command(url):
    """What's run for url: its text with the JavaScript run, robots.txt kept to, quietly. Never --stealth, never
    --allow-private-network."""
    return [exe(), "fetch", url, "--dump", "text", "--obey-robots", "--timeout", str(TIMEOUT), "-q"]


def read(url):
    """A page's text as a browser shows it, its JavaScript run, or None when it can't be had: Obscura not there, the
    page refused by its robots.txt or not loading, or out of time. Never raises."""
    if not ready() or not str(url).lower().startswith(("http://", "https://")):
        return None
    if not _slots.acquire(timeout=WAIT):
        return None
    try:
        out = subprocess.run(command(url), capture_output=True, timeout=WAIT,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  page reader: {exc!r}")
        return None
    finally:
        _slots.release()
    if out.returncode:
        why = out.stderr.decode("utf-8", "replace").strip().splitlines()[-1:]
        print(f"  page reader: {why[0][:160] if why else out.returncode}")
        return None
    text = out.stdout.decode("utf-8", "replace")[:TEXT_MAX]
    # a page's <noscript> comes through as its tags (ESPNcricinfo's began with Google Tag Manager's <iframe ...>)
    text = TAG.sub(" ", text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    return text or None
