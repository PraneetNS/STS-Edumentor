import { useMemo } from 'react';
import { studentStore } from '../stores/studentStore';

export function useStudentStore() {
  const name = studentStore.useStore((s) => s.name);
  const skillLevel = studentStore.useStore((s) => s.skillLevel);
  const topics = studentStore.useStore((s) => s.topics);
  const weakAreas = studentStore.useStore((s) => s.weakAreas);
  const lastEmotion = studentStore.useStore((s) => s.lastEmotion);
  const progress = studentStore.useStore((s) => s.progress);

  const actions = useMemo(() => ({
    updateProfile: studentStore.getState().updateProfile,
    setLastEmotion: studentStore.getState().setLastEmotion,
    addWeakArea: studentStore.getState().addWeakArea,
    resetProfile: studentStore.getState().resetProfile,
  }), []);

  return {
    name,
    skillLevel,
    topics,
    weakAreas,
    lastEmotion,
    progress,
    ...actions,
  };
}
