import { useAppStore } from '../stores/appStore'

export default function StatusBar() {
  const { activeAgent, apiEndpoint, usageStats } = useAppStore()
  const agentLabel = activeAgent === 'quote' ? '报价员' : activeAgent === 'prospect' ? '客户开发员' : ''

  return (
    <div style={{
      height:24, background:'var(--sidebar)', borderTop:'1px solid var(--line)',
      display:'flex', alignItems:'center', padding:'0 12px', fontSize:'.7rem', color:'var(--dim)',
      gap:14, flexShrink:0
    }}>
      <span style={{width:7,height:7,borderRadius:'50%',background:'var(--green)',display:'inline-block'}} />
      <span>{apiEndpoint.replace('https://', '')}</span>
      <span>AI 就绪</span>
      <span style={{marginLeft:'auto'}}>
        {agentLabel && `${agentLabel} · `}
        已学习 338 条历史 · API {usageStats.apiCalls}次
      </span>
    </div>
  )
}