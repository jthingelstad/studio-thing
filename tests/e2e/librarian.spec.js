const { test, expect } = require('@playwright/test');

test('librarian email form submits in a visible way', async ({ page }) => {
  test.setTimeout(120000);
  const consoleMessages = [];
  const requestFailures = [];
  const responses = [];
  const streamResponses = [];
  page.on('console', (message) => consoleMessages.push(`${message.type()}: ${message.text()}`));
  page.on('requestfailed', (request) => {
    requestFailures.push(`${request.method()} ${request.url()} ${request.failure()?.errorText || ''}`);
  });
  page.on('response', (response) => {
    if (response.url().includes('/auth')) {
      responses.push(`${response.status()} ${response.url()}`);
    }
    if (response.url().includes('/prompts')) {
      responses.push(`${response.status()} ${response.url()}`);
    }
    if (response.url().includes('lambda-url.us-east-1.on.aws')) {
      streamResponses.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.goto('http://localhost:8080/librarian/');
  await page.getByLabel('Subscriber email').fill('jamie@thingelstad.com');
  await page.getByRole('button', { name: 'Enter' }).click();
  await expect(page.locator('#librarian-chat')).toBeVisible({ timeout: 30000 });
  await expect(page.locator('#librarian-prompts button').first()).toBeVisible({ timeout: 30000 });

  await page.getByLabel('Ask Thingy').fill('What has the archive said about RSS and the open web?');
  await page.keyboard.press('Enter');
  await expect(page.locator('#librarian-prompts')).toBeHidden();
  await expect(page.locator('.librarian-message-assistant a[href^="/archive/"]').first()).toBeVisible({ timeout: 90000 });
  await expect(page.locator('.librarian-message-assistant ul, .librarian-message-assistant ol').first()).toBeVisible();

  const state = {
    authHidden: await page.locator('#librarian-auth').evaluate((node) => node.hidden),
    chatHidden: await page.locator('#librarian-chat').evaluate((node) => node.hidden),
    enterDisabled: await page.locator('#librarian-auth-form button[type="submit"]').evaluate((node) => node.disabled),
    visibleText: await page.locator('body').innerText(),
    renderedLists: await page.locator('.librarian-message-assistant ul, .librarian-message-assistant ol').count(),
    sourceLinks: await page.locator('.librarian-message-assistant a[href^="/archive/"]').count(),
    sourceTitle: await page.locator('.librarian-message-assistant a[href^="/archive/"]').first().getAttribute('title'),
    consoleMessages,
    requestFailures,
    responses,
    streamResponses,
  };
  console.log(JSON.stringify(state, null, 2));

  expect(state.enterDisabled).toBe(false);
  expect(state.authHidden).toBe(true);
  expect(state.chatHidden).toBe(false);
  expect(state.visibleText).not.toContain('Sources');
  expect(state.streamResponses.some((response) => response.startsWith('200 '))).toBe(true);
  expect(state.renderedLists).toBeGreaterThan(0);
  expect(state.sourceLinks).toBeGreaterThan(0);
  expect(state.sourceTitle).toContain('Weekly Thing');

  await page.getByRole('button', { name: 'Use a different email' }).click();
  await expect(page.locator('#librarian-auth')).toBeVisible();
  await expect(page.locator('#librarian-chat')).toBeHidden();
  await expect.poll(() => page.evaluate(() => window.localStorage.getItem('weeklyThingLibrarianToken'))).toBeNull();
});

test('librarian auth handles signup and unconfirmed states', async ({ page }) => {
  await page.addInitScript(() => {
    window.WEEKLY_THING_LIBRARIAN_API = 'https://mock-librarian.test';
    window.localStorage.clear();
  });
  await page.route('https://mock-librarian.test/auth', async (route) => {
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({
        status: 204,
        headers: {
          'access-control-allow-origin': '*',
          'access-control-allow-methods': 'POST, OPTIONS',
          'access-control-allow-headers': 'content-type, authorization',
        },
      });
      return;
    }
    const body = route.request().postDataJSON();
    let payload;
    if (body.action === 'subscribe') {
      payload = {
        status: 'subscribed',
        subscriber_status: 'unconfirmed',
        message: 'Check your inbox to confirm your subscription before using Thingy.',
      };
    } else if (body.action === 'resend_confirmation') {
      payload = {
        status: 'reminder_sent',
        message: 'Confirmation email sent. Check your inbox.',
      };
    } else if (body.email === 'pending@example.com') {
      payload = {
        status: 'unconfirmed',
        message: 'Please confirm your email before using Thingy.',
      };
    } else {
      payload = {
        status: 'not_found',
        message: 'That email is not subscribed. Would you like to be added?',
      };
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'access-control-allow-origin': '*',
        'access-control-allow-headers': 'content-type, authorization',
      },
      body: JSON.stringify(payload),
    });
  });
  await page.route('https://mock-librarian.test/prompts', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'access-control-allow-origin': '*',
        'access-control-allow-headers': 'content-type, authorization',
      },
      body: JSON.stringify({
        source: 'generated',
        prompts: [
          { label: 'Archive one', question: 'Question one?' },
          { label: 'Archive two', question: 'Question two?' },
          { label: 'Archive three', question: 'Question three?' },
        ],
      }),
    });
  });

  await page.goto('http://localhost:8080/librarian/');
  await page.getByLabel('Subscriber email').fill('new@example.com');
  await page.getByRole('button', { name: 'Enter' }).click();
  await expect(page.getByText('That email is not subscribed. Would you like to be added?')).toBeVisible();
  await page.getByRole('button', { name: 'Add me' }).click();
  await expect(page.getByText('Check your inbox to confirm your subscription before using Thingy.')).toBeVisible();

  await page.getByLabel('Subscriber email').fill('pending@example.com');
  await page.getByRole('button', { name: 'Enter' }).click();
  await expect(page.getByText('Please confirm your email before using Thingy.')).toBeVisible();
  await page.getByRole('button', { name: 'Resend confirmation email' }).click();
  await expect(page.getByText('Confirmation email sent. Check your inbox.')).toBeVisible();
});

