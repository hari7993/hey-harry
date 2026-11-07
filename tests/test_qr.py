"""The island's QR codes (qr.py): their correction worked out as the standard's own example has it, their fixed
patterns where a phone's camera looks for them, their size growing with the address, and a reader reading them back."""
import unittest

import numpy as np

from tests.support import siri  # noqa: F401  temp APPDATA and the tripwires, before anything else
import qr


class QR(unittest.TestCase):
    def test_the_correction_is_the_standards_own(self):
        # "HELLO WORLD" at 1-M, as the standard's tutorials work it through: its data, then its ten of correction
        data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17]
        self.assertEqual(qr._remainder(data, qr._divisor(10)), [196, 35, 39, 119, 235, 215, 231, 226, 93, 23])

    def test_its_fixed_patterns(self):
        m = qr.make("hi")
        n = m.shape[0]
        self.assertEqual(m.shape, (21, 21))  # version 1
        for y0, x0 in ((0, 0), (0, n - 7), (n - 7, 0)):  # the three finders: a dark ring, a light one, a dark middle
            f = m[y0:y0 + 7, x0:x0 + 7]
            self.assertTrue(f[0].all() and f[6].all() and f[:, 0].all() and f[:, 6].all())
            self.assertFalse(f[1, 1:6].any())
            self.assertTrue(f[2:5, 2:5].all())
        self.assertEqual(list(m[6, 8:n - 8]), [i % 2 == 0 for i in range(8, n - 8)])  # the timing line
        self.assertTrue(m[n - 8, 8])  # the square that's always dark

    def test_it_grows_with_the_address(self):
        self.assertEqual(qr.make("x" * 10).shape[0], 21)
        self.assertEqual(qr.make("http://192.168.1.23:52817/a8F3kQ9zX2mPq7Lw/").shape[0], 33)
        self.assertEqual(qr.make("x" * 200).shape[0], 57)  # version 10, with its version blocks
        with self.assertRaises(ValueError):
            qr.make("x" * 300)

    def test_a_reader_reads_them_back(self):
        try:
            import cv2
        except ImportError:
            self.skipTest("no OpenCV here to read them")
        reader = cv2.QRCodeDetector()
        for text in ("http://10.170.178.168:52817/kRpTDYeGCMyitUtD/", "https://notchpixel.com/",
                     "http://192.168.0.101:40000/" + "a1b2c3" * 20):
            m = np.pad(~qr.make(text), 4, constant_values=True).astype(np.uint8) * 255
            img = cv2.resize(m, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
            self.assertEqual(reader.detectAndDecode(img)[0], text)


if __name__ == "__main__":
    unittest.main()
