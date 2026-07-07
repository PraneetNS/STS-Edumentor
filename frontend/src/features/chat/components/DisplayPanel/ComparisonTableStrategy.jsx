import React, { useState, useEffect } from 'react';
import { Table, Search, AlertCircle } from 'lucide-react';

export default function ComparisonTableStrategy({ block }) {
  const [headers, setHeaders] = useState([]);
  const [rows, setRows] = useState([]);
  const [filterQuery, setFilterQuery] = useState('');

  useEffect(() => {
    const rawLines = block.content.split('\n');
    
    // Clean and split lines into cells
    const lineCells = rawLines
      .map(line => {
        let clean = line.trim();
        // Remove leading and trailing pipes if present
        if (clean.startsWith('|')) clean = clean.slice(1);
        if (clean.endsWith('|')) clean = clean.slice(0, -1);
        
        // Return null for empty lines so we can filter them out
        if (clean === '') return null;
        
        return clean.split('|').map(c => c.trim());
      })
      .filter(cells => cells !== null);

    // Find the separator line index (e.g. |---|---| or ---|---)
    const separatorIdx = lineCells.findIndex(cells => 
      cells.length > 0 && cells.every(cell => /^[\s:-]+$/.test(cell))
    );

    let parsedHeaders = [];
    let parsedRows = [];

    if (separatorIdx > 0) {
      // Header is the line right before the separator
      parsedHeaders = lineCells[separatorIdx - 1];
      // Rows are all lines after the separator
      parsedRows = lineCells.slice(separatorIdx + 1);
    } else if (lineCells.length > 0) {
      // Fallback: If no separator line found yet (streaming), use the first non-empty line as header
      // but only if it contains actual column separators (pipes)
      const firstLine = lineCells[0];
      if (firstLine.length > 1) {
        parsedHeaders = firstLine;
        parsedRows = lineCells.slice(1);
      }
    }

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
    <div className="flex flex-col h-full bg-[#161619] rounded-xl border border-zinc-800/80 overflow-hidden font-sans shadow-lg select-text">
      {/* Header with Search */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-5 py-4 bg-[#1e1e24] border-b border-zinc-800 select-none">
        <div className="flex items-center gap-2.5">
          <Table size={18} className="text-indigo-400" />
          <span className="font-bold text-sm text-zinc-100">{block.title || 'Comparison Table'}</span>
        </div>

        {rows.length > 0 && (
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" size={14} />
            <input
              type="text"
              placeholder="Search table..."
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              className="pl-9 pr-3.5 py-1.5 w-full sm:w-52 bg-zinc-900 border border-zinc-800 rounded-lg text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-indigo-500 transition-all"
            />
          </div>
        )}
      </div>

      {/* Body with table */}
      <div className="flex-1 overflow-auto p-5 select-text">
        {headers.length === 0 ? (
          <div className="w-full flex flex-col gap-4 animate-pulse select-none">
            {/* Processing Message */}
            <div className="flex items-center gap-2 px-1">
              <div className="flex space-x-1.5">
                <div className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                <div className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                <div className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce"></div>
              </div>
              <span className="text-xs font-semibold text-zinc-400">Processing Table...</span>
            </div>

            {/* Table Outline */}
            <div className="overflow-x-auto border border-zinc-800/80 rounded-lg bg-[#141416]/50">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-zinc-900/60 border-b border-zinc-800/80">
                    <th className="px-5 py-4">
                      <div className="h-3 w-16 bg-zinc-800 rounded-md" />
                    </th>
                    <th className="px-5 py-4">
                      <div className="h-3 w-28 bg-zinc-800 rounded-md" />
                    </th>
                    <th className="px-5 py-4">
                      <div className="h-3 w-20 bg-zinc-800 rounded-md" />
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/40">
                  {[1, 2, 3].map((rowIdx) => (
                    <tr key={rowIdx}>
                      <td className="px-5 py-4">
                        <div className="h-3 w-24 bg-zinc-800/45 rounded-md" />
                      </td>
                      <td className="px-5 py-4">
                        <div className="h-3 w-36 bg-zinc-800/45 rounded-md" />
                      </td>
                      <td className="px-5 py-4">
                        <div className="h-3 w-16 bg-zinc-800/45 rounded-md" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto border border-zinc-800/80 rounded-xl bg-zinc-900/10">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-zinc-900/60 border-b border-zinc-800/80">
                  {headers.map((h, i) => (
                    <th key={i} className="px-5 py-4 text-xs font-bold text-zinc-300 uppercase tracking-wider select-none">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/40">
                {filteredRows.length === 0 ? (
                  <tr>
                    <td colSpan={headers.length} className="px-5 py-6 text-center text-sm text-zinc-500">
                      No matching records found.
                    </td>
                  </tr>
                ) : (
                  filteredRows.map((row, rIdx) => (
                    <tr key={rIdx} className="hover:bg-zinc-900/35 transition-colors">
                      {Array.from({ length: headers.length }).map((_, cIdx) => {
                        const cell = row[cIdx] || '';
                        return (
                          <td key={cIdx} className="px-5 py-4 text-[13px] text-zinc-200 align-middle whitespace-normal break-words max-w-[300px]">
                            {formatTableCell(cell)}
                          </td>
                        );
                      })}
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
