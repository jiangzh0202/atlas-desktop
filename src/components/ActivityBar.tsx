import { useAppStore } from '../stores/appStore'

const items = [
  { id: 'knowledge', icon: '📁', label: '知识库' },
  { id: 'agents', icon: '🤖', label: '数字员工' },
] as const

export default function ActivityBar() {
  const { activeView, setActiveView, toggleSettings, showSettings } = useAppStore()

  return (
    <div style={{
      width:48, background:'var(--sidebar)', display:'flex', flexDirection:'column',
      alignItems:'center', padding:'8px 0', gap:2, borderRight:'1px solid var(--line)', flexShrink:0
    }}>
      {items.map(item => {
        const isActive = activeView === item.id
        return (
          <div key={item.id}
            onClick={() => { setActiveView(item.id); useAppStore.setState({ showSettings: false }) }}
            title={item.label}
            style={{
              width:40, height:40, display:'flex', alignItems:'center', justifyContent:'center',
              borderRadius:8, cursor:'pointer', fontSize:'1.2rem',
              color: isActive ? 'var(--ink)' : 'var(--muted)',
              background: isActive ? 'var(--active)' : 'transparent',
              position:'relative', transition:'all .15s'
            }}
            onMouseEnter={e => { if(!isActive) { e.currentTarget.style.color='var(--ink)'; e.currentTarget.style.background='var(--active)' } }}
            onMouseLeave={e => { if(!isActive) { e.currentTarget.style.color='var(--muted)'; e.currentTarget.style.background='transparent' } }}
          >
            {item.icon}
            {isActive && <div style={{position:'absolute',left:-8,top:8,bottom:8,width:2,background:'var(--green)',borderRadius:1}} />}
          </div>
        )
      })}
      <div style={{flex:1}} />
      <div
        onClick={toggleSettings}
        title="设置"
        style={{
          width:40, height:40, display:'flex', alignItems:'center', justifyContent:'center',
          borderRadius:8, cursor:'pointer', fontSize:'1.2rem',
          color: showSettings ? 'var(--ink)' : 'var(--muted)',
          background: showSettings ? 'var(--active)' : 'transparent',
          transition:'all .15s'
        }}
        onMouseEnter={e => { if(!showSettings) { e.currentTarget.style.color='var(--ink)'; e.currentTarget.style.background='var(--active)' } }}
        onMouseLeave={e => { if(!showSettings) { e.currentTarget.style.color='var(--muted)'; e.currentTarget.style.background='transparent' } }}
      >
        ⚙️
      </div>
    </div>
  )
}