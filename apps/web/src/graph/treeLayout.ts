import type { GraphNode } from './api.js';

/**
 * Left-to-right tree layout for the exploration view.
 *
 * The server stores world coordinates for its own insertion-order grid; the reference draws a
 * mind-map instead, so the view computes its own layout from the parent links it already has and
 * leaves the durable coordinates alone. Positions are screen-space: text never scales with zoom.
 */

/** Card densities by distance from the focused root, matching the reference's column style. */
export type Tier = 'root' | 'full' | 'compact' | 'chip';

export type TreeNode = {
  node: GraphNode;
  tier: Tier;
  children: TreeNode[];
  /** Column index; also the tree depth. */
  depth: number;
  /** True when the node has children that are currently hidden. */
  expandable: boolean;
  /** True when this node sits on the active path from the root. */
  onPath: boolean;
};

export type Placement = { node: GraphNode; tier: Tier; x: number; y: number; depth: number; onPath: boolean; expandable: boolean };

/** Per-tier card size in screen px. Kept in step with the matching CSS custom properties; the view
 *  replaces the heights with measured values as soon as the cards have rendered. Widths stay modest
 *  so a focused topic with two columns of children fits the canvas without shrinking anything. */
export const CARD_W: Record<Tier, number> = { root: 260, full: 180, compact: 156, chip: 128 };
export const CARD_H: Record<Tier, number> = { root: 94, full: 94, compact: 62, chip: 44 };
/** Horizontal gap between a parent's right edge and its children's left edge. */
export const GAP_X = 32;
export const GAP_Y = 22;

export const tierFor = (depth: number): Tier => (depth === 0 ? 'root' : depth === 1 ? 'full' : depth === 2 ? 'compact' : 'chip');
/** Same mapping for an ancestor column, whose distance from the focused topic is negative. */
export const tierAt = (depth: number): Tier => tierFor(Math.abs(depth));
export const cardHeight = (tier: Tier, sizes?: Partial<Record<Tier, number>>) => sizes?.[tier] ?? CARD_H[tier];
/** Injected width lookup, so edge endpoints meet the measured card edges rather than a constant. */
let widthLookup: ((tier: Tier) => number) | undefined;
export const setCardWidthLookup = (lookup?: (tier: Tier) => number) => { widthLookup = lookup; };
export const cardWidth = (tier: Tier) => widthLookup?.(tier) || CARD_W[tier];

/**
 * Build the forest that is actually drawn. The projection already contains the context window — the
 * focused topic, its ancestors and its children — so the map roots itself at the topmost ancestor it
 * received and hangs every other node off its parent link. That is what makes the parent show as a
 * column to the left of the focused topic instead of the focused topic becoming a lone card.
 */
export function buildForest(nodes: GraphNode[], focusId: string, collapsed: ReadonlySet<string>): TreeNode[] {
  const byId = new Map(nodes.map(n => [n.id, n]));
  const focus = byId.get(focusId);
  if (!focus) return [];
  const childrenOf = new Map<string, GraphNode[]>();
  for (const node of nodes) {
    if (!node.parent || node.parent === node.id || !byId.has(node.parent)) continue;
    const bucket = childrenOf.get(node.parent);
    if (bucket) bucket.push(node); else childrenOf.set(node.parent, [node]);
  }
  // Only the focused topic's own connected component is drawn. The projection can also contain
  // unrelated parentless topics, and hanging them off this map would invent structure.
  const top: GraphNode[] = [];
  let cursor: GraphNode | undefined = focus;
  const guard = new Set<string>();
  while (cursor && !guard.has(cursor.id)) {
    guard.add(cursor.id);
    top.unshift(cursor);
    cursor = cursor.parent ? byId.get(cursor.parent) : undefined;
  }
  const root = top[0] ?? focus;
  const focusDepth = Math.max(0, top.length - 1);

  const seen = new Set<string>();
  const build = (node: GraphNode, depth: number): TreeNode => {
    const all = childrenOf.get(node.id) ?? [];
    const kids = collapsed.has(node.id) ? [] : all.filter(k => !seen.has(k.id)).slice(0, 60);
    for (const kid of kids) seen.add(kid.id);
    const children = kids.map(kid => build(kid, depth + 1));
    return {
      node,
      // Card density is measured from the focused topic, not from the topmost ancestor: the topic you
      // are reading keeps its full card, its parent and children sit at the same level, and only the
      // deeper descendants thin out. Otherwise adding an ancestor would demote the focused card.
      tier: tierFor(Math.abs(depth - focusDepth)),
      children,
      depth,
      expandable: children.length === 0 && all.length > 0,
      onPath: isAncestorOrSelf(node.id, focusId, byId),
    };
  };
  seen.add(root.id);
  return [build(root, 0)];
}

/** True when `id` is the focused topic or one of its ancestors, i.e. sits on the active path. */
function isAncestorOrSelf(id: string, focusId: string, byId: Map<string, GraphNode>): boolean {
  let cursor = byId.get(focusId);
  const guard = new Set<string>();
  while (cursor && !guard.has(cursor.id)) {
    if (cursor.id === id) return true;
    guard.add(cursor.id);
    cursor = cursor.parent ? byId.get(cursor.parent) : undefined;
  }
  return false;
}

