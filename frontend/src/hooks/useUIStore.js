import { useMemo } from 'react';
import { uiStore } from '../stores/uiStore';

export function useUIStore() {
  const theme = uiStore.useStore((s) => s.theme);
  const sidebarOpen = uiStore.useStore((s) => s.sidebarOpen);
  const activeDisplayTab = uiStore.useStore((s) => s.activeDisplayTab);
  const showDocsModal = uiStore.useStore((s) => s.showDocsModal);
  const shortcutsEnabled = uiStore.useStore((s) => s.shortcutsEnabled);

  const actions = useMemo(() => ({
    setTheme: uiStore.getState().setTheme,
    toggleTheme: uiStore.getState().toggleTheme,
    setSidebarOpen: uiStore.getState().setSidebarOpen,
    toggleSidebar: uiStore.getState().toggleSidebar,
    setActiveDisplayTab: uiStore.getState().setActiveDisplayTab,
    setShowDocsModal: uiStore.getState().setShowDocsModal,
    setShortcutsEnabled: uiStore.getState().setShortcutsEnabled,
  }), []);

  return {
    theme,
    sidebarOpen,
    activeDisplayTab,
    showDocsModal,
    shortcutsEnabled,
    ...actions,
  };
}
