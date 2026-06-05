export function openEndedCreativeGuardAnswer(question) {
  const normalized = String(question || '')
    .toLowerCase()
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/[^a-z0-9'"\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const blockedPatterns = [
    /^tell me (?:a |the )?story$/,
    /^tell me (?:a |the )?story please$/,
    /^write (?:me )?(?:a |the )?story(?: please)?$/,
    /^make up (?:a |the )?story(?: please)?$/,
    /^give me (?:a |the )?story(?: please)?$/,
    /^bedtime story(?: please)?$/
  ];
  if (!blockedPatterns.some((pattern) => pattern.test(normalized))) return '';
  return 'I can tell stories from the archive, but I need one thread to pull on. Good archive-shaped versions of that prompt are: "Tell me the story of Jamie and RSS," "Tell me a story about a long-running project," or "Tell me a story about Minneapolis in the archive."';
}
