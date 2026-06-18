import ChatPanel from './ChatPanel'

const WELCOME = <>
  我可以帮你：<br/>
  • 输入关键词 → 搜索潜在客户<br/>
  • 分析客户画像 → 匹配你的产品线<br/>
  • 自动写开发信 → 一键发送<br/><br/>
  试试输入产品关键词 👇
</>

function simulateProspect(msg: string): React.ReactNode {
  const isDiesel = msg.toLowerCase().includes('diesel') || msg.includes('柴油')
  const location = msg.includes('Dubai') || msg.includes('迪拜') ? '迪拜' : msg.includes('Saudi') || msg.includes('沙特') ? '利雅得' : '中东'

  const prospects = isDiesel ? [
    { name:'Al-Futtaim Auto', loc:'迪拜', amount:'$2.8M', match:92, email:'procurement@alfuttaim.ae' },
    { name:'Diesel Tech ME', loc:'利雅得', amount:'$1.5M', match:85, email:'info@dieseltech-me.com' },
    { name:'Arabian Auto Parts', loc:'多哈', amount:'$900K', match:78, email:'sales@arabianautoparts.qa' },
  ] : [
    { name:'Gulf Parts Trading', loc:location, amount:'$1.2M', match:88, email:'sales@gulfparts.com' },
    { name:'MENA Diesel Supply', loc:'阿布扎比', amount:'$800K', match:75, email:'info@menadiesel.ae' },
    { name:'Desert Fleet Parts', loc:'科威特城', amount:'$600K', match:70, email:'orders@desertfleet.kw' },
  ]

  return <>
    搜索完成。找到 <strong>{prospects.length} 家</strong> 潜在客户：<br/><br/>
    {prospects.map((p, i) => (
      <div key={i} style={{background:'var(--panel)',border:'1px solid var(--line)',borderRadius:8,padding:12,marginBottom:8}}>
        <strong>🏭 {p.name}</strong> · {p.loc}<br/>
        <span style={{color:'var(--muted)',fontSize:'.75rem'}}>年采购额 ~{p.amount} · 匹配度 {p.match}%</span><br/>
        <span style={{fontSize:'.78rem'}}>📧 {p.email}</span>
      </div>
    ))}
    要为以上客户生成开发信吗？ ✉️
  </>
}

export default function ProspectAgent() {
  return (
    <ChatPanel
      agentIcon="🎯"
      agentName="客户开发员"
      welcomeMessage={WELCOME}
      onSend={async (msg) => simulateProspect(msg)}
      placeholder="输入关键词，如：diesel engine parts Dubai…"
    />
  )
}