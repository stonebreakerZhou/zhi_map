import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { WorkspaceController } from '../controller.js';
import { ConfirmDialog, Dialog } from '../components/Dialog.js';
import { Icon } from '../components/UI.js';
import { graphApi, type GraphEdge, type Projection } from './api.js';
import { buildForest, cardHeight, cardWidth, edgePath, layoutTree, setCardWidthLookup, spanOf, type Placement, type Tier } from './treeLayout.js';
import './treeGraph.css';

/**
 * Exploration view: a left-to-right mind map of the topic tree, following the reference clip.
 *
 * The server's stored world coordinates are left untouched. This view lays the tree out itself from
 * the parent links, keeps every card in screen space so text never rasterizes at a fraction, and
 * animates card positions, card opacity and edge paths between states.
 */

const ANIM_MS = 420;
const PAN_MS = 340;
/** Horizontal gap between a column's cards and the next column, matching the reference's fan. */
const COLUMN_GAP = 32;
/** Vertical gap between two stacked cards. */
const ROW_GAP = 24;
/** Preferred horizontal position of the focused card's centre, as a fraction of canvas width. The
 *  clamp in `panTo` overrides it whenever the tree needs the room. */
const FOCUS_ANCHOR = .42;
/** Canvas margin kept clear when the whole tree is made to fit. */
const FIT_MARGIN = 24;
/** Never shrink the map below this: past it, cards stop being readable and panning is the answer. */
const FIT_MIN = .72;

type Point = { x: number; y: number };
type Frame = { from: Point; to: Point; started: number };

