"""Your hand in front of the laptop's camera, and a finger snap seen in it (29 October 2026, the owner's ask: "my
fingers snap on camera, then it needs to do it"). A snap heard alone wasn't enough: in their room a snap rang for 70
to 100 ms in the mic, and was taken for something else (claps.py).

Seen on this PC by MediaPipe's palm finder and its 21 points of a hand, as OpenCV Zoo has them (Apache 2.0, 3.9 and
4.1 MB, downloaded once and checked: speech.MODELS "palm" and "hand"), with their code cut down from OpenCV Zoo's
mp_palmdet.py and mp_handpose.py. Run by ONNX Runtime, already in her venv for speech: on this laptop the palm finder
took 8.6 ms of CPU a look and the 21 points 3.1 ms, against 69 and 31 in OpenCV's own DNN, which is used if ONNX
Runtime isn't there. Quick enough to follow a hand frame by frame (handmouse.py). No new package.

A snap, seen: a sharp sound heard (claps.py) with your hand up in front of the camera at that moment (cues.py). The
palm finder only looks at the camera's last frames when a sharp sound comes (camera.Camera.around), nothing at all
otherwise.
shape() is for the log: how your thumb and middle finger were, so what a snap looks like can be learned."""
import numpy as np

import speech

PALM_SIZE = 192  # what the palm finder looks at
HAND_SIZE = 224  # and the points model
PALM_SCORE = 0.6  # a palm at least this sure
HAND_SCORE = 0.8  # and its points
# the points: 0 the wrist; 4 the thumb's tip; 9 the middle finger's knuckle, 12 its tip
WRIST, THUMB_TIP, MIDDLE_KNUCKLE, MIDDLE_TIP = 0, 4, 9, 12


def anchors():
    """MediaPipe's palm anchors for a 192 px picture: 24 x 24 places 2 each, then 12 x 12 places 6 each, centres
    only (OpenCV Zoo's mp_palmdet.py lists the same 2,016)."""
    out = []
    for size, each in ((24, 2), (12, 6)):
        for y in range(size):
            for x in range(size):
                out += [((x + 0.5) / size, (y + 0.5) / size)] * each
    return np.array(out, dtype=np.float32)


def _net(path):
    """A model run on one picture at a time: net(blob) -> its outputs in the model's own order. ONNX Runtime on one
    thread, or OpenCV's DNN if it isn't there."""
    try:
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads, options.inter_op_num_threads = 1, 1
        session = ort.InferenceSession(path, options, providers=["CPUExecutionProvider"])
        name = session.get_inputs()[0].name
        return lambda blob: session.run(None, {name: blob})
    except ImportError:
        import cv2
        net = cv2.dnn.readNet(path)
        outs = net.getUnconnectedOutLayersNames()

        def run(blob):
            net.setInput(blob)
            return net.forward(outs)
        return run


