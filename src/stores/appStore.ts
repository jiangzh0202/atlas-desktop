import { create } from 'zustand'

export interface Tab { id: string; label: string }

interface AppState {
  activeView: 'knowledge' | 'agents' | 'settings'
  activeAgent: string | null
  tabs: Tab[]
  activeTab: string
  sidebarWidth: number
  showPalette: boolean
  showSettings: boolean
  settingsSection: string
  theme: 'dark' | 'light'
  accentColor: string
  language: 'zh' | 'en'
  zoom: number
  model: string
  apiEndpoint: string
  dataPath: string
  httpProxy: string
  notifications: boolean
  usageStats: { apiCalls: number; tokens: number }
  setActiveView: (v: AppState['activeView']) => void
  setActiveAgent: (a: string | null) => void
  openTab: (id: string, label: string) => void
  closeTab: (id: string) => void
  setActiveTab: (id: string) => void
  setSidebarWidth: (w: number) => void
  togglePalette: () => void
  toggleSettings: () => void
  setSettingsSection: (s: string) => void
  updateSetting: (key: string, value: any) => void
}

export const useAppStore = create<AppState>((set, get) => ({
  activeView: 'knowledge',
  activeAgent: null,
  tabs: [{ id: 'welcome', label: '🏠 欢迎' }],
  activeTab: 'welcome',
  sidebarWidth: 260,
  showPalette: false,
  showSettings: false,
  settingsSection: 'general',
  theme: 'dark',
  accentColor: '#7ecf5e',
  language: 'zh',
  zoom: 100,
  model: 'deepseek-chat',
  apiEndpoint: 'https://atlas.traceclaw.cn',
  dataPath: '',
  httpProxy: '',
  notifications: true,
  usageStats: { apiCalls: 0, tokens: 0 },

  setActiveView: (v) => set({ activeView: v }),
  setActiveAgent: (a) => set({ activeAgent: a }),

  openTab: (id, label) => {
    const { tabs } = get()
    if (!tabs.find(t => t.id === id)) {
      set({ tabs: [...tabs, { id, label }] })
    }
    set({ activeTab: id })
  },

  closeTab: (id) => {
    const { tabs, activeTab } = get()
    const idx = tabs.findIndex(t => t.id === id)
    if (idx < 0) return
    const next = tabs.filter(t => t.id !== id)
    let nextActive = activeTab
    if (activeTab === id) {
      nextActive = next[Math.min(idx, next.length - 1)]?.id || 'welcome'
    }
    set({ tabs: next.length ? next : [{ id: 'welcome', label: '🏠 欢迎' }], activeTab: nextActive })
  },

  setActiveTab: (id) => set({ activeTab: id }),
  setSidebarWidth: (w) => set({ sidebarWidth: Math.max(180, Math.min(400, w)) }),
  togglePalette: () => set(s => ({ showPalette: !s.showPalette })),
  toggleSettings: () => set(s => ({ showSettings: !s.showSettings })),
  setSettingsSection: (s) => set({ settingsSection: s }),
  updateSetting: (key, value) => set({ [key]: value } as any),
}))
