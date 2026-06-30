import React, { useState, useEffect } from 'react';
import { Table, Search, AlertCircle } from 'lucide-react';

export default function ComparisonTableStrategy({ block }) {
  const [headers, setHeaders] = useState([]);
  const [rows, setRows] = useState([]);
  const [filterQuery, setFilterQuery] = useState('');

  useEffect(() => {
    const lines = block.content.split('\n');
    const parsedHeaders = [];
    const parsedRows = [];

    lines.forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed || !trimmed.startsWith('|')) return;

      // Skip separators like |---|---|
      if (trimmed.match(/^\|[\s:-|]+$/)) return;

      const cells = trimmed
        .split('|')
        .map((c) => c.trim())
        .filter((_, idx, arr) => idx > 0 && idx < arr.length - 1); // remove first/last empty cells from boundary split

      if (parsedHeaders.length === 0) {
        parsedHeaders.push(...cells);
      } else {
        parsedRows.push(cells);
      }
    });

    setHeaders(parsedHeaders);
    setRows(parsedRows);
  }, [block.content]);

  // Highlights specific content cells (e.g., Pros/Cons/Yes/No)
  const formatTableCell = (cell) => {
    const text = cell.toLowerCase();
    
    if (text === 'yes' || text === 'true' || text === 'pro' || text === 'pros' || text === 'advantage' || text === 'fast' || text === 'high') {
      return (
        <span className="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-800 text-emerald-400 text-[10px] font-bold">
          {cell}
        </span>
      );
    }
    
    if (text === 'no' || text === 'false' || text === 'con' || text === 'cons' || text === 'disadvantage' || text === 'slow' || text === 'low') {
      return (
        <span className="px-2 py-0.5 rounded bg-rose-950/60 border border-rose-900/40 text-rose-400 text-[10px] font-bold">
          {cell}
        </span>
      );
    }

    if (text === 'medium' || text === 'average' || text === 'moderate') {
      return (
        <span className="px-2 py-0.5 rounded bg-amber-950/60 border border-amber-800/50 text-amber-400 text-[10px] font-bold">
          {cell}
        </span>
      );
    }

    return <span className="text-zinc-300 text-xs">{cell}</span>;
  };

  const filteredRows = rows.filter((row) =>
    row.some((cell) => cell.toLowerCase().includes(filterQuery.toLowerCase()))
  );

  return (
    <div className="flex flex-col h-full bg-[#121214] rounded-lg border border-zinc-800 overflow-hidden font-sans">
      {/* Header with Search */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-4 py-3 bg-[#18181B] border-b border-zinc-800 select-none">
        <div className="flex items-center gap-2">
          <Table size={16} className="text-indigo-400" />
          <span className="font-semibold text-xs text-zinc-200">{block.title || 'Comparison Table'}</span>
        </div>

        {rows.length > 0 && (
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" size={13} />
            <input
              type="text"
              placeholder="Search table..."
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              className="pl-8 pr-3 py-1 w-full sm:w-48 bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-200 placeholder:text-zinc-650 focus:outline-none focus:border-indigo-500"
            />
          </div>
        )}
      </div>

      {/* Body with table */}
      <div className="flex-1 overflow-auto p-4 select-text">
        {headers.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 gap-2 text-zinc-500">
            <AlertCircle size={20} />
            <p className="text-xs">Failed to parse table layout.</p>
          </div>
        ) : (
          <div className="overflow-x-auto border border-zinc-800/80 rounded-lg">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-zinc-900 border-b border-zinc-800">
                  {headers.map((h, i) => (
                    <th key={i} className="px-4 py-3 text-xs font-bold text-zinc-400 uppercase tracking-wider select-none">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50">
                {filteredRows.length === 0 ? (
                  <tr>
                    <td colSpan={headers.length} className="px-4 py-6 text-center text-xs text-zinc-500">
                      No matching records found.
                    </td>
                  </tr>
                ) : (
                  filteredRows.map((row, rIdx) => (
                    <tr key={rIdx} className="hover:bg-zinc-900/20 transition-colors">
                      {row.map((cell, cIdx) => (
                        <td key={cIdx} className="px-4 py-3 whitespace-nowrap align-middle">
                          {formatTableCell(cell)}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
