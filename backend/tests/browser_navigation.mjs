/** Drive the native drawer; legacy feature tests retain their operations and assertions. */
export async function navClick(page, selector, double = false) {
  const toggle = page.getByRole('button', { name: '菜单', exact: true });
  const account = page.locator('#conversation-actions-button');
  if (selector === '#settings-button') {
    await account.waitFor({ state: 'attached' });
    if (!await account.isVisible() && await toggle.isVisible()) await toggle.click();
    if (await account.getAttribute('aria-expanded') !== 'true') await account.click();
  }
  const target = page.locator(selector);
  await target.waitFor({ state: 'attached' });
  if (!await target.isVisible() && await toggle.isVisible() && await toggle.getAttribute('aria-expanded') !== 'true') await toggle.click();
  if (double) await target.dblclick();
  else await target.click();
}

export async function focusConversation(page) {
  if (await page.locator('.mode-graph').count()) await page.getByRole('button', { name: '返回对话', exact: true }).click();
  await page.locator('.mode-chat #draft').waitFor();
}

export async function openModelSettings(page) {
  await navClick(page, '#settings-button');
  await page.getByRole('button', { name: /模型服务/ }).click();
  await page.locator('#ai-provider').waitFor();
}

export async function conversationAction(page, selector) {
  const toggle = page.getByRole('button', { name: '菜单', exact: true });
  const account = page.locator('#conversation-actions-button');
  await account.waitFor({ state: 'attached' });
  if (!await account.isVisible() && await toggle.isVisible()) await toggle.click();
  if (await account.getAttribute('aria-expanded') !== 'true') await account.click();
  await page.locator(selector).click();
}
