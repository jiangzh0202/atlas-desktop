import { useAppStore } from './stores/appStore'
import ActivityBar from './components/ActivityBar'
import Sidebar from './components/Sidebar'
import Workspace from './components/Workspace'
import CommandPalette from './components/CommandPalette'
import StatusBar from './components/StatusBar'
import Settings from './components/Settings'
import { useEffect } from 'react'

export default function App() {
  const { showPalette, showSettings } = useAppStore()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        useAppStore.getState().togglePalette()
      }
      if (e.key === 'Escape') {
        useAppStore.setState({ showPalette: false, showSettings: false })
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  return (
    <>
      <ActivityBar />
      <Sidebar />
      <div style={{width:3,flexShrink:0,cursor:'col-resize',background:'transparent',transition:'background .15s'}}
        onMouseDown={() => {
          const onMove = (e: MouseEvent) => useAppStore.getState().setSidebarWidth(e.clientX - 48)
          const onUp = () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); document.body.style.cursor = '' }
          document.body.style.cursor = 'col-resize'
          document.addEventListener('mousemove', onMove)
          document.addEventListener('mouseup', onUp)
        }}
        onMouseEnter={e => (e.target as HTMLElement).style.background = 'var(--green)'}
        onMouseLeave={e => (e.target as HTMLElement).style.background = 'transparent'}
      />
      <Workspace />
      <StatusBar />
      {showPalette && <CommandPalette />}
      {showSettings && <Settings />}
    </>
  )
}