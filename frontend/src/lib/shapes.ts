/**
 * Les 10 formes morphiques du réseau neuronal Orion.
 * Porté de orion_ui.html (logique identique, juste typée).
 */
export type Pt3 = { x: number; y: number; z: number };

export const SHAPES = [
  "sphere", "star", "cube", "arcreactor", "atom",
  "hub", "tore", "face", "letterO", "orion",
] as const;
export type ShapeName = (typeof SHAPES)[number];

export const SHAPE_LABELS: Record<ShapeName, string> = {
  sphere: "SPHÈRE", star: "ÉTOILE", cube: "CUBE", arcreactor: "ARC REACTOR",
  atom: "ATOME", hub: "HUB NEURONAL", tore: "TORE", face: "VISAGE IA",
  letterO: "LETTRE O", orion: "ORION",
};

export const FLAT_SHAPES = new Set<ShapeName>(["arcreactor", "hub", "letterO", "orion"]);

export function shapeSphere(n: number, r: number): Pt3[] {
  const pts: Pt3[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2;
    const rad = Math.sqrt(1 - y * y);
    const theta = golden * i;
    pts.push({ x: Math.cos(theta) * rad * r, y: y * r, z: Math.sin(theta) * rad * r });
  }
  return pts;
}

export function shapeStar(n: number, r: number): Pt3[] {
  const pts: Pt3[] = [];
  const arms = 5, innerR = r * 0.4;
  const verts: { x: number; y: number }[] = [];
  for (let i = 0; i < arms * 2; i++) {
    const angle = (i * Math.PI) / arms - Math.PI / 2;
    const radius = i % 2 === 0 ? r : innerR;
    verts.push({ x: Math.cos(angle) * radius, y: Math.sin(angle) * radius });
  }
  const segs: { a: { x: number; y: number }; b: { x: number; y: number }; len: number }[] = [];
  let total = 0;
  for (let i = 0; i < verts.length; i++) {
    const a = verts[i], b = verts[(i + 1) % verts.length];
    const len = Math.hypot(b.x - a.x, b.y - a.y);
    segs.push({ a, b, len });
    total += len;
  }
  let acc = 0, segIdx = 0;
  for (let i = 0; i < n; i++) {
    const target = i * (total / n);
    while (segIdx < segs.length - 1 && acc + segs[segIdx].len < target) {
      acc += segs[segIdx].len;
      segIdx++;
    }
    const t = (target - acc) / segs[segIdx].len;
    const { a, b } = segs[segIdx];
    pts.push({
      x: a.x + (b.x - a.x) * t,
      y: a.y + (b.y - a.y) * t,
      z: (Math.random() - 0.5) * r * 0.15,
    });
  }
  return pts;
}

export function shapeCube(n: number, r: number): Pt3[] {
  const s = r * 0.78;
  const corners: [number, number, number][] = [
    [-s, -s, -s], [s, -s, -s], [s, s, -s], [-s, s, -s],
    [-s, -s, s], [s, -s, s], [s, s, s], [-s, s, s],
  ];
  const edges: [number, number][] = [
    [0, 1], [1, 2], [2, 3], [3, 0],
    [4, 5], [5, 6], [6, 7], [7, 4],
    [0, 4], [1, 5], [2, 6], [3, 7],
  ];
  const pts: Pt3[] = [];
  const perEdge = Math.max(2, Math.floor(n / edges.length));
  for (const [a, b] of edges) {
    const ca = corners[a], cb = corners[b];
    for (let i = 0; i < perEdge; i++) {
      const t = i / (perEdge - 1);
      pts.push({
        x: ca[0] + (cb[0] - ca[0]) * t,
        y: ca[1] + (cb[1] - ca[1]) * t,
        z: ca[2] + (cb[2] - ca[2]) * t,
      });
    }
  }
  while (pts.length < n) pts.push({ ...pts[pts.length % edges.length] });
  return pts.slice(0, n);
}

