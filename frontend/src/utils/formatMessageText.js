const WORDS_PER_LINE = 12;

function isStructuredMarkdownLine(line) {
  const trimmed = line.trim();
  return (
    trimmed.startsWith('# ') ||
    trimmed.startsWith('## ') ||
    trimmed.startsWith('### ') ||
    trimmed.startsWith('- ') ||
    trimmed.startsWith('* ') ||
    /^\d+\.\s/.test(trimmed) ||
    trimmed.startsWith('> ') ||
    trimmed.startsWith('|') ||
    trimmed.trim() === '---' ||
    trimmed.startsWith('```')
  );
}

function wrapLineByWordCount(line, wordsPerLine = WORDS_PER_LINE) {
  const trimmed = line.trim();
  if (!trimmed || isStructuredMarkdownLine(trimmed)) return [line];

  const words = trimmed.split(/\s+/).filter(Boolean);
  if (words.length <= wordsPerLine) return [trimmed];

  const wrapped = [];
  for (let i = 0; i < words.length; i += wordsPerLine) {
    wrapped.push(words.slice(i, i + wordsPerLine).join(' '));
  }
  return wrapped;
}

export function wrapTextByWordCount(text, wordsPerLine = WORDS_PER_LINE) {
  if (!text) return '';
  return text
    .split('\n')
    .flatMap((line) => wrapLineByWordCount(line, wordsPerLine))
    .join('\n');
}

export function splitWrappedLines(text, wordsPerLine = WORDS_PER_LINE) {
  return wrapTextByWordCount(text, wordsPerLine)
    .split('\n')
    .filter((line) => line.trim() !== '');
}
