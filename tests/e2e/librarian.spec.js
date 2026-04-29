const { test, expect } = require('@playwright/test');

test('librarian email form submits in a visible way', async ({ page }) => {
  test.setTimeout(120000);
  const consoleMessages = [];
  const requestFailures = [];
  const responses = [];
  const streamResponses = [];
  await page.addInitScript(() => {
    window.WEEKLY_THING_LIBRARIAN_API = 'https://mock-premium-librarian.test';
    window.WEEKLY_THING_LIBRARIAN_STREAM_API = 'https://mock-premium-librarian-stream.test';
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  await page.route('https://mock-premium-librarian.test/auth', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'access-control-allow-origin': '*' },
      body: JSON.stringify({
        status: 'premium',
        token: 'mock-premium-token',
        expires_at: 9999999999,
        message: 'Thanks for being a Weekly Thing Supporting Member!',
      }),
    });
  });
  await page.route('https://mock-premium-librarian-stream.test/chat', async (route) => {
    const citations = [
      {
        issue_number: 336,
        subject: 'Weekly Thing #336: Why RSS matters',
        publish_date: '2025-01-01T13:00:00Z',
        section: 'Essay',
        url: '/archive/336/',
      },
    ];
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: { 'access-control-allow-origin': '*' },
      body: [
        'event: meta',
        'data: {"request_id":"mock-premium-request"}',
        '',
        'event: answer_delta',
        'data: {"delta":"The archive treats RSS as open-web agency and reader control (#336)."}',
        '',
        'event: citations',
        `data: ${JSON.stringify({ citations })}`,
        '',
        'event: done',
        'data: {"request_id":"mock-premium-request"}',
        '',
        ''
      ].join('\n'),
    });
  });
  page.on('console', (message) => consoleMessages.push(`${message.type()}: ${message.text()}`));
  page.on('requestfailed', (request) => {
    requestFailures.push(`${request.method()} ${request.url()} ${request.failure()?.errorText || ''}`);
  });
  page.on('response', (response) => {
    if (response.url().includes('/auth')) {
      responses.push(`${response.status()} ${response.url()}`);
    }
    if (response.url().includes('lambda-url.us-east-1.on.aws') || response.url().includes('mock-premium-librarian-stream.test')) {
      streamResponses.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.goto('/thingy/');
  await page.getByLabel('Subscriber email').fill('jamiethingelstad@icloud.com');
  await page.getByRole('button', { name: 'Enter' }).click();
  await expect(page.locator('#librarian-chat')).toBeVisible({ timeout: 30000 });
  await page.getByRole('button', { name: 'I understand' }).click();
  await expect(page.locator('#librarian-prompts button')).toHaveCount(3);

  const questionBox = page.getByLabel('Ask Thingy');
  await questionBox.fill('What has the archive said about RSS and the open web?');
  await questionBox.press('Enter');
  await expect(page.locator('#librarian-prompts')).toBeHidden();
  await expect(page.locator('.librarian-message-assistant a[href^="/archive/"]').first()).toBeVisible({ timeout: 90000 });

  const state = {
    authHidden: await page.locator('#librarian-auth').evaluate((node) => node.hidden),
    chatHidden: await page.locator('#librarian-chat').evaluate((node) => node.hidden),
    enterDisabled: await page.locator('#librarian-auth-form button[type="submit"]').evaluate((node) => node.disabled),
    visibleText: await page.locator('body').innerText(),
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
    window.WEEKLY_THING_LIBRARIAN_STREAM_API = 'https://mock-librarian-stream.test';
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
  await page.goto('/thingy/');
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

test('librarian query parameters prefill email and auto-submit prompt', async ({ page }) => {
  const authRequests = [];
  const chatRequests = [];
  await page.addInitScript(() => {
    window.WEEKLY_THING_LIBRARIAN_API = 'https://mock-librarian.test';
    window.WEEKLY_THING_LIBRARIAN_STREAM_API = 'https://mock-librarian-stream.test';
    window.localStorage.clear();
    window.sessionStorage.setItem('weeklyThingLibrarianBetaNotice', 'dismissed');
  });
  await page.route('https://mock-librarian.test/auth', async (route) => {
    authRequests.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'access-control-allow-origin': '*' },
      body: JSON.stringify({ status: 'active', token: 'mock-token', expires_at: 9999999999 }),
    });
  });
  await page.route('https://mock-librarian-stream.test/chat', async (route) => {
    chatRequests.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: { 'access-control-allow-origin': '*' },
      body: [
        'event: meta',
        'data: {"request_id":"mock-query-param-request"}',
        '',
        'event: answer_delta',
        'data: {"delta":"Here is an answer from Thingy."}',
        '',
        'event: done',
        'data: {"request_id":"mock-query-param-request"}',
        '',
        ''
      ].join('\n'),
    });
  });

  const prompt = 'What has Jamie written about RSS?';
  await page.goto(`/thingy/?email=reader%40example.com&prompt=${encodeURIComponent(prompt)}`);
  await expect(page.getByLabel('Subscriber email')).toHaveValue('reader@example.com');
  await expect(page.locator('#librarian-chat')).toBeVisible();
  await expect.poll(() => chatRequests.length).toBe(1);
  expect(authRequests[0]).toMatchObject({ email: 'reader@example.com', action: 'check' });
  expect(chatRequests[0]).toMatchObject({ message: prompt, history: [] });
  await expect(page.locator('#librarian-prompts')).toBeHidden();

  await page.getByRole('button', { name: 'Use a different email' }).click();
  authRequests.length = 0;
  chatRequests.length = 0;
  await page.goto(`/thingy/?prompt=${encodeURIComponent(prompt)}`);
  await expect(page.getByLabel('Subscriber email')).toHaveValue('');
  await page.getByLabel('Subscriber email').fill('manual@example.com');
  await page.getByRole('button', { name: 'Enter' }).click();
  await expect.poll(() => chatRequests.length).toBe(1);
  expect(authRequests[0]).toMatchObject({ email: 'manual@example.com', action: 'check' });
  expect(chatRequests[0]).toMatchObject({ message: prompt, history: [] });
});

