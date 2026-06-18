import { useAppStore } from '../stores/appStore'

const knowledgeFiles = [
  { icon: '📊', name: '历史报价_2024.xlsx' },
  { icon: '📊', name: '历史报价_2025Q1.xlsx' },
  { icon: '👥', name: '客户清单.csv' },
  { icon: '💰', name: '供应商价格表.xlsx' },
  { icon: '📋', name: '报价模板.xlsx' },
  { icon: '📝', name: 'pricing.md' },
]

const agents = [
  { id: 'quote', icon: '💎', name: '报价员', desc: '从历史数据学习，3秒出价', subscribed: true },
  { id: 'prospect', icon: '🎯', name: '客户开发员', desc: '搜客户→画像→开发信', subscribed: true },
  { id: 'image', icon: '🔍', name: '图片识零件员', desc: '拍照识OE号，匹配库存', subscribed: false },
  { id: 'stock', icon: '📦', name: '库存管理员', desc: '预测需求+呆滞预警', subscribed: false },
  { id: 'customs', icon: '🛃', name: '清关助理', desc: 'HS编码+报关单自动生成', subscribed: false },
]

export default function Sidebar() {
  const { activeView, sidebarWidth, setActiveAgent, activeAgent, openTab } = useAppStore()

  return (
    <div style={{
      width: sidebarWidth, background:'var(--panel)', borderRight:'1px solid var(--line)',
      display:'flex', flexDirection:'column', flexShrink:0, overflow:'hidden'
    }}>
      <div style={{
        padding:'12px 14px', fontSize:'.7rem', fontWeight:600, textTransform:'uppercase',
        color:'var(--dim)', letterSpacing:'.5px', display:'flex', alignItems:'center', justifyContent:'space-between'
      }}>
        <span>{activeView === 'knowledge' ? '知识库' : '数字员工'}</span>
        <span style={{fontSize:'.9rem',cursor:'pointer',padding:'2px 6px',borderRadius:4}}
          onMouseEnter={e => (e.target as HTMLElement).style.background = 'var(--active)'}
          onMouseLeave={e => (e.target as HTMLElement).style.background = 'transparent'}
        >＋</span>
      </div>
      <div style={{flex:1, overflowY:'auto', padding:'4px 0'}}>
        {activeView === 'knowledge' ? (
          knowledgeFiles.map((f, i) => (
            <div key={i}
              onClick={() => openTab(`file-${i}`, `${f.icon} ${f.name}`)}
              style={{
                padding:'6px 14px', display:'flex', alignItems:'center', gap:8, cursor:'pointer',
                fontSize:'.8rem', color:'var(--muted)', borderLeft:'2px solid transparent',
                transition:'all .1s'
              }}
              onMouseEnter={e => { e.currentTarget.style.background='var(--active)'; e.currentTarget.style.color='var(--ink)' }}
              onMouseLeave={e => { e.currentTarget.style.background='transparent'; e.currentTarget.style.color='var(--muted)' }}
            >
              <span style={{fontSize:'.9rem',width:16,textAlign:'center'}}>{f.icon}</span>
              {f.name}
            </div>
          ))
        ) : (
          agents.map(a => (
            <div key={a.id}
              onClick={() => { if(a.subscribed){ setActiveAgent(a.id); openTab(a.id, `${a.icon} ${a.name}`) } }}
              style={{
                display:'flex', alignItems:'center', gap:12, padding:14, margin:'6px 10px',
                background: activeAgent === a.id ? 'var(--green-bg)' : 'var(--active)',
                borderRadius:10, cursor: a.subscribed ? 'pointer' : 'not-allowed',
                border:'1px solid transparent', opacity: a.subscribed ? 1 : 0.5,
                transition:'all .15s'
              }}
              onMouseEnter={e => { if(a.subscribed) e.currentTarget.style.borderColor='var(--line)' }}
              onMouseLeave={e => { e.currentTarget.style.borderColor='transparent' }}
            >
              <div style={{
                fontSize:'1.5rem', width:40, height:40, display:'flex', alignItems:'center',
                justifyContent:'center', background: a.subscribed ? 'var(--green-bg)' : 'var(--line)',
                borderRadius:10
              }}>{a.icon}</div>
              <div style={{flex:1}}>
                <div style={{fontSize:'.85rem',fontWeight:600}}>{a.name}</div>
                <div style={{fontSize:'.72rem',color:'var(--muted)'}}>{a.desc}</div>
              </div>
              <span style={{
                fontSize:'.65rem', padding:'2px 8px', borderRadius:10,
                background: a.subscribed ? 'var(--green-bg)' : 'var(--line)',
                color: a.subscribed ? 'var(--green)' : 'var(--dim)'
              }}>{a.subscribed ? '已订阅' : '未订阅'}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}