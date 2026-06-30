import React, { useId } from 'react';

export function Input({
  label,
  error,
  type = 'text',
  disabled = false,
  className = '',
  placeholder = '',
  value,
  onChange,
  ...props
}) {
  const inputId = useId();
  const errorId = useId();

  return (
    <div className={`flex flex-col gap-1.5 w-full ${className}`}>
      {label && (
        <label
          htmlFor={inputId}
          className="text-xs font-semibold text-zinc-700 dark:text-zinc-300 select-none"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        type={type}
        disabled={disabled}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        aria-invalid={!!error}
        aria-describedby={error ? errorId : undefined}
        className={`w-full h-10 px-3 text-sm bg-transparent border rounded-md transition-colors placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 disabled:bg-zinc-50 dark:disabled:bg-zinc-950 ${
          error
            ? 'border-rose-500 focus:ring-rose-500'
            : 'border-zinc-200 dark:border-zinc-800 hover:border-zinc-300 dark:hover:border-zinc-700 focus:border-zinc-400 dark:focus:border-zinc-650'
        }`}
        {...props}
      />
      {error && (
        <span
          id={errorId}
          className="text-xs text-rose-500 font-medium"
          role="alert"
        >
          {error}
        </span>
      )}
    </div>
  );
}
