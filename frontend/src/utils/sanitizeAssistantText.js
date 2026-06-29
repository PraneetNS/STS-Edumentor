/**
 * sanitizeAssistantText — Strip LLM markup/JSON wrappers; return only user-visible message text.
 *
 * Key responsibility: convert <show type="code"> blocks to markdown ``` fences so
 * MarkdownViewer renders them as proper multi-line code blocks.
 *
 * Must handle TWO cases:
 *   1. Complete block  — <show ...>code</show> is fully present in the buffer
 *   2. Partial/streaming block — <show ...>code  (</show> not yet arrived)
 *
 * The partial case is the one that caused single-line rendering: the closing tag
 * was never there during streaming so regex with </show> never matched, and the
 * fallback tag-stripper ate the opening tag and left raw code as plain text.
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

/**
 * Extract lang from a <show> opening tag attribute string.
 * Handles both: lang="python" type="code"  AND  type="code" lang="python"
 */
function extractLang(attrs) {
  const m = attrs.match(/lang=["']([^"']*)["']/i);
  return m ? m[1] : '';
}

/**
 * Convert <show type="code"> blocks → markdown fenced code blocks.
 *
 * Processes the text in a single left-to-right pass to correctly handle
 * both complete blocks and the partial (still-streaming) tail block.
 */
function convertShowCodeBlocks(text) {
  // Regex that matches the opening tag of a code show block (attributes in any order)
  const openTagRe = /<show\b([^>]*\btype=["']code["'][^>]*)>/gi;

  let result = '';
  let lastIndex = 0;
  let match;

  // Reset lastIndex before loop
  openTagRe.lastIndex = 0;

  while ((match = openTagRe.exec(text)) !== null) {
    const attrs = match[1];
    const lang = extractLang(attrs);
    const afterOpenTag = match.index + match[0].length;

    // Append everything before this opening tag verbatim
    result += text.slice(lastIndex, match.index);

    // Look for closing </show> after the opening tag
    const closeTagIndex = text.indexOf('</show>', afterOpenTag);

    if (closeTagIndex !== -1) {
      // Complete block — extract code content and wrap in fences
      const code = text.slice(afterOpenTag, closeTagIndex).trim();
      result += `\n\`\`\`${lang}\n${code}\n\`\`\`\n`;
      lastIndex = closeTagIndex + '</show>'.length;
      openTagRe.lastIndex = lastIndex;
    } else {
      // Partial block — </show> hasn't streamed in yet.
      // Emit an open fence and let MarkdownViewer render the rest as code.
      const code = text.slice(afterOpenTag);
      result += `\n\`\`\`${lang}\n${code}`;
      lastIndex = text.length; // consumed everything
      break;
    }
  }

  // Append any remaining text after the last show block
  result += text.slice(lastIndex);

  return result;
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

  // Convert <show type="code"> → ``` fences BEFORE generic tag stripping.
  // This preserves newlines and indentation inside the code content.
  cleaned = convertShowCodeBlocks(cleaned);

  // Strip all remaining XML-style tags (<speak>, <followup>, leftover <show> etc.)
  cleaned = stripMarkupTags(cleaned);

  return cleaned.trim();
}
