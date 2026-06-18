import ChatPanel from './ChatPanel'

const WELCOME = <>
  <strong>📊 已学习 338 条历史报价</strong><br/><br/>
  我发现的规律：<br/>
  • 福田康明斯喷油器 均价 ¥3,200，波动 ±8%<br/>
  • 七星客户加价系数 1.15-1.25<br/>
  • 中东地区运费加成 ¥200-400/件<br/>
  • 50件以上批量折扣 5-8%<br/><br/>
  直接粘贴询盘或输入配件名 👇
</>

function simulateQuote(msg: string): React.ReactNode {
  const hasFoton = msg.includes('福田') || msg.includes('康明斯')
  const hasDongfeng = msg.includes('东风')
  const qtyMatch = msg.match(/(\d+)\s*件/)
  const qty = qtyMatch ? parseInt(qtyMatch[1]) : 1
  const isMiddleEast = msg.includes('迪拜') || msg.includes('中东')
  const partName = hasFoton ? '福田康明斯喷油器 (OE: 5264231)' : hasDongfeng ? '东风康明斯油泵 (OE: 3975818)' : '康明斯配件'
  const basePrice = hasFoton ? 3200 : hasDongfeng ? 4800 : 2500
  const freight = isMiddleEast ? 350 : 150
  const discount = qty >= 100 ? 0.90 : qty >= 50 ? 0.94 : 1.0
  const unitPrice = Math.round((basePrice + freight) * discount)
  const total = unitPrice * qty

  return <>
    <strong>分析完成。</strong> 基于 338 条历史报价记录：<br/><br/>
    <div style={{background:'var(--panel)',border:'1px solid var(--line)',borderRadius:8,padding:12,marginTop:8,fontSize:'.8rem'}}>
      <table style={{width:'100%',borderCollapse:'collapse'}}>
        <tr><td style={{color:'var(--dim)',padding:'4px 8px'}}>配件</td><td style={{padding:'4px 8px'}}>{partName}</td></tr>
        <tr><td style={{color:'var(--dim)',padding:'4px 8px'}}>数量</td><td style={{padding:'4px 8px'}}>{qty} 件</td></tr>
        {isMiddleEast && <tr><td style={{color:'var(--dim)',padding:'4px 8px'}}>地区</td><td style={{padding:'4px 8px'}}>中东（运费+¥{freight}/件）</td></tr>}
        <tr><td style={{color:'var(--dim)',padding:'4px 8px'}}>历史均价</td><td style={{padding:'4px 8px'}}>¥{basePrice.toLocaleString()} · 毛利率 22%</td></tr>
        <tr><td style={{color:'var(--dim)',padding:'4px 8px'}}>建议单价</td><td style={{color:'var(--green)',fontWeight:700,padding:'4px 8px'}}>¥{unitPrice.toLocaleString()}</td></tr>
        {discount < 1 && <tr><td style={{color:'var(--dim)',padding:'4px 8px'}}>批量折扣</td><td style={{padding:'4px 8px'}}>{qty}件 → 减 {Math.round((1-discount)*100)}% → ¥{unitPrice.toLocaleString()}/件</td></tr>}
        <tr style={{borderTop:'1px solid var(--line)'}}><td style={{color:'var(--dim)',padding:'4px 8px'}}>总报价</td><td style={{color:'var(--green)',fontWeight:700,fontSize:'.9rem',padding:'4px 8px'}}>¥{total.toLocaleString()}</td></tr>
      </table>
    </div>
    <br/>📥 导出 Excel？ ✅ 确认报价？
  </>
}

export default function QuoteAgent() {
  return (
    <ChatPanel
      agentIcon="💎"
      agentName="报价员"
      welcomeMessage={WELCOME}
      onSend={async (msg) => simulateQuote(msg)}
      placeholder="输入询盘，如：福田康明斯喷油器 50件 发迪拜…"
    />
  )
}