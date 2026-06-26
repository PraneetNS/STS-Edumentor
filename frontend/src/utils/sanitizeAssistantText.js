/**
 * sanitizeAssistantText — Strip LLM markup/JSON wrappers; return only user-visible message text.
 */

function unescapeJsonString(value) {
  try {
    return JSON.parse(`"${value}"`);
  } catch (_) {
    return value
      .replace(/\\"/g, '"')
      .replace(/\\n/g, '\n')
      .replace(/\\t/g, '\t')
      .replace(/\\\\/g, '\\');
  }
}

function extractSpeechField(text) {
  const match = text.match(/["'](?:speech|speak|text)["']\s*:\s*["']((?:\\.|[^"'\\])*)["']/i);
  if (!match) return null;
  return unescapeJsonString(match[1]);
}

function extractFromJsonObject(text) {
  const trimmed = text.trim();

  // Wrapped in markdown code fence
  const fenced = trimmed.match(/^```(?:json)?\s*([\s\S]*?)```\s*$/i);
  const candidate = fenced ? fenced[1].trim() : trimmed;

  if (!/speech|speak|text/i.test(candidate)) {
    return null;
  }

  const jsonBlock = candidate.match(/\{[\s\S]*\}/);
  if (jsonBlock) {
    try {
      const data = JSON.parse(jsonBlock[0]);
      const speech = data.speech || data.speak || data.text || '';
      if (speech) return speech;
    } catch (_) {
      // fall through
    }
  }

  const speech = extractSpeechField(candidate);
  if (speech) return speech;

  if (/^\s*\{/.test(candidate)) return '';
  return null;
}

function stripMarkupTags(text) {
  let cleaned = text;

  cleaned = cleaned.replace(/<(?:item|step|entry|li)>/gi, '\n- ');
  cleaned = cleaned.replace(/\{\s*(?:item|step|entry|li)\s*\}/gi, '\n- ');
  cleaned = cleaned.replace(/<\/(?:item|step|entry|li)>/gi, '');
  cleaned = cleaned.replace(/\{\/\s*(?:item|step|entry|li)\s*\}/gi, '');

  cleaned = cleaned.replace(/<\/?(?:checklist|speak|followup|show|ul|ol)(?:\s+[^>]*)?>/gi, '');
  cleaned = cleaned.replace(/\{\/?(?:checklist|speak|followup|show|ul|ol)(?:\s+[^}]*)?\}/gi, '');

  cleaned = cleaned.replace(/<(?:speak|show|followup|checklist|item|step|entry|li)\b[^>]*>?/gi, '');
  cleaned = cleaned.replace(/<(?:spe|sho|fol|che|ite|ste|ent)\b[^>]*>?/gi, '');
  cleaned = cleaned.replace(/\{(?:speak|show|followup|checklist|item|step|entry|li)\b[^}]*\}?/gi, '');
  cleaned = cleaned.replace(/\{(?:spe|sho|fol|che|ite|ste|ent)\b[^}]*\}?/gi, '');

  cleaned = cleaned.replace(/<\/?[a-zA-Z][^>]*>/g, '');

  return cleaned;
}

function stripJsonLeaks(text) {
  return text
    .replace(/\{[^{}]*["'](?:speech|speak|text)["']\s*:\s*["']((?:\\.|[^"'\\])*)["'][^{}]*\}/gi, (_, speech) =>
      unescapeJsonString(speech)
    )
    .replace(/,?\s*["'](?:display|follow_up|followup|question)["']\s*:\s*(?:null|["'][^"']*["'])\s*/gi, '')
    .replace(/^\s*\{\s*/g, '')
    .replace(/\s*\}\s*$/g, '')
    .replace(/["'](?:speech|speak|text)["']\s*:\s*["']/gi, '')
    .replace(/["']\s*,?\s*$/g, '');
}

/**
 * @param {string} text Raw assistant text from the LLM stream
 * @returns {string} Clean text for display
 */
export function sanitizeAssistantText(text) {
  if (!text) return '';

  let cleaned = text;

  const fromJson = extractFromJsonObject(cleaned);
  if (fromJson !== null) {
    cleaned = fromJson;
  } else {
    cleaned = stripJsonLeaks(cleaned);
  }

  cleaned = stripMarkupTags(cleaned);

  return cleaned.trim();
}
