import { chromium } from 'playwright-core';
import { existsSync } from 'node:fs';
const url=process.argv[2] ?? 'http://127.0.0.1:4173/', chrome=process.env.CHROME_PATH ?? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
if(!existsSync(chrome)) throw new Error('Chrome executable not found; set CHROME_PATH');
const b=await chromium.launch({executablePath:chrome,headless:true}); const p=await b.newPage({viewport:{width:390,height:844},hasTouch:true,isMobile:true});
await p.goto(url,{waitUntil:'networkidle'}); await p.evaluate(()=>document.fonts.ready);
const target=p.locator('main').first(); const box=await target.boundingBox();
let singleTouch='SKIP', longPress='SKIP';
if(box){
  await p.touchscreen.tap(box.x+100,box.y+150); singleTouch='PASS';
  await p.evaluate(([x,y])=>{ const e=document.elementFromPoint(x,y); e?.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,pointerType:'touch',clientX:x,clientY:y})); },[box.x+100,box.y+150]);
  await new Promise(r=>setTimeout(r,650));
  await p.evaluate(([x,y])=>document.elementFromPoint(x,y)?.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,pointerType:'touch',clientX:x,clientY:y})),[box.x+100,box.y+150]); longPress='PASS';
}
console.log(JSON.stringify({hasTouch:true,singleTouch,longPress,lasso:'SKIP',pinch:'SKIP',skipReason:'Desktop Chromium has no real multi-contact API; lasso/pinch require WebView2/device harness.'}));
await b.close();
