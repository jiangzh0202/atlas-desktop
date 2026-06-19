/**
 * 擎天 Atlas Portal — Node.js HTTP Server :3093
 * 纯标准库，零依赖。
 * 注册/登录/JWT/套餐/充值(嘟噜支付)/发票/客户端授权
 * 报价引擎请求代理到 Flask :3092
 */
const http = require("http");
const https = require("https");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const url = require("url");

const PORT = 3093;
const FLASK_PORT = 3092;
const JWT_SECRET = "atlas_jwt_secret_2026";
const DULUPAY_PID = "1807";
const DULUPAY_KEY = "7IyAAGEA0yiIba9F9FdLa60GgdFaeWgi";
const DULUPAY_API = "https://dulupay.com/api.php?act=order";
const DULUPAY_NOTIFY = "https://atlas.traceclaw.cn/api/pay-notify";
const DULUPAY_RETURN = "https://atlas.traceclaw.cn/dashboard";
const DATA_DIR = path.join(__dirname, "..", "data");

const STATIC = path.join(__dirname, "public");

// ─── Store ───
const store = require("./store");
store.loadState();

// ─── MIME ───
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css",
  ".js": "application/javascript",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon"
};

// ─── JWT ───
function base64url(str) {
  return Buffer.from(str).toString("base64url");
}
function signJWT(payload) {
  const header = base64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = base64url(JSON.stringify(payload));
  const h = crypto.createHmac("sha256", JWT_SECRET);
  h.update(header + "." + body);
  return header + "." + body + "." + h.digest("base64url");
}
function verifyJWT(token) {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(Buffer.from(parts[1], "base64url").toString());
    const h = crypto.createHmac("sha256", JWT_SECRET);
    h.update(parts[0] + "." + parts[1]);
    if (h.digest("base64url") !== parts[2]) return null;
    return payload;
  } catch (e) { return null; }
}

// ─── Helpers ───
function sendJSON(res, code, data) {
  res.writeHead(code, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS"
  });
  res.end(JSON.stringify(data));
}

function readBody(req) {
  return new Promise((resolve) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      try { resolve(JSON.parse(body)); }
      catch { resolve({}); }
    });
  });
}

function getAuth(req) {
  const auth = req.headers["authorization"] || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!token) return null;
  const payload = verifyJWT(token);
  if (!payload) return null;
  return store.getUser(payload.uid) || null;
}

// ─── Static Files ───
function serveStatic(req, res, filePath) {
  const ext = path.extname(filePath);
  const mime = MIME[ext] || "application/octet-stream";
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end("Not Found");
    } else {
      res.writeHead(200, { "Content-Type": mime });
      res.end(data);
    }
  });
}

// ─── Proxy to Flask ───
function proxyToFlask(req, res) {
  const opts = {
    hostname: "127.0.0.1",
    port: FLASK_PORT,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: `localhost:${FLASK_PORT}` }
  };
  const proxy = http.request(opts, (presp) => {
    res.writeHead(presp.statusCode, presp.headers);
    presp.pipe(res);
  });
  proxy.on("error", () => sendJSON(res, 502, { ok: false, error: "引擎服务不可用" }));
  req.pipe(proxy);
}

// ─── Dulupay Sign ───
function dulupaySign(params) {
  const filtered = {};
  for (const [k, v] of Object.entries(params)) {
    if (k === "sign" || k === "sign_type") continue;
    if (String(v ?? "")) filtered[k] = String(v ?? "");
  }
  const str = Object.keys(filtered).sort().map(k => `${k}=${filtered[k]}`).join("&") + DULUPAY_KEY;
  return crypto.createHash("md5").update(str).digest("hex");
}

// ─── Feishu Connection Test ───
async function feishuTest(appId, appSecret) {
  return new Promise((resolve) => {
    const body = JSON.stringify({ app_id: appId, app_secret: appSecret });
    const req = https.request({
      hostname: "open.feishu.cn",
      path: "/open-apis/auth/v3/tenant_access_token/internal",
      method: "POST",
      headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) },
      timeout: 10000
    }, (resp) => {
      let data = "";
      resp.on("data", c => data += c);
      resp.on("end", () => {
        try {
          const j = JSON.parse(data);
          if (j.code === 0 && j.tenant_access_token) {
            resolve({ ok: true, msg: "飞书连接成功 ✅ tenant_access_token 已获取" });
          } else {
            const errMap = { 99991663: "App ID 不存在", 99991664: "App Secret 错误", 99991665: "应用未启用" };
            resolve({ ok: false, error: errMap[j.code] || (j.msg || "飞书连接失败") + " (code: " + (j.code || "?") + ")" });
          }
        } catch(e) { resolve({ ok: false, error: "飞书响应异常: " + e.message }); }
      });
    });
    req.on("error", e => resolve({ ok: false, error: "连接飞书服务器失败: " + e.message }));
    req.on("timeout", () => { req.destroy(); resolve({ ok: false, error: "连接飞书超时" }); });
    req.write(body);
    req.end();
  });
}

