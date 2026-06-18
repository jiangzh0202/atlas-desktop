import { useState, useRef, useEffect, ReactNode } from 'react'

interface Message {
  role: 'agent' | 'user'
  content: ReactNode
  label?: string
}

interface Props {
  agentIcon: string
  agentName: string
  welcomeMessage: ReactNode
  onSend: (msg: string) => Promise<ReactNode>
  placeholder?: string
}

export default function ChatPanel({ agentIcon, agentName, welcomeMessage, onSend, placeholder }: Props) {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'agent', content: welcomeMessage, label: `${agentIcon} ${agentName}` }
  ])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const handleSend = async () => {
    const msg = input.trim()
    if (!msg || sending) return
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setInput('')
    setSending(true)
    try {
      const response = await onSend(msg)
      setMessages(prev => [...prev, { role: 'agent', content: response, label: `${agentIcon} ${agentName}` }])
    } catch {
      setMessages(prev => [...prev, { role: 'agent', content: '⚠️ 请求失败，请检查网络连接', label: `${agentIcon} ${agentName}` }])
    }
    setSending(false)
  }

  return (
    <div style={{flex:1,display:'flex',flexDirection:'column',overflow:'hidden',background:'var(--bg)'}}>
      <div style={{flex:1,overflowY:'auto',padding:16,display:'flex',flexDirection:'column',gap:12}}>
        {messages.map((m, i) => (
          <div key={i}
            style={{
              maxWidth:'80%', padding:'10px 14px', borderRadius:12, fontSize:'.85rem', lineHeight:1.6,
              alignSelf: m.role === 'agent' ? 'flex-start' : 'flex-end',
              background: m.role === 'agent' ? 'var(--active)' : 'var(--green-bg)',
              border: m.role === 'user' ? '1px solid rgba(126,207,94,.2)' : 'none',
              borderBottomLeftRadius: m.role === 'agent' ? 4 : undefined,
              borderBottomRightRadius: m.role === 'user' ? 4 : undefined,
              animation:'fadeIn .2s ease'
            }}
          >
            {m.label && <div style={{fontSize:'.7rem',color:'var(--green)',fontWeight:600,marginBottom:4}}>{m.label}</div>}
            {m.content}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div style={{padding:'12px 16px',borderTop:'1px solid var(--line)',display:'flex',gap:8,alignItems:'center'}}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();handleSend()} }}
          placeholder={placeholder || '输入消息…'}
          rows={1}
          disabled={sending}
          style={{
            flex:1, background:'var(--active)', border:'1px solid var(--line)', borderRadius:8,
            padding:'10px 14px', color:'var(--ink)', fontFamily:'inherit', fontSize:'.85rem',
            resize:'none', outline:'none', minHeight:40, maxHeight:120
          }}
        />
        <button
          onClick={handleSend}
          disabled={sending || !input.trim()}
          style={{
            width:36, height:36, borderRadius:'50%', background:'var(--green)', color:'var(--bg)',
            border:'none', cursor:'pointer', fontSize:'1rem', display:'flex', alignItems:'center',
            justifyContent:'center', transition:'all .15s', flexShrink:0,
            opacity: sending || !input.trim() ? 0.3 : 1
          }}
        >↑</button>
      </div>
    </div>
  )
}