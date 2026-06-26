import React, { memo } from 'react';
import { splitWrappedLines } from '../utils/formatMessageText';

export const UserMessageText = memo(function UserMessageText({ text = '' }) {
  const lines = splitWrappedLines(text);

  if (lines.length === 0) return null;

  return (
    <div className="user-message-text">
      {lines.map((line, index) => (
        <p key={index} className="message-text-line">
          {line}
        </p>
      ))}
    </div>
  );
});
