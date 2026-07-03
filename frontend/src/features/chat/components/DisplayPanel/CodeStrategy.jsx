import { useState } from 'react';
import { Check, Copy, Code } from 'lucide-react';

export default function CodeStrategy({ block }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(block.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy code:', err);
    }
  };

  // Simple, elegant token-based syntax highlighter for popular languages (prevents nested/polluted HTML tags)
  const highlightCode = (code) => {
    if (!code) return '';

    // Separate comment first to avoid styling inside comments
    let commentIndex = -1;
    let inDoubleQuote = false;
    let inSingleQuote = false;
    let inBacktick = false;

    for (let c = 0; c < code.length; c++) {
      const char = code[c];
      if (char === '"' && !inSingleQuote && !inBacktick) {
        if (c === 0 || code[c - 1] !== '\\') {
          inDoubleQuote = !inDoubleQuote;
        }
      } else if (char === "'" && !inDoubleQuote && !inBacktick) {
        if (c === 0 || code[c - 1] !== '\\') {
          inSingleQuote = !inSingleQuote;
        }
      } else if (char === '\x60' && !inDoubleQuote && !inSingleQuote) {
        if (c === 0 || code[c - 1] !== '\\') {
          inBacktick = !inBacktick;
        }
      } else if (!inDoubleQuote && !inSingleQuote && !inBacktick) {
        if (char === '#') {
          commentIndex = c;
          break;
        } else if (char === '/' && c + 1 < code.length && code[c + 1] === '/') {
          commentIndex = c;
          break;
        }
      }
    }

    let codePart = code;
    let commentPart = '';
    if (commentIndex !== -1) {
      codePart = code.substring(0, commentIndex);
      commentPart = code.substring(commentIndex);
    }

    const keywordRegex = /\b(const|let|var|function|return|import|export|from|default|class|extends|if|else|for|while|do|switch|case|break|continue|try|catch|finally|async|await|yield|def|class|self|print|import|as|from|in|is|not|and|or|true|false|null|undefined|fn|let|mut|pub|use|mod|struct|impl|enum|type|interface|any|string|number|boolean|void)\b/;
    
    // Scan codePart token-by-token
    const combinedRegex = /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\x60(?:\\.|[^\x60\\])*\x60|\b(?:const|let|var|function|return|import|export|from|default|class|extends|if|else|for|while|do|switch|case|break|continue|try|catch|finally|async|await|yield|def|class|self|print|import|as|from|in|is|not|and|or|true|false|null|undefined|fn|let|mut|pub|use|mod|struct|impl|enum|type|interface|any|string|number|boolean|void)\b|\b\d+\b|\b\w+(?=\()|[^\s\w"'\x60]+|\w+|\s+)/g;
    
    let match;
    let htmlResult = '';
    
    combinedRegex.lastIndex = 0;
    while ((match = combinedRegex.exec(codePart)) !== null) {
      const token = match[0];
      const escaped = token.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      
      if (token.startsWith('"') || token.startsWith("'") || token.startsWith('`')) {
        htmlResult += `<span class="code-string">${escaped}</span>`;
      } else if (keywordRegex.test(token)) {
        htmlResult += `<span class="code-keyword">${escaped}</span>`;
      } else if (/^\d+$/.test(token)) {
        htmlResult += `<span class="code-number">${escaped}</span>`;
      } else if (codePart[combinedRegex.lastIndex] === '(') {
        htmlResult += `<span class="code-function">${escaped}</span>`;
      } else {
        htmlResult += escaped;
      }
    }

    if (commentPart) {
      const escapedComment = commentPart.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      htmlResult += `<span class="code-comment">${escapedComment}</span>`;
    }

    return htmlResult;
  };

  const lines = block.content.split('\n');

  return (
    <div className="flex flex-col h-full bg-[#0D0D11] rounded-none border border-zinc-800 overflow-hidden font-mono text-xs text-zinc-300">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-[#14141A] border-b border-zinc-800 select-none">
        <div className="flex items-center gap-2 text-zinc-400">
          <Code size={14} className="text-indigo-400" />
          <span className="font-semibold text-zinc-300">{block.title || 'Source Code'}</span>
          {block.lang && (
            <span className="px-1.5 py-0.5 rounded-none bg-zinc-800 text-[10px] uppercase font-bold text-zinc-500">
              {block.lang}
            </span>
          )}
        </div>

        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-none bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors cursor-pointer"
          title="Copy code to clipboard"
        >
          {copied ? (
            <>
              <Check size={12} className="text-emerald-400" />
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy size={12} />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>

      {/* Code body */}
      <div className="flex-1 overflow-auto p-4 select-text">
        <table className="w-full border-collapse">
          <tbody>
            {lines.map((line, idx) => (
              <tr key={idx} className="hover:bg-zinc-900/30">
                <td className="w-8 pr-4 text-right text-zinc-600 select-none border-r border-zinc-900">
                  {idx + 1}
                </td>
                <td 
                  className="pl-4 whitespace-pre-wrap break-all" 
                  dangerouslySetInnerHTML={{ __html: highlightCode(line, block.lang) || '&nbsp;' }} 
                />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
