export const EMOTIONS = {
  NORMAL: 'normal',
  ENCOURAGING: 'encouraging',
  EXCITED: 'excited',
  THINKING: 'thinking',
  CONFUSED: 'confused',
};

export const PIPELINE_STATES = {
  IDLE: 'IDLE',
  LISTENING: 'LISTENING',
  THINKING: 'THINKING',
  TRANSCRIBING: 'TRANSCRIBING',
  SPEAKING: 'SPEAKING',
  INTERRUPTED: 'INTERRUPTED',
  ERROR: 'ERROR'
};

export const AVATAR_STATE_MAP = {
  [PIPELINE_STATES.IDLE]: 'idle',
  [PIPELINE_STATES.LISTENING]: 'listening',
  [PIPELINE_STATES.THINKING]: 'thinking',
  [PIPELINE_STATES.TRANSCRIBING]: 'thinking',
  [PIPELINE_STATES.SPEAKING]: 'speaking',
  [PIPELINE_STATES.INTERRUPTED]: 'idle',
  [PIPELINE_STATES.ERROR]: 'idle'
};

export const getEmotionClass = (emotion) => {
  return emotion ? `emotion-${emotion}` : '';
};

export const getStateClass = (state, isRecording, isProcessing, isPlaying) => {
  if (state === PIPELINE_STATES.LISTENING || isRecording) return 'state-listening';
  if (state === PIPELINE_STATES.THINKING || state === PIPELINE_STATES.TRANSCRIBING || isProcessing) return 'state-thinking';
  if (state === PIPELINE_STATES.SPEAKING || isPlaying) return 'state-speaking';
  return 'state-idle';
};
