#!/usr/bin/env python3
"""TikTok / Facebook 爬虫 — 占位模块，这两个平台需要付费 API 或 OAuth"""
import json


def crawl_tiktok(keywords, country="", max_results=10):
    """
    TikTok 商业账号搜索 — 当前不可用
    原因: TikTok Business API 需要审核，个人开发者无法直接获取
    替代方案: 使用 Google search site:tiktok.com 间接搜索
    """
    return [{
        "company": "",
        "website": "",
        "contact": "",
        "email": "",
        "country": country,
        "source": "tiktok",
        "score": 0,
        "snippet": "⚠️ TikTok 需要商业 API 认证。建议改用 Google/Reddit/Alibaba 搜索。",
        "_status": "platform_paywalled",
        "_alternative": "Google site:tiktok.com search"
    }]


def crawl_facebook(keywords, country="", max_results=10):
    """
    Facebook 商业主页搜索 — 当前不可用
    原因: Facebook Graph API 商业页面搜索需要 App Review + Business Verification
    替代方案: 使用 Google search site:facebook.com 间接搜索
    """
    return [{
        "company": "",
        "website": "",
        "contact": "",
        "email": "",
        "country": country,
        "source": "facebook",
        "score": 0,
        "snippet": "⚠️ Facebook 需要商业验证。建议改用 Google/Reddit/LinkedIn 搜索。",
        "_status": "platform_paywalled",
        "_alternative": "Google site:facebook.com/pg search"
    }]


def crawl_social(keywords, country="", max_results=10):
    """组合社交媒体爬虫：TikTok + Facebook"""
    result = []
    result.extend([r for r in crawl_tiktok(keywords, country, max_results) if r.get("score", 0) > 0])
    result.extend([r for r in crawl_facebook(keywords, country, max_results) if r.get("score", 0) > 0])
    
    # If no real results, return a note
    if not result:
        result.append({
            "company": "社交媒体搜索",
            "website": "",
            "contact": "",
            "email": "",
            "country": country,
            "source": "social_media",
            "score": 0,
            "snippet": "TikTok/Facebook 需要商业API。已通过 Google/LinkedIn/Reddit 替代搜索。",
            "_status": "fallback"
        })
    
    return result


if __name__ == "__main__":
    results = crawl_social("diesel engine parts", "UAE", 5)
    print(json.dumps(results, indent=2, ensure_ascii=False))
