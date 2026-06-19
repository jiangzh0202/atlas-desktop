#!/usr/bin/env python3
"""
Atlas 客户拼图员 — 三层管道引擎
1. 找线索: Linkedin / Facebook / TikTok / Google → 企业 + 联系人
2. 拼背调: 工商信息 + 采购数据 + 社交媒体画像
3. 写开发信: 多语言个性化邮件
"""
import json, re, time, threading, sys, os

# 添加 crawlers 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "crawlers"))
try:
    from crawlers import multi_platform_crawl, PLATFORM_STATUS
    CRAWLERS_AVAILABLE = True
except ImportError:
    CRAWLERS_AVAILABLE = False
    print("[puzzler_engine] 爬虫模块未安装，将使用 AI 模式")

# ═══ 配置 ═══
DEEPSEEK_KEY = "sk-f4aef21293b5472d9f22f86ad289b573"
DEEPSEEK_API = "https://api.deepseek.com/v1/chat/completions"

def ask_deepseek(prompt, temperature=0.3, max_tokens=1500):
    """调用 DeepSeek，自动解析 JSON"""
    import urllib.request
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens
    }).encode()
    req = urllib.request.Request(DEEPSEEK_API, body, {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_KEY}"
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]

def extract_json(text):
    """从 DeepSeek 返回中提取 JSON"""
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try:
            return json.loads(m.group(0))
        except:
            pass
    return None

# ═══ 产品线配置（用户业务核心）═══
PRODUCT_LINES = {
    "福田配件": {
        "brand": "Foton",
        "keywords": ["foton", "福田", "aumark", "auman", "ollin", "tunland", "view"],
        "parts": ["发动机配件", "底盘件", "变速箱", "驾驶室", "车桥"],
        "target_markets": ["中东", "非洲", "东南亚", "南美", "俄罗斯"],
        "price_range": "$50-5,000"
    },
    "东风康明斯": {
        "brand": "Dongfeng Cummins",
        "keywords": ["dongfeng cummins", "东风康明斯", "ISF", "ISL", "ISZ", "QSZ", "QSB", "4BT", "6BT", "6CT"],
        "parts": ["发动机总成", "喷油器", "油泵", "涡轮增压器", "曲轴", "缸体"],
        "target_markets": ["中东", "非洲", "东南亚", "中亚"],
        "price_range": "$100-15,000"
    },
    "康明斯中国": {
        "brand": "Cummins China",
        "keywords": ["cummins china", "康明斯中国", "ISB", "ISD", "ISG", "ISM", "QSB", "QSL", "QSX", "NTA855", "KTA19"],
        "parts": ["发动机总成", "喷油器", "油泵", "涡轮增压器", "滤清器", "传感器"],
        "target_markets": ["中东", "非洲", "东欧", "南美", "东南亚"],
        "price_range": "$200-20,000"
    },
    "东风商用车": {
        "brand": "Dongfeng Commercial Vehicle",
        "keywords": ["dongfeng truck", "东风商用车", "tianlong", "天龙", "tianjin", "天锦", "kinland"],
        "parts": ["发动机配件", "变速箱", "车桥", "驾驶室", "底盘件"],
        "target_markets": ["非洲", "东南亚", "中东", "中亚", "南美"],
        "price_range": "$50-8,000"
    },
    "舍弗勒": {
        "brand": "Schaeffler",
        "keywords": ["schaeffler", "舍弗勒", "luk", "ina", "fag", "clutch", "bearing", "timing"],
        "parts": ["离合器", "轴承", "正时套件", "轮毂", "皮带张紧器"],
        "target_markets": ["欧洲", "北美", "中东", "东南亚"],
        "price_range": "$20-3,000"
    }
}

