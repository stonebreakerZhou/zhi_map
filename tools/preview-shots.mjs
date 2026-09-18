/** Development helper: capture the app UI so redesign work can be reviewed against real pixels. */
import { mkdir, rm } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import { chromium } from 'playwright-core';

const CHROME = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const base = process.argv[2] ?? 'http://127.0.0.1:8123';
const out = 'test-results/ui-review';
const port = Number(process.env.CDP_PORT ?? 9333);
// Second profile so a Chrome left over from an earlier run cannot lock this one out.
const profile = process.env.PROFILE_DIR ?? `${tmpdir()}/zhishu-review-${port}`;
await mkdir(out, { recursive: true });

// The sandbox denies piped stdio, so Chrome is started detached and Playwright attaches over CDP.
// The profile persists between runs so the anonymous session keeps pointing at the seeded workspace;
// point PROFILE_DIR/FRESH_PROFILE at a new one when a previous Chrome is still holding the old lock.
if (process.env.FRESH_PROFILE === '1') await rm(profile, { recursive: true, force: true });
const chrome = spawn(CHROME, [
  '--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  '--no-first-run', '--no-default-browser-check', '--disable-extensions', '--hide-scrollbars',
  '--window-size=1440,900', 'about:blank',
], { detached: true, stdio: 'ignore' });

const endpoint = async () => {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (r.ok) return (await r.json()).webSocketDebuggerUrl;
    } catch { /* still starting */ }
    await new Promise(r => setTimeout(r, 250));
  }
  throw new Error('Chrome did not expose a CDP endpoint');
};

const stop = () => { try { process.kill(-chrome.pid); } catch { try { chrome.kill(); } catch { /* already gone */ } } };

try {
  const browser = await chromium.connectOverCDP(await endpoint());
  const context = browser.contexts()[0] ?? await browser.newContext();
  const page = await context.newPage();
  // The preview serves fixed asset filenames, so a cached bundle would hide this run's changes.
  await page.route('**/*', route => route.continue({ headers: { ...route.request().headers(), 'cache-control': 'no-cache' } }));
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto(base, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);

  for (let i = 0; i < 10; i++) {
    const next = page.locator('.tutorial-card button').last();
    if (!(await next.count())) break;
    await next.click().catch(() => {});
    await page.waitForTimeout(250);
  }
  await page.waitForTimeout(800);
  const start = page.locator('.onboarding button').last();
  if (await start.count()) { await start.click().catch(() => {}); await page.waitForTimeout(2000); }
  await page.screenshot({ path: `${out}/00-chat-top.png` });

  // A workspace with no transcript is fine: the graph captures below still matter.
  if (await page.locator('.message').count()) {
    await page.locator('.message').last().scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    await page.locator('.message.assistant').last().hover();
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/01-chat-assistant-actions.png` });
    await page.locator('.message.user').last().hover();
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/02-chat-user-actions.png` });
  } else {
    console.log('no transcript in this workspace; skipping the chat crops');
  }

  const view = () => page.evaluate(() => document.querySelector('.constellation')?.getAttribute('data-view'));
  const openCurrent = async () => {
    for (let i = 0; i < 8 && (await view()) !== 'Focus'; i++) {
      await page.locator('.graph-tools .graph-primary').click();
      await page.waitForTimeout(1000);
    }
  };

  await page.click('.mode-toggle');
  await page.waitForTimeout(2600);
  await page.screenshot({ path: `${out}/03-graph-overview.png` });

  await page.click('.graph-capsule');
  await page.waitForTimeout(1500);
  if ((await view()) !== 'Focus') { await openCurrent(); }
  await page.waitForTimeout(2200);
  await page.screenshot({ path: `${out}/04-graph-focus.png` });

  await page.locator('.graph-tools .graph-secondary').click();
  await page.waitForTimeout(2400);
  if (await page.locator('.graph-node-header').count()) {
    const box = await page.locator('.graph-node-header').first().boundingBox();
    if (box) { await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.waitForTimeout(700); }
  }
  await page.screenshot({ path: `${out}/05-graph-hover.png` });

  console.log('graph:', JSON.stringify(await page.evaluate(() => ({
    view: document.querySelector('.constellation')?.getAttribute('data-view'),
    nodes: document.querySelector('.constellation')?.getAttribute('data-node-count'),
    edges: document.querySelector('.constellation')?.getAttribute('data-edge-count'),
    labels: [...document.querySelectorAll('.graph-label')].map(n => n.textContent),
    crowded: document.querySelector('.graph-crowded')?.textContent ?? null,
  }))));

  // Narrow layout: the same components must stay reachable at 390x844.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}/06-narrow-graph.png` });
  await page.click('.mode-toggle');
  await page.waitForTimeout(1500);
  await page.locator('.message').last().scrollIntoViewIfNeeded();
  await page.locator('.message.user').last().hover();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${out}/07-narrow-chat.png` });

  console.log('errors:', errors.length ? [...new Set(errors)].slice(0, 6) : 'none');
} finally {
  stop();
}
