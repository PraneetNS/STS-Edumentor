import React, { useState } from 'react';
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

  // Simple, elegant regex-based syntax highlighter for popular languages
  const highlightCode = (code, lang) => {
    if (!code) return '';
    const safeCode = code
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    const language = (lang || 'javascript').toLowerCase();

    // Custom syntax rules
    const rules = [
      // Comments
      { regex: /(\/\/.*|\/\*[\s\S]*?\*\/|#.*)/g, clazz: 'code-comment' },
      // Strings
      { regex: /(["'`])(.*?)\1/g, clazz: 'code-string' },
      // Keywords
      {
        regex: /\b(const|let|var|function|return|import|export|from|default|class|extends|if|else|for|while|do|switch|case|break|continue|try|catch|finally|async|await|yield|def|class|self|print|import|as|from|in|is|not|and|or|true|false|null|undefined|fn|let|mut|pub|use|mod|struct|impl|enum|type|interface|any|string|number|boolean|void)\b/g,
        clazz: 'code-keyword'
      },
      // Numbers
      { regex: /\b(\d+)\b/g, clazz: 'code-number' },
      // Function calls
      { regex: /\b(\w+)(?=\()/g, clazz: 'code-function' },
    ];

    let highlighted = safeCode;
    // We apply rules by wrapping matches in span tags
    // To prevent matching inside already wrapped span tags, we tokenize the rules carefully
    // For a lightweight renderer, we can process rules sequentially
    rules.forEach((rule) => {
      // Avoid replacing inside existing span classes by doing a safe regex search
      highlighted = highlighted.replace(rule.regex, (match) => {
        // Simple check to make sure we aren't replacing inside a tag name
        if (match.startsWith('&lt;') || match.startsWith('&gt;') || match.startsWith('span')) {
          return match;
        }
        return `<span class="${rule.clazz}">${match}</span>`;
      });
    });

    return highlighted;
  };

  const lines = block.content.split('\n');

  return (
    <div className="flex flex-col h-full bg-[#0D0D11] rounded-lg border border-zinc-800 overflow-hidden font-mono text-xs text-zinc-300">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-[#14141A] border-b border-zinc-800 select-none">
        <div className="flex items-center gap-2 text-zinc-400">
          <Code size={14} className="text-indigo-400" />
          <span className="font-semibold text-zinc-300">{block.title || 'Source Code'}</span>
          {block.lang && (
            <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-[10px] uppercase font-bold text-zinc-500">
              {block.lang}
            </span>
          )}
        </div>

        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors cursor-pointer"
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
                  className="pl-4 whitespace-pre" 
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
