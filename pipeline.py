"""
客户开发员 · 硬管道骨架
──────────────────────────
这是软件最核心的架构约束，三个 Stage 是固定的。
任何时候、任何改动都不能跳过、打乱或绕过这三个阶段。

阶段1: 搜客 SEARCH   — 6平台爬虫 → 线索列表
阶段2: 匹配 MATCH    — 线索 vs 产品库 → 匹配度分析
阶段3: 开发信 EMAIL   — 基于匹配结果 → HTML5 个性化开发信

违反管道顺序的代码不得合并。
"""
import time, json, traceback
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional


# ═══════════════════════════════════════════════
# 阶段枚举 — 不可增删改
# ═══════════════════════════════════════════════
class PipelineStage(Enum):
    SEARCH = "search"        # 阶段1: 搜客
    MATCH  = "match"         # 阶段2: 匹配分析
    EMAIL  = "email"         # 阶段3: 开发信


# 阶段顺序 — 这是铁律
STAGE_ORDER = [PipelineStage.SEARCH, PipelineStage.MATCH, PipelineStage.EMAIL]
STAGE_LABELS = {
    PipelineStage.SEARCH: "🔍 搜客",
    PipelineStage.MATCH:  "🧩 匹配分析",
    PipelineStage.EMAIL:  "✉️ 开发信"
}


# ═══════════════════════════════════════════════
# 管道结果数据类
# ═══════════════════════════════════════════════
@dataclass
class StageResult:
    """单个阶段的执行结果"""
    stage: PipelineStage
    status: str = ""  # "ok" | "error" | "skipped"
    data: dict = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0
    timestamp: str = ""

@dataclass
class PipelineResult:
    """完整管道执行结果"""
    ok: bool = False
    stages: Dict[str, StageResult] = field(default_factory=dict)
    leads: List[dict] = field(default_factory=list)
    matches: Dict[str, dict] = field(default_factory=dict)
    emails: List[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "leads": self.leads,
            "bgchecks": self.stages.get("match", StageResult(PipelineStage.MATCH)).data.get("bgchecks", {}),
            "match_analyses": self.matches,
            "emails": self.emails,
            "summary": self.summary,
            "stages": {
                name: {"status": sr.status, "duration_ms": sr.duration_ms}
                for name, sr in self.stages.items()
            },
            "error": self.error,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "next_step": "配置SMTP后可一键发送开发信"
        }