test('librarian starter prompts and inline citations render with mocked APIs', async ({ page }) => {
  const chatRequests = [];
  await page.addInitScript(() => {
    window.WEEKLY_THING_LIBRARIAN_API = 'https://mock-librarian.test';
    window.WEEKLY_THING_LIBRARIAN_STREAM_API = 'https://mock-librarian-stream.test';
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
  await page.route('https://mock-librarian-stream.test/chat', async (route) => {
    chatRequests.push(route.request().postDataJSON());
    const citations = [
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
    ];
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: { 'access-control-allow-origin': '*' },
      body: [
        'event: meta',
        'data: {"request_id":"mock-request"}',
        '',
        'event: answer_delta',
        'data: {"delta":"The archive connects RSS to open-web agency (#336, #233)."}',
        '',
        'event: citations',
        `data: ${JSON.stringify({ citations })}`,
        '',
        'event: done',
        'data: {"request_id":"mock-request"}',
        '',
        ''
      ].join('\n'),
    });
  });

  await page.goto('/thingy/');
  await page.getByLabel('Subscriber email').fill('reader@example.com');
  await page.getByRole('button', { name: 'Enter' }).click();
  await page.getByRole('button', { name: 'I understand' }).click();
  const promptButtons = page.locator('#librarian-prompts button');
  await expect(promptButtons).toHaveCount(3);
  const firstPrompt = promptButtons.first();
  const firstPromptQuestion = await firstPrompt.getAttribute('data-question');
  await firstPrompt.click();

  await expect(page.locator('#librarian-prompts')).toBeHidden();
  await expect(page.locator('.librarian-citations')).toHaveCount(0);
  await expect(page.locator('.librarian-message-assistant a[href="/archive/336/"]')).toHaveText('#336');
  await expect(page.locator('.librarian-message-assistant a[href="/archive/233/"]')).toHaveText('#233');
  await expect(page.locator('.librarian-message-assistant a[href="/archive/336/"]')).toHaveAttribute('title', /Why RSS matters/);
  expect(chatRequests[0].message).toEqual(firstPromptQuestion);
  expect(chatRequests[0].history).toEqual([]);

  await page.getByLabel('Ask Thingy').fill('Tell me more about privacy.');
  await page.getByLabel('Ask Thingy').press('Enter');
  await expect.poll(() => chatRequests.length).toBe(2);
  expect(chatRequests[1].history).toEqual([
    { role: 'user', content: firstPromptQuestion },
    { role: 'assistant', content: 'The archive connects RSS to open-web agency (#336, #233).' },
  ]);

  await page.getByRole('button', { name: 'Start over' }).click();
  await expect(page.locator('.librarian-message-user')).toHaveCount(0);
  await expect(page.locator('.librarian-message-assistant')).toHaveCount(0);
  await expect(promptButtons).toHaveCount(3);
  const restartPromptQuestion = await promptButtons.first().getAttribute('data-question');
  await promptButtons.first().click();
  await expect.poll(() => chatRequests.length).toBe(3);
  expect(chatRequests[2].message).toEqual(restartPromptQuestion);
  expect(chatRequests[2].history).toEqual([]);

  await page.getByLabel('Ask Thingy').fill('First line');
  await page.keyboard.down('Shift');
  await page.keyboard.press('Enter');
  await page.keyboard.up('Shift');
  await expect(page.getByLabel('Ask Thingy')).toHaveValue('First line\n');
});
