#!/usr/bin/env python3
"""
Atlas 多平台爬虫模块
统一入口：multi_platform_crawl(keywords, country, channels, max_results)
"""
import json, time, concurrent.futures

from .google_crawler import crawl_google
from .reddit_crawler import crawl_reddit
from .linkedin_crawler import crawl_linkedin
from .alibaba_crawler import crawl_alibaba
from .social_crawler import crawl_tiktok, crawl_facebook, crawl_social

# ═══════════════════════════════════════════════
# 代理配置
# ═══════════════════════════════════════════════
import os

PROXY_CONFIG = {
    "enabled": False,
    "http": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or "",
    "https": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "",
    "socks5": os.environ.get("ALL_PROXY") or os.environ.get("all_proxy") or "",
}

# 优先使用显式配置的代理，其次环境变量
_config_file = os.path.join(os.path.dirname(__file__), "..", "proxy.json")
if os.path.exists(_config_file):
    try:
        import json
        with open(_config_file) as f:
            cfg = json.load(f)
        PROXY_CONFIG.update(cfg)
    except:
        pass

def get_proxy_dict():
    """返回 requests 可用的 proxies 字典"""
    proxies = {}
    if not PROXY_CONFIG.get("enabled", False):
        return None
    socks = PROXY_CONFIG.get("socks5", "")
    https = PROXY_CONFIG.get("https", "")
    http = PROXY_CONFIG.get("http", "")
    if socks:
        proxies["http"] = socks
        proxies["https"] = socks
    elif https:
        proxies["https"] = https
        if http:
            proxies["http"] = http
        else:
            proxies["http"] = https
    return proxies if proxies else None

def proxy_available():
    """代理是否可用"""
    return PROXY_CONFIG.get("enabled", False) and bool(get_proxy_dict())

# 平台→爬虫映射
CRAWLER_MAP = {
    "google": crawl_google,
    "reddit": crawl_reddit,
    "linkedin": crawl_linkedin,
    "alibaba": crawl_alibaba,
    "tiktok": crawl_tiktok,
    "facebook": crawl_facebook,
}

# 平台状态（哪些是活跃的，哪些是占位的）
PLATFORM_STATUS = {
    "google": {"active": True, "desc": "Google 搜索引擎"},
    "reddit": {"active": True, "desc": "Reddit 社区搜索 (JSON API)"},
    "linkedin": {"active": True, "desc": "LinkedIn 公司页面 (公共)"},
    "alibaba": {"active": True, "desc": "Alibaba 国际站供应商"},
    "tiktok": {"active": False, "desc": "需要商业API认证", "alternative": "google"},
    "facebook": {"active": False, "desc": "需要商业验证", "alternative": "google"},
}


def multi_platform_crawl(keywords, country="", channels=None, max_results=10, timeout=60):
    """
    多平台并行爬取
    
    参数:
        keywords: 搜索关键词
        country: 目标国家
        channels: 要使用的平台列表，默认全部
        max_results: 每个平台最多返回结果数
        timeout: 总超时秒数
    
    返回: {
        results: [{company, website, contact, email, source, score}, ...],
        stats: {google: 5, linkedin: 3, ...},
        platform_status: {...}
    }
    """
    if channels is None:
        channels = ["google", "reddit", "linkedin", "alibaba"]
    
    # 并行执行爬虫
    all_results = []
    stats = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        for ch in channels:
            crawler = CRAWLER_MAP.get(ch)
            if crawler:
                futures[executor.submit(crawler, keywords, country, max_results)] = ch
        
        for future in concurrent.futures.as_completed(futures, timeout=timeout):
            ch = futures[future]
            try:
                results = future.result(timeout=30)
                # 过滤掉占位/不可用结果
                valid = [r for r in results if r.get("score", 0) > 0]
                stats[ch] = len(valid)
                
                # 标记来源平台
                for r in valid:
                    r["source"] = ch
                
                all_results.extend(valid)
            except Exception as e:
                stats[ch] = 0
                print(f"[multi_crawl] {ch} failed: {e}")
    
    # 去重（按公司名）
    seen = set()
    deduped = []
    for r in sorted(all_results, key=lambda x: x.get("score", 0), reverse=True):
        key = r.get("company", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)
    
    return {
        "results": deduped[:max_results * len(channels)],
        "stats": stats,
        "platform_status": {ch: PLATFORM_STATUS.get(ch, {}) for ch in channels},
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }


def get_available_platforms():
    """返回可用平台列表"""
    return PLATFORM_STATUS


if __name__ == "__main__":
    # 快速测试
    result = multi_platform_crawl("diesel engine parts", "UAE", ["google", "reddit"], 3, timeout=30)
    print(f"Stats: {json.dumps(result['stats'])}")
    for r in result["results"]:
        print(f"  [{r['source']}] {r['company']} (score:{r['score']}) — {r.get('website','')}")
    print(f"\nTotal: {len(result['results'])} unique results")
