import type { GraphNode } from './api.js';
import { screen, intersects, type Box, type Camera } from './gestures.js';

export type Detail = 0 | 1 | 2;
export function detail(width: number, height: number, previous: Detail): Detail {
  const threshold = (level: Detail, w: number, h: number) => width >= w * (previous >= level ? 1 : 1.1) && height >= h * (previous >= level ? 1 : 1.1);
  if (threshold(2, 240, 144)) return 2;
  return threshold(1, 120, 44) ? 1 : 0;
}

/** Screen-space allocation: text and hit targets never inherit geometric scaling. */
export function allocate(nodes: GraphNode[], camera: Camera, width: number, height: number,
  previous: Map<string, Detail>, priority: string[]) {
  const boxes: Box[] = [], visible: { node: GraphNode; level: Detail }[] = [], crowded: GraphNode[] = [];
  let previews = 0, labels = 0;
  const rank = (id: string) => { const i = priority.indexOf(id); return i < 0 ? priority.length : i; };
  for (const node of [...nodes].sort((a, b) => rank(a.id) - rank(b.id))) {
    const p = screen(node, camera);
    if (p.x < 22 || p.x > width - 22 || p.y < 70 || p.y > height - 22) continue;
    let level = detail(360 * camera.scale, 240 * camera.scale, previous.get(node.id) ?? 0);
    if (level === 2 && (previews >= 12 || !node.previews.length)) level = 1;
    if (labels >= 59) level = 0;
    const box = { id: node.id, left: p.x - 110, right: p.x + 150, top: p.y - 24, bottom: p.y + (level === 2 ? 210 : 24) };
    if (boxes.some(b => intersects(b, box))) { crowded.push(node); continue; }
    boxes.push(box); previous.set(node.id, level);
    visible.push({ node, level });
    if (level > 0) labels++;
    if (level === 2) previews++;
  }
  return { visible, crowded };
}
