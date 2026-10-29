"""What the PC is playing, as audio, for the meeting helper (28 October 2026): the other people in a call come out of
the speakers or headphones, so this is how she hears them. Windows' WASAPI loopback on the default output device, in
shared mode: it takes nothing from the call and changes nothing in it, and works whatever the output is (laptop
speakers, headphones, Bluetooth), where Stereo Mix only hears the built-in sound card.

It hands on 16 kHz mono float32 blocks, the kind speech.py works on. Nothing is played, kept or sent from here."""
import ctypes
import threading
import time
from ctypes import POINTER, c_byte, c_uint32, c_ulonglong
from ctypes.wintypes import DWORD

import numpy as np

RATE = 16000
BLOCK = 512  # 32 ms, what Silero VAD looks at
SHARED, LOOPBACK = 0, 0x00020000  # AUDCLNT_SHAREMODE_SHARED, AUDCLNT_STREAMFLAGS_LOOPBACK
SILENT = 0x2  # AUDCLNT_BUFFERFLAGS_SILENT
BUFFER = 10_000_000  # 1 s, in 100 ns units


def _capture_client():
    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

    class IAudioCaptureClient(IUnknown):
        _iid_ = GUID("{C8ADBD64-E71E-48a0-A4DE-185C395CD317}")
        _methods_ = (
            COMMETHOD([], HRESULT, "GetBuffer", (["out"], POINTER(POINTER(c_byte)), "ppData"),
                      (["out"], POINTER(c_uint32), "pNumFramesToRead"), (["out"], POINTER(DWORD), "pdwFlags"),
                      (["out"], POINTER(c_ulonglong), "pu64DevicePosition"),
                      (["out"], POINTER(c_ulonglong), "pu64QPCPosition")),
            COMMETHOD([], HRESULT, "ReleaseBuffer", (["in"], c_uint32, "NumFramesRead")),
            COMMETHOD([], HRESULT, "GetNextPacketSize", (["out"], POINTER(c_uint32), "pNumFramesInNextPacket")),
        )
    return IAudioCaptureClient


class Resampler:
    """Any rate to 16 kHz, carried on from block to block: an average over each output sample's span (so what's
    above 8 kHz doesn't fold back in), then linear in between."""

    def __init__(self, rate):
        self.step = rate / RATE
        self.pos = 0.0  # where the next output sample is, in input samples from the start of what's kept
        self.kept = np.zeros(0, np.float32)

    def __call__(self, x):
        x = np.concatenate([self.kept, np.asarray(x, np.float32)])
        if self.step <= 1.0001:
            self.kept = np.zeros(0, np.float32)
            return x
        k = max(1, int(round(self.step)))
        smooth = np.convolve(x, np.ones(k, np.float32) / k, mode="same") if len(x) >= k else x
        last = len(x) - 1
        if self.pos > last:
            self.kept = x
            return np.zeros(0, np.float32)
        at = np.arange(self.pos, last, self.step)
        out = np.interp(at, np.arange(len(x)), smooth).astype(np.float32)
        nxt = self.pos + len(at) * self.step
        keep_from = max(0, int(nxt) - k)
        self.kept = x[keep_from:]
        self.pos = nxt - keep_from
        return out


class Loopback:
    """Hands what the default output device plays to on_block, BLOCK samples at a time, until stop(). Quiet stretches
    come as silence, at the rate the clock goes, so a pause in a call is a pause here too."""

    def __init__(self, on_block, every=0.01):
        """every: seconds between looks at what's come in: 0.01 for a call's voices; claps.py, which only needs to
        know a sharp sound came from the speakers, looks every 0.03 for a third of the work."""
        self.on_block, self.stopped, self.every = on_block, threading.Event(), every
        self.error, self.rate, self.thread = None, None, None
        self.started = threading.Event()

    def start(self, wait=3.0):
        self.thread = threading.Thread(target=self._run, name="harry-loopback", daemon=True)
        self.thread.start()
        self.started.wait(wait)
        if self.error:
            raise RuntimeError(f"I couldn't listen to the PC's sound: {self.error}")
        return self

    def stop(self):
        self.stopped.set()

    def _run(self):
        import comtypes
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:
            pass
        client = None
        try:
            from pycaw.api.audioclient import IAudioClient
            from pycaw.pycaw import AudioUtilities
            speakers = AudioUtilities.GetSpeakers()
            device = getattr(speakers, "_dev", speakers)
            client = device.Activate(IAudioClient._iid_, comtypes.CLSCTX_ALL, None).QueryInterface(IAudioClient)
            fmt = client.GetMixFormat()
            info = fmt.contents
            channels, rate, bits, align = info.nChannels, info.nSamplesPerSec, info.wBitsPerSample, info.nBlockAlign
            tag = info.wFormatTag
            if tag == 0xFFFE:  # WAVE_FORMAT_EXTENSIBLE: its SubFormat says float (3) or PCM (1)
                raw = ctypes.string_at(ctypes.addressof(info), 40)
                tag = int.from_bytes(raw[24:28], "little")
            is_float = tag == 3
            client.Initialize(SHARED, LOOPBACK, BUFFER, 0, fmt, None)
            capture = client.GetService(_capture_client()._iid_).QueryInterface(_capture_client())
            ctypes.windll.ole32.CoTaskMemFree(fmt)
            self.rate = rate
            resample = Resampler(rate)
            client.Start()
        except Exception as exc:
            self.error = str(exc) or exc.__class__.__name__
            self.started.set()
            return
        self.started.set()
        pending = np.zeros(0, np.float32)
        last = time.monotonic()
        dtype = np.float32 if is_float else (np.int16 if bits == 16 else np.int32)
        scale = 1.0 if is_float else float(2 ** (bits - 1))
        try:
            while not self.stopped.is_set():
                time.sleep(self.every)
                got = []
                size = capture.GetNextPacketSize()
                while size:
                    data, frames, flags, _, _ = capture.GetBuffer()
                    if frames:
                        if flags & SILENT or not data:
                            got.append(np.zeros(frames, np.float32))
                        else:
                            buf = np.frombuffer(ctypes.string_at(data, frames * align), dtype=dtype)
                            got.append((buf.reshape(-1, channels).astype(np.float32) / scale).mean(axis=1))
                    capture.ReleaseBuffer(frames)
                    size = capture.GetNextPacketSize()
                now = time.monotonic()
                if got:
                    last = now
                    pending = np.concatenate([pending, resample(np.concatenate(got))])
                elif now - last > 0.1:  # nothing playing: Windows sends nothing, so the quiet is made here
                    pending = np.concatenate([pending, np.zeros(int((now - last) * RATE), np.float32)])
                    last = now
                while len(pending) >= BLOCK:
                    block, pending = pending[:BLOCK], pending[BLOCK:]
                    try:
                        self.on_block(block)
                    except Exception as exc:
                        print(f"  loopback block: {exc!r}")
        except Exception as exc:
            self.error = str(exc) or exc.__class__.__name__
            print(f"  loopback stopped: {exc!r}")
        finally:
            try:
                client.Stop()
            except Exception:
                pass
