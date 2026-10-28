"use strict";
// Dream mode's scenes (28 October 2026, the owner's ask): pixel art drawn in code, 180 px tall and as wide as the
// screen's shape, scaled up with its pixels kept square. Skies and glows are ordered-dithered the way pixel artists
// shade them; what doesn't move is drawn once into a layer, so a frame is a few hundred small rectangles. Each scene:
// {label, init(W, H), draw(g, t)} with t in seconds. Nothing here is anyone's art: every shape is worked out below.

const SCENES = {};

// --------------------------------------------------------------------------------------------- the pixel kit
const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map(v => (v + 0.5) / 16);
const dith = (x, y) => BAYER[((y & 3) << 2) | (x & 3)];
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const fract = v => v - Math.floor(v);
const wrap = (v, m) => ((v % m) + m) % m;

function rgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function css(c, a = 1) {
  const [r, g, b] = c.map(v => clamp(Math.round(v), 0, 255));
  return a >= 1 ? `rgb(${r},${g},${b})` : `rgba(${r},${g},${b},${a.toFixed(3)})`;
}
function mix(a, b, t) {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}
function ramp(stops, t) {  // stops: [[0, rgb], ..., [1, rgb]], already parsed
  t = clamp(t, 0, 1);
  for (let i = 1; i < stops.length; i++) {
    if (t <= stops[i][0]) {
      const [t0, c0] = stops[i - 1], [t1, c1] = stops[i];
      return mix(c0, c1, (t - t0) / Math.max(1e-6, t1 - t0));
    }
  }
  return stops[stops.length - 1][1];
}
const parse = stops => stops.map(([t, c]) => [t, rgb(c)]);

// A small fast random, the same every time for the same seed, so a scene looks the same each time it opens
function rng(seed) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const hash = (a, b) => fract(Math.sin(a * 127.1 + b * 311.7) * 43758.5453);

function layer(w, h) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}
function rect(g, x, y, w, h, c) {
  g.fillStyle = c;
  g.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h));
}
function px(g, x, y, c) {
  g.fillStyle = c;
  g.fillRect(Math.round(x), Math.round(y), 1, 1);
}

// A vertical gradient, each channel cut to `levels` steps and dithered between them: the dotted skies of pixel art
function gradient(g, x0, y0, w, h, stops, levels = 16) {
  const S = parse(stops), img = g.getImageData(x0, y0, w, h), d = img.data;
  for (let y = 0; y < h; y++) {
    const c = ramp(S, y / Math.max(1, h - 1));
    for (let x = 0; x < w; x++) {
      const k = dith(x0 + x, y0 + y), i = (y * w + x) * 4;
      for (let ch = 0; ch < 3; ch++) d[i + ch] = Math.min(255, Math.floor((c[ch] / 255) * levels + k) * (255 / levels));
      d[i + 3] = 255;
    }
  }
  g.putImageData(img, x0, y0);
}

// Light round a moon, a sun or a lamp, fading out in dithered steps over what's drawn already
function glow(g, cx, cy, r, color, strength = 0.6, steps = 6) {
  const c = rgb(color), x0 = Math.floor(cx - r), y0 = Math.floor(cy - r), s = Math.ceil(2 * r) + 2;
  const img = g.getImageData(x0, y0, s, s), d = img.data;
  for (let y = 0; y < s; y++) {
    for (let x = 0; x < s; x++) {
      const dist = Math.hypot(x0 + x + 0.5 - cx, y0 + y + 0.5 - cy) / r;
      if (dist >= 1) continue;
      const q = Math.floor((1 - dist) ** 2 * strength * steps + dith(x0 + x, y0 + y)) / steps;
      if (q <= 0) continue;
      const i = (y * s + x) * 4;
      for (let ch = 0; ch < 3; ch++) d[i + ch] += (c[ch] - d[i + ch]) * Math.min(1, q);
    }
  }
  g.putImageData(img, x0, y0);
}

// A soft round light as a sprite, its colour fading to nothing, kept once made; bloom adds it to what's there, so
// lamps, candles and tail lights glow rather than sit on top
const SOFT = new Map();
function soft(r, color) {
  const key = `${r}${color}`;
  if (!SOFT.has(key)) {
    const c = layer(2 * r, 2 * r), g = c.getContext("2d"), [R, G, B] = rgb(color);
    const grad = g.createRadialGradient(r, r, 0, r, r, r);
    grad.addColorStop(0, `rgba(${R},${G},${B},1)`);
    grad.addColorStop(0.3, `rgba(${R},${G},${B},0.42)`);
    grad.addColorStop(1, `rgba(${R},${G},${B},0)`);
    g.fillStyle = grad;
    g.fillRect(0, 0, 2 * r, 2 * r);
    SOFT.set(key, c);
  }
  return SOFT.get(key);
}
function bloom(g, x, y, r, color, a = 1) {
  g.save();
  g.globalCompositeOperation = "lighter";
  g.globalAlpha = clamp(a, 0, 1);
  g.drawImage(soft(r, color), Math.round(x - r), Math.round(y - r));
  g.restore();
}

// A shape filled crisply, a pixel wherever its middle is inside, with no soft edges, as pixel art has none
function solid(g, pts, color) {
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  g.fillStyle = color;
  for (let y = Math.floor(Math.min(...ys)); y <= Math.ceil(Math.max(...ys)); y++) {
    for (let x = Math.floor(Math.min(...xs)); x <= Math.ceil(Math.max(...xs)); x++) {
      let inside = false;
      for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
        const [xi, yi] = pts[i], [xj, yj] = pts[j];
        if ((yi > y + 0.5) !== (yj > y + 0.5) && x + 0.5 < ((xj - xi) * (y + 0.5 - yi)) / (yj - yi) + xi) inside = !inside;
      }
      if (inside) g.fillRect(x, y, 1, 1);
    }
  }
}
function disc(g, cx, cy, r, color) {
  g.fillStyle = color;
  for (let y = -r; y <= r; y++) {
    const w = Math.floor(Math.sqrt(Math.max(0, r * r - y * y)) + 0.35);
    g.fillRect(Math.round(cx - w), Math.round(cy + y), 2 * w + 1, 1);
  }
}
function ellipse(g, cx, cy, rx, ry, color) {
  g.fillStyle = color;
  for (let y = -ry; y <= ry; y++) {
    const w = Math.floor(rx * Math.sqrt(Math.max(0, 1 - (y * y) / (ry * ry))) + 0.35);
    g.fillRect(Math.round(cx - w), Math.round(cy + y), 2 * w + 1, 1);
  }
}
function poly(g, pts, color) {
  g.fillStyle = color;
  g.beginPath();
  g.moveTo(pts[0][0], pts[0][1]);
  for (const p of pts.slice(1)) g.lineTo(p[0], p[1]);
  g.closePath();
  g.fill();
}
function line(g, x0, y0, x1, y1, color) {  // one pixel wide, every pixel whole
  const n = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0), 1);
  g.fillStyle = color;
  for (let i = 0; i <= n; i++) g.fillRect(Math.round(x0 + ((x1 - x0) * i) / n), Math.round(y0 + ((y1 - y0) * i) / n), 1, 1);
}

// Hills, dunes and mountains: smooth random heights across w, a few sizes of bump on top of each other. It comes
// round to where it began, so a band of it scrolls by with no seam
function noise(rand, w, period, octaves = 3) {
  const out = new Float32Array(w);
  let amp = 1, total = 0;
  for (let o = 0; o < octaves; o++) {
    const n = Math.max(1, Math.round(w / Math.max(2, period / 2 ** o))), p = w / n;
    const knots = Array.from({ length: n }, rand);
    for (let x = 0; x < w; x++) {
      const i = Math.floor(x / p), f = x / p - i, s = (1 - Math.cos(f * Math.PI)) / 2;
      out[x] += amp * (knots[i % n] * (1 - s) + knots[(i + 1) % n] * s);
    }
    total += amp;
    amp /= 2.2;
  }
  return out.map(v => v / total);
}
function ridge(g, w, base, amp, color, rand, period = 60, bottom = 180) {
  const n = noise(rand, w, period);
  g.fillStyle = color;
  for (let x = 0; x < w; x++) {
    const top = Math.round(base - n[x] * amp);
    g.fillRect(x, top, 1, bottom - top);
  }
  return n;
}

