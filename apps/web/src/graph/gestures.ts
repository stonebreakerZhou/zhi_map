import type { Point } from './api.js';

export type Camera = Point & { scale: number };
export type Box = { id: string; left: number; top: number; right: number; bottom: number };
export type Phase = 'idle' | 'pressCandidate' | 'pan' | 'lasso' | 'connectPreview' | 'movePreview' | 'erasePreview' | 'submitting' | 'resultUnknown';
export type Gesture = {
  phase: Phase; pointerId: number; button: number; origin: Point; point: Point;
  started: number; distance: number; maximum: number; holdEligible: boolean;
  source?: string; target?: string; ambiguous: boolean; boxes: Box[]; path: Point[];
  camera: Camera; organize: boolean; connector: boolean;
};
export const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
export const screen = (p: Point, c: Camera): Point => ({ x: p.x * c.scale + c.x, y: p.y * c.scale + c.y });
export const world = (p: Point, c: Camera): Point => ({ x: (p.x - c.x) / c.scale, y: (p.y - c.y) / c.scale });
export function zoomAt(c: Camera, p: Point, factor: number): Camera {
  const w = world(p, c), scale = Math.min(2, Math.max(.25, c.scale * factor));
  return { scale, x: p.x - w.x * scale, y: p.y - w.y * scale };
}
export function intersects(a: Box, b: Box) {
  return a.left <= b.right && a.right >= b.left && a.top <= b.bottom && a.bottom >= b.top;
}
export function rectangle(a: Point, b: Point): Box {
  return { id: '', left: Math.min(a.x, b.x), top: Math.min(a.y, b.y), right: Math.max(a.x, b.x), bottom: Math.max(a.y, b.y) };
}
/** Slab intersection returns entry distance along the sampled segment, including fast crossings. */
export function segmentEntry(a: Point, b: Point, box: Box): number | undefined {
  let low = 0, high = 1;
  for (const [start, delta, min, max] of [[a.x, b.x - a.x, box.left, box.right], [a.y, b.y - a.y, box.top, box.bottom]]) {
    if (Math.abs(delta) < 1e-9) { if (start < min || start > max) return; }
    else {
      const t1 = (min - start) / delta, t2 = (max - start) / delta;
      low = Math.max(low, Math.min(t1, t2)); high = Math.min(high, Math.max(t1, t2));
      if (low > high) return;
    }
  }
  return low;
}
export function begin(pointerId: number, button: number, point: Point, now: number, boxes: Box[], camera: Camera, source?: string, organize = false, connector = false): Gesture {
  return { phase: 'pressCandidate', pointerId, button, origin: point, point, started: now,
    distance: 0, maximum: 0, holdEligible: true, source, ambiguous: false, boxes,
    path: [point], camera, organize, connector };
}
export function advance(g: Gesture, point: Point, now: number, occluded = false): Gesture {
  const next = { ...g, point, distance: g.distance + distance(g.point, point), maximum: Math.max(g.maximum, distance(g.origin, point)) };
  if (next.maximum > 6) next.holdEligible = false;
  if (g.phase === 'pressCandidate') {
    if (g.button === 2 && next.distance >= 24 && next.maximum >= 8) next.phase = 'erasePreview';
    if (g.button === 0) {
      if (next.maximum >= 8 && g.source && g.organize) next.phase = 'movePreview';
      else if (next.maximum >= 8 && g.source && !g.organize) next.phase = 'connectPreview';
      else if (next.holdEligible && now - g.started >= 350 && !g.source) next.phase = 'lasso';
      else if (next.maximum >= 8 && !g.source) next.phase = 'pan';
    }
  }
  if (next.phase === 'erasePreview') {
    next.path = [...g.path.slice(-127), point];
    if (!next.target && !next.ambiguous && !occluded) {
      const hits = g.boxes.map(box => ({ id: box.id, t: segmentEntry(g.point, point, box) }))
        .filter((h): h is { id: string; t: number } => h.t !== undefined).sort((a, b) => a.t - b.t);
      if (hits.length > 1 && Math.abs(hits[0].t - hits[1].t) < 1e-6) next.ambiguous = true;
      else next.target = hits[0]?.id;
    }
  }
  if (next.phase === 'connectPreview') {
    const hits = occluded ? [] : g.boxes.filter(b => point.x >= b.left && point.x <= b.right && point.y >= b.top && point.y <= b.bottom && b.id !== g.source);
    next.target = hits.length === 1 ? hits[0].id : undefined;
  }
  return next;
}
