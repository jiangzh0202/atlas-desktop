/**
 * 擎天 Atlas — JSON 数据层
 * 等同于 TraceClaw 的 store.mjs 模式
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const DATA_DIR = path.join(__dirname, "..", "data");
const STORE_PATH = path.join(DATA_DIR, "atlas-store.json");

// ─── 内存状态 ───
let state = { users: {}, orders: [], invoices: [] };
let lastSaved = "";

function loadState() {
  try {
    if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
    if (fs.existsSync(STORE_PATH)) {
      const raw = fs.readFileSync(STORE_PATH, "utf-8");
      const parsed = JSON.parse(raw);
      state.users = parsed.users || {};
      state.agents = parsed.agents || [];
      state.plans_config = parsed.plans_config || null;
      state.model_config = parsed.model_config || {
        free:     { model: "deepseek-chat",   temperature: 0.7, max_tokens: 1200 },
        basic:    { model: "deepseek-chat",   temperature: 0.5, max_tokens: 1500 },
        standard: { model: "deepseek-v4-pro", temperature: 0.3, max_tokens: 2000 },
        pro:      { model: "deepseek-v4-pro", temperature: 0.2, max_tokens: 3000 }
      };
      state.orders = parsed.orders || [];
      state.invoices = parsed.invoices || [];
    }
  } catch (e) {
    console.error("Store load error:", e.message);
  }
}

function saveState() {
  try {
    const json = JSON.stringify(state, null, 2);
    if (json === lastSaved) return;
    fs.writeFileSync(STORE_PATH, json);
    lastSaved = json;
  } catch (e) {
    console.error("Store save error:", e.message);
  }
}

function uid() {
  return "u_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
}
function oid() {
  return "ord_" + Date.now().toString(36);
}
function invid() {
  return "inv_" + Date.now().toString(36);
}

// ─── 密码哈希 ───
function hashPassword(password) {
  const salt = "atlas_salt_2026";
  return crypto.createHash("sha256").update(salt + ":" + password).digest("hex");
}

// ─── 用户 ───
function createUser({ email, password, company, company_type }) {
  if (!email || !password || !company || !company_type) return null;
  const existing = findByEmail(email);
  if (existing) return { error: "该邮箱已注册" };
  const id = uid();
  const now = new Date().toISOString();
  state.users[id] = {
    id, email, password_hash: hashPassword(password),
    company, company_type,
    plan_quoter: "free", plan_developer: "free",
    quota_quoter_limit: 1, quota_quoter_used: 0,
    quota_developer_limit: 1, quota_developer_used: 0,
    balance: 0, created_at: now, updated_at: now
  };
  saveState();
  return sanitizeUser(state.users[id]);
}

function listAllUsers() {
  return Object.values(state.users).map(u => {
    const { password_hash, ...safe } = u;
    return safe;
  });
}

function findByEmail(email) {
  for (const u of Object.values(state.users)) {
    if (u.email === email) return u;
  }
  return null;
}

function getUser(id) {
  return state.users[id] || null;
}

function verifyLogin(email, password) {
  const user = findByEmail(email);
  if (!user) return null;
  if (user.password_hash !== hashPassword(password)) return null;
  return sanitizeUser(user);
}

function sanitizeUser(user) {
  if (!user) return null;
  const { password_hash, ...safe } = user;
  return safe;
}

// ─── 套餐 ───
const PLANS = {
  quoter: {
    free:   { name: "免费试用", price_month: 0, price_year: 0, quota: 1, unit_price: "-", max_channels: 0 },
    basic:  { name: "入门", price_month: 998, price_year: 10778, quota: 50, unit_price: "20.0", max_channels: 1 },
    standard: { name: "标准", price_month: 2980, price_year: 32184, quota: 200, unit_price: "14.9", max_channels: 2 },
    pro:    { name: "专业", price_month: 5980, price_year: 64584, quota: 500, unit_price: "12.0", max_channels: 3 }
  },
  developer: {
    free:   { name: "免费试用", price_month: 0, price_year: 0, quota: 1, unit_price: "-", max_channels: 0 },
    standard: { name: "标准", price_month: 998, price_year: 10778, quota: 100, unit_price: "9.98", max_channels: 2 },
    pro:    { name: "专业", price_month: 3980, price_year: 42984, quota: 500, unit_price: "7.96", max_channels: 3 },
    enterprise: { name: "企业", price_month: 7900, price_year: 85320, quota: 1000, unit_price: "7.90", max_channels: 3 }
  }
};

function getPlans(type) { return type ? PLANS[type] : PLANS; }

function updateUserPlan(userId, planType, planKey) {
  const user = state.users[userId];
  if (!user) return false;
  const category = PLANS[planType];
  if (!category) return false;
  const p = category[planKey];
  if (!p) return false;
  const planField = "plan_" + planType;
  const limitField = "quota_" + planType + "_limit";
  const usedField = "quota_" + planType + "_used";
  user[planField] = planKey;
  user[limitField] = p.quota;
  user[usedField] = 0;
  // Compute max_channels: take highest across all purchased plans
  let maxCh = 0;
  for (const t of ["quoter", "developer"]) {
    const pk = user["plan_" + t] || "free";
    const cat = PLANS[t];
    const plan = (cat && cat[pk]) || cat.free;
    if (plan.max_channels > maxCh) maxCh = plan.max_channels;
  }
  user.max_channels = maxCh;
  user.updated_at = new Date().toISOString();
  saveState();
  return true;
}

function getUserQuota(userId) {
  const user = state.users[userId];
  if (!user) return { quoter: { used: 0, limit: 0, plan: "free", plan_name: "免费试用" }, developer: { used: 0, limit: 0, plan: "free", plan_name: "免费试用" } };
  
  function build(type) {
    const planKey = user["plan_" + type] || "free";
    const category = PLANS[type];
    const p = (category && category[planKey]) || category.free;
    const limit = user["quota_" + type + "_limit"] ?? p.quota;
    return {
      plan: planKey,
      plan_name: p.name,
      quota_used: user["quota_" + type + "_used"] || 0,
      quota_limit: limit,
      unlimited: p.quota < 0
    };
  }
  
  return { quoter: build("quoter"), developer: build("developer") };
}

function useQuota(userId, planType) {
  const user = state.users[userId];
  if (!user) return false;
  const type = planType || "quoter";
  const planKey = user["plan_" + type] || "free";
  const category = PLANS[type];
  const p = (category && category[planKey]) || { quota: 0 };
  if (p.quota < 0) return true; // 企业不限
  const limitField = "quota_" + type + "_limit";
  const usedField = "quota_" + type + "_used";
  const limit = user[limitField] || 0;
  const used = user[usedField] || 0;
  if (used >= limit) return false;
  user[usedField] = used + 1;
  user.updated_at = new Date().toISOString();
  saveState();
  return true;
}

// ─── 订单 ───
function createOrder(userId, planType, planKey, period) {
  const user = state.users[userId];
  const category = PLANS[planType];
  if (!user || !category) return null;
  const p = category[planKey];
  if (!p) return null;
  const amount = period === "year" ? p.price_year : p.price_month;
  if (!amount || amount <= 0) return null;
  const typeName = planType === "quoter" ? "报价员" : "客户开发员";
  const id = oid();
  const order = {
    id, user_id: userId, plan_type: planType, plan: planKey, period, amount, 
    item_name: `擎天${typeName}·${p.name}(${period==="year"?"年付":"月付"})`,
    pay_url: "", trade_no: "", status: "pending",
    created_at: new Date().toISOString(), paid_at: null
  };
  state.orders.push(order);
  saveState();
  return order;
}

function getOrder(id) {
  return state.orders.find(o => o.id === id) || null;
}

function getUserOrders(userId) {
  return state.orders.filter(o => o.user_id === userId).sort((a, b) => b.created_at.localeCompare(a.created_at));
}

function listAllOrders() {
  const enriched = state.orders.map(o => {
    const user = state.users[o.user_id];
    return { ...o, user_email: user ? user.email : o.user_id, user_company: user ? user.company : '' };
  });
  return enriched.sort((a, b) => b.created_at.localeCompare(a.created_at));
}

function markOrderPaid(trade_no) {
  const order = state.orders.find(o => o.trade_no === trade_no);
  if (!order) return null;
  order.status = "paid";
  order.paid_at = new Date().toISOString();
  updateUserPlan(order.user_id, order.plan_type || "quoter", order.plan);
  saveState();
  return order;
}

// ─── 发票 ───
function requestInvoice(userId, { order_id, title, tax_id }) {
  const order = state.orders.find(o => o.id === order_id && o.user_id === userId);
  if (!order) return { error: "订单不存在" };
  const id = invid();
  const inv = {
    id, user_id: userId, order_id, title, tax_id,
    amount: order.amount, status: "pending",
    created_at: new Date().toISOString()
  };
  state.invoices.push(inv);
  saveState();
  return inv;
}

function getUserInvoices(userId) {
  return state.invoices.filter(i => i.user_id === userId).sort((a, b) => b.created_at.localeCompare(a.created_at));
}

// ─── 通道绑定 ───
function getMaxChannels(userId) {
  const user = state.users[userId];
  if (!user) return 0;
  return user.max_channels || 0;
}

function getBoundChannels(userId) {
  const user = state.users[userId];
  if (!user) return [];
  return user.channels || [];
}

function bindChannel(userId, channel, appId) {
  const user = state.users[userId];
  if (!user) return { ok: false, error: "用户不存在" };
  const maxCh = user.max_channels || 0;
  if (maxCh <= 0) return { ok: false, error: "当前套餐不支持通道绑定" };
  const channels = user.channels || [];
  if (channels.length >= maxCh && !channels.find(c => c.channel === channel)) {
    return { ok: false, error: "通道名额已满（当前套餐支持 " + maxCh + " 个通道）" };
  }
  const existing = channels.findIndex(c => c.channel === channel);
  if (existing >= 0) {
    channels[existing].app_id = appId;
    channels[existing].updated_at = new Date().toISOString();
  } else {
    channels.push({ channel, app_id: appId, created_at: new Date().toISOString(), updated_at: new Date().toISOString() });
  }
  user.channels = channels;
  user.updated_at = new Date().toISOString();
  saveState();
  return { ok: true, channels };
}

function getUserByChannelAppId(queryAppId) {
  for (const uid in state.users) {
    const user = state.users[uid];
    const channels = user.channels || [];
    for (const ch of channels) {
      if (ch.app_id === queryAppId) return user;
    }
  }
  return null;
}

function useChannelQuota(userId, channelType) {
  const user = state.users[userId];
  if (!user) return { ok: false, error: "user_not_found" };
  for (const t of ["quoter", "developer"]) {
    const pk = user["plan_" + t] || "free";
    if (pk === "free") continue;
    const limit = user["quota_" + t + "_limit"] || 0;
    const used = user["quota_" + t + "_used"] || 0;
    if (used >= limit) continue;
    user["quota_" + t + "_used"] = used + 1;
    user.updated_at = new Date().toISOString();
    saveState();
    return { ok: true, remaining: limit - used - 1 };
  }
  return { ok: false, error: "quota_exhausted" };
}


// ─── 代理管理 ───
function createAgent({ name, city, phone, wechat, discount, commission, level }) {
  const id = "agt_" + Date.now().toString(36);
  const now = new Date().toISOString();
  const agent = {
    id, name, city, phone: phone || "", wechat: wechat || "",
    discount: discount || 0.85, commission: commission || 0.10,
    level: level || "ambassador",
    customers: [],
    total_sales: 0, total_commission: 0,
    status: "active",
    created_at: now, updated_at: now
  };
  state.agents.push(agent);
  saveState();
  return agent;
}

function getAgents() { return state.agents || []; }

function getAgent(id) {
  return (state.agents || []).find(a => a.id === id) || null;
}

function updateAgent(id, updates) {
  const agent = getAgent(id);
  if (!agent) return null;
  Object.assign(agent, updates, { updated_at: new Date().toISOString() });
  saveState();
  return agent;
}

function deleteAgent(id) {
  const idx = (state.agents || []).findIndex(a => a.id === id);
  if (idx === -1) return false;
  state.agents.splice(idx, 1);
  saveState();
  return true;
}

function getAgentsByCity(city) {
  return (state.agents || []).filter(a => a.city === city);
}

// ─── 模型配置 ───
function getModelConfig() { return state.model_config || {}; }

function updateModelConfig(tier, config) {
  if (!state.model_config) state.model_config = {};
  state.model_config[tier] = { ...state.model_config[tier], ...config };
  saveState();
  return state.model_config[tier];
}

// ─── 套餐管理 ───
function getPlansConfig() {
  if (state.plans_config) return state.plans_config;
  // Default: return hardcoded PLANS
  return JSON.parse(JSON.stringify(PLANS));
}

function updatePlansConfig(type, tierKey, updates) {
  if (!state.plans_config) {
    state.plans_config = JSON.parse(JSON.stringify(PLANS));
  }
  if (!state.plans_config[type]) state.plans_config[type] = {};
  state.plans_config[type][tierKey] = { ...state.plans_config[type][tierKey], ...updates };
  saveState();
  return state.plans_config[type][tierKey];
}

function addPlanTier(type, tierKey, planData) {
  if (!state.plans_config) {
    state.plans_config = JSON.parse(JSON.stringify(PLANS));
  }
  if (!state.plans_config[type]) state.plans_config[type] = {};
  state.plans_config[type][tierKey] = {
    name: planData.name || tierKey,
    price_month: parseInt(planData.price_month) || 0,
    price_year: parseInt(planData.price_year) || 0,
    quota: parseInt(planData.quota) || 10,
    max_channels: parseInt(planData.max_channels) || 0,
    unit_price: planData.unit_price || "0"
  };
  saveState();
  return state.plans_config[type][tierKey];
}

function deletePlanTier(type, tierKey) {
  if (!state.plans_config || !state.plans_config[type]) return false;
  delete state.plans_config[type][tierKey];
  saveState();
  return true;
}

function resetPlansToDefault() {
  state.plans_config = null;
  saveState();
  return PLANS;
}

// ─── 自动代理升级：客户买年付套餐 → 自动成为代理 ───
const AGENT_AUTO_UPGRADE = {
  standard:   { level: "ambassador", discount: 0.85, name: "推广大使" },
  pro:        { level: "regional",   discount: 0.80, name: "区域代理" },
  enterprise: { level: "city",       discount: 0.75, name: "城市总代" },
};

function autoUpgradeToAgent(userId, planKey) {
  const user = state.users[userId];
  if (!user) return null;

  const upgrade = AGENT_AUTO_UPGRADE[planKey];
  if (!upgrade) return null;

  // 检查是否已经是代理
  const existing = (state.agents || []).find(a => a.user_id === userId);
  if (existing) {
    // 如果已有代理但等级更低，升级
    const levelOrder = { ambassador: 1, regional: 2, city: 3 };
    if (levelOrder[existing.level] < levelOrder[upgrade.level]) {
      existing.level = upgrade.level;
      existing.discount = upgrade.discount;
      existing.updated_at = new Date().toISOString();
      saveState();
      return existing;
    }
    return null; // 已是最优等级，不变
  }

  // 新建代理记录
  const now = new Date().toISOString();
  const agent = {
    id: "agt_" + Date.now().toString(36),
    user_id: userId,
    name: user.company || user.email,
    city: "",
    phone: "",
    wechat: "",
    discount: upgrade.discount,
    commission: 0.10,
    level: upgrade.level,
    deposit: 0,
    bulk_count: 0,
    min_sales: upgrade.level === "city" ? 100000 : (upgrade.level === "regional" ? 40000 : 10000),
    trial_months: 0,
    customers: [],
    total_sales: 0,
    total_commission: 0,
    status: "active",
    source: "auto_upgrade",  // 标记：自动从客户升级
    created_at: now,
    updated_at: now
  };
  state.agents.push(agent);
  saveState();
  return agent;
}

module.exports = {
  loadState, saveState, hashPassword,
  createUser, findByEmail, getUser, listAllUsers, verifyLogin, sanitizeUser,
  getPlans, updateUserPlan, getUserQuota, useQuota,
  createOrder, getOrder, getUserOrders, markOrderPaid, listAllOrders,
  requestInvoice, getUserInvoices,
  getMaxChannels, getBoundChannels, bindChannel, getUserByChannelAppId, useChannelQuota,
  createAgent, getAgents, getAgent, updateAgent, deleteAgent, getAgentsByCity,
  autoUpgradeToAgent, AGENT_AUTO_UPGRADE,
  getPlansConfig, updatePlansConfig, addPlanTier, deletePlanTier, resetPlansToDefault,
  getModelConfig, updateModelConfig,
  PLANS
};
