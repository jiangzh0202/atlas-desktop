import { useAppStore } from '../stores/appStore'
import WelcomeHome from './WelcomeHome'
import QuoteAgent from './QuoteAgent'
import ProspectAgent from './ProspectAgent'

const viewMap: Record<string, React.ComponentType> = {
  welcome: WelcomeHome,
  quote: QuoteAgent,
  prospect: ProspectAgent,
}

export default function Workspace() {
  const { tabs, activeTab, closeTab, setActiveTab } = useAppStore()
  const ActiveComponent = viewMap[activeTab] || WelcomeHome

  return (
    <div style={{flex:1, display:'flex', flexDirection:'column', overflow:'hidden'}}>
      <div style={{
        display:'flex', background:'var(--panel)', borderBottom:'1px solid var(--line)',
        padding:'0 8px', minHeight:36, alignItems:'flex-end', gap:2, flexShrink:0
      }}>
        {tabs.map(tab => {
          const isActive = tab.id === activeTab
          return (
            <div key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding:'7px 14px', fontSize:'.78rem', cursor:'pointer',
                borderRadius:'6px 6px 0 0', display:'flex', alignItems:'center', gap:6,
                color: isActive ? 'var(--ink)' : 'var(--muted)',
                background: isActive ? 'var(--bg)' : 'transparent',
                border: isActive ? '1px solid var(--line)' : '1px solid transparent',
                borderBottomColor: isActive ? 'var(--bg)' : undefined,
                transition:'all .1s', whiteSpace:'nowrap'
              }}
              onMouseEnter={e => { if(!isActive) { e.currentTarget.style.color='var(--ink)'; e.currentTarget.style.background='var(--active)' } }}
              onMouseLeave={e => { if(!isActive) { e.currentTarget.style.color='var(--muted)'; e.currentTarget.style.background='transparent' } }}
            >
              {tab.label}
              {tab.id !== 'welcome' && (
                <span
                  onClick={e => { e.stopPropagation(); closeTab(tab.id) }}
                  style={{fontSize:'.7rem',padding:'2px 4px',borderRadius:3,opacity:0,transition:'opacity .1s'}}
                  onMouseEnter={e => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.background='var(--line)' }}
                  onMouseLeave={e => { e.currentTarget.style.opacity = ''; e.currentTarget.style.background='transparent' }}
                >×</span>
              )}
            </div>
          )
        })}
      </div>
      <div style={{flex:1, overflow:'hidden', display:'flex', flexDirection:'column'}}>
        <ActiveComponent />
      </div>
    </div>
  )
}