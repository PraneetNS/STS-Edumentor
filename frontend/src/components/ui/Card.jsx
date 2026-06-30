import React from 'react';

export function Card({
  title,
  subtitle,
  children,
  footer,
  hoverable = false,
  className = '',
  ...props
}) {
  return (
    <div
      className={`rounded-lg border border-zinc-200 bg-white text-zinc-950 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-50 shadow-sm transition-all ${
        hoverable ? 'hover:shadow-md hover:border-zinc-300 dark:hover:border-zinc-700' : ''
      } ${className}`}
      {...props}
    >
      {(title || subtitle) && (
        <div className="flex flex-col gap-1 p-4 border-b border-zinc-100 dark:border-zinc-800">
          {title && <h3 className="text-sm font-semibold leading-none tracking-tight">{title}</h3>}
          {subtitle && <p className="text-xs text-zinc-500 dark:text-zinc-400">{subtitle}</p>}
        </div>
      )}
      {children && <div className="p-4 text-sm leading-relaxed">{children}</div>}
      {footer && (
        <div className="flex items-center p-4 border-t border-zinc-100 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-950/20 rounded-b-lg">
          {footer}
        </div>
      )}
    </div>
  );
}
