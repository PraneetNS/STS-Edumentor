/**
 * Parses raw message text to extract visual <show> blocks.
 * Supports both complete and streaming blocks.
 * 
 * Returns an array of block objects:
 * {
 *   id: string,
 *   type: 'code' | 'roadmap' | 'workflow' | 'table' | 'checklist' | 'mermaid',
 *   lang: string,
 *   title: string,
 *   content: string,
 *   isStreaming: boolean
 * }
 */
export function extractVisualBlocks(text) {
  if (!text) return [];

  // Match both <show ...> and {show ...}
  const showBlockRegex = /<(show|mermaid)\b([^>]*?)>|\{(show|mermaid)\b([^}]*?)\}/gi;
  const blocks = [];
  let match;

  while ((match = showBlockRegex.exec(text)) !== null) {
    const isTag = !!match[1];
    const tagName = (isTag ? match[1] : match[3]).toLowerCase();
    const attrsString = isTag ? match[2] : match[4];

    // Extract attributes
    const typeMatch = attrsString.match(/type=["']([^"']*)["']/i);
    const langMatch = attrsString.match(/lang=["']([^"']*)["']/i);
    const titleMatch = attrsString.match(/title=["']([^"']*)["']/i);

    let type = typeMatch ? typeMatch[1] : (tagName === 'mermaid' ? 'mermaid' : 'code');
    const lang = langMatch ? langMatch[1] : '';
    const title = titleMatch ? titleMatch[1] : '';

    const startTagIndex = match.index;
    const contentStartIndex = startTagIndex + match[0].length;

    // Look for corresponding close tag </show> or {/show} or </mermaid> or {/mermaid}
    const closeTagPattern = isTag ? `</${tagName}>` : `{\/${tagName}}`;
    const closeTagIndex = text.indexOf(closeTagPattern, contentStartIndex);

    let content = '';
    let isStreaming = false;

    if (closeTagIndex !== -1) {
      content = text.substring(contentStartIndex, closeTagIndex).trim();
    } else {
      // Stream is still open, extract up to the end of the text
      content = text.substring(contentStartIndex).trim();
      isStreaming = true;
    }

    let cleanContent = content;
    // Strip wrapping ``` fences if present
    if (cleanContent.startsWith('\x60\x60\x60')) {
      cleanContent = cleanContent.replace(/^\x60\x60\x60[a-zA-Z0-9]*\n/, '').replace(/\n\x60\x60\x60$/, '').trim();
    }

    blocks.push({
      id: `${tagName}_${startTagIndex}`,
      type,
      lang,
      title: title || getDefaultTitle(type, lang),
      content: cleanContent,
      isStreaming
    });
  }

  return blocks;
}

function getDefaultTitle(type, lang) {
  switch (type) {
    case 'code':
      return lang ? `${lang.toUpperCase()} Implementation` : 'Source Code';
    case 'roadmap':
      return 'Learning Roadmap';
    case 'workflow':
      return 'Engineering Workflow';
    case 'table':
      return 'Comparison Table';
    case 'checklist':
      return 'Topic Summary';
    case 'mermaid':
      return 'System Architecture';
    default:
      return 'Visual Reference';
  }
}

export function stripVisualBlocks(text) {
  if (!text) return '';
  
  let result = '';
  let lastIndex = 0;
  const showBlockRegex = /<(show|mermaid)\b([^>]*?)>|\{(show|mermaid)\b([^}]*?)\}/gi;
  let match;

  while ((match = showBlockRegex.exec(text)) !== null) {
    const isTag = !!match[1];
    const tagName = (isTag ? match[1] : match[3]).toLowerCase();
    const startTagIndex = match.index;
    const contentStartIndex = startTagIndex + match[0].length;

    result += text.slice(lastIndex, startTagIndex);

    const closeTagPattern = isTag ? `</${tagName}>` : `{\/${tagName}}`;
    const closeTagIndex = text.indexOf(closeTagPattern, contentStartIndex);

    if (closeTagIndex !== -1) {
      lastIndex = closeTagIndex + closeTagPattern.length;
    } else {
      lastIndex = text.length;
      break;
    }
  }

  if (lastIndex < text.length) {
    result += text.slice(lastIndex);
  }

  return result.trim();
}