// ─── Get Feishu tenant_access_token (cached) ───
let feishuTokenCache = { token: null, expires: 0 };
async function getFeishuToken() {
  const now = Date.now();
  if (feishuTokenCache.token && feishuTokenCache.expires > now + 60000) {
    return feishuTokenCache.token;
  }
  try {
    const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "data", "channel_feishu.json"), "utf-8"));
    if (!cfg.app_id || !cfg.app_secret) return null;
    const body = JSON.stringify({ app_id: cfg.app_id, app_secret: cfg.app_secret });
    const result = await new Promise((resolve) => {
      const req = https.request({
        hostname: "open.feishu.cn",
        path: "/open-apis/auth/v3/tenant_access_token/internal",
        method: "POST",
        headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) },
        timeout: 10000
      }, (resp) => {
        let data = "";
        resp.on("data", c => data += c);
        resp.on("end", () => {
          try {
            const j = JSON.parse(data);
            if (j.code === 0) resolve(j.tenant_access_token);
            else resolve(null);
          } catch(e) { resolve(null); }
        });
      });
      req.on("error", () => resolve(null));
      req.on("timeout", () => { req.destroy(); resolve(null); });
      req.write(body);
      req.end();
    });
    if (result) {
      feishuTokenCache = { token: result, expires: now + 3600000 };
      console.log("[飞书] Token 已获取");
    }
    return result;
  } catch(e) {
    console.log("[飞书] 读取配置失败:", e.message);
    return null;
  }
}

// ─── Send Feishu message ───
async function sendFeishuReply(content, messageId, chatId, msgType) {
  const token = await getFeishuToken();
  if (!token) { console.log("[飞书] 无 token，无法回复"); return false; }
  
  return new Promise((resolve) => {
    const replyBody = JSON.stringify({
      msg_type: msgType || "text",
      content: typeof content === "string" ? JSON.stringify({ text: content }) : JSON.stringify(content)
    });
    
    const options = {
      hostname: "open.feishu.cn",
      path: "/open-apis/im/v1/messages/" + encodeURIComponent(messageId) + "/reply",
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token,
        "Content-Length": Buffer.byteLength(replyBody)
      },
      timeout: 15000
    };
    
    const req = https.request(options, (resp) => {
      let data = "";
      resp.on("data", c => data += c);
      resp.on("end", () => {
        try {
          const j = JSON.parse(data);
          if (j.code === 0) {
            console.log("[飞书] 回复成功, msg_id:", j.data?.message_id);
            resolve(true);
          } else {
            console.log("[飞书] 回复失败:", j.code, j.msg);
            resolve(false);
          }
        } catch(e) {
          console.log("[飞书] 回复响应异常:", data.slice(0, 200));
          resolve(false);
        }
      });
    });
    req.on("error", (e) => { console.log("[飞书] 网络错误:", e.message); resolve(false); });
    req.on("timeout", () => { req.destroy(); resolve(false); });
    req.write(replyBody);
    req.end();
  });
}

// ─── DeepSeek AI Chat ───
async function callDeepSeek(userMessage) {
  try {
    const body = JSON.stringify({
      model: "deepseek-v4-pro",
      messages: [
        { role: "system", content: "你是擎天 Atlas 的 AI 助手，帮助汽车零部件行业的客户处理报价、查询配件、管理订单。用简洁专业的中文回复，不超过3句话。自称「擎天小助手」。" },
        { role: "user", content: userMessage }
      ],
      temperature: 0.7,
      max_tokens: 300
    });
    
    const result = await new Promise((resolve) => {
      const req = https.request({
        hostname: "api.deepseek.com",
        path: "/v1/chat/completions",
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer sk-f4aef21293b5472d9f22f86ad289b573",
          "Content-Length": Buffer.byteLength(body)
        },
        timeout: 30000
      }, (resp) => {
        let data = "";
        resp.on("data", c => data += c);
        resp.on("end", () => {
          try {
            const j = JSON.parse(data);
            let replyText = j.choices?.[0]?.message?.content || "";
              // v4-pro reasoning model: if content is empty, use reasoning_content
              if (!replyText && j.choices?.[0]?.message?.reasoning_content) {
                replyText = j.choices[0].message.reasoning_content.slice(-500);
              }
              resolve(replyText || "嗯，收到了。有什么我可以帮您的？");
          } catch(e) { resolve("抱歉，我暂时无法处理，请稍后再试。"); }
        });
      });
      req.on("error", () => resolve("网络异常，请稍后再试。"));
      req.on("timeout", () => { req.destroy(); resolve("回复超时，请重新发送。"); });
      req.write(body);
      req.end();
    });
    return result;
  } catch(e) {
    return "抱歉，出了点问题，请再试一次。";
  }
}