# ═══ 信息源定义 ═══
INFO_SOURCES = {
    "linkedin": {"type": "社媒", "reliability": "中", "data": ["公司规模", "员工", "职位", "动态"]},
    "facebook": {"type": "社媒", "reliability": "中", "data": ["主页", "互动", "业务动态"]},
    "google": {"type": "搜索", "reliability": "高", "data": ["官网", "新闻", "工商公示"]},
    "b2b": {"type": "B2B平台", "reliability": "高", "data": ["主营产品", "采购量", "贸易记录"]},
    "tiktok": {"type": "社媒", "reliability": "低", "data": ["品牌展示", "产品视频"]},
    "company_registry": {"type": "官方", "reliability": "极高", "data": ["注册号", "法人", "注册资本"]},
    "trade_data": {"type": "海关", "reliability": "极高", "data": ["进出口记录", "贸易伙伴", "货量"]}
}


# ═══ 第1层: 找线索 ═══
def find_leads(industry, country, keywords, channels=None):
    """
    多渠道搜索潜在客户
    channels: ['google','linkedin','reddit','alibaba','tiktok','facebook'] 默认全部活跃平台
    策略: 优先使用真实爬虫，无数据时 Fallback 到 DeepSeek AI
    返回: [{company, website, contact, email, source, score}, ...]
    """
    if not channels:
        channels = ["google", "reddit", "linkedin", "alibaba"]
    
    search_query = f"{industry} {keywords} {country}"
    
    # ── 阶段1: 真实爬虫 ──
    if CRAWLERS_AVAILABLE:
        try:
            crawler_result = multi_platform_crawl(search_query, country, channels, max_results=8, timeout=45)
            crawler_leads = crawler_result.get("results", [])
            crawler_stats = crawler_result.get("stats", {})
            
            if crawler_leads:
                # 标记为真实爬取
                for lead in crawler_leads:
                    lead["_method"] = "crawler"
                    # 补充产品线匹配
                    lead.setdefault("products_interested", [])
                    lead.setdefault("reason", f"{lead['source']}搜索匹配 {lead['score']}/10")
                    lead.setdefault("phone", "")
                
                print(f"[find_leads] 爬虫返回 {len(crawler_leads)} 条 (stats: {crawler_stats})")
                
                # 如果爬虫结果 >= 3 条，直接返回
                if len(crawler_leads) >= 3:
                    return crawler_leads
                
                # 否则用 AI 补充
                print(f"[find_leads] 爬虫结果不足，启用 AI 补充...")
        except Exception as e:
            print(f"[find_leads] 爬虫失败: {e}，回退到 AI 模式")
    else:
        crawler_leads = []
    
    # ── 阶段2: DeepSeek AI 补充 ──
    product_keywords = []
    for pl_name, pl_info in PRODUCT_LINES.items():
        product_keywords.extend(pl_info["keywords"][:3])
    product_context = ", ".join(product_keywords[:10])
    
    prompt = f"""你是外贸客户开发专家，专门为发动机配件/商用车配件供应商寻找海外买家。

行业: {industry}
目标国家: {country}
搜索关键词: {keywords}
核心产品线: {product_context}

请以JSON数组返回真实存在的海外买家/进口商，每条包含：
- company: 公司名（英文全称）
- website: 官网URL
- contact: 关键联系人职位
- email: 最佳联系邮箱（推测或公开）
- phone: 联系电话（如有）
- country: 所在国家
- source: 来源渠道
- products_interested: [该客户可能感兴趣的产品线]
- score: 综合匹配度 1-10
- reason: 推荐理由（1句话）

格式：[{{"company":"ABC Corp","website":"https://abc.com","contact":"Purchasing Manager","email":"purchase@abc.com","phone":"+1-555-0100","country":"UAE","source":"google","products_interested":["康明斯中国"],"score":8,"reason":"主营柴油配件进口"}}]

只返回JSON数组，不要解释。最少5家，最多10家。"""

    response = ask_deepseek(prompt, temperature=0.5, max_tokens=2000)
    ai_leads = extract_json(response)
    if not isinstance(ai_leads, list):
        m = re.search(r'\[[\s\S]*\]', response)
        if m:
            try:
                ai_leads = json.loads(m.group(0))
            except:
                ai_leads = []
    
    for lead in ai_leads:
        lead["_method"] = "ai"
    
    # 合并：爬虫结果在前 + AI 补充
    all_leads = crawler_leads + ai_leads
    
    # 去重
    seen = set()
    unique = []
    for lead in all_leads:
        key = lead.get("company", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(lead)
    
    return unique[:12]

# ═══ 第2层: 信息拼图 / 背景调查 ═══
def background_check(company_name, website=None, country=None):
    """
    多维度客户背调:
    1. 工商注册信息 (DeepSeek 知识库)
    2. 采购能力评估
    3. 社交媒体画像
    4. 风险提示
    """
    prompt = f"""请对以下公司进行全面的背景调查：

公司: {company_name}
网站: {website or '未知'}
国家: {country or '未知'}

以JSON返回以下信息（严格JSON格式，不要markdown）：

{{
  "company": "{company_name}",
  "basic": {{
    "full_name": "公司全称",
    "est_year": "成立年份",
    "employees": "员工规模(如50-200)",
    "revenue": "年营收估算(如$5M-20M)",
    "type": "制造商/进口商/分销商/代理商"
  }},
  "registration": {{
    "credit_code": "工商注册号(如有)",
    "legal_person": "法人",
    "capital": "注册资本",
    "status": "经营状态"
  }},
  "purchasing": {{
    "main_products": ["主营产品1","主营产品2"],
    "annual_import_volume": "年进口量估算",
    "suppliers_from": ["中国","越南"],
    "price_range": "采购价格区间",
    "payment_terms": "常用付款方式"
  }},
  "social": {{
    "linkedin": "LinkedIn活跃度(高/中/低/无)",
    "facebook": "Facebook主页URL或说明",
    "other_platforms": ["其他平台"],
    "online_presence": "线上影响力评分 1-10"
  }},
  "risk": {{
    "credit_rating": "信用评级(A/B/C)",
    "lawsuit_risk": "诉讼风险(低/中/高)",
    "payment_risk": "付款风险提示",
    "red_flags": ["风险点1","风险点2"]
  }},
  "recommendation": {{
    "score": "综合评分 1-100",
    "verdict": "推荐/谨慎/不推荐",
    "approach": "建议开发策略(1-2句话)",
    "first_contact_channel": "首选联系渠道"
  }}
}}

只返回JSON，不要解释。"""
    
    response = ask_deepseek(prompt, temperature=0.2, max_tokens=2000)
    result = extract_json(response)
    if result:
        result["_raw_timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        result["_source"] = "DeepSeek + 公开数据"
        return result
    
    # Fallback
    return {
        "company": company_name,
        "basic": {"full_name": company_name, "est_year": "", "employees": "", "revenue": "", "type": ""},
        "registration": {"credit_code": "", "legal_person": "", "capital": "", "status": ""},
        "purchasing": {"main_products": [], "annual_import_volume": "", "suppliers_from": [], "price_range": "", "payment_terms": ""},
        "social": {"linkedin": "", "facebook": "", "other_platforms": [], "online_presence": 0},
        "risk": {"credit_rating": "", "lawsuit_risk": "", "payment_risk": "", "red_flags": []},
        "recommendation": {"score": 0, "verdict": "数据不足", "approach": "", "first_contact_channel": ""},
        "_raw_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "_source": "解析失败"
    }

# ═══ 第2.5层: 匹配度分析 ═══
def match_analysis(lead, bgcheck, product_lines=None):
    """
    分析客户与我们的产品线匹配度
    返回: {product_scores, best_match, pitch_strategy, overall_score}
    """
    if product_lines is None:
        product_lines = PRODUCT_LINES
    
    company = lead.get("company", "")
    bg_basic = bgcheck.get("basic", {})
    bg_purchasing = bgcheck.get("purchasing", {})
    bg_recommendation = bgcheck.get("recommendation", {})
    
    # 拼接所有可用信息
    all_text = f"{company} {bg_basic.get('full_name','')} {bg_basic.get('type','')} "
    all_text += " ".join(bg_purchasing.get("main_products", []))
    all_text += f" {bgcheck.get('_raw_text','')}"
    all_text = all_text.lower()
    
    product_scores = {}
    best_match = None
    best_score = 0
    
    for pl_name, pl_info in product_lines.items():
        score = 0
        matched_keywords = []
        
        for kw in pl_info["keywords"]:
            if kw.lower() in all_text:
                score += 2
                matched_keywords.append(kw)
        
        # Check if our parts match their purchasing
        for part in pl_info["parts"]:
            for purchased in bg_purchasing.get("main_products", []):
                if part.lower() in purchased.lower() or purchased.lower() in part.lower():
                    score += 3
                    matched_keywords.append(f"产品匹配:{part}")
        
        # Market match bonus
        target_country = lead.get("country", "")
        if target_country in pl_info["target_markets"]:
            score += 1
        
        # Normalize to 0-100
        normalized = min(100, score * 8)
        product_scores[pl_name] = {
            "score": normalized,
            "matched_keywords": matched_keywords[:5],
            "price_range": pl_info["price_range"],
            "parts_applicable": pl_info["parts"][:3]
        }
        
        if normalized > best_score:
            best_score = normalized
            best_match = pl_name
    
    # Generate pitch strategy
    if best_match and best_score >= 40:
        strategy = f"主推 {best_match}（匹配度{best_score}%），提及{', '.join(product_scores[best_match]['matched_keywords'][:2]) or '共同的配件需求'}"
    elif best_match:
        strategy = f"试探性推荐 {best_match}，先建立联系了解需求"
    else:
        strategy = "通用开发策略，展示全线产品目录"
    
    return {
        "product_scores": product_scores,
        "best_match": best_match,
        "best_score": best_score,
        "pitch_strategy": strategy,
        "overall_score": bg_recommendation.get("score", best_score)
    }

# ═══ 第3层: 开发信 ═══
def generate_email(company_info, bg_check, match_result=None, language="zh", style="professional"):
    """
    基于背调结果 + 匹配分析 → 生成个性化开发信
    """
    company = company_info.get("company", "")
    contact = company_info.get("contact", "")
    email_addr = company_info.get("email", "")
    
    match_context = ""
    if match_result:
        match_context = f"""
匹配分析:
- 最佳匹配产品线: {match_result.get('best_match', '待定')}
- 匹配度: {match_result.get('best_score', 0)}%
- 推荐策略: {match_result.get('pitch_strategy', '')}"""
    
    prompt = f"""基于以下客户信息，写一封外贸开发信：

公司: {company}
联系人: {contact or '采购经理'}
联系邮箱: {email_addr or '未提供'}
背调摘要: {json.dumps(bg_check, ensure_ascii=False)[:600]}
{match_context}

要求：
- 语言: {language}（英文客户用英文，中文客户用中文）
- 风格: {style} （professional/warm/concise）
- 字数: 120-200字
- 结构: ① 一句话自我介绍（我们是XXX配件供应商）→ ② 为什么联系他们（引用背调发现的具体信息，如他们的主营产品/市场）→ ③ 我们能提供什么（引用匹配分析里的产品线）→ ④ CTA（请求回复/安排电话/发产品目录）
- 个性化: 必须引用背调和匹配分析中的具体信息
- 避免: 不要用"Dear Sir/Madam", "We are a leading company in China"
- 邮件主题: 简洁有力，包含产品关键词

以JSON返回：
{{"subject": "邮件主题", "body": "邮件正文（纯文本，用\\n换行）", "language": "{language}", "tone": "{style}", "recipient": "{email_addr}", "personalization_hooks": ["引用了什么具体信息"]}}

只返回JSON。"""
    
    response = ask_deepseek(prompt, temperature=0.6, max_tokens=1000)
    result = extract_json(response)
    if not result:
        result = {"subject": f"Cooperation opportunity - {company}", "body": response[:500], "language": language, "tone": style}
    
    # ── HTML5 模板 + 垃圾检测 ──
    subject = result.get("subject", "")
    body_text = result.get("body", "")
    
    # 跑垃圾词检测
    spam_check = check_spam_score(subject, body_text)
    
    # 生成 HTML5 版本
    sender_info = {
        "name": SMTP_CONFIG.get("from_name", ""),
        "company": SMTP_CONFIG.get("from_name", "Atlas Auto Parts"),
        "website": "",
        "email": SMTP_CONFIG.get("from_email", "")
    }
    html_result = build_html_email(subject, body_text, company, sender_info)
    
    return {
        "subject": subject,
        "body": body_text,
        "body_html": html_result.get("body_html", ""),
        "language": language,
        "tone": style,
        "recipient": email_addr,
        "spam_check": spam_check,
        "personalization_hooks": result.get("personalization_hooks", [])
    }


# ═══ 邮件配置与发送 ═══
import smtplib
from email_utils import build_html_email, check_spam_score
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_CONFIG = {
    "host": "",
    "port": 587,
    "user": "",
    "password": "",
    "from_name": "",
    "from_email": "",
    "use_tls": True
}

def configure_smtp(host, port, user, password, from_name="", from_email=""):
    """配置 SMTP 发送参数"""
    SMTP_CONFIG["host"] = host
    SMTP_CONFIG["port"] = int(port)
    SMTP_CONFIG["user"] = user
    SMTP_CONFIG["password"] = password
    SMTP_CONFIG["from_name"] = from_name or user
    SMTP_CONFIG["from_email"] = from_email or user
    return {"ok": True, "message": f"SMTP配置完成: {user}"}

def send_email_via_smtp(to_email, subject, body, to_name="", body_html=""):
    """
    通过 SMTP 发送邮件（支持 HTML + 纯文本双版本）
    返回: {ok, message, spam_check}
    """
    if not SMTP_CONFIG["host"]:
        return {"ok": False, "error": "SMTP未配置，请先配置邮箱"}
    
    # 垃圾检测（发送前最后一道防线）
    spam_check = check_spam_score(subject, body)
    
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f'{SMTP_CONFIG["from_name"]} <{SMTP_CONFIG["from_email"]}>'
        msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email
        msg["Subject"] = subject
        
        # 反垃圾邮件头
        msg["X-Priority"] = "3"
        msg["Precedence"] = "bulk"
        msg["X-Mailer"] = "Atlas Customer Development Engine"
        if SMTP_CONFIG["from_email"]:
            msg["List-Unsubscribe"] = f"<mailto:{SMTP_CONFIG['from_email']}?subject=Unsubscribe>"
        
        # 附件顺序：纯文本在前，HTML 在后（邮件客户端优先显示 HTML）
        msg.attach(MIMEText(body, "plain", "utf-8"))
        
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))
        
        if SMTP_CONFIG["use_tls"]:
            server = smtplib.SMTP(SMTP_CONFIG["host"], SMTP_CONFIG["port"], timeout=30)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(SMTP_CONFIG["host"], SMTP_CONFIG["port"], timeout=30)
        
        server.login(SMTP_CONFIG["user"], SMTP_CONFIG["password"])
        server.send_message(msg)
        server.quit()
        
        return {
            "ok": True,
            "message": f"邮件已发送至 {to_email}",
            "recipient": to_email,
            "subject": subject,
            "spam_check": spam_check
        }
    
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "error": "SMTP认证失败，请检查邮箱和密码"}
    except smtplib.SMTPException as e:
        return {"ok": False, "error": f"SMTP错误: {str(e)}"}
    except Exception as e:
        return {"ok": False, "error": f"发送失败: {str(e)}"}

