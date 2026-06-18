import { useState, useEffect, useRef } from 'react'
import { useAppStore } from '../stores/appStore'

const commands = [
  { id:'quote', icon:'💎', label:'报价员', desc:'粘贴询盘，AI 3秒出报价', shortcut:'Ctrl+1' },
  { id:'prospect', icon:'🎯', label:'客户开发员', desc:'搜索潜在客户，自动写开发信', shortcut:'Ctrl+2' },
  { id:'knowledge', icon:'📁', label:'导入知识库', desc:'拖入 Excel/CSV/PDF 文件' },
  { id:'settings', icon:'⚙️', label:'设置', desc:'订阅状态、API 端点、模型选择' },
  { id:'pricing', icon:'📝', label:'查看 pricing.md', desc:'打开当前报价策略文档' },
]

export default function CommandPalette() {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const { togglePalette, openTab, setActiveAgent, toggleSettings } = useAppStore()

  useEffect(() => { inputRef.current?.focus() }, [])

  const filtered = commands.filter(c =>
    c.label.includes(query) || c.desc.includes(query) || !query
  )

  const execute = (cmd: typeof commands[0]) => {
    togglePalette()
    if (cmd.id === 'quote') { setActiveAgent('quote'); openTab('quote', '💎 报价员') }
    else if (cmd.id === 'prospect') { setActiveAgent('prospect'); openTab('prospect', '🎯 客户开发员') }
    else if (cmd.id === 'settings') { toggleSettings() }
    else if (cmd.id === 'pricing') { openTab('pricing-md', '📝 pricing.md') }
    else if (cmd.id === 'knowledge') { useAppStore.getState().setActiveView('knowledge') }
  }

  return (
    <div onClick={togglePalette} style={{position:'fixed',inset:0,background:'rgba(0,0,0,.6)',zIndex:100,display:'flex',alignItems:'flex-start',justifyContent:'center',paddingTop:'15vh'}}>
      <div onClick={e => e.stopPropagation()} style={{width:560,maxHeight:400,background:'var(--panel)',border:'1px solid var(--line)',borderRadius:12,boxShadow:'0 16px 48px rgba(0,0,0,.5)',display:'flex',flexDirection:'column',overflow:'hidden'}}>
        <input
          ref={inputRef}
          value={query}
          onChange={e => { setQuery(e.target.value); setSelected(0) }}
          onKeyDown={e => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, filtered.length - 1)) }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)) }
            else if (e.key === 'Enter' && filtered[selected]) { execute(filtered[selected]) }
          }}
          placeholder="搜索数字员工或命令…"
          style={{background:'transparent',border:'none',borderBottom:'1px solid var(--line)',padding:'14px 16px',color:'var(--ink)',fontSize:'.9rem',outline:'none',fontFamily:'inherit'}}
        />
        <div style={{flex:1,overflowY:'auto',padding:4}}>
          {filtered.map((cmd, i) => (
            <div key={cmd.id}
              onClick={() => execute(cmd)}
              style={{
                padding:'8px 14px', display:'flex', alignItems:'center', gap:10, cursor:'pointer',
                borderRadius:6, fontSize:'.82rem', background: i === selected ? 'var(--active)' : 'transparent',
                transition:'all .1s'
              }}
              onMouseEnter={() => setSelected(i)}
            >
              <span style={{fontSize:'1rem',width:22,textAlign:'center'}}>{cmd.icon}</span>
              <div style={{flex:1}}>
                <div>{cmd.label}</div>
                <div style={{fontSize:'.72rem',color:'var(--muted)'}}>{cmd.desc}</div>
              </div>
              {cmd.shortcut && <span style={{fontSize:'.7rem',color:'var(--dim)'}}>{cmd.shortcut}</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}