// ─── WeCom Connection Test ───
async function wecomTest(corpId, secret) {
  return new Promise((resolve) => {
    const req = https.request({
      hostname: "qyapi.weixin.qq.com",
      path: "/cgi-bin/gettoken?corpid=" + encodeURIComponent(corpId) + "&corpsecret=" + encodeURIComponent(secret),
      method: "GET",
      timeout: 10000
    }, (resp) => {
      let data = "";
      resp.on("data", c => data += c);
      resp.on("end", () => {
        try {
          const j = JSON.parse(data);
          if (j.errcode === 0 && j.access_token) {
            resolve({ ok: true, msg: "企业微信连接成功 ✅ access_token 已获取" });
          } else {
            const errMap = { 40001: "Secret 无效", 40013: "Corp ID 无效", 40084: "IP 不在白名单", 41001: "缺少 access_token 参数" };
            resolve({ ok: false, error: errMap[j.errcode] || (j.errmsg || "企业微信连接失败") + " (errcode: " + (j.errcode || "?") + ")" });
          }
        } catch(e) { resolve({ ok: false, error: "企业微信响应异常: " + e.message }); }
      });
    });
    req.on("error", e => resolve({ ok: false, error: "连接企业微信服务器失败: " + e.message }));
    req.on("timeout", () => { req.destroy(); resolve({ ok: false, error: "连接企业微信超时" }); });
    req.end();
  });
}

