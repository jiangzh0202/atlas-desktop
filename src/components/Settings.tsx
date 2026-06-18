import { useAppStore } from '../stores/appStore'

const sections = [
  { id:'general', icon:'⚙️', label:'常规' },
  { id:'storage', icon:'💾', label:'数据存储' },
  { id:'preview', icon:'👁', label:'报价预览' },
  { id:'theme', icon:'🎨', label:'主题' },
  { id:'model', icon:'🧠', label:'模型设置' },
  { id:'market', icon:'🛒', label:'数字员工市场' },
  { id:'mcp', icon:'🔌', label:'MCP 连接器' },
  { id:'plugins', icon:'🧩', label:'插件管理' },
  { id:'index', icon:'📇', label:'索引库' },
  { id:'usage', icon:'📊', label:'用量统计' },
] as const

export default function Settings() {
  const { settingsSection, setSettingsSection, toggleSettings, updateSetting,
    language, zoom, httpProxy, notifications, dataPath, theme, accentColor, model, usageStats } = useAppStore()

  const renderContent = () => {
    switch (settingsSection) {
      case 'general':
        return (
          <div style={{display:'flex',flexDirection:'column',gap:16}}>
            <h3 style={{fontSize:'.95rem'}}>常规设置</h3>
            <div>
              <div style={{fontSize:'.78rem',color:'var(--muted)',marginBottom:6}}>语言</div>
              <select value={language} onChange={e => updateSetting('language', e.target.value)}
                style={{background:'var(--active)',border:'1px solid var(--line)',borderRadius:6,padding:'8px 12px',color:'var(--ink)',fontSize:'.85rem',width:'100%'}}>
                <option value="zh">简体中文</option><option value="en">English</option>
              </select>
            </div>
            <div>
              <div style={{fontSize:'.78rem',color:'var(--muted)',marginBottom:6}}>缩放 ({zoom}%)</div>
              <input type="range" min={80} max={150} value={zoom} onChange={e => updateSetting('zoom', parseInt(e.target.value))}
                style={{width:'100%',accentColor:'var(--green)'}} />
            </div>
            <div>
              <div style={{fontSize:'.78rem',color:'var(--muted)',marginBottom:6}}>HTTP 代理</div>
              <input value={httpProxy} onChange={e => updateSetting('httpProxy', e.target.value)} placeholder="不使用代理（直连）"
                style={{width:'100%',background:'var(--active)',border:'1px solid var(--line)',borderRadius:6,padding:'8px 12px',color:'var(--ink)',fontSize:'.85rem'}} />
            </div>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
              <span style={{fontSize:'.85rem'}}>系统通知</span>
              <button onClick={() => updateSetting('notifications', !notifications)}
                style={{padding:'6px 16px',borderRadius:6,border:'1px solid var(--line)',background:notifications ? 'var(--green-bg)' : 'var(--active)',color:notifications ? 'var(--green)' : 'var(--muted)',cursor:'pointer',fontSize:'.8rem',fontWeight:600}}>
                {notifications ? '已开启' : '已关闭'}
              </button>
            </div>
          </div>
        )
      case 'storage':
        return (
          <div style={{display:'flex',flexDirection:'column',gap:16}}>
            <h3 style={{fontSize:'.95rem'}}>数据存储路径</h3>
            <input value={dataPath} readOnly placeholder="~/atlas-data"
              style={{width:'100%',background:'var(--active)',border:'1px solid var(--line)',borderRadius:6,padding:'8px 12px',color:'var(--muted)',fontSize:'.85rem'}} />
            <button style={{padding:'8px 16px',borderRadius:6,background:'var(--green)',color:'var(--bg)',border:'none',cursor:'pointer',fontSize:'.85rem',fontWeight:600,alignSelf:'flex-start'}}>选择文件夹</button>
            <p style={{fontSize:'.75rem',color:'var(--dim)'}}>知识库文件、历史报价、pricing.md 均存储在此目录</p>
          </div>
        )
      case 'preview':
        return (
          <div style={{display:'flex',flexDirection:'column',gap:16}}>
            <h3 style={{fontSize:'.95rem'}}>报价预览格式</h3>
            <p style={{fontSize:'.82rem',color:'var(--muted)'}}>报价单导出时的默认格式和字段</p>
            <div style={{display:'flex',flexDirection:'column',gap:8}}>
              {['OE号', '品名', '数量', '单价', '小计', '总价', '品牌', '适用车型', '备注'].map(f => (
                <label key={f} style={{display:'flex',alignItems:'center',gap:8,fontSize:'.82rem',cursor:'pointer'}}>
                  <input type="checkbox" defaultChecked style={{accentColor:'var(--green)'}} /> {f}
                </label>
              ))}
            </div>
          </div>
        )
      case 'theme':
        return (
          <div style={{display:'flex',flexDirection:'column',gap:16}}>
            <h3 style={{fontSize:'.95rem'}}>主题</h3>
            <div style={{display:'flex',gap:10}}>
              {['dark', 'light'].map(t => (
                <button key={t} onClick={() => updateSetting('theme', t)}
                  style={{flex:1,padding:'12px',borderRadius:8,border:`2px solid ${theme===t?'var(--green)':'var(--line)'}`,background:theme===t?'var(--green-bg)':'var(--active)',color:'var(--ink)',cursor:'pointer',fontSize:'.85rem',fontWeight:600}}>
                  {t === 'dark' ? '🌙 深色' : '☀️ 浅色'}
                </button>
              ))}
            </div>
            <div>
              <div style={{fontSize:'.78rem',color:'var(--muted)',marginBottom:6}}>强调色</div>
              <div style={{display:'flex',gap:8}}>
                {['#7ecf5e', '#8ab4f8', '#fdd663', '#f28b82', '#c58af9'].map(c => (
                  <div key={c} onClick={() => updateSetting('accentColor', c)}
                    style={{width:32,height:32,borderRadius:'50%',background:c,cursor:'pointer',border:accentColor===c?'2px solid var(--ink)':'2px solid transparent',transition:'all .15s'}} />
                ))}
              </div>
            </div>
          </div>
        )
      case 'model':
        return (
          <div style={{display:'flex',flexDirection:'column',gap:16}}>
            <h3 style={{fontSize:'.95rem'}}>模型设置</h3>
            <div>
              <div style={{fontSize:'.78rem',color:'var(--muted)',marginBottom:6}}>AI 模型</div>
              <select value={model} onChange={e => updateSetting('model', e.target.value)}
                style={{background:'var(--active)',border:'1px solid var(--line)',borderRadius:6,padding:'8px 12px',color:'var(--ink)',fontSize:'.85rem',width:'100%'}}>
                <option value="deepseek-chat">DeepSeek V3</option>
                <option value="glm-4">GLM-4 (智谱)</option>
                <option value="gpt-4o">GPT-4o</option>
                <option value="claude-sonnet-4">Claude Sonnet 4</option>
              </select>
            </div>
            <p style={{fontSize:'.75rem',color:'var(--dim)'}}>模型由 atlas.traceclaw.cn 代理，根据订阅套餐自动选择可用模型</p>
          </div>
        )
      case 'market':
        return (
          <div style={{display:'flex',flexDirection:'column',gap:16}}>
            <h3 style={{fontSize:'.95rem'}}>数字员工市场</h3>
            <p style={{fontSize:'.82rem',color:'var(--muted)'}}>订阅更多数字员工，扩展你的 AI 团队</p>
            {[
              { id:'quote', icon:'💎', name:'报价员', price:'已订阅', desc:'从历史数据学习定价规律' },
              { id:'prospect', icon:'🎯', name:'客户开发员', price:'已订阅', desc:'搜客户→画像→开发信' },
              { id:'image', icon:'🔍', name:'图片识零件员', price:'¥98/月', desc:'拍照识OE号，自动匹配' },
              { id:'stock', icon:'📦', name:'库存管理员', price:'¥198/月', desc:'需求预测+呆滞预警' },
              { id:'customs', icon:'🛃', name:'清关助理', price:'¥298/月', desc:'HS编码+报关单生成' },
            ].map(a => (
              <div key={a.id} style={{display:'flex',alignItems:'center',gap:12,padding:14,background:'var(--active)',borderRadius:10}}>
                <div style={{fontSize:'1.5rem'}}>{a.icon}</div>
                <div style={{flex:1}}>
                  <div style={{fontSize:'.85rem',fontWeight:600}}>{a.name}</div>
                  <div style={{fontSize:'.72rem',color:'var(--muted)'}}>{a.desc}</div>
                </div>
                <button style={{
                  padding:'6px 14px',borderRadius:6,fontSize:'.78rem',fontWeight:600,cursor:'pointer',border:'none',
                  background: a.price === '已订阅' ? 'var(--green-bg)' : 'var(--green)',
                  color: a.price === '已订阅' ? 'var(--green)' : 'var(--bg)'
                }}>{a.price}</button>
              </div>
            ))}
          </div>
        )
      case 'mcp':
        return (
          <div style={{display:'flex',flexDirection:'column',gap:16}}>
            <h3 style={{fontSize:'.95rem'}}>MCP 连接器</h3>
            <p style={{fontSize:'.82rem',color:'var(--muted)'}}>MCP (Model Context Protocol) 让数字员工连接你的 ERP、CRM、数据库等外部系统</p>
            <div style={{padding:40,textAlign:'center',color:'var(--dim)'}}>
              <div style={{fontSize:'2rem',marginBottom:8}}>🔌</div>
              <div>即将上线</div>
              <div style={{fontSize:'.78rem',marginTop:4}}>支持 JSON-RPC 和 Streamable HTTP 连接</div>
            </div>
          </div>
        )
      case 'plugins':
        return (
          <div style={{display:'flex',flexDirection:'column',gap:16}}>
            <h3 style={{fontSize:'.95rem'}}>插件管理</h3>
            <div style={{padding:40,textAlign:'center',color:'var(--dim)'}}>
              <div style={{fontSize:'2rem',marginBottom:8}}>🧩</div>
              <div>即将上线</div>
              <div style={{fontSize:'.78rem',marginTop:4}}>支持自定义插件扩展数字员工能力</div>
            </div>
          </div>
        )
      case 'index':
        return (
          <div style={{display:'flex',flexDirection:'column',gap:16}}>
            <h3 style={{fontSize:'.95rem'}}>索引库</h3>
            <p style={{fontSize:'.82rem',color:'var(--muted)'}}>重建知识库索引以更新 AI 学习数据。索引后新数据将出现在数字员工的上下文中。</p>
            <div style={{background:'var(--active)',padding:14,borderRadius:8}}>
              <div style={{display:'flex',justifyContent:'space-between',marginBottom:8}}>
                <span style={{fontSize:'.82rem'}}>历史报价索引</span>
                <span style={{fontSize:'.75rem',color:'var(--green)'}}>338 条</span>
              </div>
              <div style={{display:'flex',justifyContent:'space-between',marginBottom:8}}>
                <span style={{fontSize:'.82rem'}}>客户数据索引</span>
                <span style={{fontSize:'.75rem',color:'var(--green)'}}>156 条</span>
              </div>
              <div style={{display:'flex',justifyContent:'space-between',marginBottom:8}}>
                <span style={{fontSize:'.82rem'}}>供应商价格索引</span>
                <span style={{fontSize:'.75rem',color:'var(--green)'}}>42 条</span>
              </div>
              <div style={{display:'flex',justifyContent:'space-between'}}>
                <span style={{fontSize:'.82rem'}}>pricing.md</span>
                <span style={{fontSize:'.75rem',color:'var(--green)'}}>已加载</span>
              </div>
            </div>
            <button style={{padding:'8px 16px',borderRadius:6,background:'var(--amber-bg)',color:'var(--amber)',border:'1px solid rgba(253,214,99,.2)',cursor:'pointer',fontSize:'.85rem',fontWeight:600,alignSelf:'flex-start'}}>
              🔄 重建全部索引
            </button>
          </div>
        )
      case 'usage':
        return (
          <div style={{display:'flex',flexDirection:'column',gap:16}}>
            <h3 style={{fontSize:'.95rem'}}>用量统计</h3>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
              {[
                { label:'API 调用', value:usageStats.apiCalls.toLocaleString(), unit:'次' },
                { label:'Token 消耗', value:usageStats.tokens.toLocaleString(), unit:'tokens' },
                { label:'历史报价', value:'338', unit:'条' },
                { label:'生成报价', value:'47', unit:'次' },
              ].map(s => (
                <div key={s.label} style={{background:'var(--active)',padding:14,borderRadius:8}}>
                  <div style={{fontSize:'.72rem',color:'var(--muted)',marginBottom:4}}>{s.label}</div>
                  <div style={{fontSize:'1.2rem',fontWeight:700}}>{s.value} <span style={{fontSize:'.75rem',color:'var(--dim)',fontWeight:400}}>{s.unit}</span></div>
                </div>
              ))}
            </div>
            <p style={{fontSize:'.75rem',color:'var(--dim)'}}>详细用量请前往 atlas.traceclaw.cn 查看</p>
          </div>
        )
      default: return null
    }
  }

  return (
    <div onClick={toggleSettings} style={{position:'fixed',inset:0,background:'rgba(0,0,0,.6)',zIndex:100,display:'flex',alignItems:'center',justifyContent:'center'}}>
      <div onClick={e => e.stopPropagation()} style={{width:760,height:540,background:'var(--panel)',border:'1px solid var(--line)',borderRadius:12,boxShadow:'0 16px 48px rgba(0,0,0,.5)',display:'flex',overflow:'hidden'}}>
        {/* Settings sidebar */}
        <div style={{width:160,background:'var(--sidebar)',borderRight:'1px solid var(--line)',padding:'8px 0',overflowY:'auto',flexShrink:0}}>
          <div style={{padding:'10px 14px',fontSize:'.75rem',fontWeight:600,color:'var(--dim)',textTransform:'uppercase',letterSpacing:'.5px'}}>设置</div>
          {sections.map(s => (
            <div key={s.id}
              onClick={() => setSettingsSection(s.id)}
              style={{
                padding:'8px 14px', display:'flex', alignItems:'center', gap:8, cursor:'pointer',
                fontSize:'.82rem', borderLeft:'2px solid transparent',
                color: settingsSection === s.id ? 'var(--ink)' : 'var(--muted)',
                background: settingsSection === s.id ? 'var(--active)' : 'transparent',
                borderLeftColor: settingsSection === s.id ? 'var(--green)' : 'transparent',
                transition:'all .1s'
              }}
              onMouseEnter={e => { if(settingsSection!==s.id){ e.currentTarget.style.background='var(--active)'; e.currentTarget.style.color='var(--ink)' } }}
              onMouseLeave={e => { if(settingsSection!==s.id){ e.currentTarget.style.background='transparent'; e.currentTarget.style.color='var(--muted)' } }}
            >
              <span style={{fontSize:'.9rem'}}>{s.icon}</span> {s.label}
            </div>
          ))}
        </div>
        {/* Settings content */}
        <div style={{flex:1,padding:24,overflowY:'auto'}}>
          {renderContent()}
        </div>
      </div>
    </div>
  )
}