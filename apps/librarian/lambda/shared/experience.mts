export function isExperienceRequest(question = '') {
  return /\b(?:archive\s+spark|thingy\s+trail|reading\s+path|guided\s+path|surprise\s+me|surprising|serendipit|forgotten\s+gem|archive\s+gem|what\s+should\s+i\s+(?:read|listen\s+to|open|explore)|recommend|recommendation|something\s+(?:interesting|surprising|delightful)|delightful\s+starting\s+point|adjacent\s+thread|branches?\s+(?:out|from))\b/i.test(
    String(question || '')
  );
}

export function answerFramesExperience(answer = '') {
  return /\b(?:thingy\s+trail|reading\s+path|guided\s+path|archive\s+spark|archive\s+gem|continue\s+this\s+trail|follow\s+this\s+spark)\b/i.test(
    String(answer || '')
  );
}

export function shouldEmitExperienceForTurn({ question = '', answer = '' } = {}) {
  return isExperienceRequest(question) || answerFramesExperience(answer);
}