// A cloud as a sprite: round puffs side by side, lit on top and shaded under, dithered where the two meet
function cloud(rand, w, h, light, dark, edge = null) {
  const c = layer(w, h), g = c.getContext("2d"), L = rgb(light), D = rgb(dark), E = edge ? rgb(edge) : null;
  const count = 4 + Math.floor(rand() * 4);
  const puffs = Array.from({ length: count }, (_, i) => {
    const f = i / (count - 1), middle = Math.sin(f * Math.PI);  // biggest in the middle, a heap of rounds
    return { x: w * (0.14 + 0.72 * f) + (rand() - 0.5) * w * 0.06, y: h * (0.7 - middle * 0.12),
      rx: w * (0.09 + middle * 0.07 + rand() * 0.05), ry: h * (0.16 + middle * 0.34 + rand() * 0.08) };
  });
  const img = g.getImageData(0, 0, w, h), d = img.data;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let inside = 0;
      for (const p of puffs) inside = Math.max(inside, 1 - ((x - p.x) / p.rx) ** 2 - ((y - p.y) / p.ry) ** 2);
      if (inside <= 0 || y > h * 0.82) continue;
      const shade = clamp((y / h - 0.35) * 2.2, 0, 1), k = dith(x, y);
      let col = shade > k ? D : L;
      if (E && inside < 0.16 && y < h * 0.5) col = E;  // the rim the light catches
      const i = (y * w + x) * 4;
      d[i] = col[0]; d[i + 1] = col[1]; d[i + 2] = col[2]; d[i + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
  return c;
}

// A thin cloud at night as a sprite: long and ragged, thickest in its middle, darker than the sky behind it
function wisp(rand, w, h, body, under) {
  const c = layer(w, h), g = c.getContext("2d"), top = noise(rand, w, 8, 3), low = noise(rand, w, 9, 2);
  for (let x = 0; x < w; x++) {
    const env = Math.sin((x / (w - 1)) * Math.PI) ** 0.6, mid = Math.round(h * 0.62);
    const up = Math.round(h * 0.62 * env * (0.1 + 0.9 * top[x] ** 1.4)), down = Math.round(h * 0.38 * env * low[x]);
    if (up + down < 1) continue;
    rect(g, x, mid - up, 1, up + down, body);
    rect(g, x, mid + down - 1, 1, 1, under);
  }
  return c;
}

function starfield(rand, n, w, h) {
  return Array.from({ length: n }, () => ({ x: Math.floor(rand() * w), y: Math.floor(h * rand() ** 1.35),  // more up high
    b: rand(), s: 0.6 + rand() * 2.2, p: rand() * 6.28 }));
}
function stars(g, list, t, dim, mid, bright) {
  for (const s of list) {
    const v = s.b * (0.55 + 0.45 * Math.sin(t * s.s + s.p));
    if (v < 0.18) continue;
    px(g, s.x, s.y, v > 0.72 ? bright : v > 0.42 ? mid : dim);
    if (v > 0.93) {  // the brightest few twinkle into a small cross
      px(g, s.x - 1, s.y, dim); px(g, s.x + 1, s.y, dim); px(g, s.x, s.y - 1, dim); px(g, s.x, s.y + 1, dim);
    }
  }
}

// 3 by 5 digits, for the car's clock
const DIGITS = { 0: "111101101101111", 1: "010110010010111", 2: "111001111100111", 3: "111001111001111",
  4: "101101111001001", 5: "111100111001111", 6: "111100111101111", 7: "111001001001001", 8: "111101111101111",
  9: "111101111001111", ":": "000010000010000" };
function digits(g, str, x, y, color) {
  g.fillStyle = color;
  for (const ch of str) {
    const bits = DIGITS[ch];
    if (bits) {
      for (let i = 0; i < 15; i++) if (bits[i] === "1") g.fillRect(x + (i % 3), y + Math.floor(i / 3), 1, 1);
    }
    x += ch === ":" ? 3 : 4;
  }
}
const clock = () => {
  const d = new Date();
  return `${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`;
};

// A palm tree's silhouette as a sprite, h tall: a curving trunk notched by its rings, and fronds that leave the crown,
// arch over and droop under their own weight, thick at the crown and thin at the tip, their leaflets hanging off
// their undersides, longest midway, every other one shorter. sway (-1 to 1) moves them
function palm(h, color, sway = 0, lean = 0.25) {
  const w = Math.round(h * 1.5), c = layer(w, h + 4), g = c.getContext("2d");
  const baseX = w * 0.45, topX = baseX + h * lean, topY = Math.round(h * 0.26);
  for (let i = 0; i <= h; i++) {
    const f = i / h, x = baseX + (topX - baseX) * f ** 1.8, y = h + 3 - (h + 3 - topY) * f;
    const tw = (3.6 - f * 1.8) * Math.max(1, h / 60);
    rect(g, x - tw / 2, y, tw - (i % 4 === 0 ? 1 : 0), 1, color);
  }
  const every = h > 70 ? 3 : 2;  // a big one up close shows its leaflets apart
  for (const dir of [-1, 1]) {  // four fronds each way: [how far above level each sets off, its length in h]
    for (const [e0, l] of [[1.2, 0.3], [0.7, 0.42], [0.25, 0.48], [-0.2, 0.42]]) {
      const e = e0 + sway * 0.12 * dir, len = h * l * (dir > 0 ? 1.04 : 0.96), n = Math.round(len * 1.4);
      for (let i = 1; i <= n; i++) {
        const s = i / n, x = topX + dir * Math.cos(e) * len * s, y = topY - Math.sin(e) * len * s + 0.5 * len * s * s;
        const th = Math.max(1, Math.round(2.4 * (1 - s) + 0.6));
        rect(g, x - th / 2, y - th / 2, th, th, color);
        if (s > 0.1 && s < 0.96 && i % every === 0) {
          const leaf = (h / 34) * (0.8 + 2 * Math.sin(Math.PI * s)) * (i % (2 * every) ? 1 : 0.6);
          line(g, x, y, x + dir * leaf * 0.6, y + leaf, color);  // hanging down and out
          if (e0 > 0.5) line(g, x, y, x + dir * leaf * 0.7, y - leaf * 0.35, color);  // a few up, off the arching ones
        }
      }
    }
  }
  disc(g, topX - 1, topY + 2, 2, color);  // the coconuts
  disc(g, topX + 2, topY + 3, 1, color);
  return c;
}

// --------------------------------------------------------------------------------------------- 1: night drive
// At the wheel on an empty road at night, as the owner's picture has it (28 October 2026): thin dark clouds over a
// dotted teal sky and a small moon, the road ahead lit by your headlights in bands, brighter nearer, the line down
// its middle coming at you on your right (driving on the left, as here), the car's inside dark and a little warm,
// lit teal where the night comes in through the glass, your left hand on the wheel, the orange gauges through it,
// the mirror, stickers on the glass, and the radio's clock showing the real time. Its sizes are measured off that
// picture: the car is laid out in a frame 1.17 times as wide as it's tall, in the middle, and a wider screen sees
// more of the door on the left and of the dashboard on the right
SCENES["night-drive"] = {
  label: "Night drive",
  init(W, H) {
    const r = rng(7), F = this.F = Math.round(H * 1.17), x0 = Math.round((W - F) / 2);
    const X = this.X = f => x0 + f * F, Y = this.Y = f => f * H;
    const hz = this.hz = Math.round(Y(0.5)), vx = this.vx = Math.round(X(0.57));
    const back = this.back = layer(W, H), b = back.getContext("2d");
    gradient(b, 0, 0, W, hz, [[0, "#2a4749"], [0.3, "#2a4d51"], [0.75, "#29464b"], [1, "#253c42"]], 14);
    this.stars = starfield(r, Math.round(W * 0.3), W, hz - 4);
    const mx = Math.round(X(0.755)), my = Math.round(Y(0.085));
    glow(b, mx, my, 12, "#6f9c9c", 0.3);
    disc(b, mx, my, 4, "#f2faf9");
    for (const [dx, dy] of [[-1, -1], [1, 1], [2, -1], [-2, 1]]) px(b, mx + dx, my + dy, "#cfdedd");  // its seas
    // the land and the road in the dark, and your headlights on the road ahead in bands, flatter and wider nearer
    rect(b, 0, hz, W, H - hz, "#212324");
    const cx = X(0.58), cy = Y(0.62);
    ["#253237", "#29404a", "#2d4c54", "#345a62", "#3b6470", "#436a78", "#4d6e7c"].forEach((col, k) => {
      const s = 1 - k * 0.13;
      ellipse(b, cx, cy, F * 0.4 * Math.sqrt(s), (cy - hz) * s, col);
    });
    rect(b, 0, hz, W, 1, "#1c1d1e");  // the far edge of the land
    this.clouds = Array.from({ length: 16 }, (_, i) => {
      const w = 18 + Math.floor(r() * 56), h = 5 + Math.floor(r() * 7);
      const y = i % 2 ? Y(0.24) + r() * Y(0.1) : Y(0.03) + r() * Y(0.4);  // half of them in a long bank across the middle
      return { img: wisp(r, w, h, "#232d31", "#1e2629"), x: r() * (W + w), y, v: 0.5 + r() * 1.1, w };
    });
    this.front = this.interior(W, H);
  },
  interior(W, H) {  // the car round you, drawn once, the glass left clear
    const c = layer(W, H), g = c.getContext("2d"), { X, Y, F } = this;
    const IN = "#252022", CY = "#4fc4cf";
    const top = Math.round(Y(0.05)), foot = Math.round(Y(0.6));
    rect(g, 0, 0, W, top, "#222d33");  // the roof's edge
    rect(g, 0, top, W, 1, "#2e3f47");
    // the door's window on the left, darker, its mirror outside; the pillar between that and the windscreen, lit
    // along its inside edge and its face; the door below
    const inner = y => Math.round(X(0) + (X(0.205) - X(0)) * (y - top) / (foot - top)), outer = y => inner(y) - Math.round(F * 0.07);
    for (let y = top + 1; y < foot; y++) {
      for (let x = 0; x < outer(y); x++) px(g, x, y, y >= this.hz ? "#1a1d1f" : dith(x, y) < 0.5 ? "#1b2b2f" : "#203539");
    }
    // its mirror outside, the glass towards you showing the road behind, on an arm from the door
    const sx = Math.round(X(-0.085)), sy = Math.round(Y(0.48)), sw = Math.round(F * 0.11), sh = Math.round(Y(0.07));
    poly(g, [[sx + sw - 2, sy + sh - 4], [outer(sy + sh) + 1, sy + sh - 1], [outer(sy + sh) + 1, sy + sh + 3], [sx + sw - 2, sy + sh]], "#161f22");
    ellipse(g, sx + sw / 2, sy + sh / 2, sw / 2, sh / 2, "#172427");
    ellipse(g, sx + sw / 2, sy + sh / 2, sw / 2 - 1.5, sh / 2 - 1.5, "#22373b");
    rect(g, sx + 4, sy + 3, sw - 9, 1, "#2e4d51");
    rect(g, sx + 3, sy + sh - 4, sw - 6, 1, "#1d2b2e");
    for (let x = 2; x < sw - 2; x++) px(g, sx + x, sy + sh / 2 - Math.sqrt(Math.max(0, 1 - ((x - sw / 2) / (sw / 2)) ** 2)) * sh / 2, "#2f7a80");
    for (let y = top + 1; y < foot; y++) {
      const a = outer(y), e = inner(y);
      rect(g, a, y, e - a, 1, "#212f38");
      px(g, a, y, "#2b4a52");
      rect(g, e - 4, y, 3, 1, dith(e, y) > 0.7 ? "#4f8689" : "#3f7f86");
      px(g, e - 5, y, "#2b6a70");
      px(g, e - 1, y, "#278490");
      px(g, e, y, CY);
    }
    rect(g, 0, foot, W, H - foot, IN);  // everything under the glass, dark to begin with
    rect(g, 0, foot, inner(foot) - 2, 1, "#2b6e76");  // the door: its sill, the armrest, the pocket, their edges lit
    rect(g, 0, Y(0.725), X(0.085), Y(0.05), "#2a2427");
    rect(g, 0, Y(0.725), X(0.085), 1, "#2f6c74");
    px(g, X(0.085), Y(0.725), "#22484e");
    rect(g, 0, Y(0.93), X(0.07), 1, "#2b6e76");
    rect(g, 0, Y(0.93) + 1, X(0.07), H, "#201b1e");
    // stickers on the glass at the top on the left, as on a car that's been places
    rect(g, X(0.09), Y(0.12), F * 0.04, Y(0.022), "#1e1f23");
    rect(g, X(0.07), Y(0.172), F * 0.07, Y(0.02), "#1e1f23");
    ellipse(g, X(0.215), Y(0.23), Math.round(F * 0.032), Math.round(Y(0.045)), "#1f2125");
    // the mirror, top right, on its stem from the roof, lit along its left and its bottom
    const ml = Math.round(X(0.865)), mr = Math.round(X(1.13)), mt = Math.round(Y(0.055)), mb = Math.round(Y(0.165));
    rect(g, (ml + mr) / 2 - 3, 0, 6, mt + 1, "#1d262b");
    rect(g, ml, mt, mr - ml, mb - mt, IN);
    rect(g, ml + 2, mt + 2, mr - ml - 4, mb - mt - 4, "#1f1c1f");
    rect(g, ml, mt, 1, mb - mt, "#2a7a84");
    rect(g, ml + 1, mt + 1, 1, mb - mt - 2, "#1a4248");
    rect(g, ml, mb - 1, mr - ml, 1, "#246972");
    const mid = X(0.82);  // on a very wide screen, the pillar on the far side too, the car's middle between them
    for (let y = top + 1; y < foot; y++) {
      const e = Math.round(2 * mid - inner(y));
      if (e >= W) continue;
      rect(g, e + 1, y, Math.round(F * 0.07), 1, "#212f38");
      px(g, e, y, CY);
    }
    // the dashboard: the cowl under the glass, dark; its front edge catching the night in two lit lines; behind the
    // wheel its face, dark; on the passenger's side a wide lit slope, in bands, parted by its seams
    const d0 = inner(foot) - 3, ly = Math.round(Y(0.622));
    rect(g, d0, foot, W - d0, ly - foot, "#1d1c21");
    [["#0a2730", 1], ["#53abb2", 1], ["#163e4a", 1], ["#43aeb9", 2], ["#39a2ad", 1], ["#25696d", 1], ["#1c545a", 1],
      ["#243e43", 1]].reduce((y, [col, n]) => { rect(g, d0, y, W - d0, n, col); return y + n; }, ly);
    const [wx, wy, R] = this.wheel = [X(0.39), Y(0.968), Y(0.31)];
    const steps = [[ly + 6, "#073c43"], [ly + 7, "#5aa6af"], [ly + 8, "#286e74"], [Y(0.68), "#22565d"],
      [Y(0.717), "#193f45"], [Y(0.756), "#1f343c"], [Y(0.77), null]];
    for (let x = Math.round(X(0.5)); x < W; x++) {
      for (let k = 0; k < steps.length - 1; k++) {
        for (let y = Math.round(steps[k][0]); y < Math.round(steps[k + 1][0]); y++) {
          if (Math.hypot(x + 0.5 - wx, y + 0.5 - wy) > R + 4) px(g, x, y, steps[k][1]);
        }
      }
    }
    for (let i = 0; i <= 40; i++) {  // a seam curving down the slope, and a short one across its top
      const s = i / 40, a = (1 - s) ** 2, m = 2 * (1 - s) * s, e = s * s;
      px(g, a * X(0.704) + m * X(0.762) + e * X(0.766), a * (ly + 1) + m * Y(0.64) + e * Y(0.725), "#0f2a30");
    }
    line(g, X(0.836), ly - 1, X(0.88), ly + 7, "#0f2a30");
    // down the middle, the radio and the vents: two grilles of slats, a slider in each; the tape deck, its station in
    // orange and its slot lit; the clock's window; two dials under it all
    const cl = Math.round(X(0.69)), cr = Math.round(X(0.99)), ct = Math.round(Y(0.755));
    rect(g, cl, ct, cr - cl, H - ct, "#23262e");
    rect(g, cl, ct, cr - cl, 1, "#2d323b");
    for (const [l, rr] of [[X(0.712), X(0.814)], [X(0.825), X(0.927)]]) {
      const vt = Math.round(Y(0.766)), vb = Math.round(Y(0.806)), L = Math.round(l), Rr = Math.round(rr);
      rect(g, L, vt, Rr - L, vb - vt, "#1a1d23");
      for (let y = vt + 1; y < vb - 1; y += 2) rect(g, L + 1, y, Rr - L - 2, 1, "#2a313b");
      rect(g, Math.round((L + Rr) / 2) - 2, vt + 2, 4, 2, "#3a4652");
      rect(g, L, vb, Rr - L, 1, "#2f3741");
    }
    const rl = Math.round(X(0.704)), rr = Math.round(X(0.854)), rt = Math.round(Y(0.88)), rb = Math.round(Y(0.936));
    rect(g, rl, rt, rr - rl, rb - rt, "#1c1f25");
    rect(g, rl, rt, rr - rl, 1, "#2f3741");
    for (let i = 0; i < 6; i++) rect(g, rl + 3 + i * 3, rt + 3, 2, 2, "#2c333c");
    rect(g, X(0.803), rt + 2, F * 0.047, 3, "#3a1c0e");
    for (let i = 0; i < 4; i++) px(g, X(0.806) + i * 2, rt + 3, i ? "#c86a32" : "#e88a48");
    rect(g, X(0.792), rb - 3, F * 0.058, 1, "#b85c26");
    const kl = Math.round(X(0.858)), kt = Math.round(Y(0.815));
    rect(g, kl, kt, 23, 9, "#2a1408");
    rect(g, kl, kt, 23, 1, "#3a2414");
    this.radio = [kl + 2, kt + 2];
    for (let i = 0; i < 3; i++) rect(g, kl + 2 + i * 7, kt + 11, 5, 2, "#2c333c");
    for (const [dx, red] of [[X(0.733), true], [X(0.935), false]]) {
      disc(g, dx, Y(0.97), 5, "#2f3741");
      disc(g, dx, Y(0.97), 4, "#1a1d23");
      if (red) for (let a = -1.2; a < 0.9; a += 0.15) px(g, dx + Math.cos(a) * 5, Y(0.97) + Math.sin(a) * 5, "#a8392e");
      line(g, dx, Y(0.97), dx - 2, Y(0.97) + 2, "#5a6670");
    }
    // through the wheel: the hood over the gauges, orange round its rim, the gauges in it, and the warning lights
    for (let a = Math.PI * 1.1; a < Math.PI * 1.8; a += 0.006) {
      px(g, wx + Math.cos(a) * Y(0.285), wy + Math.sin(a) * Y(0.285), "#8a5526");
      px(g, wx + Math.cos(a) * Y(0.278), wy + Math.sin(a) * Y(0.278), "#5d3d1f");
    }
    this.gauges = [[X(0.34), Y(0.767), 10, Math.PI * 1.72], [X(0.461), Y(0.777), 10, Math.PI * 1.93],
      [X(0.266), Y(0.81), 4, Math.PI * 1.3], [X(0.537), Y(0.808), 4, Math.PI * 1.62]];
    for (const [x, y, rr] of this.gauges) {
      disc(g, x, y, rr, "#1f1b1d");
      for (let a = 0; a < 6.283; a += 0.05) px(g, x + Math.cos(a) * rr, y + Math.sin(a) * rr, "#3a2418");
      for (let a = Math.PI * 0.75; a <= Math.PI * 2.26; a += Math.PI / (rr > 6 ? 8 : 3)) {
        px(g, x + Math.cos(a) * (rr - 1.5), y + Math.sin(a) * (rr - 1.5), "#c2773a");
        if (rr > 6) px(g, x + Math.cos(a) * (rr - 2.5), y + Math.sin(a) * (rr - 2.5), "#7a4a26");
      }
    }
    for (const [l, w, col] of [[0.331, 0.01, "#c83a3a"], [0.394, 0.021, "#5cd66e"], [0.453, 0.009, "#c83a3a"],
      [0.464, 0.009, "#c83a3a"], [0.488, 0.008, "#e0b040"]]) rect(g, X(l), Y(0.843), Math.max(2, F * w), 2, col);
    // the wheel's rim: thin, bright along its top where the glass lights it, and fading down its sides into the dark,
    // the side towards the door window a little lighter
    const rim = parse([[0, "#13262c"], [0.2, "#0f4d58"], [0.45, "#277e8a"], [0.7, "#3faab6"], [0.88, "#54c8d3"], [1, "#72d9e0"]]);
    const img = g.getImageData(0, 0, W, H), d = img.data;
    for (let y = Math.floor(wy - R - 3); y < H; y++) {
      for (let x = Math.floor(wx - R - 3); x <= Math.ceil(wx + R + 3); x++) {
        if (x < 0 || x >= W) continue;
        const dx = x + 0.5 - wx, dy = y + 0.5 - wy, dist = Math.hypot(dx, dy), off = dist - R;
        if (Math.abs(off) > 2) continue;
        const up = -dy / dist, side = dx / dist;
        let v = clamp(up * 1.05 - side * 0.22 * (1 - up) - 0.05, 0, 1) * (off < -1 ? 1 : off < 1 ? 0.92 : 0.7);
        v = Math.floor(v * 6 + dith(x, y) * 0.8) / 6;
        const col = ramp(rim, v), i = (y * W + x) * 4;
        d[i] = col[0]; d[i + 1] = col[1]; d[i + 2] = col[2]; d[i + 3] = 255;
      }
    }
    g.putImageData(img, 0, 0);
    // its middle: the bar across, lit; the spokes down to the rim, buttons on the right one; the hub and its badge
    const bt = Math.round(Y(0.853)), bb = Math.round(Y(0.884));
    for (let y = bt; y <= bb; y++) {
      const f = (y - bt) / (bb - bt), l = Math.round(X(0.305) - f * F * 0.016), e = Math.round(X(0.476) + f * F * 0.012);
      rect(g, l, y, e - l, 1, y === bt ? "#1e5157" : y === bb ? "#405358" : y === bt + 1 ? "#3a98a3" : "#2a8490");
      px(g, l, y, "#1f6f7a");
      px(g, e, y, "#22606a");
    }
    disc(g, X(0.48), Y(0.872), 3, "#2a7a85");
    poly(g, [[X(0.49), Y(0.88)], [X(0.64), Y(0.93)], [X(0.635), Y(1.0)], [X(0.5), Y(1.0)]], "#211d21");
    line(g, X(0.49), Y(0.885), X(0.64), Y(0.932), "#2a8c98");
    line(g, X(0.49), Y(0.89), X(0.64), Y(0.937), "#1f6f7a");
    rect(g, X(0.505), Y(0.925), F * 0.1, Y(0.06), "#1f1b1f");
    rect(g, X(0.505), Y(0.925), 1, Y(0.06), "#3a3436");
    for (const y of [Y(0.946), Y(0.96)]) px(g, X(0.526), y, "#c2773a");
    const bx = Math.round(X(0.572)), by = Math.round(Y(0.958));
    for (const [dx, dy] of [[0, -2], [-1, -1], [1, -1], [-2, 0], [2, 0], [-1, 1], [1, 1], [0, 2]]) px(g, bx + dx, by + dy, "#d9773a");
    poly(g, [[X(0.29), Y(0.865)], [X(0.145), Y(0.89)], [X(0.155), Y(0.95)], [X(0.3), Y(0.9)]], "#211d21");
    line(g, X(0.29), Y(0.866), X(0.145), Y(0.89), "#2a7480");
    ellipse(g, X(0.39), Y(0.99), Math.round(F * 0.09), Math.round(Y(0.09)), "#2b2529");
    ellipse(g, X(0.39), Y(0.99), Math.round(F * 0.09) - 1, Math.round(Y(0.09)) - 1, "#201c20");
    const hx = Math.round(X(0.38)), hy = Math.round(Y(0.955));
    for (let a = 0; a < 6.283; a += 0.12) px(g, hx + Math.cos(a) * 5, hy + Math.sin(a) * 5, "#2b5a64");
    px(g, hx, hy, "#2b5a64");
    this.hand(g);
    return c;
  },
  hand(g) {  // your left hand on the wheel, the fist round the rim, the arm down out of sight
    const { X, Y } = this, ox = Math.round(X(0.12)), oy = Math.round(Y(0.7)), h = 56;
    // in pixels from (ox, oy): the fist's top column by column from its left, the knuckles along the rim from the
    // little finger up to the first, the notch where the rim goes in, and the thumb round its inside; its sides row
    // by row, narrowing to the wrist; and the arm below, widening as it comes nearer
    const crown = [, , , , 12, 10, 9, 9, 8, 7, 7, 6, 4, 4, 4, 3, 2, 2, 2, 3, 5, 9, 9, 9, 9, 10, 10, 11, 13];
    const left = y => y < 18 ? 4 : y < 23 ? [5, 5, 6, 7, 8][y - 18] : y < 27 ? 8 : Math.round(8 - (y - 26) * 0.24);
    const right = y => y < 17 ? 28 : y < 23 ? [27, 27, 26, 25, 24, 23][y - 17] : y < 27 ? 22 : Math.round(22 - (y - 26) * 0.04);
    const inside = (x, y) => x >= left(y) && x <= right(y) && (y >= 23 || (crown[x] !== undefined && y >= crown[x]));
    const T = ["#1f2a2e", "#253236", "#2b393d", "#324246", "#3b4b4f", "#475659", "#565f60", "#677070"];
    const peaks = [6, 9, 12, 13, 16, 17, 18], dips = [7, 8, 10, 11, 14, 15];
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < 31; x++) {
        if (!inside(x, y)) continue;
        const up = y < 23 ? y - crown[x] : 99, l = x - left(y), r = right(y) - x;
        let k, col;
        if (y < 23) {  // the fist, lit from the glass above, its knuckles brightest, and catching it down its right edge
          k = up === 0 ? (peaks.includes(x) ? 7 : dips.includes(x) ? 5 : 6) : up === 1 ? 5 : up === 2 ? 4 :
            y < 13 || (y < 16 && dith(x, y) < (16 - y) / 3) ? 3 : 2;
          if (up > 3 && up < 6 && x < 20) k = Math.min(k, 2);  // the shade under the knuckles
          if (r === 0 && up > 0) k = 5;
          else if (l === 0 && up > 0) k = Math.max(k, 3);
        } else if (y < 28) {  // the wrist, in the fist's shadow
          k = r === 0 ? 4 : l === 0 ? 2 : y < 25 || dith(x, y) < 0.5 ? 1 : 2;
        } else {  // the arm, lit a little blue down its left from the door's window
          k = r === 0 ? 4 : r < 4 ? 1 : 2;
          col = l === 0 ? "#36535c" : l === 1 ? "#2f4750" : null;
        }
        px(g, ox + x, oy + y, col || T[k]);
      }
    }
    // the gaps between the fingers under the dips between the knuckles, and the crease where the thumb meets the hand
    for (const [x, y] of [[8, 9], [8, 10], [11, 7], [11, 8], [15, 4], [15, 5], [21, 10], [21, 11], [20, 12], [20, 13], [19, 14]]) {
      px(g, ox + x, oy + y, T[0]);
    }
  },
  draw(g, t) {
    const { W, H, hz, vx, X } = this;
    g.drawImage(this.back, 0, 0);
    stars(g, this.stars, t, "#3d5c5e", "#86a4a3", "#e2f0ee");
    for (const c of this.clouds) g.drawImage(c.img, Math.round(wrap(c.x - t * c.v, W + c.w) - c.w), Math.round(c.y));
    const far = Math.round(Math.sin(t * 0.13) * 3);  // a lorry far ahead, its tail lights
    rect(g, vx - 4 + far, hz - 2, 4, 2, "#557f88");
    px(g, vx - 4 + far, hz - 1, "#ff5a4a");
    px(g, vx - 1 + far, hz - 1, "#ff5a4a");
    const end = X(1.22);
    for (let k = 0; k < 10; k++) {  // the line down the middle of the road, coming at you: y = hz + 30 / distance
      const d = wrap(k * 2 - t * 4, 20) + 0.7, y0 = hz + 30 / (d + 0.4), y1 = hz + 30 / d;
      for (let y = Math.ceil(y0); y <= y1 && y < H; y++) {
        const f = (y - hz) / (H - hz), w = Math.max(1, Math.round(f * 16));
        rect(g, vx + (end - vx) * f - w / 2, y, w, 1, f < 0.05 ? "#566e70" : f < 0.1 ? "#8aa6a6" : "#cfdedd");
      }
    }
    g.drawImage(this.front, 0, 0);
    for (const [i, [x, y, rr, a0]] of this.gauges.entries()) {  // the needles, never quite still
      const a = a0 + Math.sin(t * (0.9 + i * 0.3)) * 0.03 + (i === 0 ? Math.sin(t * 0.21) * 0.05 : 0);
      line(g, x, y, x + Math.cos(a) * (rr - 1.5), y + Math.sin(a) * (rr - 1.5), "#ffa24a");
      px(g, x, y, "#ffd9a0");
    }
    bloom(g, this.radio[0] + 9, this.radio[1] + 2, 10, "#ff7a2a", 0.16);
    digits(g, clock(), this.radio[0], this.radio[1], "#e88a44");
  },
};