/**
 * @deprecated Kept for the single-branch callers; `buildForest` is what the view draws.
 */
export function buildTree(nodes: GraphNode[], rootId: string, collapsed: ReadonlySet<string>): TreeNode | undefined {
  return buildForest(nodes, rootId, collapsed)[0];
}

export type LayoutOptions = {
  /** Distance between a parent's right edge and its children's left edge. */
  gapX?: number;
  gapY?: number;
  /** Vertical centre the root is aligned to; the tree is framed around it. */
  originY?: number;
  /** Left edge of the root card. */
  originX?: number;
  /** Measured card heights, used instead of the defaults as soon as the cards have rendered. */
  heights?: Partial<Record<Tier, number>>;
  /** Measured card widths **by column**, so an ancestor column is sized from its own real cards. */
  widthsByDepth?: Record<number, number>;
  /** Uniform shrink applied to every card box and gap so the tree can fit a narrower canvas. */
  scale?: number;
};

/**
 * Classic tidy tree: leaves stack, parents centre on their children's span. Every node's left edge
 * lands on its depth's column, which is what makes the reference's columns line up. `x` is the card's
 * left edge and `y` its vertical centre, matching how the cards are positioned.
 */
export function layoutTree(root: TreeNode, options: LayoutOptions = {}) {
  const gapX = options.gapX ?? GAP_X;
  const gapY = options.gapY ?? GAP_Y;
  const originY = options.originY ?? 0;
  const originX = options.originX ?? 0;
  const heights = options.heights;
  const byDepth = options.widthsByDepth;
  const scale = options.scale ?? 1;
  const placements: Placement[] = [];
  // Every column's left edge is the absolute sum of the widths before it, recomputed from the sizes
  // in scope. A cached column position keeps a width from an earlier measurement, and a new column
  // then lands on top of its neighbour.
  const widthFor = (level: number) => (byDepth?.[level] ?? CARD_W[tierAt(level)]) * scale;
  const columnFor = (depth: number) => {
    let x = originX;
    if (depth >= 0) {
      for (let level = 0; level < depth; level++) x += widthFor(level) + gapX * scale;
    } else {
      // Ancestors grow leftwards from the focused column.
      for (let level = -1; level >= depth; level--) x -= widthFor(level) + gapX * scale;
    }
    return x;
  };
  // Leaves are stacked from the root's own centre outwards, so the root sits level with the middle
  // of its children and each column steps away from it — the reference's diagonal.
  let below = originY;
  const walk = (entry: TreeNode): number => {
    const height = cardHeight(entry.tier, heights) * scale;
    let y: number;
    if (!entry.children.length) {
      y = below + height / 2;
      below += height + gapY * scale;
    } else {
      const centres = entry.children.map(walk);
      y = (centres[0] + centres[centres.length - 1]) / 2;
    }
    placements.push({ node: entry.node, tier: entry.tier, x: columnFor(entry.depth), y, depth: entry.depth, onPath: entry.onPath, expandable: entry.expandable });
    return y;
  };
  walk(root);
  const rootEntry = placements.find(p => p.depth === 0);
  if (rootEntry) rootEntry.y = originY;
  const top = Math.min(...placements.map(p => p.y - cardHeight(p.tier, heights) * scale / 2));
  const bottom = Math.max(...placements.map(p => p.y + cardHeight(p.tier, heights) * scale / 2));
  const right = Math.max(...placements.map(p => p.x + widthFor(p.depth)));
  const left = Math.min(...placements.map(p => p.x));
  return { placements, bounds: { top, bottom, left, right } };
}

/**
 * Width a laid-out placement list occupies, read back from the placements so the fit scale can never
 * disagree with the geometry it scales.
 */
export function spanOf(placements: Placement[], widthsByDepth: Record<number, number> | undefined) {
  if (!placements.length) return 0;
  let left = Infinity, right = -Infinity;
  for (const item of placements) {
    const width = widthsByDepth?.[item.depth] ?? CARD_W[item.tier];
    left = Math.min(left, item.x);
    right = Math.max(right, item.x + width);
  }
  return right - left;
}

/**
 * Reference edge: leaves the parent's right mid-edge horizontally and enters the child's left
 * mid-edge horizontally, which is what produces the fan at the parent and the calm arrival at the
 * child.
 */
export function edgePath(parent: Placement, child: Placement): string {
  const from = { x: parent.x + cardWidth(parent.tier), y: parent.y };
  const to = { x: child.x, y: child.y };
  const run = Math.max(36, Math.abs(to.x - from.x));
  const c1 = { x: from.x + run * .55, y: from.y };
  const c2 = { x: to.x - run * .45, y: to.y };
  return `M ${from.x} ${from.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${to.x} ${to.y}`;
}

export type Animation = { from: Placement; to: Placement };
