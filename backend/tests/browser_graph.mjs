import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import os from 'node:os';

export async function verifyGraph(browser, url) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [], sizes = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('response', async r => { if (new URL(r.url()).pathname === '/api/graph') { try { sizes.push((await r.body()).length); } catch {} } });
  const api = (path, body) => page.evaluate(async ({ path, body }) => {
    const response = await fetch(path, body === undefined ? undefined : { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    const value = await response.json(); if (!response.ok) throw Error(JSON.stringify(value)); return value;
  }, { path, body });
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.locator('[data-view="Overview"]').waitFor();
  await page.locator('[data-sample]').click();
  await page.locator('[data-view="Focus"]').waitFor();
  await page.locator('.graph-capsule .message').first().waitFor();
  const seedView = await api('/api/workspace/view');
  const root = await api(`/api/branches/${seedView.active}`);
  const rootPage = await api(`/api/branches/${root.id}/entries?limit=40`);
  const sourceEntry = rootPage.items.find(e => e.kind === 'message');
  const childIds = [];
  for (const title of ['配方法与完全平方', '判别式与实根个数', '抛物线与对称轴', '韦达定理与根的关系']) {
    const v = await api('/api/workspace/view');
    const child = await api('/api/workspace/actions?response=compact', { type: 'fork', branchId: root.id, entryId: sourceEntry.id, revision: v.revision });
    childIds.push(child.active);
    await api('/api/workspace/actions?response=compact', { type: 'metadata', branchId: child.active, title, tags: [], revision: child.revision });
  }
  const childPage = await api(`/api/branches/${childIds[0]}/entries?limit=40`);
  for (const title of ['顶点坐标的推导', '最小值与非负平方']) {
    const v = await api('/api/workspace/view');
    const nested = await api('/api/workspace/actions?response=compact', { type: 'fork', branchId: childIds[0], entryId: childPage.items[0].id, revision: v.revision });
    await api('/api/workspace/actions?response=compact', { type: 'metadata', branchId: nested.active, title, tags: [], revision: nested.revision });
  }
  const v = await api('/api/workspace/view');
  await api('/api/workspace/actions?response=compact', { type: 'switch', branchId: root.id, revision: v.revision });
  await page.reload({ waitUntil: 'networkidle' });
  await page.getByRole('button', { name: '继续对话', exact: true }).first().click();
  await page.waitForTimeout(320);
  await page.screenshot({ path: 'test-results/graph-focus.png' });
  const focusedBox = await page.locator('.graph-capsule').boundingBox();
  const stageBox = await page.locator('.constellation').boundingBox();
  assert(Math.abs(focusedBox.width - Math.min(stageBox.width * .9, stageBox.width - 48)) <= 1);
  assert((await page.locator('#draft').boundingBox()).width > 700);
  await page.locator('#draft').fill('IME and stable caret 😀');
  await page.locator('#draft').evaluate(el => { window.stableEditor = el; el.focus(); el.setSelectionRange(3, 3); el.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true })); });
  const h = await page.locator('.constellation').boundingBox();
  await page.mouse.move(h.x + 4, h.y + h.height / 2);
  await page.waitForTimeout(1100); // Deliberately exceeds both IME/type and dwell thresholds.
  assert.equal(await page.locator('.constellation').getAttribute('data-view'), 'Focus');
  await page.locator('#draft').evaluate(el => el.dispatchEvent(new CompositionEvent('compositionend', { bubbles: true })));
  await page.getByRole('button', { name: '查看邻域', exact: true }).click();
  await page.locator('[data-view="Peek"]').waitFor();
  assert(await page.locator('#draft').evaluate(el => el === window.stableEditor && el.selectionStart === 3));
  assert((await page.locator('#draft').evaluate(el => parseFloat(getComputedStyle(el).fontSize))) >= 12);
  await page.waitForTimeout(320);
  await page.screenshot({ path: 'test-results/graph-peek.png' });
  const peekBox = await page.locator('.graph-capsule').boundingBox();
  assert(Math.abs(peekBox.width / focusedBox.width - .62) < .01);
  assert(Math.abs(peekBox.height / focusedBox.height - .62) < .01);
  await page.getByRole('button', { name: '概览', exact: true }).click();
  await page.locator('[data-view="Overview"]').waitFor();
  await page.waitForTimeout(320);
  await page.screenshot({ path: 'test-results/graph-overview.png' });
  assert(await page.locator('#draft').evaluate(el => el === window.stableEditor && el.selectionStart === 3 && el.selectionEnd === 3));
  await page.locator('#draft').focus();
  await page.keyboard.type('native');
  assert((await page.locator('#draft').inputValue()).startsWith('IMEnative'));
  await page.getByRole('button', { name: '收起子讨论 配方法与完全平方', exact: true }).click();
  assert.equal(await page.getByRole('button', { name: '打开主题 顶点坐标的推导', exact: true }).count(), 0);
  await page.getByRole('button', { name: '展开子讨论 配方法与完全平方', exact: true }).click();
  await page.getByRole('button', { name: '关闭子讨论列表', exact: true }).click();
  const nodes = page.locator('.graph-node-header');
  await nodes.nth(1).waitFor();
  const first = await nodes.first().boundingBox(), second = await nodes.nth(1).boundingBox();
  const ids = await nodes.evaluateAll(elements => elements.map(e => e.dataset.graphNode));
  const before = await api('/api/workspace/view');
  // A real short right click exposes a menu and never removes a theme.
  await page.mouse.click(first.x + first.width / 2, first.y + 18, { button: 'right' });
  await page.getByRole('button', { name: '关闭菜单', exact: true }).click();
  assert.equal((await api('/api/workspace/view')).revision, before.revision);
  // Real long hold on blank then rectangle across the two headers.
  const left = Math.min(first.x, second.x) - 20, top = Math.min(first.y, second.y) - 20;
  await page.mouse.move(left, top); await page.mouse.down();
  await page.getByText(/框选主题/).waitFor();
  await page.mouse.move(Math.max(first.x + first.width, second.x + second.width) + 10, Math.max(first.y + first.height, second.y + second.height) + 4, { steps: 10 });
  await page.mouse.up();
  await page.locator('.graph-selection').getByRole('button', { name: '关联', exact: true }).click();
  await page.getByRole('dialog', { name: '确认关联范围', exact: true }).waitFor();
  await page.locator('#modal-confirm').click();
  await page.locator('.edge-contact').waitFor({ state: 'attached' });
  assert((await api('/api/graph')).edges.some(e => e.type === 'contact'));
  await page.locator('.graph-selection').getByRole('button', { name: '清除选择', exact: true }).click();
  // Stroke previews, only releasing submits; unrelated input does not consume recovery.
  const b = await nodes.first().boundingBox();
  await page.mouse.move(b.x - 30, b.y + 18); await page.mouse.down({ button: 'right' });
  await page.mouse.move(b.x + b.width / 2, b.y + 18, { steps: 8 });
  await page.getByText(/松开移除，可恢复/).waitFor();
  assert.equal((await api(`/api/branches/${ids[0]}`)).id, ids[0]);
  await page.screenshot({ path: 'test-results/graph-erase-preview.png' });
  await page.mouse.up({ button: 'right' });
  await page.locator('.graph-recovery').waitFor();
  await page.locator('#draft').fill('unrelated graph recovery draft');
  await page.locator('.graph-recovery').getByRole('button', { name: '恢复', exact: true }).click();
  assert.equal(await page.locator('#draft').inputValue(), 'unrelated graph recovery draft');
  assert.equal((await api(`/api/branches/${ids[0]}`)).id, ids[0]);
  // Persist another receipt, reload, and recover through the paged server list.
  const target = await api(`/api/branches/${ids[0]}`);
  await api('/api/graph/removals', { operationId: 'reload-receipt', targets: [{ id: target.id, revision: target.revision }] });
  await page.reload({ waitUntil: 'networkidle' });
  await page.getByRole('button', { name: /最近移除/ }).click();
  await page.getByRole('dialog', { name: '最近移除', exact: true }).getByRole('button', { name: '恢复', exact: true }).click();
  await page.locator('#close-modal').click();
  await page.screenshot({ path: 'test-results/graph-recovered.png' });
  // Browser navigation restores a branch visit rather than repeating its creation.
  await page.getByRole('button', { name: '继续对话', exact: true }).first().click();
  await page.waitForTimeout(320);
  const originalTitle = await page.locator('#chat-header h1').innerText();
  await page.getByRole('button', { name: '概览', exact: true }).click();
  await page.getByRole('textbox', { name: '图中搜索主题', exact: true }).fill('最小值与非负平方');
  await page.locator('.graph-search-results').getByRole('button', { name: '最小值与非负平方', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('#chat-header h1')?.textContent === '最小值与非负平方');
  await page.goBack();
  await page.waitForFunction(title => document.querySelector('#chat-header h1')?.textContent === title, originalTitle);
  await page.goForward();
  await page.waitForFunction(() => document.querySelector('#chat-header h1')?.textContent === '最小值与非负平方');
  for (const viewport of [{ width: 900, height: 600 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    if (await page.locator('.constellation').getAttribute('data-view') !== 'Focus') await page.getByRole('button', { name: '继续对话', exact: true }).first().click();
    await page.waitForTimeout(320);
    const send = await page.locator('#send').boundingBox();
    assert(send.x >= 0 && send.x + send.width <= viewport.width && send.y + send.height <= viewport.height);
    assert((await page.locator('.constellation').boundingBox()).height > viewport.height / 2);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  // Deterministic large fixture: no full state download, no full hidden graph DOM.
  const records = [{ type: 'manifest', schemaVersion: 3, active: 'g0' }, { type: 'session', data: { id: 'gs', title: '10k graph' } }];
  for (let i = 0; i < 10000; i++) records.push({ type: 'branch', data: { id: `g${i}`, sessionId: 'gs', title: `Graph topic ${i}`, tags: [], parent: i === 0 || i >= 9000 ? null : { branchId: i < 200 ? `g${i-1}` : 'g0', entryId: 'fixture-origin' }, kept: false, draft: '' } });
  records.push({ type: 'end', entries: 0 });
  await page.evaluate(async data => {
    const view = await (await fetch('/api/workspace/view')).json();
    const r = await fetch(`/api/import/ndjson?revision=${view.revision}`, { method: 'POST', headers: { 'content-type': 'application/x-ndjson' }, body: data });
    if (!r.ok) throw Error(await r.text());
  }, records.map(r => JSON.stringify(r)).join('\n') + '\n');
  const cold = performance.now(); await page.reload({ waitUntil: 'networkidle' });
  await page.locator('.graph-node-header').first().waitFor();
  const coldMs = performance.now() - cold;
  assert(Number(await page.locator('.constellation').getAttribute('data-node-count')) <= 200);
  assert(await page.locator('.graph-label').count() <= 60);
  assert(await page.locator('.graph-preview').count() <= 12);
  const framesPromise = page.evaluate(() => new Promise(resolve => {
    const frames = []; let last;
    const frame = t => { if (last !== undefined) frames.push(t - last); last = t; if (frames.length < 180) requestAnimationFrame(frame); else resolve(frames); };
    requestAnimationFrame(frame);
  }));
  for (let i = 0; i < 35; i++) {
    await page.mouse.move(h.x + 8, h.y + 200); await page.mouse.down();
    await page.mouse.move(h.x + 8 + (i % 2 ? 40 : -40), h.y + 220, { steps: 3 }); await page.mouse.up();
  }
  const frames = await framesPromise, ordered = [...frames].sort((a, b) => a - b);
  const measurement = { engine: browser.version(), os: `${os.platform()} ${os.release()}`, cpu: os.cpus()[0].model,
    coldReloadMs: coldMs, graphMaxResponseBytes: Math.max(...sizes), method: 'requestAnimationFrame intervals, headless Chrome; 35 pan gestures, not presentation trace',
    frames, p95: ordered[Math.ceil(ordered.length * .95) - 1], longest: ordered.at(-1), over33_4Ratio: frames.filter(n => n > 33.4).length / frames.length };
  await writeFile('test-results/graph-measurements.json', JSON.stringify(measurement, null, 2));
  await page.screenshot({ path: 'test-results/graph-10k.png' });
  assert(Math.max(...sizes) <= 256 * 1024); assert.deepEqual(errors, []);
  console.log(`GRAPH browser: lasso/contact/right preview/release/recovery/reload/IME/editor identity passed. Cold ${coldMs.toFixed(1)}ms; RAF p95 ${measurement.p95.toFixed(2)}ms; max graph bytes ${measurement.graphMaxResponseBytes}.`);
  await page.close();
}