// --------------------------------------------------------------------------------------------- 2: sunset drive
// Along the coast as the sun goes down: a striped sun sinking behind the hills, long thin clouds lit from below,
// gulls, the hills drifting by slowly with the light along their tops, palms and a guardrail rushing past, and a
// little coupe cruising towards the sun, its roof catching the last of it and its lights on. Everything that moves
// goes round and comes back off the screen, so it plays on forever with no seam
SCENES["sunset-drive"] = {
  label: "Sunset drive",
  init(W, H) {
    const r = rng(23), hz = this.hz = 112;
    const back = this.back = layer(W, H), b = back.getContext("2d");
    gradient(b, 0, 0, W, hz + 1, [[0, "#24184a"], [0.32, "#5a2d6e"], [0.62, "#c4506e"], [0.86, "#f08a62"], [1, "#ffc07a"]]);
    const sx = Math.round(W * 0.6), sy = hz - 4;
    glow(b, sx, sy - 10, 90, "#ff8a5a", 0.45);
    glow(b, sx, sy - 8, 40, "#ffc27a", 0.5);
    const sun = parse([[0, "#fff0a0"], [0.5, "#ffb45a"], [1, "#ff6a5a"]]), gaps = [18, 14, 15, 10, 11, 12, 6, 7, 8, 9];
    for (let y = -26; y <= 0; y++) {  // the sun, cut into bands that widen as it goes down behind the hills
      if (gaps.includes(-y)) continue;
      const w = Math.floor(Math.sqrt(26 * 26 - y * y));
      rect(b, sx - w, sy + y, 2 * w + 1, 1, css(ramp(sun, (y + 26) / 26)));
    }
    this.streaks = Array.from({ length: 7 }, () => ({ x: r() * W, y: 18 + r() * 56, w: 30 + r() * 60, v: 0.6 + r() * 0.9 }));
    const strip = (seed, base, amp, color, rim, period) => {  // a band of hills twice the screen wide, to scroll by
      const c = layer(W * 2, H), g = c.getContext("2d"), n = noise(rng(seed), W, period);
      for (let x = 0; x < W * 2; x++) {
        const top = Math.round(base - n[x % W] * amp);
        rect(g, x, top, 1, base + 40 - top, color);
        px(g, x, top, rim);
      }
      return c;
    };
    this.far = strip(5, hz + 1, 16, "#4b2f66", "#7a4a7e", 70);
    this.near = strip(9, hz + 18, 12, "#2d1c45", "#46295a", 44);
    this.palmSpan = W + 220;  // room for the widest palm off each side of the screen, so they come and go unseen
    this.palms = Array.from({ length: 5 }, (_, i) => ({ img: palm(44 + Math.floor(r() * 20), "#0c0714", 0, 0.18 + r() * 0.2),
      x: (i * this.palmSpan) / 5 + r() * 24 }));
    this.birds = Array.from({ length: 4 }, () => ({ x: r() * W, y: 30 + r() * 40, v: 3 + r() * 4, p: r() * 6 }));
    this.car = this.coupe();
  },
  coupe() {  // a little coupe in profile, facing the sun: its body, the sky in its windows, the light along it
    const c = layer(38, 9), g = c.getContext("2d");
    solid(g, [[0, 8], [0.5, 4.6], [8, 3.6], [12, 0.6], [19.5, 0.6], [25.5, 3.6], [35, 4.8], [36.5, 8]], "#0d0912");
    solid(g, [[9.2, 3.5], [12.6, 1.5], [16, 1.5], [16, 3.5]], "#3a2840");
    solid(g, [[17, 1.5], [19.2, 1.5], [24, 3.5], [17, 3.5]], "#4a3050");
    rect(g, 12, 0, 8, 1, "#ff9a8a");  // the roof and the hood, catching the sun ahead
    line(g, 25, 3, 35, 4, "#ff9a8a");
    line(g, 1, 4, 8, 3, "#c8607a");  // the edge of the boot, and the crease down its side
    rect(g, 2, 5, 32, 1, "#2a1830");
    rect(g, 0, 5, 1, 2, "#ff3b3b");  // the tail light, the headlight
    rect(g, 35, 5, 2, 1, "#ffe6b0");
    return c;
  },
  draw(g, t) {
    const { W, H } = this, hz = this.hz;
    g.drawImage(this.back, 0, 0);
    for (const s of this.streaks) {  // long thin clouds, lit from below
      const x = Math.round(wrap(s.x - t * s.v, W + s.w) - s.w);
      rect(g, x, s.y, s.w, 1, "#ffb08a");
      rect(g, x + 4, s.y + 1, s.w - 8, 1, "#a8507a");
    }
    for (const bd of this.birds) {  // gulls, flapping now and then
      const x = wrap(bd.x - t * bd.v, W + 20) - 10, y = bd.y + Math.sin(t * 0.7 + bd.p) * 2, up = Math.sin(t * 5 + bd.p) > 0;
      px(g, x, y, "#3a2042"); px(g, x - 1, y + (up ? -1 : 1), "#3a2042"); px(g, x + 1, y + (up ? -1 : 1), "#3a2042");
      px(g, x - 2, y + (up ? -1 : 0), "#3a2042"); px(g, x + 2, y + (up ? -1 : 0), "#3a2042");
    }
    g.drawImage(this.far, -Math.round(wrap(t * 2.2, W)), 0);
    g.drawImage(this.near, -Math.round(wrap(t * 7, W)), 0);
    for (const p of this.palms) {  // palms along the far side of the road, their tops against the hills and the sky
      const x = Math.round(wrap(p.x - t * 70, this.palmSpan) - 110);
      g.drawImage(p.img, x, hz + 28 - p.img.height);
    }
    rect(g, 0, hz + 30, W, 4, "#20142c");  // the road's shoulder, the road, its dashes
    rect(g, 0, hz + 34, W, 18, "#1b1222");
    rect(g, 0, hz + 34, W, 1, "#3e2944");
    for (let x = -Math.round(wrap(t * 70, 24)); x < W; x += 24) rect(g, x, hz + 43, 10, 1, "#e09a72");
    rect(g, 0, hz + 52, W, H - hz - 52, "#120c18");
    rect(g, 0, hz + 26, W, 1, "#2a1a33");  // the guardrail and its posts
    for (let x = -Math.round(wrap(t * 70, 16)); x < W; x += 16) rect(g, x, hz + 26, 2, 7, "#120a19");
    const cx = Math.round(W * 0.3), road = hz + 48, bounce = Math.round(Math.max(0, Math.sin(t * 9)) * 0.7);  // the car
    ellipse(g, cx + 18, road, 19, 1, "#0d0912");
    g.drawImage(this.car, cx, road - 10 - bounce);
    for (const wx of [cx + 7, cx + 29]) {  // its wheels, turning
      disc(g, wx, road - 3, 3, "#07050a");
      const a = t * 14;
      px(g, wx + Math.round(Math.cos(a) * 1.5), road - 3 + Math.round(Math.sin(a) * 1.5), "#5a4a60");
    }
    bloom(g, cx, road - 4 - bounce, 8, "#ff3b3b", 0.7);
    bloom(g, cx + 37, road - 5 - bounce, 6, "#ffd9a0", 0.4);
  },
};