// ─── Server ───
const server = http.createServer(async (req, res) => {
  const parsed = url.parse(req.url, true);
  const pathname = parsed.pathname;

  // CORS preflight
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
      "Access-Control-Allow-Methods": "GET,POST,OPTIONS"
    });
    return res.end();
  }

  // ═══ API Routes ═══

  // Health
  if (pathname === "/api/health") {
    return sendJSON(res, 200, { ok: true, service: "atlas-portal", version: "3.0" });
  }

  // Register
  if (pathname === "/api/register" && req.method === "POST") {
    const body = await readBody(req);
    const { email, password, company, company_type } = body;
    if (!email || !password || !company || !company_type) {
      return sendJSON(res, 400, { ok: false, error: "请填写所有字段" });
    }
    if (password.length < 6) {
      return sendJSON(res, 400, { ok: false, error: "密码至少6位" });
    }
    const types = ["配件生产商", "经销商/贸易商", "修理厂/服务站", "外贸公司"];
    if (!types.includes(company_type)) {
      return sendJSON(res, 400, { ok: false, error: "企业类型无效" });
    }
    const user = store.createUser({ email, password, company, company_type });
    if (user.error) {
      return sendJSON(res, 409, { ok: false, error: user.error });
    }
    const token = signJWT({ uid: user.id, email: user.email, iat: Date.now() });
    return sendJSON(res, 200, { ok: true, user, token, redirect: "/dashboard" });
  }

  // Login
  if (pathname === "/api/login" && req.method === "POST") {
    const body = await readBody(req);
    const { email, password } = body;
    if (!email || !password) {
      return sendJSON(res, 400, { ok: false, error: "请输入邮箱和密码" });
    }
    const user = store.verifyLogin(email, password);
    if (!user) {
      return sendJSON(res, 401, { ok: false, error: "邮箱或密码错误" });
    }
    const token = signJWT({ uid: user.id, email: user.email, iat: Date.now() });
    return sendJSON(res, 200, { ok: true, user, token, redirect: "/dashboard" });
  }

  // Get current user
  if (pathname === "/api/me" && req.method === "GET") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请登录" });
    const { password_hash, channels, ...safe } = user;
    // Add role for atlas.js nav filtering: quoter/purchaser
    safe.role = safe.role || 'quoter';
    safe.role_label = '报价员';
    return sendJSON(res, 200, { ok: true, user: safe, data: safe });
  }

  // Channels config save (store server-side for callback verification)
  if (pathname === "/api/channels/save" && req.method === "POST") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请先登录" });
    const body = await readBody(req);
    const { channel, config } = body || {};
    if (!channel || !config) return sendJSON(res, 400, { ok: false, error: "参数错误" });
    try {
      const cfgPath = path.join(__dirname, "..", "data", "channel_" + channel + ".json");
      const existing = fs.existsSync(cfgPath) ? JSON.parse(fs.readFileSync(cfgPath, "utf-8")) : {};
      Object.assign(existing, config, { updated_at: new Date().toISOString(), updated_by: user.id });
      fs.writeFileSync(cfgPath, JSON.stringify(existing, null, 2));
      // Bind channel to user account
      const appId = config.app_id || config.corp_id || config.smtp_host || "";
      if (appId) {
        const bindResult = store.bindChannel(user.id, channel, appId);
        if (!bindResult.ok) {
          return sendJSON(res, 400, { ok: false, error: bindResult.error });
        }
      }
      return sendJSON(res, 200, { ok: true, msg: channel + " 配置已保存", channels: store.getBoundChannels(user.id) });
    } catch(e) {
      return sendJSON(res, 500, { ok: false, error: "保存失败: " + (e.message || "") });
    }
  }

  // Feishu event callback (URL verification + message receiving)
  if (pathname === "/api/feishu/callback" && req.method === "POST") {
    const body = await readBody(req);
    console.log("[飞书回调]", JSON.stringify(body).slice(0, 500));
    
    // URL verification: Feishu sends {challenge, token, type:"url_verification"}
    if (body && body.type === "url_verification" && body.challenge) {
      // Load verification token from saved config for comparison
      let validToken = false;
      try {
        const cfgPath = path.join(__dirname, "..", "data", "channel_feishu.json");
        if (fs.existsSync(cfgPath)) {
          const cfg = JSON.parse(fs.readFileSync(cfgPath, "utf-8"));
          validToken = (cfg.verification_token === body.token);
        }
      } catch(e) { /* token file not yet configured */ }
      
      if (body.token && !validToken) {
        console.log("[飞书回调] Token 不匹配, 收到:", body.token);
        // Still respond with challenge for now (lenient mode)
      }
      return sendJSON(res, 200, { challenge: body.challenge });
    }
    
    // Event callback: message received etc.
    if (body && body.header && body.header.event_type === "im.message.receive_v1") {
      const event = body.event;
      const msgContent = (() => {
        try { return JSON.parse(event.message.content); } catch(e) { return null; }
      })();
      const text = msgContent?.text || "";
      const senderId = event.sender?.sender_id?.open_id || "unknown";
      const messageId = event.message?.message_id || "";
      const chatId = event.message?.chat_id || "";
      const chatType = event.message?.chat_type || "";
      const appId = body.header.app_id || "";
      
      console.log("[飞书回调] 消息:", text.slice(0, 100), "from:", senderId, "chat:", chatType);
      
      if (messageId && text) {
        // Check channel ownership + quota
        const owner = appId ? store.getUserByChannelAppId(appId) : null;
        console.log('[飞书绑定] app_id:', appId, 'owner:', owner ? owner.email : 'NULL', 'max_channels:', owner?.max_channels, 'channels:', JSON.stringify(owner?.channels || []));
        let replyText = null;
        if (!owner) {
          replyText = "该通道未绑定 Atlas 账号，请先在 Atlas 控制台「通道设置」中保存配置。";
        } else {
          const qr = store.useChannelQuota(owner.id, "feishu");
          if (!qr.ok) {
            replyText = qr.error === "quota_exhausted" 
              ? "本月消息额度已用完，请在 Atlas 控制台升级套餐或等待下月重置。"
              : "服务暂不可用，请稍后再试。";
          }
        }
        
        if (replyText) {
          sendFeishuReply(replyText, messageId, chatId);
        } else {
          // Async AI reply
          callDeepSeek(text).then(replyText => {
            sendFeishuReply(replyText, messageId, chatId);
          });
        }
      }
      return sendJSON(res, 200, { code: 0, msg: "ok" });
    }
    
    return sendJSON(res, 200, { code: 0, msg: "ok" });
  }

  // Channels test (verify Feishu/WeCom/Email config)
  if (pathname === "/api/channels/test" && req.method === "POST") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请先登录" });
    const body = await readBody(req);
    const { channel, config } = body || {};
    if (!channel || !config) return sendJSON(res, 400, { ok: false, error: "参数错误" });

    try {
      if (channel === "feishu") {
        if (!config.app_id || !config.app_secret) return sendJSON(res, 400, { ok: false, error: "请填写 App ID 和 App Secret" });
        const result = await feishuTest(config.app_id, config.app_secret);
        return sendJSON(res, result.ok ? 200 : 400, result);
      } else if (channel === "wecom") {
        if (!config.corp_id || !config.secret) return sendJSON(res, 400, { ok: false, error: "请填写 Corp ID 和 Secret" });
        const result = await wecomTest(config.corp_id, config.secret);
        return sendJSON(res, result.ok ? 200 : 400, result);
      } else if (channel === "email") {
        if (!config.smtp_host) return sendJSON(res, 400, { ok: false, error: "请填写 SMTP 服务器" });
        return sendJSON(res, 200, { ok: true, msg: "SMTP 配置格式正确，邮件通道将在客户端启动后生效" });
      } else {
        return sendJSON(res, 400, { ok: false, error: "不支持的通道类型" });
      }
    } catch(e) {
      return sendJSON(res, 500, { ok: false, error: "通道测试异常: " + (e.message || "网络错误") });
    }
  }

