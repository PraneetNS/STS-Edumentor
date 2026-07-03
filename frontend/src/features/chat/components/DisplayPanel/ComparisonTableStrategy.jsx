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
                      {Array.from({ length: headers.length }).map((_, cIdx) => {
                        const cell = row[cIdx] || '';
                        return (
                          <td key={cIdx} className="px-4 py-3 text-xs text-zinc-300 align-middle whitespace-normal break-words max-w-[300px]">
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