// --------------------------------------------------------------------------------------------- 3: night beach
// Moonlight on a calm sea: the moon's path shimmering on the water, waves rolling in and breaking into foam with a
// faint blue glow, a palm swaying, a lighthouse's beam going round, and now and then a shooting star
SCENES["night-beach"] = {
  label: "Night beach",
  init(W, H) {
    const r = rng(41), hz = this.hz = 100;
    const back = this.back = layer(W, H), b = back.getContext("2d");
    gradient(b, 0, 0, W, hz + 1, [[0, "#050a1c"], [0.45, "#0d1a42"], [0.85, "#1f3266"], [1, "#30477a"]]);
    this.stars = starfield(r, Math.round(W * 0.45), W, hz - 10);
    const mx = this.mx = Math.round(W * 0.3), my = 30;
    glow(b, mx, my, 46, "#3d5590", 0.5);
    glow(b, mx, my, 16, "#b7c4ea", 0.45);
    disc(b, mx, my, 8, "#f1efe0");
    for (const [dx, dy, c] of [[-3, -2, "#d9d6c4"], [2, 1, "#d9d6c4"], [3, -3, "#e3e0cf"], [-1, 4, "#d9d6c4"]]) px(b, mx + dx, my + dy, c);
    gradient(b, 0, hz + 1, W, 40, [[0, "#14244e"], [0.6, "#0d1a3c"], [1, "#0a1432"]], 14);  // the sea
    gradient(b, 0, hz + 41, W, H - hz - 41, [[0, "#1a2140"], [1, "#2a2f4e"]], 14);  // the sand
    for (let i = 0; i < W * 0.6; i++) px(b, r() * W, hz + 44 + r() * (H - hz - 44), r() > 0.5 ? "#353b5c" : "#151a33");
    const lx = this.lx = Math.round(W * 0.9);  // the cliff and the lighthouse on it, a window lit
    for (let x = Math.round(W * 0.8); x < W; x++) {
      const top = Math.round(hz - 5 - Math.sqrt(Math.max(0, x - W * 0.8)) * 1.1 + Math.sin(x * 0.4) * 0.8);
      rect(b, x, top, 1, hz + 6 - top, "#070b1a");
    }
    const ty = this.ly = hz - 30;
    rect(b, lx - 2, ty + 4, 5, 16, "#0d1430");
    rect(b, lx - 2, ty + 8, 5, 2, "#1d2a52");
    rect(b, lx - 3, ty, 7, 4, "#0d1430");
    px(b, lx, ty + 13, "#c9a860");
    this.palmX = Math.round(W * 0.06);
    this.palms = Array.from({ length: 13 }, (_, i) => palm(96, "#04060f", i / 6 - 1, 0.32));  // its sway, in small steps
    this.shoot = null;
  },
  draw(g, t) {
    const { W, H } = this, hz = this.hz;
    g.drawImage(this.back, 0, 0);
    stars(g, this.stars, t, "#2a3a6a", "#7d8fc4", "#eef0ff");
    if (!this.shoot && hash(Math.floor(t / 2), 9) > 0.93) {  // a shooting star, about every half a minute
      this.shoot = { x: W * (0.45 + hash(t, 2) * 0.45), y: 8 + hash(t, 3) * 30, t0: t };
    }
    if (this.shoot) {
      const s = this.shoot, f = (t - s.t0) / 0.9;
      if (f > 1) this.shoot = null;
      else {
        for (let k = 0; k < 10; k++) {
          const ff = f - k * 0.025;
          if (ff < 0) continue;
          px(g, s.x - ff * 70, s.y + ff * 26, k < 2 ? "#ffffff" : k < 5 ? "#a9b8ee" : "#4d5f9a");
        }
      }
    }
    // the lighthouse's beam going round: long across the sky as it turns past, fading with distance, and a flash as
    // it faces you
    const turn = t * 0.6, along = Math.sin(turn), toward = Math.cos(turn), ly = this.ly + 2, lx = this.lx;
    if (Math.abs(along) > 0.06) {
      const reach = Math.abs(along), end = lx - W * 0.85 * along, spread = 2 + 9 * reach;
      const beam = g.createLinearGradient(lx, ly, end, ly);
      beam.addColorStop(0, `rgba(255,236,180,${(0.1 + 0.12 * reach).toFixed(3)})`);
      beam.addColorStop(1, "rgba(255,236,180,0)");
      g.save();
      g.globalCompositeOperation = "lighter";
      g.fillStyle = beam;
      g.beginPath();
      g.moveTo(lx, ly - 1);
      g.lineTo(end, ly - 3 - spread);
      g.lineTo(end, ly - 3 + spread);
      g.lineTo(lx, ly + 1);
      g.closePath();
      g.fill();
      g.restore();
    }
    rect(g, lx - 1, ly - 1, 3, 2, toward > 0.8 ? "#fffbe0" : "#ffe7a0");
    bloom(g, lx, ly, 10, "#ffd890", 0.3 + 0.7 * Math.max(0, toward) ** 6);
    for (let y = hz + 2; y < hz + 40; y += 1) {  // the moon's path on the water
      const f = (y - hz) / 40, w = 4 + f * 22;
      if (hash(y, Math.floor(t * 2.5)) < 0.45) continue;
      const o = (hash(y * 3, Math.floor(t * 2.5)) - 0.5) * w, len = 1 + Math.floor(hash(y, 7) * (2 + f * 5));
      rect(g, this.mx + o, y, len, 1, f < 0.3 ? "#e3e6ff" : "#9aa6dc");
    }
    for (let i = 0; i < 3; i++) {  // waves rolling in, breaking into patches of foam, spreading up the sand and going
      const p = fract(t / 9 + i / 3), y0 = hz + 30 + p * 16, fade = Math.sin(p * Math.PI);
      for (let x = 0; x < W; x++) {
        const foam = Math.sin(x * 0.09 + i * 5.3 + p * 2) * 0.6 + Math.sin(x * 0.031 + i * 1.7) * 0.4;
        if (foam < 0.25 - fade * 1.2) continue;
        const y = Math.round(y0 + Math.sin(x * 0.045 + i * 2.1 + t * 0.35) * 1.6 + Math.sin(x * 0.13 + i + t * 0.8) * 0.6);
        px(g, x, y, fade > 0.55 ? "#c4d6f6" : "#6f84b8");
        if (fade > 0.3) px(g, x, y + 1, "#34477c");  // the wet edge it leaves
        if (fade > 0.75 && hash(x, Math.floor(t * 4) + i) > 0.985) px(g, x, y - 1, "#7ff0ff");  // the glow in the foam
      }
    }
    const pose = Math.round((Math.sin(t * 0.55) + 1) * 6);
    g.drawImage(this.palms[pose], this.palmX - 40, H - 96);
  },
};

