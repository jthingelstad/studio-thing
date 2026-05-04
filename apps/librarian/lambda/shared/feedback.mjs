export function normalizeFeedbackReaction(value) {
  const reaction = String(value || '').trim().toLowerCase();
  return reaction === 'up' || reaction === 'down' ? reaction : '';
}

export function validFeedbackRequestId(value) {
  const requestId = String(value || '').trim();
  return /^[A-Za-z0-9._:-]{1,128}$/.test(requestId) ? requestId : '';
}