export function shapeArcReactor(n: number, r: number): Pt3[] {
  const pts: Pt3[] = [];
  const branches = 6;
  const ringOuter = Math.floor(n * 0.5);
  for (let i = 0; i < ringOuter; i++) {
    const a = (i / ringOuter) * Math.PI * 2;
    pts.push({ x: Math.cos(a) * r, y: Math.sin(a) * r, z: 0 });
  }
  const branchTotal = Math.floor(n * 0.3);
  const perBranch = Math.floor(branchTotal / branches);
  for (let b = 0; b < branches; b++) {
    const a = (b / branches) * Math.PI * 2;
    for (let i = 0; i < perBranch; i++) {
      const t = 0.4 + (i / Math.max(1, perBranch - 1)) * 0.55;
      pts.push({ x: Math.cos(a) * r * t, y: Math.sin(a) * r * t, z: 0 });
    }
  }
  const remaining = n - pts.length;
  for (let i = 0; i < remaining; i++) {
    const a = (i / remaining) * Math.PI * 2;
    pts.push({ x: Math.cos(a) * r * 0.4, y: Math.sin(a) * r * 0.4, z: 0 });
  }
  return pts.slice(0, n);
}

export function shapeAtom(n: number, r: number): Pt3[] {
  const pts: Pt3[] = [];
  const nucleusN = Math.floor(n * 0.15);
  const nR = r * 0.18;
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < nucleusN; i++) {
    const y = 1 - (i / Math.max(1, nucleusN - 1)) * 2;
    const rad = Math.sqrt(1 - y * y);
    const theta = golden * i;
    pts.push({ x: Math.cos(theta) * rad * nR, y: y * nR, z: Math.sin(theta) * rad * nR });
  }
  const orbR = r * 0.98;
  const remaining = n - pts.length;
  const perOrbit = Math.floor(remaining / 3);
  for (let i = 0; i < perOrbit; i++) {
    const a = (i / perOrbit) * Math.PI * 2;
    pts.push({ x: Math.cos(a) * orbR, y: Math.sin(a) * orbR, z: 0 });
  }
  for (let i = 0; i < perOrbit; i++) {
    const a = (i / perOrbit) * Math.PI * 2;
    pts.push({ x: Math.cos(a) * orbR, y: 0, z: Math.sin(a) * orbR });
  }
  while (pts.length < n) {
    const i = pts.length - 2 * perOrbit - nucleusN;
    const a = (i / perOrbit) * Math.PI * 2;
    pts.push({ x: 0, y: Math.cos(a) * orbR, z: Math.sin(a) * orbR });
  }
  return pts.slice(0, n);
}

export function shapeHub(n: number, r: number): Pt3[] {
  const pts: Pt3[] = [];
  const outerN = 40, innerN = 20, spokes = 5, spokeN = 6;
  for (let i = 0; i < outerN; i++) {
    const a = (i / outerN) * Math.PI * 2;
    pts.push({ x: Math.cos(a) * r, y: Math.sin(a) * r, z: 0 });
  }
  for (let i = 0; i < innerN; i++) {
    const a = (i / innerN) * Math.PI * 2;
    pts.push({ x: Math.cos(a) * r * 0.45, y: Math.sin(a) * r * 0.45, z: 0 });
  }
  for (let s = 0; s < spokes; s++) {
    const a = (s / spokes) * Math.PI * 2;
    for (let i = 1; i <= spokeN; i++) {
      const t = i / (spokeN + 1);
      const rad = r * 0.45 + (r - r * 0.45) * t;
      pts.push({ x: Math.cos(a) * rad, y: Math.sin(a) * rad, z: 0 });
    }
  }
  while (pts.length < n) pts.push({ ...pts[pts.length % outerN] });
  return pts.slice(0, n);
}

export function shapeTore(n: number, r: number): Pt3[] {
  const pts: Pt3[] = [];
  const R = r * 0.65, rad = r * 0.32;
  const U = 18, V = Math.ceil(n / U);
  for (let i = 0; i < U; i++) {
    const u = (i / U) * Math.PI * 2;
    for (let j = 0; j < V && pts.length < n; j++) {
      const v = (j / V) * Math.PI * 2;
      pts.push({
        x: (R + rad * Math.cos(v)) * Math.cos(u),
        y: (R + rad * Math.cos(v)) * Math.sin(u),
        z: rad * Math.sin(v),
      });
    }
  }
  while (pts.length < n) pts.push({ ...pts[0] });
  return pts.slice(0, n);
}