// --------------------------------------------------------------------------------------------- 4: morning beach
// Early morning by the sea: a soft pastel sky, the sun just up, clouds drifting, the water sparkling, a sailboat on
// the horizon, gulls gliding, and the waves washing up the sand by an umbrella
SCENES["morning-beach"] = {
  label: "Morning beach",
  init(W, H) {
    const r = rng(77), hz = this.hz = 104;
    const back = this.back = layer(W, H), b = back.getContext("2d");
    gradient(b, 0, 0, W, hz + 1, [[0, "#86bde4"], [0.45, "#b9d4ee"], [0.78, "#f4cdcb"], [1, "#ffd9aa"]]);
    const sx = this.sx = Math.round(W * 0.42), sy = hz - 16;
    glow(b, sx, sy, 80, "#ffd59a", 0.55);
    glow(b, sx, sy, 24, "#ffefc8", 0.65);
    disc(b, sx, sy, 8, "#fff8e6");
    gradient(b, 0, hz + 1, W, 34, [[0, "#8fcfd8"], [0.5, "#66b5c8"], [1, "#7fcdd0"]], 16);  // the sea
    rect(b, 0, hz + 1, W, 1, "#cdeef0");
    gradient(b, 0, hz + 35, W, H - hz - 35, [[0, "#e7bb8e"], [0.25, "#f3d2a2"], [1, "#efc791"]], 16);  // the sand
    for (let i = 0; i < W * 0.5; i++) px(b, r() * W, hz + 44 + r() * (H - hz - 44), r() > 0.5 ? "#e0b582" : "#f8dfb6");
    for (let i = 0; i < 9; i++) px(b, W * 0.25 + i * 7 + (i % 2) * 2, hz + 60 + i * 3, "#d9a978");  // footprints
    const ux = Math.round(W * 0.56), uy = hz + 40;  // the umbrella, its shade, the towel under it
    ellipse(b, ux + 6, uy + 28, 20, 4, "#dfb184");
    rect(b, ux - 12, uy + 24, 26, 8, "#5fb3c2");
    for (let i = 0; i < 26; i += 6) rect(b, ux - 12 + i, uy + 24, 2, 8, "#f6f1e8");
    line(b, ux, uy - 14, ux + 4, uy + 26, "#7a5a40");
    for (let y = -10; y <= 0; y++) {
      const w = Math.floor(Math.sqrt(100 - y * y) * 2.2);
      for (let x = -w; x <= w; x++) px(b, ux + x + (y + 10) * 0.2, uy - 14 + y + 10, Math.floor((x + w) / 6) % 2 ? "#f9efe4" : "#e8584c");
    }
    this.clouds = Array.from({ length: 4 }, (_, i) => {
      const w = 44 + Math.floor(r() * 50);
      return { img: cloud(r, w, 16 + Math.floor(r() * 8), "#fffaf6", "#f0c9cf", "#ffffff"),
        x: r() * (W + w), y: 12 + i * 16 + r() * 6, v: 1.2 + r() * 1.4, w };
    });
    this.gulls = Array.from({ length: 3 }, () => ({ x: r() * W, y: 26 + r() * 40, v: 4 + r() * 3, p: r() * 6 }));
    this.glints = Array.from({ length: Math.round(W * 0.35) }, () => {
      const near = r() < 0.55;
      return { x: near ? sx + (r() - 0.5) * 50 : r() * W, y: hz + 2 + r() * 30, p: r() * 6.28, s: 1 + r() * 3 };
    });
  },
  draw(g, t) {
    const { W, H } = this, hz = this.hz;
    g.drawImage(this.back, 0, 0);
    for (const c of this.clouds) g.drawImage(c.img, Math.round(wrap(c.x + t * c.v, W + c.w) - c.w), Math.round(c.y));
    for (const s of this.glints) if (Math.sin(t * s.s + s.p) > 0.86) px(g, s.x, s.y, "#ffffff");  // the sea sparkling
    const bx = Math.round(wrap(W * 0.15 + t * 1.6, W + 20) - 10);  // a sailboat, far off
    rect(g, bx - 3, hz - 1, 8, 1, "#4a5d6e");
    line(g, bx + 1, hz - 2, bx + 1, hz - 9, "#4a5d6e");
    for (let i = 0; i < 6; i++) rect(g, bx + 2, hz - 8 + i, Math.max(1, i - 1), 1, "#fbf6ee");
    for (const gl of this.gulls) {  // gulls gliding, a flap now and then
      const x = wrap(gl.x + t * gl.v, W + 20) - 10, y = gl.y + Math.sin(t * 0.5 + gl.p) * 3;
      const up = Math.sin(t * 3 + gl.p) > 0.6;
      px(g, x, y, "#5d6b7b");
      px(g, x - 1, y - (up ? 1 : 0), "#5d6b7b"); px(g, x - 2, y - (up ? 2 : 1), "#5d6b7b");
      px(g, x + 1, y - (up ? 1 : 0), "#5d6b7b"); px(g, x + 2, y - (up ? 2 : 1), "#5d6b7b");
    }
    for (let i = 0; i < 3; i++) {  // the waves washing up the sand and back
      const p = fract(t / 7.5 + i / 3), reach = Math.sin(p * Math.PI), y0 = hz + 34 + reach * 10;
      for (let x = 0; x < W; x++) {
        const y = y0 + Math.sin(x * 0.05 + i * 1.7 + t * 0.3) * 1.6;
        if (hash(x, i + 4) > reach * 1.2) continue;
        px(g, x, y, "#ffffff");
        if (reach > 0.4) px(g, x, y + 1, "#e0b48a");  // wet sand behind it
      }
    }
  },
};