test('librarian prompts and inline citations render with mocked APIs', async ({ page }) => {
  const chatRequests = [];
  await page.addInitScript(() => {
    window.WEEKLY_THING_LIBRARIAN_API = 'https://mock-librarian.test';
    window.WEEKLY_THING_LIBRARIAN_STREAM_API = '';
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  await page.route('https://mock-librarian.test/auth', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'access-control-allow-origin': '*' },
      body: JSON.stringify({ status: 'active', token: 'mock-token', expires_at: 9999999999 }),
    });
  });
  await page.route('https://mock-librarian.test/prompts', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'access-control-allow-origin': '*' },
      body: JSON.stringify({
        source: 'generated',
        prompts: [
          { label: 'Open web', question: 'What does the archive say about the open web?' },
          { label: 'AI notes', question: 'Where does AI show up?' },
          { label: 'Systems', question: 'What systems are discussed?' },
        ],
      }),
    });
  });
  await page.route('https://mock-librarian.test/chat', async (route) => {
    chatRequests.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'access-control-allow-origin': '*' },
      body: JSON.stringify({
        answer: 'The archive connects RSS to open-web agency (#336, #233).',
        citations: [
          {
            issue_number: 336,
            subject: 'Why RSS matters',
            publish_date: '2025-01-01T13:00:00Z',
            section: 'Essay',
            url: '/archive/336/',
          },
          {
            issue_number: 233,
            subject: 'Use RSS for privacy and efficiency',
            publish_date: '2023-01-01T13:00:00Z',
            section: 'Links',
            url: '/archive/233/',
          },
        ],
      }),
    });
  });

  await page.goto('http://localhost:8080/librarian/');
  await page.getByLabel('Subscriber email').fill('reader@example.com');
  await page.getByRole('button', { name: 'Enter' }).click();
  await expect(page.getByRole('button', { name: 'Open web' })).toBeVisible();
  await page.getByRole('button', { name: 'Open web' }).click();

  await expect(page.locator('#librarian-prompts')).toBeHidden();
  await expect(page.locator('.librarian-citations')).toHaveCount(0);
  await expect(page.locator('.librarian-message-assistant a[href="/archive/336/"]')).toHaveText('#336');
  await expect(page.locator('.librarian-message-assistant a[href="/archive/233/"]')).toHaveText('#233');
  await expect(page.locator('.librarian-message-assistant a[href="/archive/336/"]')).toHaveAttribute('title', /Why RSS matters/);
  expect(chatRequests[0].history).toEqual([]);

  await page.getByLabel('Ask Thingy').fill('Tell me more about privacy.');
  await page.keyboard.press('Enter');
  await expect.poll(() => chatRequests.length).toBe(2);
  expect(chatRequests[1].history).toEqual([
    { role: 'user', content: 'What does the archive say about the open web?' },
    { role: 'assistant', content: 'The archive connects RSS to open-web agency (#336, #233).' },
  ]);

  await page.getByLabel('Ask Thingy').fill('First line');
  await page.keyboard.down('Shift');
  await page.keyboard.press('Enter');
  await page.keyboard.up('Shift');
  await expect(page.getByLabel('Ask Thingy')).toHaveValue('First line\n');
});
