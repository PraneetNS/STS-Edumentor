import { createStore } from './createStore';

export const studentStore = createStore((set, get) => ({
  name: 'Student',
  skillLevel: 'intermediate',
  topics: ['Computer Science', 'Software Engineering'],
  weakAreas: [],
  lastEmotion: 'neutral',
  progress: 75, // Rating out of 100

  updateProfile: (profile) => set((state) => ({ ...state, ...profile })),
  setLastEmotion: (emotion) => set({ lastEmotion: emotion }),
  addWeakArea: (area) => {
    if (!get().weakAreas.includes(area)) {
      set((state) => ({ weakAreas: [...state.weakAreas, area] }));
    }
  },
  resetProfile: () => set({
    name: 'Student',
    skillLevel: 'intermediate',
    topics: ['Computer Science', 'Software Engineering'],
    weakAreas: [],
    lastEmotion: 'neutral',
    progress: 75
  }),
}));
