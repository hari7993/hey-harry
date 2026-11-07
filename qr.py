"""QR codes for the island (7 November 2026, the owner's ask, after NotchPixel's "scan a code with your phone's camera"
for files to the phone and PC Deck): a short web address made into the squares a phone's camera reads. No package for
it: only what the island needs, the address as bytes and error correction at level M, a version from 1 to 10 (up to
213 bytes), from the standard (ISO/IEC 18004) as Project Nayuki's generator lays it out.

make(text) gives the squares as a numpy array, True for dark, without the quiet zone round it."""
import numpy as np

# error correction M, by version (1 to 10): codewords of correction in each block, and how many blocks
ECC_PER_BLOCK = (None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26)
BLOCKS = (None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5)
MOST = 10
M_BITS = 0  # level M's two bits in the format information


def _mul(x, y):
    """x times y in the field of 256 the codes are counted in (its polynomial 0x11D)."""
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _divisor(degree):
    """The Reed-Solomon generator for degree codewords of correction, highest power first, its leading 1 left off."""
    out = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            out[j] = _mul(out[j], root)
            if j + 1 < degree:
                out[j] ^= out[j + 1]
        root = _mul(root, 0x02)
    return out


def _remainder(data, divisor):
    """The correction codewords for data."""
    out = [0] * len(divisor)
    for b in data:
        factor = b ^ out.pop(0)
        out.append(0)
        for i, coef in enumerate(divisor):
            out[i] ^= _mul(coef, factor)
    return out


def _raw_modules(ver):
    """How many squares a version has for its data and correction, after its fixed patterns."""
    n = (16 * ver + 128) * ver + 64
    if ver >= 2:
        align = ver // 7 + 2
        n -= (25 * align - 10) * align - 55
        if ver >= 7:
            n -= 36
    return n


def _data_codewords(ver):
    return _raw_modules(ver) // 8 - ECC_PER_BLOCK[ver] * BLOCKS[ver]


def _alignment(ver, size):
    """Where the alignment patterns' middles go along each side."""
    if ver == 1:
        return []
    align = ver // 7 + 2
    step = (ver * 8 + align * 3 + 5) // (align * 4 - 4) * 2
    return list(reversed([size - 7 - i * step for i in range(align - 1)] + [6]))


def _bits(text):
    """The data's bit string for version-choosing: mode, count and bytes."""
    data = text.encode("utf-8")
    for ver in range(1, MOST + 1):
        count_bits = 8 if ver < 10 else 16
        need = 4 + count_bits + 8 * len(data)
        if need <= _data_codewords(ver) * 8:
            return ver, data, count_bits
    raise ValueError("too long for the island's QR codes")


def _codewords(ver, data, count_bits):
    """The data codewords, filled to their number, then all of them with their correction, interleaved."""
    bits = [0, 1, 0, 0] + [(len(data) >> i) & 1 for i in reversed(range(count_bits))]
    for b in data:
        bits += [(b >> i) & 1 for i in reversed(range(8))]
    room = _data_codewords(ver) * 8
    bits += [0] * min(4, room - len(bits))
    bits += [0] * (-len(bits) % 8)
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(words) < room // 8:
        words.append(pad)
        pad ^= 0xEC ^ 0x11
    blocks_n, ecc_n = BLOCKS[ver], ECC_PER_BLOCK[ver]
    raw = _raw_modules(ver) // 8
    short_n = blocks_n - raw % blocks_n
    short_len = raw // blocks_n
    divisor = _divisor(ecc_n)
    blocks, k = [], 0
    for i in range(blocks_n):
        take = short_len - ecc_n + (0 if i < short_n else 1)
        dat = words[k:k + take]
        k += take
        ecc = _remainder(dat, divisor)
        if i < short_n:
            dat = dat + [0]
        blocks.append(dat + ecc)
    out = []
    for i in range(len(blocks[0])):
        for j, block in enumerate(blocks):
            if i != short_len - ecc_n or j >= short_n:
                out.append(block[i])
    return out


MASKS = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
         lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
         lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
         lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)


def _format(mask):
    """The 15 bits saying level M and the mask, with their own correction."""
    data = M_BITS << 3 | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return (data << 10 | rem) ^ 0x5412


def _version_bits(ver):
    rem = ver
    for _ in range(12):
        rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
    return ver << 12 | rem


def _penalty(m):
    """How hard a mask makes it to read, as the standard counts it: long runs, 2 by 2 blocks, and too much dark or
    light (the finder-like rule left out: near enough to pick a good one)."""
    score = 0
    for grid in (m, m.T):
        for line in grid:
            run = 1
            for a, b in zip(line[:-1], line[1:]):
                if a == b:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run = 1
            if run >= 5:
                score += run - 2
    same = (m[:-1, :-1] == m[1:, :-1]) & (m[:-1, :-1] == m[:-1, 1:]) & (m[:-1, :-1] == m[1:, 1:])
    score += 3 * int(same.sum())
    dark = m.mean()
    score += int(abs(dark * 100 - 50) // 5) * 10
    return score


def make(text):
    """text as a QR code's squares (size x size, True dark), version 1 to 10, level M, the best of its eight masks."""
    ver, data, count_bits = _bits(text)
    size = ver * 4 + 17
    dark = np.zeros((size, size), bool)
    fixed = np.zeros((size, size), bool)

    def put(x, y, on):
        dark[y, x], fixed[y, x] = bool(on), True
    for i in range(size):  # the timing lines
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):  # the three finders, with the light round them
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    put(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    spots = _alignment(ver, size)
    last = len(spots) - 1
    for i, ax in enumerate(spots):
        for j, ay in enumerate(spots):
            if (i, j) in ((0, 0), (0, last), (last, 0)):
                continue  # where the finders are
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    put(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
    fixed[:9, 8] = fixed[8, :9] = True  # the format's places, kept for now and drawn last
    fixed[8, size - 8:] = fixed[size - 8:, 8] = True
    if ver >= 7:
        bits = _version_bits(ver)
        for i in range(18):
            on = (bits >> i) & 1
            a, b = size - 11 + i % 3, i // 3
            put(a, b, on)
            put(b, a, on)
    words = _codewords(ver, data, count_bits)
    i, right = 0, size - 1
    while right >= 1:  # the codewords up and down in two-wide columns, from the right
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                y = size - 1 - vert if ((right + 1) & 2) == 0 else vert
                if not fixed[y, x] and i < len(words) * 8:
                    dark[y, x] = (words[i >> 3] >> (7 - (i & 7))) & 1
                    i += 1
        right -= 2
    ys, xs = np.mgrid[0:size, 0:size]
    best = None
    for mask, rule in enumerate(MASKS):
        m = dark ^ (np.vectorize(rule)(xs, ys) & ~fixed)
        f = _format(mask)
        for k in range(6):
            m[k, 8] = (f >> k) & 1
        m[7, 8], m[8, 8], m[8, 7] = (f >> 6) & 1, (f >> 7) & 1, (f >> 8) & 1
        for k in range(9, 15):
            m[8, 14 - k] = (f >> k) & 1
        for k in range(8):
            m[8, size - 1 - k] = (f >> k) & 1
        for k in range(8, 15):
            m[size - 15 + k, 8] = (f >> k) & 1
        m[size - 8, 8] = True  # the one that's always dark
        score = _penalty(m)
        if best is None or score < best[0]:
            best = (score, m)
    return best[1]
