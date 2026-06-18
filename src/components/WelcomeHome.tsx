import { useAppStore } from '../stores/appStore'

export default function WelcomeHome() {
  const { openTab, setActiveAgent } = useAppStore()

  const startAgent = (id: string, label: string) => {
    setActiveAgent(id)
    openTab(id, label)
  }

  return (
    <div style={{flex:1,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',gap:16,padding:40,textAlign:'center'}}>
      <div style={{fontSize:'3rem'}}>🏭</div>
      <h1 style={{fontSize:'1.4rem',fontWeight:700}}>Atlas <span style={{color:'var(--green)'}}>Desktop</span></h1>
      <p style={{color:'var(--muted)',fontSize:'.85rem',maxWidth:400,lineHeight:1.6}}>汽车配件 AI 助手 · 从历史数据中学习你的定价逻辑</p>
      <div style={{display:'inline-flex',alignItems:'center',gap:6,padding:'4px 10px',background:'var(--active)',borderRadius:6,fontSize:'.78rem',color:'var(--muted)',marginTop:8}}>
        <kbd style={{fontFamily:'monospace',fontSize:'.75rem',padding:'1px 6px',background:'var(--bg)',borderRadius:4,border:'1px solid var(--line)',color:'var(--ink)'}}>Ctrl</kbd>
        + <kbd style={{fontFamily:'monospace',fontSize:'.75rem',padding:'1px 6px',background:'var(--bg)',borderRadius:4,border:'1px solid var(--line)',color:'var(--ink)'}}>K</kbd>
        打开命令面板
      </div>
      <div style={{display:'flex',gap:10,marginTop:10}}>
        {[
          { id: 'quote', icon: '💎', name: '报价员', desc: '拖入询盘，AI 3秒出价' },
          { id: 'prospect', icon: '🎯', name: '客户开发员', desc: '找新客户 + 写开发信' },
        ].map(a => (
          <button key={a.id}
            onClick={() => startAgent(a.id, `${a.icon} ${a.name}`)}
            style={{
              display:'flex',alignItems:'center',gap:12,padding:14,background:'var(--active)',borderRadius:10,
              cursor:'pointer',border:'1px solid transparent',transition:'all .15s'
            }}
            onMouseEnter={e => (e.currentTarget as HTMLElement).style.borderColor='var(--line)'}
            onMouseLeave={e => (e.currentTarget as HTMLElement).style.borderColor='transparent'}
          >
            <div style={{fontSize:'1.5rem',width:40,height:40,display:'flex',alignItems:'center',justifyContent:'center',background:'var(--green-bg)',borderRadius:10}}>{a.icon}</div>
            <div style={{textAlign:'left'}}>
              <div style={{fontSize:'.85rem',fontWeight:600}}>{a.name}</div>
              <div style={{fontSize:'.72rem',color:'var(--muted)'}}>{a.desc}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}