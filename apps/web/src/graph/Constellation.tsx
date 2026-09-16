import { useEffect, useRef, useState, type CSSProperties, type ReactNode, type PointerEvent as ReactPointerEvent } from 'react';
import type { WorkspaceController } from '../controller.js';
import { Dialog, ConfirmDialog } from '../components/Dialog.js';
import { graphApi, type GraphEdge, type GraphNode, type Point, type Projection } from './api.js';
import { advance, begin, intersects, rectangle, screen, world, zoomAt, type Box, type Camera, type Gesture } from './gestures.js';
import { allocate, type Detail } from './geometry.js';
import { readSelection } from '../selection.js';
import type { Jump } from '../components/MessageViewport.js';
import './constellation.css';

type View = 'Focus' | 'Peek' | 'Overview';
type Relation = { source: string; targets: string[] };
type Visit = { branchId: string; entryId?: string; scroll: number; camera: Camera; view: View; selection?: Jump };

/** Native history projection; the reading children and editor remain mounted across every camera state. */
export function Constellation({ app, children, references, modal, newTopic, restoreReading }: {
  app: WorkspaceController; children: ReactNode; references: (source?: string) => void; modal: boolean; newTopic: () => void; restoreReading: (jump: Jump) => void;
}) {
  const host = useRef<HTMLDivElement>(null), capsule = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 1000, height: 700 });
  const [view, setView] = useState<View>('Overview');
  const [camera, setCamera] = useState<Camera>({ x: 200, y: 200, scale: 1 });
  const cameraRef = useRef(camera), animation = useRef(0), generation = useRef(0);
  const editorGeometry = useRef({ width: 0, height: 0, activeX: 0, activeY: 0, peek: .62 });
  const [projection, setProjection] = useState<Projection>();
  const [loading, setLoading] = useState(false), [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0), [search, setSearch] = useState(''), [cursor, setCursor] = useState(-1);
  const [automatic, setAutomatic] = useState(true), [locked, setLocked] = useState(false);
  const [titles, setTitles] = useState(false), [organize, setOrganize] = useState(false);
  const [ratio, setRatio] = useState(.9), [peek, setPeek] = useState(.62);
  const [selected, setSelected] = useState<string[]>([]), [selectMode, setSelectMode] = useState(false);
  const [keyboardNode, setKeyboardNode] = useState(0);
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const [hoveredNode, setHoveredNode] = useState<string>();
  const [cursorHint, setCursorHint] = useState<{ x: number; y: number; title: string }>();
  const [toolsOpen, setToolsOpen] = useState(false);
  const [expanded, setExpanded] = useState<string>();
  const [childCursor, setChildCursor] = useState(-1);
  const lod = useRef(new Map<string, Detail>());
  const [crowdedOpen, setCrowdedOpen] = useState(false);
  const [gesture, setGesture] = useState<Gesture>(), gestureRef = useRef<Gesture | undefined>(undefined);
  const touches = useRef(new Map<number, Point>());
  const pinch = useRef<{ distance: number; center: Point; camera: Camera } | undefined>(undefined);
  const [relation, setRelation] = useState<Relation>(), [edge, setEdge] = useState<GraphEdge>();
  const [removeIds, setRemoveIds] = useState<string[]>(), [menu, setMenu] = useState<{ id?: string; point: Point }>();
  const [busy, setBusy] = useState(false);
  const pressed = useRef(false), composing = useRef(false), typed = useRef(0), hoverTimer = useRef(0), autoTimer = useRef(0), holdTimer = useRef(0), hoverCandidate = useRef<string | undefined>(undefined);
  const suppress = useRef(false), lastActive = useRef<string | undefined>(undefined), autoRef = useRef({ modal, locked, automatic, busy });
  const branchBefore = useRef(app.branch?.id);
  const historyBranch = useRef<string | undefined>(undefined);
  const restoring = useRef<Visit | undefined>(undefined);
  autoRef.current = { modal: Boolean(modal || relation || edge || removeIds), locked, automatic, busy };
  useEffect(() => {
    const ids = new Set(projection?.nodes.map(n => n.id));
    for (const id of lod.current.keys()) if (!ids.has(id)) lod.current.delete(id);
  }, [projection]);
  const active = projection?.nodes.find(n => n.id === app.branch?.id);
  const focusWidth = Math.max(0, Math.min(size.width * ratio, size.width - 48));
  const focusHeight = Math.max(0, Math.min(size.height * ratio, size.height - 48));
  editorGeometry.current = { width: focusWidth, height: focusHeight, activeX: active?.x ?? 0, activeY: active?.y ?? 0, peek };
  const activePoint = active ? screen(active, camera) : { x: size.width / 2, y: size.height / 2 };
  const capsuleBox = { left: activePoint.x - focusWidth * camera.scale / 2,
    top: activePoint.y - focusHeight * camera.scale / 2, width: focusWidth * camera.scale, height: focusHeight * camera.scale };

  const setCam = (c: Camera, commit = true) => {
    cameraRef.current = c;
    host.current?.style.setProperty('--cx', `${c.x}px`);
    host.current?.style.setProperty('--cy', `${c.y}px`);
    host.current?.style.setProperty('--scale', String(c.scale));
    const h = host.current?.getBoundingClientRect();
    if (h) {
      const g = editorGeometry.current;
      host.current?.style.setProperty('--focus-width', `${g.width}px`);
      host.current?.style.setProperty('--focus-height', `${g.height}px`);
      const t = Math.max(0, Math.min(1, (1 - c.scale) / (1 - g.peek)));
      const fullWidth = Math.min(840, g.width - 24);
      const trayWidth = Math.min(840, h.width - 32);
      const fullLeft = h.left + c.x + g.activeX * c.scale - fullWidth / 2;
      const trayLeft = h.left + (h.width - trayWidth) / 2;
      const fullBottom = innerHeight - h.top - (c.y + (g.activeY + g.height / 2) * c.scale) + 1;
      host.current?.style.setProperty('--editor-left', `${fullLeft + (trayLeft - fullLeft) * t}px`);
      host.current?.style.setProperty('--editor-width', `${fullWidth + (trayWidth - fullWidth) * t}px`);
      host.current?.style.setProperty('--editor-bottom', `${fullBottom + (innerHeight - h.bottom + 16 - fullBottom) * t}px`);
    }
    if (commit) setCamera(c);
  };
  const animate = (target: Camera) => {
    cancelAnimationFrame(animation.current);
    const from = cameraRef.current, started = performance.now();
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) { setCam(target); return; }
    const frame = (now: number) => {
      const t = Math.min(1, (now - started) / 520);
      // Soft spring arrival — cubic-bezier(.34, 1.56, .64, 1) with a gentle overshoot.
      let low = 0, high = 1, u = t;
      for (let i = 0; i < 12; i++) { const x = 3 * (1 - u) ** 2 * u * .34 + 3 * (1 - u) * u ** 2 * .64 + u ** 3; if (x < t) low = u; else high = u; u = (low + high) / 2; }
      const eased = 3 * (1 - u) ** 2 * u * 1.56 + 3 * (1 - u) * u ** 2 + u ** 3;
      setCam({ x: from.x + (target.x - from.x) * eased, y: from.y + (target.y - from.y) * eased, scale: from.scale + (target.scale - from.scale) * eased }, false);
      if (t < 1) animation.current = requestAnimationFrame(frame);
      else setCam(target);
    };
    animation.current = requestAnimationFrame(frame);
  };
  const changeView = (next: View) => {
    clearTimeout(hoverTimer.current); setView(next);
    if (active && (next !== 'Overview' || view !== 'Overview')) {
      const scale = next === 'Focus' ? 1 : next === 'Peek' ? peek : .4;
      animate({ scale, x: size.width * (next === 'Overview' ? .28 : next === 'Peek' ? .4 : .5) - active.x * scale, y: size.height * (next === 'Overview' ? .4 : .5) - active.y * scale });
    }
  };
  useEffect(() => {
    if (app.branch?.id !== branchBefore.current) {
      branchBefore.current = app.branch?.id;
      if (app.branch) setView('Focus');
    }
  }, [app.branch?.id]);
  useEffect(() => {
    const pop = (event: PopStateEvent) => {
      const visit = event.state?.graph as Visit | undefined;
      if (!visit?.branchId || !Number.isFinite(visit.camera?.scale)) return;
      restoring.current = visit;
      void app.action({ type: 'switch', branchId: visit.branchId }, visit.entryId).then(() => {
        const selection = visit.selection;
        const entry = selection && app.page.items.find(e => e.id === selection.entryId);
        if (entry && selection && Number.isInteger(selection.start) && Number.isInteger(selection.end) && selection.start >= 0 && selection.end > selection.start && selection.end <= entry.text.length) restoreReading(selection);
        if (restoring.current !== visit) return;
        restoring.current = undefined; historyBranch.current = visit.branchId; lastActive.current = visit.branchId;
        setView(visit.view); setCam({ ...visit.camera, scale: Math.max(.25, Math.min(2, visit.camera.scale)) });
        requestAnimationFrame(() => { const chat = host.current?.querySelector('.chat'); if (chat) chat.scrollTop = visit.scroll; });
      }).catch(e => { restoring.current = undefined; app.report(e); });
    };
    window.addEventListener('popstate', pop);
    return () => window.removeEventListener('popstate', pop);
  }, []);
  useEffect(() => {
    const branchId = app.branch?.id;
    if (!branchId || restoring.current) return;
    const save = () => {
      if (app.branch?.id !== branchId) return;
      const visit: Visit = { branchId, entryId: app.page.items[0]?.id, scroll: host.current?.querySelector('.chat')?.scrollTop ?? 0, camera: cameraRef.current, view };
      if (history.state?.graph?.branchId === branchId) {
        const saved = history.state.graph.selection as Jump | undefined;
        if (saved && app.page.items.some(e => e.id === saved.entryId)) { visit.selection = saved; visit.entryId = saved.entryId; }
      }
      const selection = window.getSelection(), root = host.current?.querySelector<HTMLElement>('#messages');
      if (selection && !selection.isCollapsed && root) {
        try { const picked = readSelection(selection, root); visit.selection = { branchId, entryId: picked.entryId, start: picked.start, end: picked.end }; visit.entryId = picked.entryId; }
        catch { /* Native cross-message selections are not history anchors. */ }
      }
      if (historyBranch.current && historyBranch.current !== branchId) history.pushState({ ...history.state, graph: visit }, '', `#branch=${encodeURIComponent(branchId)}`);
      else history.replaceState({ ...history.state, graph: visit }, '', `#branch=${encodeURIComponent(branchId)}`);
      historyBranch.current = branchId;
    };
    save();
    const chat = host.current?.querySelector('.chat');
    chat?.addEventListener('scroll', save);
    document.addEventListener('selectionchange', save);
    return () => { chat?.removeEventListener('scroll', save); document.removeEventListener('selectionchange', save); };
  }, [app.branch?.id, app.page.items[0]?.id, camera, view]);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setSize({ width: element.clientWidth, height: element.clientHeight }));
    observer.observe(element); return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const editor = host.current?.querySelector('.bottom');
    if (!editor) return;
    const observer = new ResizeObserver(() => host.current?.style.setProperty('--editor-height', `${editor.getBoundingClientRect().height}px`));
    observer.observe(editor);
    return () => observer.disconnect();
  }, [app.branch?.id]);
  useEffect(() => {
    // Resize changes usable screen geometry, never durable world coordinates.
    // Recenter before the next interaction so a narrow host cannot hide Send.
    if (view === 'Focus' && active) {
      cancelAnimationFrame(animation.current);
      setCam({ scale: 1, x: size.width / 2 - active.x, y: size.height / 2 - active.y });
    }
   }, [size.width, size.height, ratio]);
  useEffect(() => {
    const controller = new AbortController(), requestId = ++generation.current;
    const timer = window.setTimeout(() => {
      const c = cameraRef.current;
      const a = world({ x: -360, y: -240 }, c), b = world({ x: size.width + 360, y: size.height + 240 }, c);
      const clamp = (n: number) => String(Math.max(-1e6, Math.min(1e6, n)));
      const params = new URLSearchParams({ left: clamp(a.x), top: clamp(a.y), right: clamp(b.x), bottom: clamp(b.y), search, cursor: String(cursor) });
      if (app.branch) { params.set('focus', app.branch.id); if (app.page.items[0]) params.set('reading', app.page.items[0].id); }
      if (expanded) { params.set('expand', expanded); params.set('childCursor', String(childCursor)); }
      setLoading(true);
      void graphApi.query(params, controller.signal).then(data => {
        if (generation.current !== requestId) return;
        if (!gestureRef.current) setProjection(data);
        setError('');
      }).catch(e => { if (!controller.signal.aborted && generation.current === requestId) setError(e instanceof Error ? e.message : String(e)); })
        .finally(() => { if (generation.current === requestId) setLoading(false); });
    }, 160);
    return () => { clearTimeout(timer); controller.abort(); };
   }, [camera, size, search, cursor, app.branch?.id, app.revision, refresh, expanded, childCursor]);
  useEffect(() => {
    if (!app.branch) lastActive.current = '';
    if (active && lastActive.current !== active.id) {
      const first = lastActive.current === undefined; lastActive.current = active.id;
      if (restoring.current?.branchId === active.id) {
        const visit = restoring.current;
        restoring.current = undefined; historyBranch.current = active.id;
        setView(visit.view); setCam({ ...visit.camera, scale: Math.max(.25, Math.min(2, visit.camera.scale)) });
        requestAnimationFrame(() => { const chat = host.current?.querySelector('.chat'); if (chat) chat.scrollTop = visit.scroll; });
        return;
      }
      if (!first) {
        setView('Focus');
        cancelAnimationFrame(animation.current);
        setCam({ x: size.width / 2 - active.x, y: size.height / 2 - active.y, scale: 1 });
      }
      else {
        const scale = view === 'Focus' ? 1 : view === 'Peek' ? peek : .4;
        setCam({ x: size.width * (view === 'Overview' ? .28 : view === 'Peek' ? .4 : .5) - active.x * scale, y: size.height * (view === 'Overview' ? .4 : .5) - active.y * scale, scale });
      }
    }
  }, [active?.id, app.branch?.id, view]);
  const cancel = () => {
    clearTimeout(holdTimer.current); clearTimeout(hoverTimer.current); clearTimeout(autoTimer.current);
    const g = gestureRef.current; gestureRef.current = undefined; setGesture(undefined);
    if (g && host.current?.hasPointerCapture(g.pointerId)) host.current.releasePointerCapture(g.pointerId);
    pressed.current = false;
    pinch.current = undefined; touches.current.clear();
  };
  useEffect(() => {
    const blur = () => cancel();
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { cancel(); setMenu(undefined); setEdge(undefined); } };
    window.addEventListener('blur', blur); window.addEventListener('keydown', key);
    return () => { blur(); cancelAnimationFrame(animation.current); window.removeEventListener('blur', blur); window.removeEventListener('keydown', key); };
  }, []);
  const graphPoint = (e: { clientX: number; clientY: number }) => { const r = host.current?.getBoundingClientRect(); return { x: e.clientX - (r?.left ?? 0), y: e.clientY - (r?.top ?? 0) }; };
  const protectedElement = (target: EventTarget | null) => target instanceof Element && Boolean(target.closest('[data-graph-protected], .graph-capsule, .selection-toolbar, dialog'));
  const hitBoxes = (): Box[] => Array.from(host.current?.querySelectorAll<HTMLElement>('.graph-node-header[data-graph-node]') ?? []).map(el => {
    const r = el.getBoundingClientRect(), h = host.current!.getBoundingClientRect();
    const visible = document.elementFromPoint(Math.max(h.left + 1, Math.min(h.right - 1, r.left + r.width / 2)), Math.max(h.top + 1, Math.min(h.bottom - 1, r.top + r.height / 2)));
    return { id: visible && el.contains(visible) ? el.dataset.graphNode ?? '' : '', left: r.left - h.left, right: r.right - h.left, top: r.top - h.top, bottom: r.bottom - h.top };
  }).filter(b => b.id && b.right > 0 && b.left < size.width && b.bottom > 0 && b.top < size.height);
  const syncGesture = (g: Gesture) => {
    const previous = gestureRef.current;
    gestureRef.current = g;
    if (g.phase !== 'pan' || previous?.phase !== 'pan') setGesture(g);
    if (g.phase !== 'pressCandidate') {
      clearTimeout(hoverTimer.current); cancelAnimationFrame(animation.current); setView('Overview');
      if (!host.current?.hasPointerCapture(g.pointerId)) host.current?.setPointerCapture(g.pointerId);
    }
  };
  const down = (e: ReactPointerEvent<HTMLDivElement>) => {
    clearTimeout(hoverTimer.current); clearTimeout(autoTimer.current); setToolsOpen(false);
    if (menu && !(e.target instanceof Element && e.target.closest('.graph-context'))) setMenu(undefined);
    if (expanded && !(e.target instanceof Element && e.target.closest('.graph-children-panel'))) setExpanded(undefined);
    if (crowdedOpen && !(e.target instanceof Element && e.target.closest('.graph-crowded'))) setCrowdedOpen(false);
    pressed.current = true;
    cancelAnimationFrame(animation.current);
    const capsuleTarget = e.target instanceof Element && e.target.closest('.graph-capsule, .graph-preview-capsule');
    const interactiveTarget = e.target instanceof Element && Boolean(e.target.closest('button, input, textarea, select, a, [data-graph-interactive], .message-text, p, h1, h2, h3, blockquote, pre, code'));
    const canvasPanTarget = !interactiveTarget && (!protectedElement(e.target) || Boolean(capsuleTarget));
    const protectedTarget = protectedElement(e.target) && !canvasPanTarget;
    if (protectedTarget || (e.button !== 0 && e.button !== 2) || busy || app.removalBusy) return;
    if (canvasPanTarget) e.preventDefault();
    if (e.pointerType === 'touch') {
      touches.current.set(e.pointerId, graphPoint(e));
      if (touches.current.size === 2) {
        clearTimeout(holdTimer.current);
        gestureRef.current = undefined; setGesture(undefined);
        const [a, b] = [...touches.current.values()];
        pinch.current = { distance: Math.max(1, Math.hypot(a.x-b.x, a.y-b.y)), center: { x: (a.x+b.x)/2, y: (a.y+b.y)/2 }, camera: cameraRef.current };
        for (const id of touches.current.keys()) host.current?.setPointerCapture(id);
        setView('Overview'); return;
      }
    }
    const el = e.target instanceof Element ? e.target.closest<HTMLElement>('[data-graph-node]') : null;
    const source = el?.dataset.graphNode;
    if (e.target instanceof Element && e.target.closest('button') && !source) return;
    suppress.current = false; setMenu(undefined);
    const connector = e.target instanceof Element && Boolean(e.target.closest('[data-connector]'));
    const g = begin(e.pointerId, e.button, graphPoint(e), performance.now(), hitBoxes(), { ...cameraRef.current }, source, organize, connector);
    syncGesture(g);
    if (!host.current?.hasPointerCapture(e.pointerId)) host.current?.setPointerCapture(e.pointerId);
    if (e.button === 0) holdTimer.current = window.setTimeout(() => { const current = gestureRef.current; if (current?.phase === 'pressCandidate') syncGesture(advance(current, current.point, performance.now())); }, 355);
  };
  const hover = (e: { pointerId: number; clientX: number; clientY: number; target: EventTarget | null }) => {
     clearTimeout(autoTimer.current);
    if (pinch.current && touches.current.has(e.pointerId)) {
      touches.current.set(e.pointerId, graphPoint(e));
      const [a, b] = [...touches.current.values()];
      if (a && b) {
        const p = pinch.current;
        const c = zoomAt(p.camera, p.center, Math.hypot(a.x-b.x, a.y-b.y) / p.distance);
        setCam({ ...c, x: c.x + (a.x+b.x)/2 - p.center.x, y: c.y + (a.y+b.y)/2 - p.center.y }, false);
      }
      return;
    }
    const g = gestureRef.current;
    if (g && g.pointerId === e.pointerId) {
      const target = document.elementFromPoint(e.clientX, e.clientY);
      const next = advance(g, graphPoint(e), performance.now(), protectedElement(target));
      syncGesture(next);
      if (next.phase === 'pan') setCam({ ...g.camera, x: g.camera.x + next.point.x - g.origin.x, y: g.camera.y + next.point.y - g.origin.y }, false);
      return;
    }
    if (view === 'Overview' && !protectedElement(e.target)) {
      const hovered = e.target instanceof Element ? e.target.closest<HTMLElement>('[data-hover-node]')?.dataset.hoverNode : undefined;
      const node = hovered ? projection?.nodes.find(n => n.id === hovered) : undefined;
      setCursorHint(node ? { x: e.clientX, y: e.clientY, title: node.title } : undefined);
      if (!node) { hoverCandidate.current = undefined; setHoveredNode(undefined); return; }
      if (hoverCandidate.current !== node.id) {
        clearTimeout(hoverTimer.current);
        hoverCandidate.current = node.id;
        setHoveredNode(undefined);
        hoverTimer.current = window.setTimeout(() => {
          if (hoverCandidate.current === node.id) setHoveredNode(node.id);
        }, 5);
      }
    }
    if (view === 'Overview' && hoveredNode && capsule.current && capsule.current.contains(e.target as Node)) setHoveredNode(undefined);
    if (!automatic || locked || autoRef.current.modal || busy || app.removalBusy || pressed.current || composing.current || performance.now() - typed.current < 800 || (e.target instanceof Element && e.target.closest('.bottom, [data-graph-protected]')) || protectedElement(e.target) && !(e.target instanceof Element && e.target.closest('.graph-capsule'))) return;
    if (!capsule.current || !app.branch || view === 'Overview') return;
    const r = capsule.current.getBoundingClientRect();
    const outside = e.clientX < r.left - 12 || e.clientX > r.right + 12 || e.clientY < r.top - 12 || e.clientY > r.bottom + 12;
    const inside = e.clientX > r.left + 12 && e.clientX < r.right - 12 && e.clientY > r.top + 12 && e.clientY < r.bottom - 12;
    const target: View | undefined = view === 'Focus' && outside ? 'Peek' : view === 'Peek' && inside ? 'Focus' : undefined;
    if (target) autoTimer.current = window.setTimeout(() => {
      const protection = autoRef.current;
      if (!pressed.current && !composing.current && performance.now() - typed.current >= 800 && !protection.modal && !protection.locked && protection.automatic && !protection.busy) changeView(target);
    }, target === 'Peek' ? 240 : 150);
  };
  useEffect(() => {
    const move = (event: PointerEvent) => hover(event);
    window.addEventListener('pointermove', move, true);
    return () => window.removeEventListener('pointermove', move, true);
  }, [view, projection, automatic, locked, busy, app.removalBusy, hoveredNode]);
  const remove = async (ids: string[], point?: Point) => {
    try { await app.remove(ids); setSelected([]); setRefresh(n => n + 1); }
    catch (e) { app.report(e); setError(e instanceof Error ? e.message : String(e)); }
  };
  const up = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (pinch.current) { const ids = [...touches.current.keys()]; cancel(); for (const id of ids) if (host.current?.hasPointerCapture(id)) host.current.releasePointerCapture(id); setCamera(cameraRef.current); return; }
    touches.current.delete(e.pointerId);
    pressed.current = false; const g = gestureRef.current;
    if (!g || g.pointerId !== e.pointerId) return;
    const completed = g.phase !== 'pressCandidate'; suppress.current = completed;
    cancel();
    if (g.phase === 'pan') setCamera(cameraRef.current);
    if (g.phase === 'lasso') setSelected(g.boxes.filter(b => intersects(b, rectangle(g.origin, g.point))).map(b => b.id));
    if (g.phase === 'connectPreview' && g.source && g.target) setRelation({ source: g.source, targets: [g.target] });
    if (g.phase === 'erasePreview' && g.target && !g.ambiguous) void remove([g.target], g.point);
    if (g.phase === 'movePreview' && g.source) {
      const node = projection?.nodes.find(n => n.id === g.source);
      if (node) { setBusy(true); void graphApi.position(node, { x: node.x + (g.point.x - g.origin.x) / g.camera.scale, y: node.y + (g.point.y - g.origin.y) / g.camera.scale }).then(() => setRefresh(n => n + 1)).catch(app.report).finally(() => setBusy(false)); }
    }
    if (!completed && g.button === 2) setMenu({ id: g.source, point: g.point });
    if (!completed && g.button === 0 && !g.source) changeView('Overview');
  };
  const open = (id: string) => {
    if (suppress.current) { suppress.current = false; return; }
    if (selectMode) { setSelected(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]); return; }
    if (id === app.branch?.id) { changeView('Focus'); document.getElementById('draft')?.focus(); return; }
    void app.action({ type: 'switch', branchId: id }).then(() => { setView('Focus'); requestAnimationFrame(() => document.getElementById('draft')?.focus()); }).catch(app.report);
  };
  const nodeName = (id: string) => projection?.nodes.find(n => n.id === id)?.title ?? id;
  const moveNode = async (id: string, dx: number, dy: number) => {
    const node = projection?.nodes.find(n => n.id === id);
    if (!node || busy) return;
    setBusy(true);
    try { await graphApi.position(node, { x: node.x + dx, y: node.y + dy }); setRefresh(n => n + 1); }
    catch (e) { app.report(e); }
    finally { setBusy(false); }
  };
  const drawn = (projection?.nodes ?? []).filter(n => {
    if (projection?.path.includes(n.id) || selected.includes(n.id)) return true;
    let parent = n.parent;
    const seen = new Set<string>();
    while (parent && !seen.has(parent)) {
      if (collapsed.includes(parent)) return false;
      seen.add(parent); parent = projection?.nodes.find(p => p.id === parent)?.parent ?? null;
    }
    return true;
  });
  const positions = new Map(drawn.map(n => [n.id, screen(n, camera)]));
  const allocation = allocate(drawn.filter(n => n.id !== app.branch?.id), camera, size.width, size.height, lod.current,
    [...selected, ...(edge ? [edge.source, edge.target] : []), ...(projection?.path ?? [])]);
  const renderedIds = new Set([app.branch?.id, ...allocation.visible.map(n => n.node.id)]);
  const renderedEdges = (projection?.edges ?? []).filter(e => renderedIds.has(e.source) && renderedIds.has(e.target));
  const changeZoom = (factor: number, p = { x: size.width / 2, y: size.height / 2 }) => { setView('Overview'); animate(zoomAt(cameraRef.current, p, factor)); };
  const selectionBox = gesture?.phase === 'lasso' ? rectangle(gesture.origin, gesture.point) : undefined;

  return <>
     <div className="graph-tools" data-graph-protected role="toolbar" aria-label="图谱视图工具" onPointerLeave={(e) => { const related = e.relatedTarget; if (related instanceof Node && e.currentTarget.contains(related)) return; setToolsOpen(false); }}>
        <button className="graph-primary" disabled={!app.branch} onClick={() => changeView(view === 'Focus' ? 'Overview' : 'Focus')}>{view === 'Focus' ? '查看图谱' : '聚焦当前'}</button>
        <div className="zoom-controls" aria-label="图谱缩放"><button aria-label="缩小图" onClick={() => changeZoom(1 / 1.2)}>−</button><span>{Math.round(camera.scale * 100)}%</span><button aria-label="放大图" onClick={() => changeZoom(1.2)}>＋</button></div>
        <button aria-expanded={toolsOpen} aria-controls="graph-options" onClick={() => setToolsOpen(open => !open)}>工具</button>
        <button id="refresh" onClick={() => void app.flush().then(() => { app.cache.clear(); return app.load(); }).catch(app.report)}>刷新</button>
        {toolsOpen && <div id="graph-options" className="graph-options">
         <button onClick={newTopic}>新的学习问题</button><button disabled={!active} onClick={() => changeView('Focus')}>聚焦当前</button>
        <button onClick={() => history.back()}>返回上次位置</button><button onClick={() => history.forward()}>前进到下次位置</button>
        <details><summary>主树路径</summary>{[...(projection?.path ?? [])].reverse().map(id => <button key={id} onClick={() => open(id)}>{nodeName(id)}</button>)}</details>
        <details><summary>主题列表（当前窗口）</summary>{drawn.slice(0, 40).map(n => <button key={n.id} onClick={() => open(n.id)}>{n.kind === 'root' ? '根主题' : '子讨论'} · {n.title} · 子讨论 {n.childrenCount}</button>)}</details>
        <button disabled={!app.branch?.parent} onClick={() => { const parent = app.branch?.parent; if (parent) open(parent.branchId); }}>上级主题</button>
        <button disabled={!app.branch} onClick={() => { if (app.branch) void graphApi.root(app.branch.id).then(r => { const id = r.rootId ?? r.continuationId; if (id) open(id); }).catch(app.report); }}>所属根 / 继续上溯</button>
        <label><input type="checkbox" checked={automatic} onChange={e => setAutomatic(e.target.checked)} />移出自动展开</label>
        <label><input type="checkbox" checked={locked} onChange={e => setLocked(e.target.checked)} />锁定专注</label>
        <label><input type="checkbox" checked={titles} onChange={e => setTitles(e.target.checked)} />仅标题</label>
        <label><input type="checkbox" checked={organize} onChange={e => setOrganize(e.target.checked)} />整理解锁 · 拖动标题保存位置</label>
        <label><input type="checkbox" checked={selectMode} onChange={e => setSelectMode(e.target.checked)} />选择模式</label>
        <label>专注占比<input type="range" min=".88" max=".92" step=".01" value={ratio} onChange={e => setRatio(Number(e.target.value))} /></label>
        <label>邻域比例<input type="range" min=".45" max=".75" step=".01" value={peek} onChange={e => setPeek(Number(e.target.value))} /></label>
        <p>空白立即拖动平移；长按 350ms 框选。标题长按连线，右键划过主题后松开移除；可恢复。正文保持原生选区。</p>
       </div>}
     </div>
    <div ref={host} className={`constellation view-${view.toLowerCase()}`} data-view={view} data-node-count={drawn.length} data-edge-count={projection?.edges.length ?? 0} data-gesture-phase={gesture?.phase ?? 'idle'} data-gesture-boxes={gesture?.boxes.length ?? 0} data-selection-count={selected.length}
      onPointerDown={down} onPointerUp={up} onPointerCancel={cancel} onLostPointerCapture={() => { if (gestureRef.current) cancel(); }}
       onPointerLeave={() => { clearTimeout(hoverTimer.current); clearTimeout(autoTimer.current); hoverCandidate.current = undefined; setHoveredNode(undefined); setCursorHint(undefined); }}
      onInputCapture={() => { typed.current = performance.now(); clearTimeout(hoverTimer.current); }}
      onCompositionStartCapture={() => { composing.current = true; clearTimeout(hoverTimer.current); }}
      onCompositionEndCapture={() => { composing.current = false; typed.current = performance.now(); }}
      onContextMenu={e => { if (!protectedElement(e.target)) { e.preventDefault(); if (!gestureRef.current && !suppress.current) setMenu({ point: graphPoint(e), id: e.target instanceof Element ? e.target.closest<HTMLElement>('[data-graph-node]')?.dataset.graphNode : undefined }); } }}
      onWheel={e => { if (!protectedElement(e.target) && !e.ctrlKey && !e.metaKey && !gestureRef.current) { e.preventDefault(); changeZoom(Math.exp(-e.deltaY * .0015), graphPoint(e)); } }}>
      <svg className="graph-edges" aria-label="主题关系" width="100%" height="100%">
        <defs><marker id="graph-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" /></marker></defs>
        <g className="graph-world-edges">{renderedEdges.map(e => { const a = drawn.find(n => n.id === e.source), b = drawn.find(n => n.id === e.target); const d = a && b ? `M ${a.x} ${a.y} C ${(a.x+b.x)/2} ${a.y}, ${(a.x+b.x)/2} ${b.y}, ${b.x} ${b.y}` : ''; return a && b && <g key={e.id} data-graph-protected className={`graph-edge edge-${e.type}`} onPointerDown={event => event.stopPropagation()} onClick={() => setEdge(e)}><title>{e.type} · {nodeName(e.source)} → {nodeName(e.target)}</title><path d={d} markerEnd={e.type !== 'contact' ? 'url(#graph-arrow)' : undefined} /><path className="edge-hit" d={d} /></g>; })}</g>
      </svg>
      <div className="graph-nodes" role="group" aria-label="星空主题">
        {allocation.visible.map(({ node: n, level }, index) => {
          if (n.id === app.branch?.id) return null;
          const p = positions.get(n.id)!;
          const move = gesture?.phase === 'movePreview' && gesture.source === n.id ? { x: gesture.point.x - gesture.origin.x, y: gesture.point.y - gesture.origin.y } : { x: 0, y: 0 };
           const nodePreview = !titles && level === 2;
          const label = level >= 1;
          const preselected = selectionBox && gesture?.boxes.some(b => b.id === n.id && intersects(b, selectionBox));
           return <div key={n.id} data-hover-node={n.id} className={`graph-node ${selected.includes(n.id) || preselected ? 'selected' : ''} ${gesture?.target === n.id ? 'gesture-target' : ''} ${n.id === app.branch?.id ? 'active' : ''} ${hoveredNode === n.id ? 'hovered' : ''}`}
             style={{ left: `calc(var(--cx, 0px) + ${n.x} * var(--scale, 1) * 1px + ${move.x}px)`, top: `calc(var(--cy, 0px) + ${n.y} * var(--scale, 1) * 1px + ${move.y}px)` }}>
            <button data-graph-node={n.id} className="graph-node-header" tabIndex={index === keyboardNode ? 0 : -1} aria-label={`打开主题 ${n.title}`} title={n.title} onClick={() => open(n.id)} onFocus={() => setKeyboardNode(index)} onKeyDown={e => {
              if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
              e.preventDefault();
              const buttons = Array.from(host.current?.querySelectorAll<HTMLButtonElement>('.graph-node-header') ?? []);
              const at = buttons.indexOf(e.currentTarget), delta = ['ArrowLeft', 'ArrowUp'].includes(e.key) ? -1 : 1;
              buttons[(at + delta + buttons.length) % buttons.length]?.focus();
            }}>
              <span className={`graph-dot ${n.kind}`} />{label && <span className="graph-label">{n.title}{n.id === app.branch?.id ? ' · 当前' : n.kind === 'root' ? ' · 根' : ''}</span>}
            </button>
             {label && <button className="graph-connector" data-graph-node={n.id} data-connector aria-label={`关联 ${n.title}`} onClick={() => { if (!suppress.current) { setSelected([n.id]); setSelectMode(true); } }}>○</button>}
            {label && n.childrenCount > 0 && <button data-graph-protected aria-label={`${collapsed.includes(n.id) ? '展开' : '收起'}子讨论 ${n.title}`} onClick={() => { setCollapsed(s => s.includes(n.id) ? s.filter(id => id !== n.id) : [...s, n.id]); setExpanded(n.id); setChildCursor(-1); }}>{collapsed.includes(n.id) ? '+' : '−'} {n.childrenCount}</button>}
              {nodePreview && <div className="graph-preview" data-graph-protected><small>原文摘录</small>{n.previews.map(e => <p key={e.entryId}>{e.text}</p>)}</div>}
              {hoveredNode === n.id && view === 'Overview' && <div className="graph-hover-summary" aria-hidden="true"><small>{n.kind === 'root' ? '主线节点' : '子讨论'} · 点击进入专注视图</small><strong>{n.title}</strong>{n.previews.slice(0, 1).map(e => <p key={e.entryId}>{e.text}</p>)}</div>}
           </div>;
        })}
      </div>
      {allocation.crowded.length > 0 && <div className="graph-crowded" data-graph-protected><button onClick={() => setCrowdedOpen(!crowdedOpen)}>重叠区域 · {allocation.crowded.length} 个主题</button>{crowdedOpen && <div>{allocation.crowded.slice(0, 40).map(n => <button key={n.id} onClick={() => { setCrowdedOpen(false); open(n.id); }}>{n.title}</button>)}</div>}</div>}
      {expanded && <div className="graph-children-panel" data-graph-protected><strong>{nodeName(expanded)} · 既有子讨论</strong><button onClick={() => setExpanded(undefined)}>关闭子讨论列表</button><p>收起祖先时保留当前活动路径与所选主题。</p><div>{projection?.nodes.filter(n => n.parent === expanded).slice(0, 40).map(n => <button key={n.id} onClick={() => open(n.id)}>{n.title}</button>)}</div>{projection?.childNextCursor != null && <button onClick={() => setChildCursor(projection.childNextCursor!)}>下一页子讨论</button>}</div>}
      {projection && projection.aggregate > 0 && <button className="graph-aggregate" data-graph-protected onClick={() => document.getElementById('nav-toggle')?.click()}>其余 {projection.aggregate} 个主题 · 搜索 / 分页</button>}
      <div className="graph-query" data-graph-protected><input aria-label="图中搜索主题" placeholder="查找" value={search} maxLength={120} onChange={e => { setSearch(e.target.value); setCursor(-1); }} />
        {search && <div className="graph-search-results">{drawn.filter(n => n.title.includes(search)).slice(0, 40).map(n => <button key={n.id} onClick={() => { setSearch(''); open(n.id); }}>{n.title}</button>)}</div>}
        {projection?.pathContinuation && <button onClick={() => open(projection.pathContinuation!)}>主路径已截断 · 继续上溯</button>}
        {projection?.childNextCursor != null && <button onClick={() => setChildCursor(projection.childNextCursor!)}>继续加载子讨论</button>}
        {projection?.nextCursor !== null && projection?.nextCursor !== undefined && <button onClick={() => setCursor(projection.nextCursor ?? -1)}>下一窗口</button>}
        {cursor >= 0 && <button onClick={() => setCursor(-1)}>首窗口</button>}
        {loading && <span role="status">正在加载邻域…</span>}{error && <span role="alert">{error}<button onClick={() => setRefresh(n => n + 1)}>重试</button></span>}
      </div>
        <div ref={capsule} className="graph-capsule" data-view-label={view === 'Focus' ? '专注对话' : view === 'Peek' ? '领域预览' : '主题概览'} onClick={e => { if (suppress.current) { suppress.current = false; e.preventDefault(); return; } const target = e.target instanceof Element ? e.target : null; if (view !== 'Focus' && app.branch && !target?.closest('button, input, textarea, select, a, [data-graph-interactive], .message-text')) open(app.branch.id); }} style={(app.branch && active ? { left: `calc(var(--cx, 0px) + ${active.x - focusWidth / 2} * var(--scale, 1) * 1px)`, top: `calc(var(--cy, 0px) + ${active.y - focusHeight / 2} * var(--scale, 1) * 1px)`, width: `calc(${focusWidth}px * var(--scale, 1))`, height: `calc(${focusHeight}px * var(--scale, 1))` } : { left: 24, top: 80, width: size.width - 48, height: size.height - 104 }) as CSSProperties} aria-label="对话胶囊">
          {app.branch && <div className="capsule-summary" data-graph-protected role="button" tabIndex={view === 'Overview' ? 0 : -1} aria-label={`打开主题 ${app.branch.title}`} aria-hidden={view === 'Focus'} onClick={() => { if (view === 'Overview') open(app.branch!.id); }} onKeyDown={e => { if (view === 'Overview' && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); open(app.branch!.id); } }}><h2>{app.branch.title} · 当前</h2>{!titles && active?.previews.map(p => <p key={p.entryId}>{p.text}</p>)}</div>}
        {children}
      </div>
       {gesture && gesture.phase !== 'pressCandidate' && <div className="gesture-status" data-graph-protected role="status">
        {gesture.phase === 'erasePreview' ? gesture.target ? `「${nodeName(gesture.target)}」松开移除，可恢复` : gesture.ambiguous ? '目标重叠，请取消后明确选择' : '划过一个主题以预览移除' : gesture.phase === 'lasso' ? '框选主题' : gesture.phase === 'connectPreview' ? '松开后确认关系类型' : '拖动中'}
        <button onPointerDown={e => e.stopPropagation()} onClick={cancel}>取消操作</button>
       </div>}
       {cursorHint && <div className="graph-cursor-hint" aria-hidden="true" style={{ left: cursorHint.x + 16, top: cursorHint.y + 16 }}><span>拖到另一主题即可关联</span><strong>{cursorHint.title}</strong></div>}
      <svg className="gesture-overlay" width="100%" height="100%">
        {selectionBox && <rect x={selectionBox.left} y={selectionBox.top} width={selectionBox.right - selectionBox.left} height={selectionBox.bottom - selectionBox.top} />}
        {gesture?.phase === 'erasePreview' && <polyline className="erase-path" points={gesture.path.map(p => `${p.x},${p.y}`).join(' ')} />}
        {gesture?.phase === 'connectPreview' && <line x1={gesture.origin.x} y1={gesture.origin.y} x2={gesture.point.x} y2={gesture.point.y} />}
      </svg>
       {selected.length > 0 && <div className="graph-selection" data-graph-protected><span>已选 {selected.length} 个主题</span><button disabled={selected.length < 2 || selected.length > 21} onClick={() => setRelation({ source: selected[0], targets: selected.slice(1) })}>关联</button><button className="danger" disabled={selected.length > 20} onClick={() => setRemoveIds(selected)}>移除所选</button><button onClick={() => setSelected([])}>清除选择</button></div>}
      {menu && <div className="graph-context" data-graph-protected style={{ left: Math.max(16, Math.min(menu.point.x, size.width - 240)), top: Math.max(16, Math.min(menu.point.y, size.height - 200)) }}>
         {menu.id && <><strong>{nodeName(menu.id)}</strong><button onClick={() => { open(menu.id!); setMenu(undefined); }}>继续对话</button><button className="danger" onClick={() => { setRemoveIds([menu.id!]); setMenu(undefined); }}>移除主题（可恢复）</button><button onClick={() => { setSelected([menu.id!]); setSelectMode(true); setMenu(undefined); }}>关联到…选择目标</button></>}
        {menu.id && <div><button disabled={busy} onClick={() => void moveNode(menu.id!, -80, 0)}>向左移动</button><button disabled={busy} onClick={() => void moveNode(menu.id!, 80, 0)}>向右移动</button><button disabled={busy} onClick={() => void moveNode(menu.id!, 0, -80)}>向上移动</button><button disabled={busy} onClick={() => void moveNode(menu.id!, 0, 80)}>向下移动</button></div>}
        <button onClick={() => { setSelectMode(true); setMenu(undefined); }}>选择模式</button><button onClick={() => setMenu(undefined)}>关闭菜单</button>
      </div>}
    </div>
    {relation && <Dialog title="确认关联范围" close={() => setRelation(undefined)} confirm={async () => { await graphApi.contact(relation.source, relation.targets); setRelation(undefined); setRefresh(n => n + 1); }}>
      <label>主源<select value={relation.source} onChange={e => { const all = [relation.source, ...relation.targets]; setRelation({ source: e.target.value, targets: all.filter(id => id !== e.target.value) }); }}>{[relation.source, ...relation.targets].map(id => <option key={id} value={id}>{nodeName(id)}</option>)}</select></label>
      <p>联系（无向）：{nodeName(relation.source)} ↔ {relation.targets.map(nodeName).join('、')}</p><p>仅建立以上联系，不生成全连接。关联不进入上下文。</p>
      <button disabled={relation.targets.length !== 1} onClick={() => { const intent = relation; void app.action({ type: 'switch', branchId: intent.targets[0] }).then(() => { setRelation(undefined); references(intent.source); }).catch(app.report); }}>改为引用：选择来源、原文范围和背景（单目标）</button>
    </Dialog>}
    {edge && <Dialog title="关系详情" close={() => setEdge(undefined)}>
      <p>{edge.type === 'parent' ? '分支由来' : edge.type === 'reference' ? '有向引用' : '无向联系'}：{nodeName(edge.source)} → {nodeName(edge.target)}</p>
      <p>{edge.type === 'contact' ? '关联不进入上下文。断开不删除对话。' : edge.type === 'reference' ? '引用由既有消息记录派生，可在对话中返回来源。' : '移动与断开联系不改变主树归属。'}</p>
      <button onClick={() => { open(edge.source); setEdge(undefined); }}>打开来源</button><button onClick={() => { open(edge.target); setEdge(undefined); }}>打开目标</button>
      {edge.type === 'contact' && <button onClick={() => { void graphApi.contact(edge.source, [edge.target], true).then(() => { setEdge(undefined); setRefresh(n => n + 1); }).catch(app.report); }}>断开联系</button>}
    </Dialog>}
    {removeIds && <ConfirmDialog title="移除所选主题？" label="确认移除" close={() => setRemoveIds(undefined)} confirm={async () => { await remove(removeIds); setRemoveIds(undefined); }}><p>{removeIds.length} 个主题：{removeIds.map(nodeName).join('、')}</p><p>主题、消息和已保存草稿可在十分钟内恢复；独立子分支保留。不永久删除会话。</p></ConfirmDialog>}
  </>;
}