// --------------------------------------------------------------------------------------------- 5: city terrace
// A rooftop terrace at night: string lights swaying, a mug steaming on the table, plants by the railing, and the city
// beyond with its windows coming on and off, a tower's red light blinking, cars streaming over a bridge, a plane
SCENES["city-terrace"] = {
  label: "City terrace",
  init(W, H) {
    const r = rng(101), hz = this.hz = 120;
    const back = this.back = layer(W, H), b = back.getContext("2d");
    gradient(b, 0, 0, W, hz + 1, [[0, "#09071d"], [0.55, "#1b1442"], [0.9, "#3d2a62"], [1, "#55356e"]]);
    this.stars = starfield(r, Math.round(W * 0.12), W, 60);
    const mx = Math.round(W * 0.82);
    glow(b, mx, 22, 22, "#5a4a8a", 0.5);
    disc(b, mx, 22, 5, "#f4ead8");
    this.windows = [];
    const row = (seed, base, lo, hi, color, lit, chance, wide) => {  // a row of buildings and their windows
      const rr = rng(seed);
      for (let x = -4; x < W;) {
        const w = wide[0] + Math.floor(rr() * wide[1]), h = lo + Math.floor(rr() * (hi - lo)), top = base - h;
        rect(b, x, top, w, h + 40, color);
        if (rr() < 0.3) rect(b, x + Math.floor(w / 2), top - 4 - Math.floor(rr() * 6), 1, 6, color);  // an antenna
        for (let y = top + 3; y < base - 2; y += 3) {
          for (let wx = x + 2; wx < x + w - 2; wx += 3) {
            if (rr() < chance) this.windows.push({ x: wx, y, c: lit[Math.floor(rr() * lit.length)], p: rr() * 100, s: rr() });
          }
        }
        x += w + Math.floor(rr() * 3);
      }
    };
    row(3, hz - 4, 18, 46, "#1c1638", ["#3d3366", "#46396e"], 0.22, [10, 14]);
    row(5, hz + 2, 22, 62, "#120e2a", ["#ffcf7a", "#ffb35a", "#8fd8ff", "#ffe6b0"], 0.18, [12, 16]);
    this.tower = [Math.round(W * 0.34), hz - 74];
    rect(b, this.tower[0] - 3, this.tower[1] + 6, 7, 80, "#100c26");
    rect(b, this.tower[0], this.tower[1], 1, 7, "#100c26");
    this.bridge = hz - 1;
    rect(b, 0, this.bridge + 1, W, 1, "#2a2048");
    for (let x = 6; x < W; x += 22) rect(b, x, this.bridge - 6, 1, 7, "#2a2048");
    rect(b, 0, hz + 4, W, H - hz - 4, "#0b0918");  // the terrace: floor, railing, posts
    for (let y = hz + 26; y < H; y += 7) rect(b, 0, y, W, 1, "#151228");
    rect(b, 0, hz + 6, W, 2, "#2c2440");
    rect(b, 0, hz + 6, W, 1, "#4a3d62");
    rect(b, 0, hz + 18, W, 1, "#2c2440");
    for (let x = 4; x < W; x += 14) rect(b, x, hz + 8, 1, 10, "#231c36");
    const tx = this.tableX = Math.round(W * 0.74);  // the table and the mug on it
    ellipse(b, tx, hz + 30, 18, 4, "#2c2238");
    for (let x = -17; x <= 17; x++) px(b, tx + x, hz + 30 - Math.round(4 * Math.sqrt(1 - (x / 18) ** 2)), "#4a3a5c");
    rect(b, tx - 1, hz + 34, 3, 26, "#1e1828");
    rect(b, tx - 4, hz + 22, 7, 7, "#e2d8cc");
    rect(b, tx + 3, hz + 24, 2, 3, "#e2d8cc");
    rect(b, tx - 4, hz + 22, 7, 1, "#8a5a3a");
    this.plants = [[Math.round(W * 0.07), 1.3], [Math.round(W * 0.2), 0.9], [Math.round(W * 0.93), 1.1]];
    for (const [x, s] of this.plants) {  // their pots, lit along the rim by the string of lights
      const w = Math.round(9 * s), top = hz + 22, h = Math.round(13 * s);
      solid(b, [[x - w, top], [x + w, top], [x + w - 2, top + h], [x - w + 2, top + h]], "#3a2420");
      rect(b, x - w - 1, top, 2 * w + 2, 2, "#4e3026");
      rect(b, x - w - 1, top, 2 * w + 2, 1, "#6a4232");
    }
    this.cars = Array.from({ length: 12 }, (_, i) => ({ x: r() * W, v: (i % 2 ? -1 : 1) * (14 + r() * 10) }));
  },
  draw(g, t) {
    const { W, H } = this, hz = this.hz;
    g.drawImage(this.back, 0, 0);
    stars(g, this.stars, t, "#2a2450", "#6a5c9a", "#e8e0ff");
    for (const w of this.windows) {  // windows coming on and off, slowly, one here and one there
      const on = hash(w.p, Math.floor(t / (6 + w.s * 14))) > 0.25;
      if (on) px(g, w.x, w.y, w.c);
    }
    if (Math.floor(t / 1.4) % 2 === 0) {  // the tower's light
      px(g, this.tower[0], this.tower[1], "#ff4a4a");
      bloom(g, this.tower[0], this.tower[1], 5, "#ff4a4a", 0.6);
    }
    for (const c of this.cars) {  // cars on the bridge, lights one way and tail lights the other
      const x = wrap(c.x + t * c.v, W);
      px(g, x, this.bridge, c.v > 0 ? "#fff3d0" : "#ff4a4a");
    }
    const plane = fract(t / 38);  // a plane, high up, now and then
    if (plane < 0.6) {
      const x = W * 1.1 - plane / 0.6 * W * 1.2, y = 34 - plane * 18;
      if (Math.floor(t * 1.5) % 2) px(g, x, y, "#ff6a6a");
      px(g, x + 2, y, "#e8e8ff");
    }
    const tx = this.tableX;  // steam from the mug
    for (let i = 0; i < 3; i++) {
      for (let k = 0; k < 8; k++) {
        const f = fract(t * 0.35 + i / 3 + k / 24), y = hz + 20 - f * 20, x = tx - 2 + i * 2 + Math.sin(f * 7 + t + i) * 2;
        if (hash(k, i) > 0.4) px(g, x, y, `rgba(230,220,255,${(0.45 * (1 - f)).toFixed(2)})`);
      }
    }
    for (const [x, s] of this.plants) {  // ferns by the railing, swaying a little in the air up here
      for (let k = 0; k < 11; k++) {
        const a = -1.35 + k * 0.27 + Math.sin(t * 0.8 + x + k * 0.3) * 0.05, len = 20 * s * (0.75 + 0.25 * Math.cos(k * 1.7));
        const dx = Math.sin(a), dy = -Math.cos(a);
        for (let i = 1; i < len; i++) {
          const f = i / len, xx = x + dx * i, yy = hz + 22 + dy * i + f * f * len * 0.45 * Math.abs(dx);
          px(g, xx, yy, k % 2 ? "#1d4128" : "#16301f");
          if (i > 2 && i % 2 === 0) {  // its leaflets, both sides, pointing on up the frond
            const leaf = 1 + 2.2 * Math.sin(Math.PI * f) * s;
            line(g, xx, yy, xx - dy * leaf + dx * leaf * 0.6, yy + dx * leaf + dy * leaf * 0.6, "#1f4a2c");
            line(g, xx, yy, xx + dy * leaf + dx * leaf * 0.6, yy - dx * leaf + dy * leaf * 0.6, "#1f4a2c");
          }
        }
      }
    }
    const sag = 20 + Math.sin(t * 0.5) * 1.5;  // the string of lights across the top
    for (let x = 0; x <= W; x += 2) {
      const f = x / W, y = 6 + f * 6 + Math.sin(f * Math.PI) * sag;
      px(g, x, y, "#1a1426");
    }
    for (let i = 0, n = Math.round(W / 14); i <= n; i++) {
      const f = i / n, x = f * W, y = 7 + f * 6 + Math.sin(f * Math.PI) * sag + 2, on = 0.75 + 0.25 * Math.sin(t * 1.3 + i * 1.7);
      bloom(g, x, y + 1, 9, "#ffb85a", 0.55 * on);
      rect(g, x, y - 2, 1, 2, "#1a1426");  // its socket on the wire
      rect(g, x - 1, y, 2, 3, on > 0.9 ? "#fff1c8" : "#ffd88a");
    }
  },
};

