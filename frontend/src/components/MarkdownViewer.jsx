import React from 'react';
import { ThinkingIndicator } from './ThinkingIndicator';
import { sanitizeAssistantText } from '../utils/sanitizeAssistantText';
import { wrapTextByWordCount } from '../utils/formatMessageText';

// Simple custom markdown renderer for rendering markdown content nicely
export function parseInlineMarkdown(text) {
  if (!text) return '';
  const parts = [];
  let remaining = text;
  let key = 0;

  while (remaining) {
    const nextStrong = remaining.indexOf('**');
    const nextCode = remaining.indexOf('`');
    const nextLink = remaining.indexOf('[');

    const indices = [
      nextStrong !== -1 ? nextStrong : Infinity,
      nextCode !== -1 ? nextCode : Infinity,
      nextLink !== -1 ? nextLink : Infinity
    ];

    const minIndex = Math.min(...indices);

    if (minIndex === Infinity) {
      parts.push(remaining);
      break;
    }

    if (minIndex === 0) {
      // Avoid infinite loop if we are matching index 0 but didn't parse anything
      // (safeguard, should not happen in correct flow)
    }

    if (minIndex > 0) {
      parts.push(remaining.substring(0, minIndex));
      remaining = remaining.substring(minIndex);
    }

    if (minIndex === nextStrong) {
      const closeStrong = remaining.indexOf('**', 2);
      if (closeStrong !== -1) {
        parts.push(<strong key={`s-${key++}`} className="font-bold text-zinc-900">{remaining.substring(2, closeStrong)}</strong>);
        remaining = remaining.substring(closeStrong + 2);
      } else {
        parts.push('**');
        remaining = remaining.substring(2);
      }
    } else if (minIndex === nextCode) {
      const closeCode = remaining.indexOf('`', 1);
      if (closeCode !== -1) {
        parts.push(<code key={`c-${key++}`} className="bg-zinc-150 text-indigo-600 px-1.5 py-0.5 rounded font-mono text-xs">{remaining.substring(1, closeCode)}</code>);
        remaining = remaining.substring(closeCode + 1);
      } else {
        parts.push('`');
        remaining = remaining.substring(1);
      }
    } else if (minIndex === nextLink) {
      const closeBracket = remaining.indexOf(']');
      const openParen = remaining.indexOf('(', closeBracket);
      const closeParen = remaining.indexOf(')', openParen);

      if (closeBracket !== -1 && openParen === closeBracket + 1 && closeParen !== -1) {
        const linkText = remaining.substring(1, closeBracket);
        const linkUrl = remaining.substring(openParen + 1, closeParen);
        const isExternal = linkUrl.startsWith('http');
        parts.push(
          <a
            key={`l-${key++}`}
            href={linkUrl}
            target={isExternal ? '_blank' : '_self'}
            rel="noreferrer"
            className="text-indigo-600 hover:text-indigo-800 underline font-medium"
          >
            {linkText}
          </a>
        );
        remaining = remaining.substring(closeParen + 1);
      } else {
        parts.push('[');
        remaining = remaining.substring(1);
      }
    }
  }

  return parts;
}

// Clean custom XML/HTML tags and parse lists safely without breaking mathematical operators
export function cleanXmlTags(text) {
  return sanitizeAssistantText(text);
}

export function MarkdownViewer({ text, isStreaming = false }) {
  const cleaned = text ? cleanXmlTags(text) : '';
  const hasVisibleContent = cleaned.trim().length > 0;

  if (!hasVisibleContent) {
    if (isStreaming) return <ThinkingIndicator />;
    return null;
  }

  const lines = cleaned.split('\n');
  let inCodeBlock = false;
  let codeContent = [];
  let renderedElements = [];
  let key = 0;

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    if (line.trim().startsWith('```')) {
      if (inCodeBlock) {
        renderedElements.push(
          <pre key={`code-${key++}`} className="bg-zinc-900 text-zinc-100 p-4 rounded-lg my-3 overflow-x-auto text-xs font-mono select-text" style={{ whiteSpace: 'pre', overflowWrap: 'normal', wordBreak: 'keep-all' }}>
            <code>{codeContent.join('\n')}</code>
          </pre>
        );
        codeContent = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeContent.push(line);
      continue;
    }

    // Headings
    if (line.startsWith('# ')) {
      renderedElements.push(<h1 key={`h1-${key++}`} className="text-2xl font-extrabold text-zinc-900 mt-6 mb-3 border-b pb-2">{line.substring(2)}</h1>);
      continue;
    }
    if (line.startsWith('## ')) {
      renderedElements.push(<h2 key={`h2-${key++}`} className="text-xl font-bold text-zinc-900 mt-5 mb-2">{line.substring(3)}</h2>);
      continue;
    }
    if (line.startsWith('### ')) {
      renderedElements.push(<h3 key={`h3-${key++}`} className="text-lg font-semibold text-zinc-900 mt-4 mb-2">{line.substring(4)}</h3>);
      continue;
    }

    // Bullet points
    if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
      const content = line.trim().substring(2);
      renderedElements.push(
        <ul key={`ul-${key++}`} className="list-disc pl-5 my-1 text-zinc-700">
          <li>{parseInlineMarkdown(content)}</li>
        </ul>
      );
      continue;
    }

    // Numbered lists
    if (/^\d+\.\s/.test(line.trim())) {
      const content = line.trim().replace(/^\d+\.\s/, '');
      renderedElements.push(
        <ol key={`ol-${key++}`} className="list-decimal pl-5 my-1 text-zinc-700">
          <li>{parseInlineMarkdown(content)}</li>
        </ol>
      );
      continue;
    }

    // Blockquotes
    if (line.startsWith('> ')) {
      renderedElements.push(
        <blockquote key={`bq-${key++}`} className="border-l-4 border-indigo-500 pl-4 py-1 my-3 italic text-zinc-650 bg-indigo-50/50 rounded-r-md">
          {parseInlineMarkdown(line.substring(2))}
        </blockquote>
      );
      continue;
    }

    // Tables
    if (line.startsWith('|')) {
      renderedElements.push(
        <div key={`tbl-${key++}`} className="font-mono text-xs bg-zinc-50 p-2 border-x border-b first:border-t text-zinc-600">
          {line}
        </div>
      );
      continue;
    }

    // HR
    if (line.trim() === '---') {
      renderedElements.push(<hr key={`hr-${key++}`} className="my-6 border-zinc-200" />);
      continue;
    }

    // Paragraphs
    if (line.trim() !== '') {
      renderedElements.push(
        <p key={`p-${key++}`} className="assistant-text-line text-zinc-700 leading-relaxed">
          {parseInlineMarkdown(line)}
        </p>
      );
    }
  }

  return (
    <div className="markdown-body">
      {renderedElements}
    </div>
  );
}