// ─── MCP Helpers ───
function mcpTest(serverUrl, apiKey) {
  return new Promise((resolve) => {
    try {
      const urlObj = new URL(serverUrl);
      const isHttps = urlObj.protocol === "https:";
      const transporter = isHttps ? https : http;
      const body = JSON.stringify({ jsonrpc: "2.0", method: "tools/list", id: 1 });
      const req = transporter.request({
        hostname: urlObj.hostname,
        port: urlObj.port || (isHttps ? 443 : 80),
        path: urlObj.pathname || "/",
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body),
          ...(apiKey ? { "Authorization": "Bearer " + apiKey } : {})
        },
        timeout: 10000
      }, (resp) => {
        let data = "";
        resp.on("data", c => data += c);
        resp.on("end", () => {
          try {
            const j = JSON.parse(data);
            if (j.result && j.result.tools) {
              resolve({ ok: true, tools: j.result.tools.map(t => t.name), count: j.result.tools.length });
            } else if (j.error) {
              resolve({ ok: false, error: j.error.message || "MCP error" });
            } else {
              resolve({ ok: false, error: "响应格式不正确" });
            }
          } catch(e) { resolve({ ok: false, error: "解析失败: " + e.message }); }
        });
      });
      req.on("error", e => resolve({ ok: false, error: "连接失败: " + e.message }));
      req.on("timeout", () => { req.destroy(); resolve({ ok: false, error: "连接超时" }); });
      req.write(body);
      req.end();
    } catch(e) { resolve({ ok: false, error: "URL 格式错误: " + e.message }); }
  });
}

async function mcpCallTool(serverUrl, apiKey, toolName, args) {
  return new Promise((resolve) => {
    try {
      const urlObj = new URL(serverUrl);
      const isHttps = urlObj.protocol === "https:";
      const transporter = isHttps ? https : http;
      const body = JSON.stringify({ jsonrpc: "2.0", method: "tools/call", params: { name: toolName, arguments: args || {} }, id: Date.now() });
      const req = transporter.request({
        hostname: urlObj.hostname,
        port: urlObj.port || (isHttps ? 443 : 80),
        path: urlObj.pathname || "/",
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body),
          ...(apiKey ? { "Authorization": "Bearer " + apiKey } : {})
        },
        timeout: 30000
      }, (resp) => {
        let data = "";
        resp.on("data", c => data += c);
        resp.on("end", () => {
          try {
            const j = JSON.parse(data);
            resolve(j.result || j.error || { raw: data });
          } catch(e) { resolve({ raw: data }); }
        });
      });
      req.on("error", e => resolve({ error: e.message }));
      req.on("timeout", () => { req.destroy(); resolve({ error: "超时" }); });
      req.write(body);
      req.end();
    } catch(e) { resolve({ error: "URL 格式错误: " + e.message }); }
  });
}

const MCP_STORE = path.join(DATA_DIR, "mcp-servers.json");

function loadMcpConfigs() {
  try { return fs.existsSync(MCP_STORE) ? JSON.parse(fs.readFileSync(MCP_STORE, "utf-8")) : {}; }
  catch(e) { return {}; }
}

