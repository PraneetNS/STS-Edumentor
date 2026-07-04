import React from 'react';

/**
 * Tooltip component displays a clean popover bubble when hovering over its children.
 *
 * @param {Object} props
 * @param {string} props.text - The tooltip message to display. If falsy or empty, displays only children.
 * @param {React.ReactNode} props.children - Target element(s) which will trigger the tooltip.
 */
export function Tooltip({ text, children }) {
  // Gracefully skip rendering tooltip wrapper if no hover text is provided
  if (typeof text !== 'string' || !text.trim()) {
    return <>{children}</>;
  }

  return (
    <div className="relative group inline-block w-full" data-testid="tooltip-wrapper">
      {children}
      <div className="absolute z-[9999] bottom-full left-1/2 -translate-x-1/2 mb-2 px-2.5 py-1.5 bg-neutral-900 text-white font-sans text-[10px] font-medium rounded-lg shadow-md pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-150 whitespace-nowrap">
        {text}
        {/* Tooltip caret triangle arrow */}
        <div className="absolute top-full left-1/2 -translate-x-1/2 border-[5px] border-transparent border-t-neutral-900" />
      </div>
    </div>
  );
}
