/** Drive the native drawer; legacy feature tests retain their operations and assertions. */
export async function navClick(page, selector, double = false) {
  const toggle = page.getByRole('button', { name: '菜单', exact: true });
  if (await toggle.getAttribute('aria-expanded') !== 'true') await toggle.click();
  if (double) await page.locator(selector).dblclick();
  else await page.locator(selector).click();
}

export async function focusConversation(page) {
  await page.getByRole('button', { name: '继续对话', exact: true }).first().click();
  await page.locator('[data-view="Focus"]').waitFor();
}