// --------------------------------------------------------------------------------------------- 6: rain on a window
// A rainy night from a window seat: the city's lights blurred into soft circles behind the glass, rain streaking
// past, drops running down the pane, a candle flickering on the sill beside a plant and a mug, a far-off flash
SCENES["rain-window"] = {
  label: "Rainy window",
  init(W, H) {
    const r = rng(131);
    const back = this.back = layer(W, H), b = back.getContext("2d");
    this.pane = [12, 12, W - 24, 134];  // the glass, x y w h
    const [px0, py0, pw, ph] = this.pane;
    gradient(b, 0, 0, W, H, [[0, "#0a0d20"], [0.6, "#171a38"], [1, "#2a2244"]]);
    this.bokeh = Array.from({ length: Math.round(W * 0.09) }, () => ({ x: px0 + r() * pw, y: py0 + 30 + r() * (ph - 30),
      r: 3 + Math.floor(r() * 8), c: ["#ff7aa8", "#ffcf7a", "#7fd6ff", "#a98bff", "#ff9a5a"][Math.floor(r() * 5)],
      p: r() * 6.28, s: 0.2 + r() * 0.5 }));
    for (let x = px0; x < px0 + pw; x++) {  // the city out there, blurred
      const h = 10 + Math.floor(noise(rng(Math.floor(x / 9)), 1, 1)[0] * 26 + hash(Math.floor(x / 7), 3) * 14);
      rect(b, x, py0 + ph - h, 1, h, "#14163a");
    }
    this.rain = Array.from({ length: Math.round(W * 0.28) }, () => ({ x: r() * W, y: r() * H, v: 120 + r() * 80 }));
    this.drops = Array.from({ length: Math.round(W * 0.7) }, () => ({ x: px0 + r() * pw, y: py0 + r() * ph }));
    this.runs = Array.from({ length: 7 }, () => this.newRun(r));
    this.rand = r;
    const frame = this.frame = layer(W, H), f = frame.getContext("2d");  // the frame, the sill, the room
    rect(f, 0, 0, W, py0, "#140d0a");
    rect(f, 0, 0, px0, H, "#140d0a");
    rect(f, px0 + pw, 0, W - px0 - pw, H, "#140d0a");
    rect(f, 0, py0 + ph, W, H - py0 - ph, "#140d0a");
    rect(f, px0 - 2, py0 - 2, pw + 4, 2, "#2e211a");
    rect(f, px0 - 2, py0, 2, ph, "#2e211a");
    const mx = Math.round(px0 + pw / 2);
    rect(f, mx - 3, py0, 6, ph, "#1a120e");
    rect(f, mx - 3, py0, 1, ph, "#3a2a20");
    rect(f, px0, py0 + 60, pw, 5, "#1a120e");
    rect(f, px0, py0 + 60, pw, 1, "#3a2a20");
    rect(f, 0, py0 + ph, W, 10, "#2a1c15");
    rect(f, 0, py0 + ph, W, 1, "#5c4232");
    rect(f, 0, py0 + ph + 10, W, H - py0 - ph - 10, "#0f0a08");
    this.candle = [Math.round(W * 0.18), py0 + ph - 9];
    rect(f, this.candle[0] - 2, this.candle[1], 5, 9, "#e9dcc6");
    rect(f, this.candle[0] - 2, this.candle[1], 5, 1, "#fff1d8");
    const pot = Math.round(W * 0.82);
    rect(f, pot - 6, py0 + ph - 9, 12, 9, "#8a5434");
    rect(f, pot - 6, py0 + ph - 9, 12, 1, "#a86a44");
    for (let k = 0; k < 9; k++) {
      const a = -1.3 + k * 0.32;
      for (let i = 0; i < 14; i++) px(f, pot + Math.sin(a) * i, py0 + ph - 9 - Math.cos(a) * i + (i * i) / 30, i < 8 ? "#2e5a38" : "#3f7a4a");
    }
    this.mug = [Math.round(W * 0.64), py0 + ph - 8];
    rect(f, this.mug[0] - 3, this.mug[1], 7, 8, "#c9b8a8");
    rect(f, this.mug[0] + 4, this.mug[1] + 2, 2, 3, "#c9b8a8");
    this.flash = -10;
  },
  newRun(r) {
    const [px0, py0, pw] = this.pane;
    return { x: px0 + 4 + r() * (pw - 8), y: py0 + r() * 40, v: 6 + r() * 22, stop: 0 };
  },
  draw(g, t) {
    const { W, H } = this, [px0, py0, pw, ph] = this.pane;
    g.drawImage(this.back, 0, 0);
    for (const bk of this.bokeh) {  // the city's lights, soft and breathing
      const a = 0.16 + 0.12 * Math.sin(t * bk.s + bk.p);
      g.fillStyle = css(rgb(bk.c), a);
      for (let y = -bk.r; y <= bk.r; y++) {
        const w = Math.floor(Math.sqrt(bk.r * bk.r - y * y));
        g.fillRect(Math.round(bk.x + Math.sin(t * 0.05 + bk.p) * 3 - w), Math.round(bk.y + y), 2 * w + 1, 1);
      }
    }
    if (t - this.flash > 25 + hash(Math.floor(this.flash), 1) * 20) this.flash = t;  // lightning, far off
    const fl = Math.max(0, 1 - (t - this.flash) / 0.5);
    if (fl > 0) { g.fillStyle = `rgba(200,210,255,${(fl * 0.16).toFixed(3)})`; g.fillRect(px0, py0, pw, ph); }
    g.fillStyle = "rgba(160,178,220,0.35)";  // the rain going by outside
    for (const d of this.rain) {
      const y = wrap(d.y + t * d.v, H + 10) - 10, x = wrap(d.x - y * 0.12, W);
      if (x < px0 || x > px0 + pw || y < py0 || y > py0 + ph) continue;
      g.fillRect(Math.round(x), Math.round(y), 1, 4);
    }
    for (const d of this.drops) px(g, d.x, d.y, "rgba(200,215,255,0.35)");  // drops on the glass
    for (const run of this.runs) {  // and some running down it, leaving a trail
      run.y += run.v / 30 * (hash(Math.floor(t * 4), run.x) > 0.3 ? 1 : 0.1);
      if (run.y - 28 > py0 + ph) Object.assign(run, this.newRun(this.rand));
      for (let k = 0; k < 14; k++) px(g, run.x + Math.sin((run.y - k) * 0.3) * 0.6, run.y - k * 2, `rgba(190,205,255,${(0.32 - k * 0.02).toFixed(2)})`);
      px(g, run.x, run.y, "#e8eeff");
      px(g, run.x - 1, run.y + 1, "rgba(220,230,255,0.6)");
    }
    g.drawImage(this.frame, 0, 0);
    const [cx, cy] = this.candle, flick = Math.sin(t * 9) * 0.5 + Math.sin(t * 23) * 0.3;  // the candle
    bloom(g, cx, cy - 4, 34, "#ff8a3a", 0.32 + flick * 0.05);
    bloom(g, cx, cy - 5, 7, "#ffd27a", 0.55 + flick * 0.1);
    rect(g, cx, cy - 4 + Math.round(flick), 1, 3, "#ffd27a");
    px(g, cx, cy - 5 + Math.round(flick), "#fff3c0");
    const [mx, my] = this.mug;  // steam from the mug
    for (let k = 0; k < 10; k++) {
      const f = fract(t * 0.3 + k / 10), y = my - 2 - f * 18, x = mx + Math.sin(f * 6 + t) * 2;
      px(g, x, y, `rgba(235,225,215,${(0.4 * (1 - f)).toFixed(2)})`);
    }
  },
};

const SCENE_ORDER = ["night-drive", "sunset-drive", "night-beach", "morning-beach", "city-terrace", "rain-window"];
