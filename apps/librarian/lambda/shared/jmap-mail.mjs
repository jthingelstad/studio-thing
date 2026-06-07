const JMAP_SESSION_URL = 'https://api.fastmail.com/jmap/session';
const CAP_CORE = 'urn:ietf:params:jmap:core';
const CAP_MAIL = 'urn:ietf:params:jmap:mail';
const CAP_SUBMISSION = 'urn:ietf:params:jmap:submission';

function envValue(...names) {
  for (const name of names) {
    const value = String(process.env[name] || '').trim();
    if (value) return value;
  }
  return '';
}

export function jmapToken() {
  return envValue('FASTMAIL_JMAP_TOKEN', 'THINGY_FASTMAIL_JMAP_TOKEN', 'THINGY_JMAP_TOKEN');
}

export function jmapFromEmail() {
  return envValue('THINGY_MAGIC_LINK_FROM_EMAIL', 'THINGY_EMAIL_FROM') || 'thingy@thingelstad.com';
}

export function jmapFromName() {
  return envValue('THINGY_MAGIC_LINK_FROM_NAME', 'THINGY_EMAIL_FROM_NAME') || 'Thingy';
}

export function jmapConfigured() {
  return Boolean(jmapToken());
}

async function jmapFetch(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      accept: 'application/json',
      authorization: `Bearer ${jmapToken()}`,
      ...(options.body ? { 'content-type': 'application/json' } : {}),
      ...(options.headers || {})
    }
  });
  if (!response.ok) throw new Error(`JMAP HTTP ${response.status}`);
  return await response.json();
}

async function jmapSession() {
  return await jmapFetch(JMAP_SESSION_URL);
}

async function jmapCall(apiUrl, calls) {
  return await jmapFetch(apiUrl, {
    method: 'POST',
    body: JSON.stringify({
      using: [CAP_CORE, CAP_MAIL, CAP_SUBMISSION],
      methodCalls: calls
    })
  });
}

function methodResponse(responses = [], name, id) {
  return (responses || []).find((item) => item[0] === name && item[2] === id)?.[1] || {};
}

function primaryAccount(session, capability) {
  return session?.primaryAccounts?.[capability] || session?.primaryAccounts?.[CAP_MAIL] || '';
}

function pickIdentity(identities = [], fromEmail = '') {
  const wanted = String(fromEmail || '').toLowerCase();
  return identities.find((identity) => String(identity.email || '').toLowerCase() === wanted) || identities[0] || null;
}

async function loadSendContext(session, fromEmail) {
  const mailAccountId = primaryAccount(session, CAP_MAIL);
  const submissionAccountId = primaryAccount(session, CAP_SUBMISSION) || mailAccountId;
  if (!mailAccountId || !submissionAccountId || !session.apiUrl) {
    throw new Error('JMAP session missing mail/submission account');
  }
  const response = await jmapCall(session.apiUrl, [
    ['Identity/get', { accountId: submissionAccountId, ids: null }, 'identity'],
    ['Mailbox/get', { accountId: mailAccountId, ids: null }, 'mailboxes']
  ]);
  const identities = methodResponse(response.methodResponses, 'Identity/get', 'identity').list || [];
  const mailboxes = methodResponse(response.methodResponses, 'Mailbox/get', 'mailboxes').list || [];
  const drafts = mailboxes.find((mailbox) => mailbox.role === 'drafts');
  const identity = pickIdentity(identities, fromEmail);
  if (!identity?.id) throw new Error(`No JMAP identity available for ${fromEmail}`);
  if (!drafts?.id) throw new Error('No JMAP drafts mailbox available');
  return {
    apiUrl: session.apiUrl,
    mailAccountId,
    submissionAccountId,
    identityId: identity.id,
    draftMailboxId: drafts.id
  };
}

export function magicLinkEmailText({ magicLink, expiresMinutes }) {
  return [
    'Use this link to sign in to Thingy:',
    '',
    magicLink,
    '',
    `This link expires in ${expiresMinutes} minutes and can only be used once.`,
    '',
    'If you did not request this, you can ignore this email.'
  ].join('\n');
}

export function magicLinkEmailSubject() {
  return 'Sign in to Thingy';
}

export async function sendMagicLinkEmail({ to, magicLink, expiresMinutes }) {
  const token = jmapToken();
  if (!token) throw new Error('FASTMAIL_JMAP_TOKEN is not configured');
  const fromEmail = jmapFromEmail();
  const session = await jmapSession();
  const context = await loadSendContext(session, fromEmail);
  const text = magicLinkEmailText({ magicLink, expiresMinutes });
  const response = await jmapCall(context.apiUrl, [
    ['Email/set', {
      accountId: context.mailAccountId,
      create: {
        draft: {
          mailboxIds: { [context.draftMailboxId]: true },
          keywords: { '$draft': true },
          from: [{ name: jmapFromName(), email: fromEmail }],
          to: [{ email: to }],
          subject: magicLinkEmailSubject(),
          textBody: [{ partId: 'text' }],
          bodyValues: {
            text: { value: text, charset: 'utf-8' }
          }
        }
      }
    }, 'email'],
    ['EmailSubmission/set', {
      accountId: context.submissionAccountId,
      onSuccessDestroyEmail: ['#send'],
      create: {
        send: {
          emailId: '#draft',
          identityId: context.identityId
        }
      }
    }, 'submit']
  ]);
  const submit = methodResponse(response.methodResponses, 'EmailSubmission/set', 'submit');
  if (submit.notCreated?.send) {
    throw new Error(`JMAP submission failed: ${submit.notCreated.send.type || 'notCreated'}`);
  }
  return {
    ok: Boolean(submit.created?.send?.id),
    submission_id: submit.created?.send?.id || ''
  };
}