const easeOut = (t: number) => 1 - (1 - t) ** 3;
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export function Constellation({ app, references, openConversation }: {
  app: WorkspaceController;
  references: (source?: string) => void;
  /** Called after a card switches the active topic, so the shell can show that conversation. */
  openConversation: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const cardNodes = useRef(new Map<string, HTMLButtonElement>());
  const [size, setSize] = useState({ width: 1000, height: 700 });
  const [view, setView] = useState<Point>({ x: 0, y: 0 });
  const viewRef = useRef(view);
  const [projection, setProjection] = useState<Projection>();
  const [loading, setLoading] = useState(false), [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const [menu, setMenu] = useState<{ id: string; point: Point }>();
  const [removeIds, setRemoveIds] = useState<string[]>();
  const [edge, setEdge] = useState<GraphEdge>();
  const [hovered, setHovered] = useState<string>();
  const [revision, setRevision] = useState(0);
  /** Measured card sizes, keyed by column depth: the tree spacing follows the real boxes. */
  const [measured, setMeasured] = useState<{ heights: Partial<Record<Tier, number>>; widthsByDepth: Record<number, number> }>({ heights: {}, widthsByDepth: {} });
  const frames = useRef(new Map<string, Frame>());
  const live = useRef(new Map<string, Point>());
  const edges = useRef<{ key: string; parent: Placement; child: Placement; type: GraphEdge['type']; onPath: boolean }[]>([]);
  const raf = useRef(0), panRaf = useRef(0);
  const drag = useRef<{ x: number; y: number; view: Point } | undefined>(undefined);
  /** Latest placements, readable from callbacks that were created before this render's layout. */
  const placementsRef = useRef<Placement[]>([]);
  /** A topic being travelled to: the pan waits until the rebuilt tree actually contains its card. */
  const pending = useRef<string | undefined>(undefined);

  const activeId = app.branch?.id;
  const collapsedKey = collapsed.join('|');

  useEffect(() => { viewRef.current = view; }, [view]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setSize({ width: element.clientWidth, height: element.clientHeight }));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // One projection window for the focused topic. The viewport is wide enough that the server's own
  // spatial filter never hides a node this layout still needs.
  useEffect(() => {
    if (!activeId) { setProjection(undefined); return; }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({ cursor: '-1', left: '-9000', top: '-9000', right: '9000', bottom: '9000', focus: activeId, reading: activeId });
      setLoading(true);
      void graphApi.query(params, controller.signal)
        .then(data => { setProjection(data); setError(''); })
        .catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : String(e)); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 120);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [activeId, app.revision, refresh]);

  const layout = useMemo(() => {
    if (!projection || !activeId || !size.height) return undefined;
    const forest = buildForest(projection.nodes, activeId, new Set(collapsed));
    if (!forest.length) return undefined;
    // Lay the forest out as one continuous stack so every root shares the same columns. Components
    // are stacked vertically: placing each root at the same depth would overlap their root cards.
    const natural: Placement[] = [];
    let y = 0;
    for (const tree of forest) {
      const part = layoutTree(tree, { originX: 0, originY: y, gapX: COLUMN_GAP, gapY: ROW_GAP, heights: measured.heights, widthsByDepth: measured.widthsByDepth });
      natural.push(...part.placements);
      y = part.bounds.bottom + ROW_GAP * 4;
    }
    // A tree wider than the canvas would spill a column past the edge, where no clamp can help.
    // Shrinking the whole scene is uniform, so relative sizes and the layout stay intact. The span is
    // read back from the placements just computed, so the fit can never disagree with the geometry.
    const room = Math.max(320, size.width - FIT_MARGIN * 2);
    const wanted = spanOf(natural, measured.widthsByDepth);
    const fit = wanted > room ? Math.max(FIT_MIN, room / wanted) : 1;
    let placements = natural;
    if (fit < 1) {
      // Re-lay every component at the fitted scale so the columns match the shrunken cards.
      placements = [];
      let stack = 0;
      for (const tree of forest) {
        const part = layoutTree(tree, { originX: 0, originY: stack, gapX: COLUMN_GAP, gapY: ROW_GAP, heights: measured.heights, widthsByDepth: measured.widthsByDepth, scale: fit });
        placements.push(...part.placements);
        stack = part.bounds.bottom + ROW_GAP * 4;
      }
    }
    const ordered = [...placements].sort((a, b) => a.depth - b.depth);
    return { placements: ordered, fit };
  }, [projection, activeId, collapsedKey, size.height, size.width, measured]);

  const placements = layout?.placements ?? [];
  placementsRef.current = placements;

  // Edge endpoints read card widths through this lookup so they meet the real card edges rather than
  // the tier constants.
  setCardWidthLookup(tier => measured.widthsByDepth[Math.abs(tier === 'root' ? 0 : tier === 'full' ? 1 : tier === 'compact' ? 2 : 3)] ?? 0);

  // Cards are content-sized, so their real height is measured once they exist. The same pass seeds
  // the live position for a card that is drawn for the first time, so a newly revealed child fades
  // and scales in place instead of flying in from the scene origin.
  useLayoutEffect(() => {
    if (!placements.length) return;
    const heights: Partial<Record<Tier, number>> = {};
    const widthsByDepth: Record<number, number> = {};
    for (const placement of placements) {
      const element = cardNodes.current.get(placement.node.id);
      if (!element) continue;
      const box = element.getBoundingClientRect();
      if (!box.height) continue;
      heights[placement.tier] = Math.max(heights[placement.tier] ?? 0, Math.round(box.height));
      widthsByDepth[placement.depth] = Math.max(widthsByDepth[placement.depth] ?? 0, Math.round(box.width));
      if (!live.current.has(placement.node.id)) {
        const seed = { x: placement.x, y: placement.y };
        live.current.set(placement.node.id, seed);
        element.style.transform = `translate3d(${seed.x}px, ${seed.y}px, 0)`;
      }
    }
    // Rebuild rather than merge: a column that is no longer on screen must not keep driving spacing.
    const depths = Object.keys(widthsByDepth).map(Number);
    const stale = depths.some(depth => measured.widthsByDepth[depth] !== widthsByDepth[depth])
      || Object.keys(widthsByDepth).length !== Object.keys(measured.widthsByDepth).length;
    const heightChanged = (Object.keys(heights) as Tier[]).some(tier => measured.heights[tier] !== heights[tier]);
    if (!stale && !heightChanged) return;
    setMeasured({ heights, widthsByDepth });
  }, [placements, measured]);

  /**
   * Arm a frame for every card whose position changed. A card that has never been drawn starts at
   * its target, so the first paint never flies in from the corner.
   */
  useLayoutEffect(() => {
    if (!layout) { edges.current = []; return; }
    const now = performance.now();
    for (const placement of layout.placements) {
      const to = { x: placement.x, y: placement.y };
      const current = live.current.get(placement.node.id);
      if (!current) { live.current.set(placement.node.id, to); continue; }
      if (Math.abs(current.x - to.x) < .5 && Math.abs(current.y - to.y) < .5) continue;
      frames.current.set(placement.node.id, { from: { ...current }, to, started: now });
    }
    const ids = new Set(layout.placements.map(p => p.node.id));
    for (const id of [...live.current.keys()]) if (!ids.has(id)) live.current.delete(id);

    const byId = new Map(layout.placements.map(p => [p.node.id, p]));
    const next: typeof edges.current = [];
    const push = (parent: Placement, child: Placement, type: GraphEdge['type']) => {
      next.push({ key: `${parent.node.id}|${child.node.id}`, parent, child, type, onPath: parent.onPath && child.onPath });
    };
    for (const entry of projection?.edges ?? []) {
      const parent = byId.get(entry.source), child = byId.get(entry.target);
      if (parent && child) push(parent, child, entry.type);
    }
    // The projection carries a bounded edge window, so fall back to the parent links it did send.
    for (const child of layout.placements) {
      const parentId = child.node.parent;
      const parent = parentId ? byId.get(parentId) : undefined;
      if (!parent || next.some(e => e.key === `${parentId}|${child.node.id}`)) continue;
      push(parent, child, 'parent');
    }
    edges.current = next;
    setRevision(r => r + 1);
  }, [layout]);

  // Frame loop: interpolate card positions and repaint the edge paths that follow them.
  useEffect(() => {
    const paint = () => {
      const now = performance.now();
      let moving = false;
      for (const [id, frame] of frames.current) {
        const t = Math.min(1, (now - frame.started) / ANIM_MS);
        const eased = easeOut(t);
        const point = { x: lerp(frame.from.x, frame.to.x, eased), y: lerp(frame.from.y, frame.to.y, eased) };
        live.current.set(id, point);
        const element = cardNodes.current.get(id);
        if (element) element.style.transform = `translate3d(${point.x}px, ${point.y}px, 0)`;
        if (t >= 1) frames.current.delete(id); else moving = true;
      }
      const svg = host.current?.querySelector('svg.tree-edges');
      if (svg) {
        for (const item of edges.current) {
          const path = svg.querySelector<SVGPathElement>(`path[data-edge="${CSS.escape(item.key)}"]`);
          const from = live.current.get(item.parent.node.id), to = live.current.get(item.child.node.id);
          if (!path || !from || !to) continue;
          path.setAttribute('d', edgePath({ ...item.parent, ...from }, { ...item.child, ...to }));
        }
      }
      if (moving) raf.current = requestAnimationFrame(paint);
    };
    raf.current = requestAnimationFrame(paint);
    return () => cancelAnimationFrame(raf.current);
  }, [revision]);

  /**
   * Frame the map from the boxes that are actually on screen. Measuring the DOM beats deriving the
   * bounds analytically: the analytic version depends on measured card sizes, and those land one
   * render after the layout, which left the scene a column off.
   *
   * `animate` is used when the user travelled to a topic; the first paint of a tree is framed
   * directly so it does not fly in from the previous position.
   */
  const panTo = (id: string, animate = true) => {
    const hostBox = host.current?.getBoundingClientRect();
    const sceneBox = host.current?.querySelector('.tree-scene')?.getBoundingClientRect();
    const fit = layout?.fit ?? 1;
    if (!hostBox || !sceneBox) return;
    const boxes = placementsRef.current.map(item => {
      const element = cardNodes.current.get(item.node.id);
      if (!element) return undefined;
      const box = element.getBoundingClientRect();
      // Card rects already carry the scene transform. Undo the fit scale so everything below is in
      // layout coordinates, where the scene offset is applied.
      const k = fit && fit < 1 ? fit : 1;
      return { id: item.node.id, left: (box.left - sceneBox.left) / k, right: (box.right - sceneBox.left) / k,
        top: (box.top - sceneBox.top) / k, bottom: (box.bottom - sceneBox.top) / k };
    }).filter(Boolean) as { id: string; left: number; right: number; top: number; bottom: number }[];
    const focus = boxes.find(box => box.id === id);
    if (!focus) return;
    const left = Math.min(...boxes.map(b => b.left));
    const right = Math.max(...boxes.map(b => b.right));
    const top = Math.min(...boxes.map(b => b.top));
    const bottom = Math.max(...boxes.map(b => b.bottom));

    const margin = FIT_MARGIN;
    const viewportWidth = hostBox.width / (fit && fit < 1 ? fit : 1);
    const viewportHeight = hostBox.height / (fit && fit < 1 ? fit : 1);
    const focusX = (focus.left + focus.right) / 2;
    const focusY = (focus.top + focus.bottom) / 2;
    // Preferred place for the focused card, then a two-sided clamp so both edges stay on screen.
    const anchorX = Math.max(margin + (focusX - left), Math.min(viewportWidth * FOCUS_ANCHOR, viewportWidth - margin - (right - focusX)));
    const anchorY = Math.max(margin + (focusY - top), Math.min(viewportHeight / 2, viewportHeight - margin - (bottom - focusY)));
    // The scene offset that puts the focused card's centre on `anchorX`/`anchorY`.
    const target = { x: anchorX - focusX, y: anchorY - focusY };
    if (!animate) { setView(target); return; }
    const from = viewRef.current, started = performance.now();
    cancelAnimationFrame(panRaf.current);
    const step = () => {
      const t = Math.min(1, (performance.now() - started) / PAN_MS);
      const eased = easeOut(t);
      setView({ x: lerp(from.x, target.x, eased), y: lerp(from.y, target.y, eased) });
      if (t < 1) panRaf.current = requestAnimationFrame(step);
    };
    panRaf.current = requestAnimationFrame(step);
  };

  // Travelling to a topic waits for the new tree: switching refetches the projection, and the target
  // card only exists once that layout has been computed. Firing the pan earlier is a no-op, which is
  // what made a topic change look like a jump instead of a glide.
  const framedFor = useRef('');
  useEffect(() => {
    if (!placements.length) return;
    const wanted = pending.current && placements.some(p => p.node.id === pending.current) ? pending.current : undefined;
    const id = wanted ?? activeId;
    if (!id) return;
    const signature = `${wanted ? 'go' : 'frame'}:${id}:${placements.length}:${size.width}x${size.height}`;
    if (framedFor.current === signature) return;
    framedFor.current = signature;
    if (wanted) pending.current = undefined;
    panTo(id, Boolean(wanted));
  }, [placements, activeId, size.width, size.height]);

  /**
   * Two-step opening, matching the reference: the first click on another card makes it the focused
   * topic and glides it to the middle so its neighbourhood can be read; clicking the focused card
   * again opens its conversation.
   */
  const openTopic = (id: string) => {
    if (id === activeId) { openConversation(); return; }
    pending.current = id;
    void app.action({ type: 'switch', branchId: id }).catch(app.report);
  };
  const toggle = (id: string) => setCollapsed(current => current.includes(id) ? current.filter(x => x !== id) : [...current, id]);

  const down = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.target instanceof Element && event.target.closest('button, input, a, [data-protected]')) return;
    drag.current = { x: event.clientX, y: event.clientY, view: viewRef.current };
    host.current?.setPointerCapture(event.pointerId);
  };
  const move = (event: React.PointerEvent<HTMLDivElement>) => {
    const start = drag.current;
    if (!start) return;
    cancelAnimationFrame(panRaf.current);
    setView({ x: start.view.x + event.clientX - start.x, y: start.view.y + event.clientY - start.y });
  };
  const up = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    drag.current = undefined;
    if (host.current?.hasPointerCapture(event.pointerId)) host.current.releasePointerCapture(event.pointerId);
  };

  const nameOf = (id: string) => projection?.nodes.find(n => n.id === id)?.title ?? id;
  const childCount = (id: string) => projection?.nodes.filter(n => n.parent === id).length ?? 0;

  return <>
    <div ref={host} className="tree-graph" data-node-count={placements.length} data-edge-count={edges.current.length}
      onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
      <div className="tree-scene" style={{ transform: `translate3d(${view.x}px, ${view.y}px, 0)${layout?.fit && layout.fit < 1 ? ` scale(${layout.fit})` : ''}` }}>
        <svg className="tree-edges" aria-label="主题关系">
          {edges.current.map(item => {
            const onPath = item.onPath;
            return <path key={item.key} data-edge={item.key} className={`tree-edge ${onPath ? 'on-path' : 'ghost'} edge-${item.type}`}
              onPointerDown={event => event.stopPropagation()}
              onClick={() => setEdge((projection?.edges ?? []).find(e => e.source === item.parent.node.id && e.target === item.child.node.id))} />;
          })}
        </svg>
        {placements.map(placement => {
          const { node, tier, depth } = placement;
          const focused = node.id === activeId;
          const current = live.current.get(node.id) ?? { x: placement.x, y: placement.y };
          const kids = childCount(node.id);
          const isCollapsed = collapsed.includes(node.id);
          // Cards on the active path read as real content; everything else recedes like the reference.
          const state = focused ? 'focused' : placement.onPath ? 'on-path' : 'ghost';
          return <button
            key={node.id}
            ref={element => { if (element) cardNodes.current.set(node.id, element); else cardNodes.current.delete(node.id); }}
            type="button"
            className={`tree-card tier-${tier} ${state} ${hovered === node.id ? 'hovered' : ''}`}
            data-node={node.id}
            style={{ transform: `translate3d(${current.x}px, ${current.y}px, 0)`, zIndex: focused ? 30 : 20 - depth }}
            aria-label={`${node.title}${kids ? `，${kids} 个子讨论` : ''}`}
            title={node.title}
            onPointerEnter={() => setHovered(node.id)}
            onPointerLeave={() => setHovered(current => current === node.id ? undefined : current)}
            onClick={() => openTopic(node.id)}
            onContextMenu={event => { event.preventDefault(); event.stopPropagation(); setMenu({ id: node.id, point: { x: event.clientX, y: event.clientY } }); }}
          >
            <span className={`tree-status ${node.kind}`} aria-hidden="true" />
            <span className="tree-title">{node.title}</span>
            {(tier === 'root' || tier === 'full') && <span className="tree-excerpt">{node.previews[0]?.text ?? (kids ? `${kids} 个子讨论` : '继续追问即可展开')}</span>}
            {kids > 0 && <span
              role="button"
              tabIndex={0}
              data-protected
              className="tree-handle"
              aria-label={`${isCollapsed ? '展开' : '收起'}子讨论 ${node.title}`}
              title={isCollapsed ? `展开 ${kids} 个子讨论` : `收起 ${kids} 个子讨论`}
              onClick={event => { event.stopPropagation(); toggle(node.id); }}
              onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); toggle(node.id); } }}
            ><Icon name={isCollapsed ? 'plus' : 'minus'} size={13} /></span>}
          </button>;
        })}
      </div>

      {loading && <span className="tree-note" role="status">正在加载主题…</span>}
      {error && <span className="tree-note error" role="alert">{error}<button onClick={() => setRefresh(n => n + 1)}>重试</button></span>}

      {app.running() && <div className="tree-working" data-protected role="status">
        <span className="tree-spinner" aria-hidden="true" /><span>处理中…</span>
        <button onClick={() => app.cancel()} aria-label="停止生成">停止</button>
      </div>}

      {menu && <div className="graph-context" data-protected style={{ left: Math.min(menu.point.x, size.width - 240), top: Math.min(menu.point.y, size.height - 200) }}>
        <strong>{nameOf(menu.id)}</strong>
        <button onClick={() => { setMenu(undefined); openTopic(menu.id); }}>打开主题</button>
        <button onClick={() => { setMenu(undefined); references(menu.id); }}>引用到其他主题</button>
        <button className="danger" onClick={() => { setRemoveIds([menu.id]); setMenu(undefined); }}>移除主题（可恢复）</button>
      </div>}
    </div>

    {edge && <Dialog title="关系详情" close={() => setEdge(undefined)}>
      <p>{edge.type === 'parent' ? '分支由来' : edge.type === 'reference' ? '有向引用' : '无向联系'}：{nameOf(edge.source)} → {nameOf(edge.target)}</p>
      {edge.type === 'contact' && <button onClick={() => { void graphApi.contact(edge.source, [edge.target], true).then(() => { setEdge(undefined); setRefresh(n => n + 1); }).catch(app.report); }}>断开联系</button>}
    </Dialog>}
    {removeIds && <ConfirmDialog title="移除所选主题？" label="确认移除" close={() => setRemoveIds(undefined)} confirm={async () => { await app.remove(removeIds); setRemoveIds(undefined); setRefresh(n => n + 1); }}><p>{removeIds.map(nameOf).join('、')}</p><p>主题、消息和草稿可在十分钟内恢复；独立子分支保留。</p></ConfirmDialog>}
  </>;
}
