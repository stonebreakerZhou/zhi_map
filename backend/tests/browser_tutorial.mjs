import assert from 'node:assert/strict';

async function assertGeometry(page, expectSpotlight) {
  const card = await page.locator('.tutorial-card').boundingBox();
  const viewport = page.viewportSize();
  assert(card && card.x >= 0 && card.y >= 0 && card.x + card.width <= viewport.width && card.y + card.height <= viewport.height, 'Tutorial card must stay inside the viewport');
  const spotlight = page.locator('.tutorial-spotlight');
  assert.equal(await spotlight.count(), expectSpotlight ? 1 : 0);
  if (expectSpotlight) {
    const spot = await spotlight.boundingBox();
    assert(spot && spot.width > 20 && spot.height > 20, 'Spotlight must expose a real target');
    assert(spot.x >= 0 && spot.y >= 0 && spot.x + spot.width <= viewport.width && spot.y + spot.height <= viewport.height, 'Spotlight must stay inside the viewport');
    assert.equal(await page.locator('.tutorial-arrow').count(), 1);
  }
}

async function runViewport(browser, url, viewport, suffix) {
  const page = await browser.newPage({ viewport });
  await page.goto(url, { waitUntil: 'networkidle' });
  const tutorial = page.getByRole('dialog', { name: '知树新手教程' });
  await tutorial.waitFor();
  await assertGeometry(page, false);
  await page.screenshot({ path: `test-results/tutorial-${suffix}-welcome.png` });
  await tutorial.getByRole('button', { name: '开始导览' }).click();
  for (let step = 1; step <= 4; step++) {
    await page.waitForTimeout(400);
    await assertGeometry(page, true);
    await page.screenshot({ path: `test-results/tutorial-${suffix}-step-${step}.png` });
    await tutorial.getByRole('button', { name: step === 4 ? '完成' : '下一步' }).click();
  }
  assert.equal(await page.evaluate(() => localStorage.getItem('zhishu-tutorial-complete')), '1');
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal(await tutorial.count(), 0);
  await page.close();
}

export async function verifyTutorial(browser, url) {
  await runViewport(browser, url, { width: 1440, height: 900 }, 'desktop');
  const replay = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await replay.addInitScript(() => localStorage.setItem('zhishu-tutorial-complete', '1'));
  await replay.goto(url, { waitUntil: 'networkidle' });
  await replay.locator('#conversation-actions-button').click();
  await replay.locator('#settings-button').click();
  await replay.getByRole('button', { name: /新手教程/ }).click();
  await replay.getByRole('button', { name: '重新播放教程' }).click();
  await replay.getByRole('dialog', { name: '知树新手教程' }).waitFor();
  await assertGeometry(replay, false);
  await replay.getByRole('button', { name: '跳过' }).click();
  await replay.close();
  await runViewport(browser, url, { width: 390, height: 844 }, 'mobile');
  console.log('Tutorial: desktop/mobile coachmarks, geometry, persistence, and settings replay passed.');
}