function saveMcpConfigs(cfgs) {
  try { fs.writeFileSync(MCP_STORE, JSON.stringify(cfgs, null, 2)); } catch(e) {}
}

  // MCP Connect (save config)
  if (pathname === "/api/mcp/connect" && req.method === "POST") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请先登录" });
    const body = await readBody(req);
    const { server_id, name, url, api_key } = body || {};
    if (!server_id || !name || !url) return sendJSON(res, 400, { ok: false, error: "缺少必要参数" });
    const cfgs = loadMcpConfigs();
    cfgs[server_id] = { name, url, api_key: api_key || "", user_id: user.id, user_email: user.email, updated_at: new Date().toISOString() };
    saveMcpConfigs(cfgs);
    return sendJSON(res, 200, { ok: true, msg: "MCP 服务器已保存" });
  }

  // MCP Test connection
  if (pathname === "/api/mcp/test" && req.method === "POST") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请先登录" });
    const body = await readBody(req);
    const { url, api_key } = body || {};
    if (!url) return sendJSON(res, 400, { ok: false, error: "请填写服务器地址" });
    const result = await mcpTest(url, api_key);
    return sendJSON(res, result.ok ? 200 : 400, result);
  }

  // MCP List connected servers
  if (pathname === "/api/mcp/list" && req.method === "GET") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请先登录" });
    const cfgs = loadMcpConfigs();
    const mine = Object.entries(cfgs).filter(([k, v]) => v.user_id === user.id).map(([k, v]) => ({ id: k, ...v }));
    return sendJSON(res, 200, { ok: true, servers: mine });
  }

  // MCP Call tool (proxy)
  if (pathname === "/api/mcp/call" && req.method === "POST") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请先登录" });
    const body = await readBody(req);
    const { server_id, tool, args } = body || {};
    if (!server_id || !tool) return sendJSON(res, 400, { ok: false, error: "缺少参数" });
    const cfgs = loadMcpConfigs();
    const cfg = cfgs[server_id];
    if (!cfg || cfg.user_id !== user.id) return sendJSON(res, 403, { ok: false, error: "MCP 服务器未找到或无权访问" });
    // Execute tool call asynchronously
    mcpCallTool(cfg.url, cfg.api_key, tool, args).then(result => {
      console.log("[MCP] Tool result for", tool, ":", JSON.stringify(result).slice(0, 200));
    });
    return sendJSON(res, 200, { ok: true, msg: "工具调用已提交" });
  }

  // Plans
  if (pathname === "/api/plans" && req.method === "GET") {
    return sendJSON(res, 200, { ok: true, plans: store.getPlans() });
  }

  // Rules (memory per agent) — reads rules.{agent}.md via Portal auth
  // ?agent=quoter|developer|image|stock|customs  (default: quoter)
  if (pathname === "/api/rules" && req.method === "GET") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请先登录" });
    const agent = parsed.query.agent || "quoter";
    const rulesPath = path.join(STATIC, "..", "..", "data", `rules.${agent}.md`);
    try {
      const raw = fs.readFileSync(rulesPath, "utf-8");
      return sendJSON(res, 200, { ok: true, agent, raw, size: raw.length });
    } catch(e) {
      return sendJSON(res, 200, { ok: true, agent, raw: "# 暂无规则\n", size: 0 });
    }
  }

  if (pathname === "/api/rules" && req.method === "POST") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请先登录" });
    const body = await readBody(req);
    const content = (body && body.content) ? body.content : "";
    const agent = (body && body.agent) ? body.agent : (parsed.query.agent || "quoter");
    const rulesPath = path.join(STATIC, "..", "..", "data", `rules.${agent}.md`);
    const backupDir = path.join(STATIC, "..", "..", "data", "rules_backups");
    try { fs.mkdirSync(backupDir, { recursive: true }); } catch(e) {}
    if (fs.existsSync(rulesPath)) {
      const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      fs.copyFileSync(rulesPath, path.join(backupDir, `rules_${agent}_${ts}.md`));
    }
    fs.writeFileSync(rulesPath, content, "utf-8");
    let backups = [];
    try { backups = fs.readdirSync(backupDir).filter(f => f.endsWith(".md")).sort().reverse().slice(0, 10); } catch(e) {}
    return sendJSON(res, 200, { ok: true, message: "saved", agent, size: content.length, backups });
  }

  // Recharge (create dulupay order)
  if (pathname === "/api/recharge" && req.method === "POST") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请先登录" });
    const body = await readBody(req);
    const { plan_type, plan, period } = body;
    if (!plan_type || !plan || !period || !["month", "year"].includes(period)) {
      return sendJSON(res, 400, { ok: false, error: "参数错误" });
    }
    if (!["quoter", "developer"].includes(plan_type)) {
      return sendJSON(res, 400, { ok: false, error: "数字员工类型无效" });
    }
    const order = store.createOrder(user.id, plan_type, plan, period);
    if (!order) return sendJSON(res, 400, { ok: false, error: "套餐无效" });

    // Call dulupay
    const params = {
      pid: DULUPAY_PID,
      type: "wxpay",
      out_trade_no: order.id,
      notify_url: DULUPAY_NOTIFY,
      return_url: DULUPAY_RETURN,
      name: order.item_name,
      money: String(order.amount)
    };
    params.sign = dulupaySign(params);
    params.sign_type = "MD5";

    const query = Object.keys(params).map(k => `${k}=${encodeURIComponent(params[k])}`).join("&");
    const payUrl = `${DULUPAY_API}&${query}`;

    order.pay_url = payUrl;
    store.saveState();

    return sendJSON(res, 200, { ok: true, order: { id: order.id, amount: order.amount, plan: order.plan, pay_url: payUrl } });
  }

  // Billing (order history)
  if (pathname === "/api/billing" && req.method === "GET") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请先登录" });
    const orders = store.getUserOrders(user.id);
    return sendJSON(res, 200, { ok: true, orders });
  }

  // Invoice request
  if (pathname === "/api/invoice" && req.method === "POST") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请先登录" });
    const body = await readBody(req);
    const { order_id, title, tax_id } = body;
    if (!order_id || !title) {
      return sendJSON(res, 400, { ok: false, error: "请填写发票抬头" });
    }
    const inv = store.requestInvoice(user.id, { order_id, title, tax_id });
    if (inv.error) return sendJSON(res, 400, { ok: false, error: inv.error });
    return sendJSON(res, 200, { ok: true, invoice: inv });
  }

  // Get invoices
  if (pathname === "/api/invoice" && req.method === "GET") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请先登录" });
    const invoices = store.getUserInvoices(user.id);
    return sendJSON(res, 200, { ok: true, invoices });
  }

  // OAuth authorize (client)
  if (pathname === "/api/oauth/authorize" && req.method === "GET") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请先登录" });
    const quota = store.getUserQuota(user.id);
    return sendJSON(res, 200, { ok: true, user, quota, max_channels: store.getMaxChannels(user.id), channels: store.getBoundChannels(user.id) });
  }

  // OAuth token exchange (for desktop client)
  if (pathname === "/api/oauth/token" && req.method === "POST") {
    const user = getAuth(req);
    if (!user) return sendJSON(res, 401, { ok: false, error: "请先登录" });
    const clientToken = signJWT({ uid: user.id, type: "client", iat: Date.now(), exp: Date.now() + 30 * 24 * 3600 * 1000 });
    return sendJSON(res, 200, { ok: true, token: clientToken, user, quota: store.getUserQuota(user.id) });
  }

  // Pay notify (dulupay callback)
  if (pathname === "/api/pay-notify" && (req.method === "GET" || req.method === "POST")) {
    const trade_no = parsed.query.out_trade_no || parsed.query.trade_no || "";
    if (trade_no) {
      const order = store.markOrderPaid(trade_no);
      if (order) {
        console.log(`✅ 支付成功: ${order.id} plan=${order.plan} user=${order.user_id}`);
        // 自动代理升级：仅年付套餐 → 代理资格
        if (order.period === "year" && order.plan && order.plan !== "free" && order.plan !== "basic") {
          const agent = store.autoUpgradeToAgent(order.user_id, order.plan);
          if (agent) console.log(`🎖️ 自动升级代理: ${order.user_id} → ${agent.level} (${agent.discount*100}折)`);
        }
      }
    }
    return res.end("success");
  }

  // Proxy quote engine APIs to Flask
  if (pathname.startsWith("/api/parts") || pathname.startsWith("/api/parse") || pathname.startsWith("/api/quote") || pathname.startsWith("/api/train") || pathname.startsWith("/api/kb") || pathname.startsWith("/api/translate") || pathname.startsWith("/api/inquiry") || pathname.startsWith("/api/pi") || pathname.startsWith("/api/stock") || pathname.startsWith("/api/customers") || pathname.startsWith("/api/history") || pathname.startsWith("/api/agents/status") || pathname.startsWith("/api/trigger-event") || pathname.startsWith("/api/trace")) {
    return proxyToFlask(req, res);
  }

  
  // ═══ Admin API ═══
  if (pathname === "/api/admin/users" && req.method === "GET") {
    const token = getAuth(req);
    if (!token) return sendJSON(res, 401, { error: "请先登录" });
    const admin = store.getUser(token.id);
    if (!admin) return sendJSON(res, 403, { error: "无权限" });
    const users = store.listAllUsers();
    return sendJSON(res, 200, { ok: true, users, count: users.length });
  }

  if (pathname.startsWith("/api/admin/user/") && pathname.endsWith("/plan") && req.method === "POST") {
    const token = getAuth(req);
    if (!token) return sendJSON(res, 401, { error: "请先登录" });
    const parts = pathname.split("/");
    const userId = parts[4];
    const body = await readBody(req);
    const { plan_type, plan_key } = body;
    if (!["quoter", "developer"].includes(plan_type)) return sendJSON(res, 400, { error: "无效的员工类型" });
    const ok = store.updateUserPlan(userId, plan_type, plan_key);
    if (!ok) return sendJSON(res, 400, { error: "修改失败" });
    return sendJSON(res, 200, { ok: true, message: "套餐已更新" });
  }

  if (pathname === "/api/admin/agents" && req.method === "GET") {
    return sendJSON(res, 200, { ok: true, agents: store.getAgents() });
  }

  if (pathname === "/api/admin/agents" && req.method === "POST") {
    const body = await readBody(req);
    const agent = store.createAgent(body);
    return sendJSON(res, 200, { ok: true, agent });
  }

  if (pathname.startsWith("/api/admin/agent/") && req.method === "POST") {
    const agentId = pathname.split("/")[4];
    const body = await readBody(req);
    const agent = store.updateAgent(agentId, body);
    if (!agent) return sendJSON(res, 404, { error: "代理不存在" });
    return sendJSON(res, 200, { ok: true, agent });
  }

  if (pathname.startsWith("/api/admin/agent/") && req.method === "DELETE") {
    const agentId = pathname.split("/")[4];
    const ok = store.deleteAgent(agentId);
    return sendJSON(res, 200, { ok, message: ok ? "已删除" : "不存在" });
  }

  if (pathname === "/api/admin/models" && req.method === "GET") {
    return sendJSON(res, 200, { ok: true, config: store.getModelConfig() });
  }

  if (pathname === "/api/admin/models" && req.method === "POST") {
    const body = await readBody(req);
    const { tier, ...cfg } = body;
    const updated = store.updateModelConfig(tier, cfg);
    return sendJSON(res, 200, { ok: true, config: updated });
  }

  
  // ─── 套餐配置管理 ───
  if (pathname === "/api/admin/plans" && req.method === "GET") {
    return sendJSON(res, 200, { ok: true, plans: store.getPlansConfig() });
  }

  if (pathname.startsWith("/api/admin/plan/") && req.method === "POST") {
    // URL: /api/admin/plan/{type}/{tierKey}
    const parts = pathname.split("/");
    const planType = parts[4];  // quoter or developer
    const tierKey = parts[5];   // free/basic/standard/pro
    const body = await readBody(req);
    const updates = body;
    const plan = store.updatePlansConfig(planType, tierKey, updates);
    return sendJSON(res, 200, { ok: true, plan });
  }

  if (pathname === "/api/admin/orders" && req.method === "GET") {
    const user = getAuth(req);
    if (!user || user.email !== 'admin' && user.email !== 'admin@atlas.local') return sendJSON(res, 403, { ok: false, error: '无权限' });
    const orders = store.listAllOrders();
    return sendJSON(res, 200, { ok: true, orders });
  }

  if (pathname === "/api/admin/plan-add" && req.method === "POST") {
    const body = await readBody(req);
    const { type, tierKey, ...planData } = body;
    const plan = store.addPlanTier(type, tierKey, planData);
    return sendJSON(res, 200, { ok: true, plan });
  }

  if (pathname.startsWith("/api/admin/plan-delete/") && req.method === "POST") {
    // URL: /api/admin/plan-delete/{type}/{tierKey}
    const parts = pathname.split("/");
    const planType = parts[4];
    const tierKey = parts[5];
    const ok = store.deletePlanTier(planType, tierKey);
    return sendJSON(res, 200, { ok, message: ok ? "已删除" : "不存在" });
  }

  if (pathname === "/api/admin/plans-reset" && req.method === "POST") {
    const plans = store.resetPlansToDefault();
    return sendJSON(res, 200, { ok: true, plans, message: "已恢复默认套餐" });
  }

  // ═══ Static Pages ═══
  let filePath = pathname === "/" ? "/index.html" : pathname;
  if (filePath === "/login") filePath = "/login.html";
  if (filePath === "/dashboard") filePath = "/dashboard.html";
  if (filePath === "/download") filePath = "/download.html";
  if (filePath === "/register") filePath = "/index.html"; // registration is modal on index
  if (!path.extname(filePath)) filePath += ".html";
  serveStatic(req, res, path.join(STATIC, filePath));
});

server.listen(PORT, () => {
  console.log(`🚀 擎天 Atlas Portal :${PORT}`);
});