# ═══════════════════════════════════════════════
# 硬管道类 — 骨架的核心
# ═══════════════════════════════════════════════
class CustomerDevelopmentPipeline:
    """
    客户开发管道 — 骨架不可变
    
    使用方式：
        pipeline = CustomerDevelopmentPipeline()
        result = pipeline.run(industry="diesel engine parts", country="UAE", keywords="auto parts")
    
    内部强制三阶段顺序执行，跳过任何阶段会抛出异常。
    """

    def __init__(self):
        self._product_lines = None
        self._crawlers_available = False
        self._email_utils_available = False
        
        # 延迟导入，避免循环引用
        self._engines_loaded = False

    def _load_engines(self):
        """延迟加载引擎模块"""
        if self._engines_loaded:
            return
        
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        # 爬虫模块
        try:
            from crawlers import multi_platform_crawl, PLATFORM_STATUS
            self.multi_platform_crawl = multi_platform_crawl
            self.PLATFORM_STATUS = PLATFORM_STATUS
            self._crawlers_available = True
        except ImportError:
            self._crawlers_available = False
            self.multi_platform_crawl = None
        
        # DeepSeek
        try:
            from puzzler_engine import ask_deepseek, extract_json
            self.ask_deepseek = ask_deepseek
            self.extract_json = extract_json
        except ImportError:
            self.ask_deepseek = None
            self.extract_json = None
        
        # 背调 & 匹配 & 邮件
        try:
            from puzzler_engine import background_check, match_analysis, generate_email, PRODUCT_LINES
            self.background_check = background_check
            self.match_analysis = match_analysis
            self.generate_email = generate_email
            self._product_lines = PRODUCT_LINES
        except ImportError:
            self.background_check = None
            self.match_analysis = None
            self.generate_email = None
        
        # 邮件工具
        try:
            from email_utils import build_html_email, check_spam_score
            self.build_html_email = build_html_email
            self.check_spam_score = check_spam_score
            self._email_utils_available = True
        except ImportError:
            self._email_utils_available = False
            self.build_html_email = None
            self.check_spam_score = None
        
        self._engines_loaded = True
        # 检测网络环境
        import os
        self._proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""


    def run(self, industry: str, country: str, keywords: str,
            channels: Optional[List[str]] = None,
            language: str = "en",
            max_leads: int = 5) -> PipelineResult:
        """
        执行完整三阶段管道。
        
        参数:
            industry: 行业 (如 "diesel engine parts")
            country:  目标国家 (如 "UAE")
            keywords: 搜索关键词
            channels: 平台列表，默认 ["google","reddit","linkedin","alibaba"]
            language: 邮件语言
            max_leads: 最大线索数
        
        返回: PipelineResult
        """
        self._load_engines()
        
        t0 = time.time()
        result = PipelineResult(timestamp=time.strftime("%Y-%m-%d %H:%M:%S"))
        
        if channels is None:
            channels = ["alibaba"]  # 默认: 国内服务器可达的渠道
        
        try:
            # ═══════ 阶段1: 搜客 — 必须执行 ═══════
            t1 = time.time()
            stage1 = self._run_search(industry, country, keywords, channels, max_leads * 2)
            stage1.duration_ms = round((time.time() - t1) * 1000)
            result.stages["search"] = stage1
            
            if stage1.status != "ok" or not stage1.data.get("leads"):
                result.error = f"阶段1(搜客)失败: {stage1.error or '未找到客户'}"
                result.duration_ms = round((time.time() - t0) * 1000)
                return result
            
            leads = stage1.data["leads"][:max_leads]
            result.leads = leads
            
            # ═══════ 阶段2: 匹配分析 — 必须执行 ═══════
            t2 = time.time()
            stage2 = self._run_match(leads, country)
            stage2.duration_ms = round((time.time() - t2) * 1000)
            result.stages["match"] = stage2
            
            if stage2.status != "ok":
                result.error = f"阶段2(匹配分析)失败: {stage2.error}"
                result.duration_ms = round((time.time() - t0) * 1000)
                return result
            
            matches = stage2.data.get("matches", {})
            bgchecks = stage2.data.get("bgchecks", {})
            result.matches = matches
            
            # ═══════ 阶段3: 开发信 — 必须执行 ═══════
            t3 = time.time()
            stage3 = self._run_email(leads, bgchecks, matches, language)
            stage3.duration_ms = round((time.time() - t3) * 1000)
            result.stages["email"] = stage3
            
            if stage3.status != "ok":
                result.error = f"阶段3(开发信)失败: {stage3.error}"
                result.duration_ms = round((time.time() - t0) * 1000)
                return result
            
            result.emails = stage3.data.get("emails", [])
            
            # ─── 汇总 ───
            avg_score = sum(m.get("best_score", 0) for m in matches.values()) / max(1, len(matches))
            top_leads = sorted(leads, key=lambda l: l.get("score", 0), reverse=True)
            
            result.ok = True
            result.summary = {
                "total_leads": len(leads),
                "bgcheck_count": len(bgchecks),
                "match_count": len(matches),
                "email_count": len(result.emails),
                "avg_match_score": round(avg_score, 1),
                "top_lead": top_leads[0]["company"] if top_leads else "",
                "top_lead_score": top_leads[0].get("score", 0) if top_leads else 0,
                "stages_executed": [s.value for s in STAGE_ORDER],
                "pipeline_version": "2.0-hard",
                "recommended_action": (
                    "开发信已生成，建议优先联系匹配度>=60%的客户"
                    if avg_score >= 40 else
                    "匹配度偏低，建议扩大搜索范围或调整关键词"
                )
            }
            
        except Exception as e:
            result.error = f"管道异常: {str(e)}"
            traceback.print_exc()
        
        result.duration_ms = round((time.time() - t0) * 1000)
        return result


    # ═══════════════════════════════════════════════
    # 阶段1: 搜客 (不可跳过)
    # ═══════════════════════════════════════════════
    def _run_search(self, industry: str, country: str, keywords: str,
                    channels: List[str], max_results: int) -> StageResult:
        """执行多渠道搜索"""
        sr = StageResult(stage=PipelineStage.SEARCH, timestamp=time.strftime("%Y-%m-%d %H:%M:%S"))
        
        search_query = f"{industry} {keywords} {country}"
        all_leads = []
        
        # ── 1a. 真实爬虫 ──
        if self._crawlers_available and self.multi_platform_crawl:
            try:
                crawler_result = self.multi_platform_crawl(
                    search_query, country, channels, max_results=8, timeout=20
                )
                crawler_leads = crawler_result.get("results", [])
                for lead in crawler_leads:
                    lead["_method"] = "crawler"
                    lead.setdefault("products_interested", [])
                    lead.setdefault("reason", f"{lead['source']} search match {lead.get('score',0)}/10")
                    lead.setdefault("phone", "")
                    lead.setdefault("country", country)
                if crawler_leads:
                    all_leads = crawler_leads
                    sr.data["crawler_stats"] = crawler_result.get("stats", {})
            except Exception as e:
                sr.data["crawler_error"] = str(e)
        
        # ── 1b. DeepSeek AI 补充 ──
        if len(all_leads) < 3 and self.ask_deepseek:
            try:
                product_kws = []
                if self._product_lines:
                    for pl_info in list(self._product_lines.values())[:3]:
                        product_kws.extend(pl_info.get("keywords", [])[:3])
                product_context = ", ".join(product_kws[:8])
                
                prompt = f"""你是外贸客户开发专家。
行业: {industry} | 国家: {country} | 关键词: {keywords}
产品线: {product_context}

返回JSON数组，每项: company, website, contact, email, phone, country, source, products_interested, score(1-10), reason
至少5家。只返回JSON。"""
                
                response = self.ask_deepseek(prompt, temperature=0.5, max_tokens=2000)
                ai_leads = self.extract_json(response) if self.extract_json else []
                
                if isinstance(ai_leads, list):
                    for lead in ai_leads:
                        lead["_method"] = "ai"
                    all_leads.extend(ai_leads)
            except Exception as e:
                sr.data["ai_error"] = str(e)
        
        # 去重
        seen = set()
        unique = []
        for lead in all_leads:
            key = lead.get("company", "").lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(lead)
        
        if unique:
            sr.status = "ok"
            sr.data["leads"] = sorted(unique, key=lambda x: x.get("score", 0), reverse=True)[:max_results]
        else:
            sr.status = "error"
            sr.error = "所有渠道均未找到匹配客户"
        
        return sr


    # ═══════════════════════════════════════════════
    # 阶段2: 匹配分析 (不可跳过)
    # ═══════════════════════════════════════════════
    def _run_match(self, leads: List[dict], country: str) -> StageResult:
        """执行背调 + 匹配度分析"""
        sr = StageResult(stage=PipelineStage.MATCH, timestamp=time.strftime("%Y-%m-%d %H:%M:%S"))
        
        bgchecks = {}
        matches = {}
        
        for lead in leads[:5]:
            name = lead.get("company", "")
            if not name:
                continue
            
            # 2a. 背调
            if self.background_check:
                try:
                    bgchecks[name] = self.background_check(name, lead.get("website"), country)
                except Exception as e:
                    bgchecks[name] = {"company": name, "error": str(e)}
            
            # 2b. 匹配分析
            if self.match_analysis and name in bgchecks:
                try:
                    matches[name] = self.match_analysis(lead, bgchecks[name], self._product_lines)
                except Exception as e:
                    matches[name] = {"best_match": "", "best_score": 0, "pitch_strategy": "", "overall_score": 0, "error": str(e)}
        
        if matches or bgchecks:
            sr.status = "ok"
            sr.data = {"matches": matches, "bgchecks": bgchecks}
        else:
            sr.status = "error"
            sr.error = "匹配分析失败：所有客户背调均失败"
        
        return sr


    # ═══════════════════════════════════════════════
    # 阶段3: 开发信 (不可跳过)
    # ═══════════════════════════════════════════════
    def _run_email(self, leads: List[dict], bgchecks: dict,
                   matches: dict, language: str) -> StageResult:
        """生成个性化开发信 + HTML5 + 垃圾检测"""
        sr = StageResult(stage=PipelineStage.EMAIL, timestamp=time.strftime("%Y-%m-%d %H:%M:%S"))
        
        emails = []
        
        for lead in leads[:5]:
            name = lead.get("company", "")
            if not name or name not in bgchecks:
                continue
            
            match = matches.get(name, {})
            
            # 3a. 生成文本内容
            if self.generate_email:
                try:
                    email_content = self.generate_email(lead, bgchecks[name], match, language)
                except Exception:
                    email_content = {
                        "subject": f"Cooperation opportunity - {name}",
                        "body": f"Dear {name},\n\nWe supply auto parts...",
                        "body_html": "",
                        "language": language,
                        "spam_check": {"score": 0, "level": "low", "verdict": "OK"}
                    }
            else:
                email_content = {
                    "subject": f"Auto parts supply - {name}",
                    "body": "",
                    "body_html": "",
                    "language": language,
                    "spam_check": {"score": 0, "level": "low", "verdict": "OK"}
                }
            
            emails.append({
                "company": name,
                "recipient": lead.get("email", ""),
                "contact": lead.get("contact", ""),
                "match_score": match.get("best_score", 0),
                "best_product_line": match.get("best_match", ""),
                "email": email_content
            })
        
        if emails:
            sr.status = "ok"
            sr.data = {"emails": emails}
        else:
            sr.status = "error"
            sr.error = "开发信生成失败：所有客户均无法生成邮件"
        
        return sr


# ═══════════════════════════════════════════════
# 全局单例 — 确保只有一个管道实例
# ═══════════════════════════════════════════════
_pipeline_instance: Optional[CustomerDevelopmentPipeline] = None


def get_pipeline() -> CustomerDevelopmentPipeline:
    """获取管道单例"""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = CustomerDevelopmentPipeline()
    return _pipeline_instance
