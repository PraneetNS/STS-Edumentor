import React, { useEffect, useRef, useState } from 'react';
import { Maximize2, Minimize2, ZoomIn, ZoomOut, AlertTriangle, Cpu } from 'lucide-react';

let mermaidLoadingPromise = null;

function loadMermaid() {
  if (window.mermaid) return Promise.resolve(window.mermaid);
  if (mermaidLoadingPromise) return mermaidLoadingPromise;

  mermaidLoadingPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.type = 'module';
    script.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
    script.onload = () => {
      // Script is loaded, but because it's an ESM module, window.mermaid might be loaded via import
      import('https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs')
        .then((m) => {
          window.mermaid = m.default;
          window.mermaid.initialize({
            startOnLoad: false,
            theme: document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'default',
            securityLevel: 'strict',
            flowchart: { useMaxWidth: false, htmlLabels: false }
          });
          resolve(window.mermaid);
        })
        .catch(reject);
    };
    script.onerror = reject;
    document.head.appendChild(script);
  });

  return mermaidLoadingPromise;
}

export default function MermaidStrategy({ block }) {
  const containerRef = useRef(null);
  const [svg, setSvg] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scale, setScale] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    loadMermaid()
      .then((mermaid) => {
        if (!active) return;
        
        // Clean output of potentially harmful HTML tags prior to compilation as per standards
        const cleanedContent = block.content
          .replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, '')
          .replace(/on\w+\s*=/gi, '');

        const id = `mermaid-${Date.now()}`;
        mermaid.render(id, cleanedContent)
          .then(({ svg }) => {
            if (active) {
              setSvg(svg);
              setLoading(false);
            }
          })
          .catch((err) => {
            console.error('Mermaid render error:', err);
            if (active) {
              setError(err.message || 'Syntax error in Mermaid layout syntax.');
              setLoading(false);
            }
          });
      })
      .catch((err) => {
        console.error('Failed to load Mermaid library from CDN:', err);
        if (active) {
          setError('Failed to load chart engine. Please check your internet connection.');
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [block.content]);

  const handleZoomIn = () => setScale((s) => Math.min(s + 0.15, 3));
  const handleZoomOut = () => setScale((s) => Math.max(s - 0.15, 0.5));
  const handleResetZoom = () => setScale(1);

  return (
    <div className={`flex flex-col h-full bg-[#18181B] rounded-lg border border-zinc-800 overflow-hidden relative ${
      isFullscreen ? 'fixed inset-4 z-[100] shadow-2xl bg-zinc-950 border-zinc-700' : ''
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-[#121214] border-b border-zinc-800 select-none">
        <div className="flex items-center gap-2">
          <Cpu size={14} className="text-emerald-400" />
          <span className="font-semibold text-xs text-zinc-300">{block.title || 'System Diagram'}</span>
        </div>

        <div className="flex items-center gap-2">
          {/* Zoom controls */}
          {!error && !loading && (
            <div className="flex items-center border border-zinc-800 rounded bg-zinc-900 overflow-hidden text-[10px] font-semibold text-zinc-400">
              <button onClick={handleZoomOut} className="px-2 py-1 hover:bg-zinc-800 hover:text-zinc-200 cursor-pointer" title="Zoom Out">
                <ZoomOut size={12} />
              </button>
              <button onClick={handleResetZoom} className="px-2.5 py-1 border-x border-zinc-800 hover:bg-zinc-800 hover:text-zinc-200 cursor-pointer" title="Reset Zoom">
                {Math.round(scale * 100)}%
              </button>
              <button onClick={handleZoomIn} className="px-2 py-1 hover:bg-zinc-800 hover:text-zinc-200 cursor-pointer" title="Zoom In">
                <ZoomIn size={12} />
              </button>
            </div>
          )}

          {/* Fullscreen toggle */}
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1.5 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-400 hover:text-zinc-200 cursor-pointer"
            title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
          >
            {isFullscreen ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
          </button>
        </div>
      </div>

      {/* Main viewport */}
      <div className="flex-1 overflow-auto p-6 flex items-center justify-center bg-zinc-950/20">
        {loading ? (
          <div className="flex flex-col items-center gap-3">
            <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-xs text-zinc-500">Compiling architecture...</span>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center max-w-sm text-center gap-3 p-4">
            <AlertTriangle size={24} className="text-rose-500" />
            <h4 className="text-xs font-semibold text-zinc-200">Diagram Compilation Failed</h4>
            <pre className="text-[10px] font-mono text-rose-400 bg-rose-950/20 border border-rose-900/30 p-3 rounded-lg overflow-auto max-w-full text-left">
              {error}
            </pre>
            <div className="text-[10px] font-mono text-zinc-500 text-left w-full mt-2 border-t border-zinc-800 pt-2">
              <div className="font-semibold text-zinc-400 mb-1">Raw Markup:</div>
              {block.content}
            </div>
          </div>
        ) : (
          <div
            ref={containerRef}
            className="transition-transform duration-100 flex items-center justify-center"
            style={{ transform: `scale(${scale})`, transformOrigin: 'center center' }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        )}
      </div>
    </div>
  );
}