class Hands:
    """The hands in a picture: find(rgb) -> [{"points": 21 (x, y), "score", "box": (x1, y1, x2, y2), "size"}], the
    biggest first. size: the palm's length, wrist to middle knuckle, in pixels."""

    def __init__(self, notify=None, palm_path=None, hand_path=None):
        import cv2
        cv2.setNumThreads(1)
        self.cv2 = cv2
        self.palms = _net(palm_path or speech.model_path("palm", notify))
        self.hands = _net(hand_path or speech.model_path("hand", notify))
        self.anchors = anchors()

    def find(self, rgb):
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        found = []
        for palm in self.palm_boxes(bgr):
            hand = self.points(bgr, palm)
            if hand is not None:
                found.append(hand)
        return sorted(found, key=lambda h: -h["size"])

    # ----------------------------------------------------------------------- the palm finder (mp_palmdet.py)
    def palm_boxes(self, bgr, nms=0.3, score=PALM_SCORE):
        """[19 numbers: the box x1 y1 x2 y2, 7 points of the palm, its score] for each palm in bgr at least score
        sure."""
        cv2 = self.cv2
        h, w = bgr.shape[:2]
        ratio = min(PALM_SIZE / h, PALM_SIZE / w)
        rh, rw = int(h * ratio), int(w * ratio)
        image = cv2.resize(bgr, (rw, rh))
        top, left = (PALM_SIZE - rh) // 2, (PALM_SIZE - rw) // 2
        image = cv2.copyMakeBorder(image, top, PALM_SIZE - rh - top, left, PALM_SIZE - rw - left,
                                   cv2.BORDER_CONSTANT, None, (0, 0, 0))
        blob = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32)[np.newaxis] / 255.0
        deltas, scores = self.palms(blob)
        score = 1 / (1 + np.exp(-scores[0, :, 0].astype(np.float64)))
        keep = score >= PALM_SCORE
        if not keep.any():
            return []
        pad = np.array([left, top]) / ratio
        scale = max(w, h)
        box = deltas[0, keep, :4]
        anchor = self.anchors[keep]
        cxy, wh = box[:, :2] / PALM_SIZE, box[:, 2:] / PALM_SIZE
        boxes = np.concatenate([(cxy - wh / 2 + anchor) * scale, (cxy + wh / 2 + anchor) * scale], axis=1)
        boxes -= np.r_[pad, pad]
        marks = deltas[0, keep, 4:].reshape(-1, 7, 2) / PALM_SIZE + anchor[:, None, :]
        marks = marks * scale - pad
        rects = np.c_[boxes[:, :2], boxes[:, 2:] - boxes[:, :2]]  # NMSBoxes takes x, y, width, height
        idx = cv2.dnn.NMSBoxes(rects.tolist(), score[keep].tolist(), PALM_SCORE, nms)
        idx = np.array(idx).reshape(-1)
        return [np.r_[boxes[i], marks[i].reshape(-1), score[keep][i]] for i in idx]

    # ----------------------------------------------------------------------- its 21 points (mp_handpose.py)
    def _crop(self, image, box, rotating):
        """The palm's box shifted, grown and cut out square: (picture, box, where its corner is in image)."""
        cv2 = self.cv2
        wh = box[1] - box[0]
        box = box + (np.array([0, 0]) if rotating else np.array([0, -0.4])) * wh
        center, wh = box.sum(axis=0) / 2, box[1] - box[0]
        half = wh * (4 if rotating else 3) / 2
        box = np.array([center - half, center + half]).astype(np.int32)
        box[:, 0] = np.clip(box[:, 0], 0, image.shape[1])
        box[:, 1] = np.clip(box[:, 1], 0, image.shape[0])
        image = image[box[0][1]:box[1][1], box[0][0]:box[1][0], :]
        side = int(np.linalg.norm(image.shape[:2]) if rotating else max(image.shape[:2]))
        ph, pw = side - image.shape[0], side - image.shape[1]
        left, top = pw // 2, ph // 2
        image = cv2.copyMakeBorder(image, top, ph - top, left, pw - left, cv2.BORDER_CONSTANT, None, (0, 0, 0))
        return image, box, box[0] - [left, top]

    def points(self, bgr, palm):
        """The hand round a palm: its 21 points in bgr, or None if the model isn't sure it's a hand."""
        cv2 = self.cv2
        if bgr.size == 0:
            return None
        image, grown, bias = self._crop(bgr, palm[0:4].reshape(2, 2), True)
        if image.size == 0:
            return None
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        marks = palm[4:18].reshape(7, 2) - bias
        p1, p2 = marks[0], marks[2]  # the palm's base and the middle finger's
        radians = np.pi / 2 - np.arctan2(-(p2[1] - p1[1]), p2[0] - p1[0])
        radians -= 2 * np.pi * np.floor((radians + np.pi) / (2 * np.pi))
        angle = np.rad2deg(radians)
        center = (grown - bias).sum(axis=0) / 2  # the grown box's, as mp_handpose.py's
        rotation = cv2.getRotationMatrix2D(tuple(map(float, center)), angle, 1.0)
        rotated = cv2.warpAffine(image, rotation, (image.shape[1], image.shape[0]))
        turned = np.c_[marks, np.ones(len(marks))] @ rotation.T
        crop, box, _ = self._crop(rotated, np.array([turned.min(axis=0), turned.max(axis=0)]), False)
        if crop.size == 0:
            return None
        blob = cv2.resize(crop, (HAND_SIZE, HAND_SIZE), interpolation=cv2.INTER_AREA).astype(np.float32)[None] / 255.0
        landmarks, conf, _, _ = self.hands(blob)
        conf = float(conf[0][0])
        if conf < HAND_SCORE:
            return None
        pts = landmarks[0].reshape(-1, 3)[:, :2]
        scale = max((box[1] - box[0]) / HAND_SIZE)
        pts = (pts - HAND_SIZE / 2) * scale
        pts = pts @ cv2.getRotationMatrix2D((0, 0), angle, 1.0)[:, :2]
        rot, move = rotation[:, :2], rotation[:, 2]
        inverse = np.c_[rot.T, -rot.T @ move]
        origin = inverse @ np.r_[box.sum(axis=0) / 2, 1]
        pts = pts + origin + bias
        size = float(np.linalg.norm(pts[MIDDLE_KNUCKLE] - pts[WRIST]))
        x1, y1 = pts.min(axis=0)
        x2, y2 = pts.max(axis=0)
        return {"points": pts, "score": conf, "box": (float(x1), float(y1), float(x2), float(y2)), "size": size}


def shape(points):
    """(how near the thumb's tip is to the middle finger's, how near the middle tip is to the wrist), both in
    lengths of the palm."""
    size = float(np.linalg.norm(points[MIDDLE_KNUCKLE] - points[WRIST])) or 1.0
    return (float(np.linalg.norm(points[THUMB_TIP] - points[MIDDLE_TIP])) / size,
            float(np.linalg.norm(points[MIDDLE_TIP] - points[WRIST])) / size)

