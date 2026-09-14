import { chromium } from 'playwright-core';
import { existsSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
const url = process.argv[2] ?? 'http://127.0.0.1:4173/';
const chrome = process.env.CHROME_PATH ?? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
if (!existsSync(chrome)) throw new Error('Chrome executable not found; set CHROME_PATH');
await mkdir('test-results/pixel', { recursive: true });
const browser = await chromium.launch({ executablePath: chrome, headless: true });
const output = [];
for (const [width, height] of [[1440,900],[1024,720],[390,844],[699,900],[700,900],[701,900]]) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  await page.addStyleTag({ content: '* { animation: none !important; transition: none !important; caret-color: transparent !important; scroll-behavior: auto !important }' });
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  const measure = await page.evaluate(() => Object.fromEntries(['#app','#chat-header','#draft','#send','#connection'].map(s => { const e=document.querySelector(s); if (!e) return [s,null]; const r=e.getBoundingClientRect(), c=getComputedStyle(e); return [s,{rect:{x:r.x,y:r.y,width:r.width,height:r.height},font:c.font,color:c.color,background:c.backgroundColor,padding:c.padding,borderRadius:c.borderRadius}]; })));
  await page.screenshot({ path: `test-results/pixel/${width}x${height}.png`, fullPage: false });
  output.push({ width, height, measure }); await page.close();
}
await writeFile('test-results/pixel/measure.json', JSON.stringify({ goldens: false, note: 'No reviewed golden images; screenshots are measurement artifacts, not pixel-pass evidence.', output }, null, 2));
await browser.close();
