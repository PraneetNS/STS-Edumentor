import { createStore } from './createStore';

export const uiStore = createStore((set, get) => ({
  theme: localStorage.getItem('theme') || 'dark',
  sidebarOpen: false,
  activeDisplayTab: 'code',
  showDocsModal: false,
  shortcutsEnabled: (() => {
    const saved = localStorage.getItem('shortcutsEnabled');
    return saved !== null ? JSON.parse(saved) : true;
  })(),

  setTheme: (theme) => {
    localStorage.setItem('theme', theme);
    document.documentElement.setAttribute('data-theme', theme);
    set({ theme });
  },
  toggleTheme: () => {
    const nextTheme = get().theme === 'light' ? 'dark' : 'light';
    get().setTheme(nextTheme);
  },
  setSidebarOpen: (isOpen) => set({ sidebarOpen: isOpen }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setActiveDisplayTab: (tab) => set({ activeDisplayTab: tab }),
  setShowDocsModal: (show) => set({ showDocsModal: show }),
  setShortcutsEnabled: (enabled) => {
    localStorage.setItem('shortcutsEnabled', JSON.stringify(enabled));
    set({ shortcutsEnabled: enabled });
  },
}));

// Initialize theme on load
if (typeof window !== 'undefined') {
  const currentTheme = uiStore.getState().theme;
  document.documentElement.setAttribute('data-theme', currentTheme);
}