def send_bulk_emails(email_list):
    """
    批量发送开发信
    email_list: [{to_email, to_name, subject, body}, ...]
    """
    results = []
    for item in email_list:
        result = send_email_via_smtp(
            item.get("to_email", ""),
            item.get("subject", ""),
            item.get("body", ""),
            item.get("to_name", ""),
            item.get("body_html", "")
        )
        results.append({**item, "send_result": result})
        time.sleep(2)  # 间隔2秒防限速
    return {"ok": True, "total": len(results), "sent": sum(1 for r in results if r["send_result"].get("ok")), "results": results}

# ═══ 完整管道: 一键三连 ═══
def full_pipeline(industry, country, keywords, language="en", channels=None, product_lines=None):
    """
    完整四阶段管道: 搜客 → 背调 → 匹配分析 → 开发信
    
    阶段1: 多渠道搜索潜在客户
    阶段2: 多维度背景调查（工商/采购/社媒/风控）
    阶段3: 产品匹配度分析（与用户产品线比对）
    阶段4: 个性化开发信生成
    
    返回: {leads, bgchecks, match_analyses, emails, summary}
    """
    # Stage 1: Find leads
    leads = find_leads(industry, country, keywords, channels)
    if not leads:
        return {
            "ok": False,
            "error": "未找到匹配的潜在客户",
            "leads": [],
            "bgchecks": {},
            "match_analyses": {},
            "emails": [],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    
    # Stage 2: Background check each lead
    bgchecks = {}
    for lead in leads[:5]:  # 限5家避免超时
        name = lead.get("company", "")
        if name:
            bgchecks[name] = background_check(name, lead.get("website"), country)
    
    # Stage 3: Match analysis against product lines
    match_analyses = {}
    if product_lines is None:
        product_lines = PRODUCT_LINES
    for lead in leads[:5]:
        name = lead.get("company", "")
        if name and name in bgchecks:
            match_analyses[name] = match_analysis(lead, bgchecks[name], product_lines)
    
    # Stage 4: Generate personalized emails
    emails = []
    for lead in leads[:5]:
        name = lead.get("company", "")
        if name and name in bgchecks:
            match = match_analyses.get(name, {})
            email_content = generate_email(lead, bgchecks[name], match, language)
            emails.append({
                "company": name,
                "recipient": lead.get("email", ""),
                "contact": lead.get("contact", ""),
                "match_score": match.get("best_score", 0),
                "best_product_line": match.get("best_match", ""),
                "email": email_content
            })
    
    # Build summary
    avg_score = sum(a.get("best_score", 0) for a in match_analyses.values()) / max(1, len(match_analyses))
    top_leads = sorted(leads[:5], key=lambda l: l.get("score", 0), reverse=True)
    
    return {
        "ok": True,
        "leads": leads,
        "bgchecks": bgchecks,
        "match_analyses": match_analyses,
        "emails": emails,
        "summary": {
            "total_leads": len(leads),
            "bgcheck_count": len(bgchecks),
            "match_count": len(match_analyses),
            "email_count": len(emails),
            "avg_match_score": round(avg_score, 1),
            "top_lead": top_leads[0]["company"] if top_leads else "",
            "top_lead_score": top_leads[0].get("score", 0) if top_leads else 0,
            "crawler_method": "real_crawlers" if any(l.get("_method") == "crawler" for l in leads) else "ai_only",
            "recommended_action": "开发信已生成，建议优先联系匹配度>60%的客户" if avg_score >= 40 else "匹配度偏低，建议扩大搜索范围或调整关键词"
        },
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "next_step": "配置SMTP后可一键发送开发信"
    }

print("✅ 客户拼图员引擎已加载")
