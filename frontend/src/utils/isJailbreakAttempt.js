/**
 * isJailbreakAttempt — Client-side heuristic to detect prompt injection / jailbreak attempts.
 *
 * Returns true if the text matches known jailbreak patterns.
 * Used to prevent malicious prompts from being stored in localStorage,
 * rendered in the chat UI, or sent to the backend LLM.
 */
export function isJailbreakAttempt(text) {
  if (!text) return false;
  const lower = text.toLowerCase();

  // Quick keyword check first (fast path)
  const keywords = [
    'ignore all',
    'ignore your',
    'ignore previous',
    'disregard all',
    'disregard your',
    'disregard previous',
    'forget all instructions',
    'forget your instructions',
    'forget previous instructions',
    'override all',
    'override your',
    'override previous',
    'bypass all',
    'bypass your',
    'bypass safety',
    'bypass filters',
    'bypass rules',
    'system prompt',
    'new system prompt',
    'reveal your prompt',
    'show your prompt',
    'output your prompt',
    'print your prompt',
    'display your prompt',
    'repeat your instructions',
    'jailbreak',
    'prompt injection',
    'prompt leak',
    'developer mode',
    'god mode',
    'unrestricted mode',
    'you are now a',
    'you are now an',
    'from now on you are',
    'pretend you are',
    'pretend to be',
    'act as a',
    'act as an',
    'roleplay as',
    'switch to a new mode',
    'switch into a new mode',
    'no rules',
    'no restrictions',
    'no filters',
    'no limits',
  ];

  for (const kw of keywords) {
    if (lower.includes(kw)) return true;
  }

  // Regex patterns for trickier variants
  const patterns = [
    /\bDAN\b/,                                           // "Do Anything Now" jailbreak
    /how\s+to\s+(?:hack|exploit|attack|destroy|harm)/i,
    /(?:make|build|create)\s+(?:a\s+)?(?:bomb|weapon|virus|malware)/i,
  ];

  for (const p of patterns) {
    if (p.test(text)) return true;
  }

  return false;
}