export function shapeText(text: string, n: number, w: number, h: number): Pt3[] {
  const off = document.createElement("canvas");
  off.width = w; off.height = h;
  const octx = off.getContext("2d")!;
  octx.fillStyle = "#fff";
  octx.textAlign = "center";
  octx.textBaseline = "middle";
  let fontSize = h * 0.65;
  octx.font = `900 ${fontSize}px Orbitron, monospace`;
  while (octx.measureText(text).width > w * 0.95 && fontSize > 8) {
    fontSize -= 2;
    octx.font = `900 ${fontSize}px Orbitron, monospace`;
  }
  octx.fillText(text, w / 2, h / 2);
  const data = octx.getImageData(0, 0, w, h).data;
  const opaque: { x: number; y: number }[] = [];
  for (let py = 0; py < h; py += 2) {
    for (let px = 0; px < w; px += 2) {
      if (data[(py * w + px) * 4 + 3] > 128) {
        opaque.push({ x: px - w / 2, y: py - h / 2 });
      }
    }
  }
  if (!opaque.length) return shapeSphere(n, Math.min(w, h) / 3);
  const pts: Pt3[] = [];
  for (let i = 0; i < n; i++) {
    const p = opaque[Math.floor(Math.random() * opaque.length)];
    pts.push({ x: p.x, y: p.y, z: (Math.random() - 0.5) * 8 });
  }
  return pts;
}

export function shapeFace(n: number, r: number): Pt3[] {
  const pts: Pt3[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  const headN = Math.floor(n * 0.76);
  for (let i = 0; i < headN; i++) {
    const yRaw = -1 + (i / (headN - 1)) * 2;
    const yNorm = (yRaw + 1) / 2;
    let wScale: number;
    if (yNorm < 0.12) wScale = 0.28 + yNorm * 4.2;
    else if (yNorm < 0.32) wScale = 0.88;
    else if (yNorm < 0.55) wScale = 1.0;
    else if (yNorm < 0.78) wScale = 0.48 + yNorm * 0.8;
    else wScale = 0.28 + (1 - yNorm) * 1.5;
    const rad = Math.sqrt(Math.max(0, 1 - yRaw * yRaw)) * wScale;
    const theta = golden * i;
    pts.push({
      x: Math.cos(theta) * rad * r * 0.74,
      y: yRaw * r * 0.96,
      z: Math.sin(theta) * rad * r * 0.25,
    });
  }
  const eyeY = -r * 0.08, eyeX = r * 0.28, eyeZ = r * 0.26;
  const eyeN = Math.floor(n * 0.08);
  for (let i = 0; i < eyeN / 2; i++) {
    const a = (i / (eyeN / 2)) * Math.PI * 2, er = r * 0.055;
    pts.push({ x: -eyeX + Math.cos(a) * er * 0.5, y: eyeY + Math.sin(a) * er * 0.3, z: eyeZ });
  }
  for (let i = 0; i < eyeN / 2; i++) {
    const a = (i / (eyeN / 2)) * Math.PI * 2, er = r * 0.055;
    pts.push({ x: eyeX + Math.cos(a) * er * 0.5, y: eyeY + Math.sin(a) * er * 0.3, z: eyeZ });
  }
  const noseN = Math.floor(n * 0.04);
  for (let i = 0; i < noseN; i++) {
    const t = i / noseN;
    pts.push({ x: (Math.random() - 0.5) * r * 0.08, y: r * 0.05 + t * r * 0.16, z: r * 0.26 + t * r * 0.04 });
  }
  const mouthN = Math.floor(n * 0.05);
  for (let i = 0; i < mouthN; i++) {
    const t = i / mouthN, a = Math.PI * 0.22 + t * Math.PI * 0.56;
    pts.push({ x: Math.cos(a) * r * 0.22, y: r * 0.28 + Math.sin(a) * r * 0.05, z: r * 0.2 });
  }
  while (pts.length < n) pts.push({ ...pts[Math.floor(Math.random() * headN)] });
  return pts.slice(0, n);
}

export function shapeForName(name: ShapeName, n: number, r: number): Pt3[] {
  switch (name) {
    case "sphere":     return shapeSphere(n, r);
    case "star":       return shapeStar(n, r * 1.05);
    case "cube":       return shapeCube(n, r);
    case "arcreactor": return shapeArcReactor(n, r);
    case "atom":       return shapeAtom(n, r);
    case "hub":        return shapeHub(n, r);
    case "tore":       return shapeTore(n, r);
    case "face":       return shapeFace(n, r);
    case "letterO":    return shapeText("O", n, 300, 300);
    case "orion":      return shapeText("ORION", n, 340, 120);
  }
}
