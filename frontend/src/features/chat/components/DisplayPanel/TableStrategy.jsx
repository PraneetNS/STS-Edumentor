import React from 'react';

export function TableStrategy({ block }) {
  const lines = block.content.split('\n').map((line) => line.trim()).filter((line) => line.startsWith('|'));

  if (lines.length === 0) {
    return (
      <div className="p-4 bg-zinc-50 dark:bg-zinc-900 border border-dashed border-zinc-200 dark:border-zinc-800 rounded-lg text-center text-xs text-zinc-400">
        No comparative data available
      </div>
    );
  }

  // Parse lines to columns
  const parseRow = (rowText) => {
    // Strip leading and trailing pipe
    const clean = rowText.replace(/^\|/, '').replace(/\|$/, '');
    return clean.split('|').map((col) => col.trim());
  };

  const headers = parseRow(lines[0]);
  const rows = [];

  // Start from line 2 to skip header separator row (like |---|---|)
  const startIndex = lines[1]?.includes('---') ? 2 : 1;

  for (let i = startIndex; i < lines.length; i++) {
    const columns = parseRow(lines[i]);
    if (columns.length > 0) {
      rows.push(columns);
    }
  }

  return (
    <div className="w-full border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden bg-white dark:bg-zinc-900 shadow-sm">
      <div className="px-5 py-4 border-b border-zinc-150 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-950/20 select-none">
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 uppercase tracking-wider text-xs">
          {block.title || 'Data Comparison Matrix'}
        </h3>
      </div>
      <div className="overflow-x-auto select-text">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950/50 font-semibold text-zinc-700 dark:text-zinc-300">
              {headers.map((h, i) => (
                <th key={i} className="px-5 py-3 border-r border-zinc-200/60 dark:border-zinc-800/60 last:border-0 font-medium text-xs uppercase tracking-wider">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIdx) => (
              <tr
                key={rowIdx}
                className="border-b border-zinc-150 dark:border-zinc-800 last:border-0 hover:bg-zinc-50/40 dark:hover:bg-zinc-950/10 text-zinc-650 dark:text-zinc-350"
              >
                {row.map((cell, cellIdx) => (
                  <td key={cellIdx} className="px-5 py-3 border-r border-zinc-200/40 dark:border-zinc-800/40 last:border-0 leading-relaxed font-normal">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
