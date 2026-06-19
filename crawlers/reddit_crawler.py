#!/usr/bin/env python3
"""Reddit 针对性爬虫 — 从行业子版块挖掘买家线索"""
import re, time, json, urllib.parse, urllib.request

REDDIT_SUBREDDITS = [
    "importexport", "smallbusiness", "manufacturing", "supplychain",
    "logistics", "entrepreneur", "business", "B2B", "trucking", "diesel"
]

HEADERS = {
    "User-Agent": "AtlasBot/1.0 (B2B lead research; contact@traceclaw.cn)",
    "Accept": "application/json"
}


def crawl_reddit(keywords, country="", max_results=10):
    """
    从 Reddit 行业子版块搜索潜在买家/讨论
    搜索策略: 在 r/importexport, r/smallbusiness 等搜索关键词
    返回: [{company, website, contact, email, source: "reddit", score}]
    """
    results = []
    seen_users = set()
    keyword_list = keywords.split()
    
    for subreddit in REDDIT_SUBREDDITS:
        if len(results) >= max_results:
            break
        
        for kw in keyword_list[:3]:  # 用前3个关键词搜索
            if len(results) >= max_results:
                break
            try:
                query = urllib.parse.quote(f"{kw} {country}")
                url = f"https://www.reddit.com/r/{subreddit}/search.json?q={query}&restrict_sr=on&sort=relevance&limit=10"
                
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                
                posts = data.get("data", {}).get("children", [])
                
                for post in posts:
                    post_data = post.get("data", {})
                    title = post_data.get("title", "")
                    selftext = post_data.get("selftext", "")
                    author = post_data.get("author", "")
                    permalink = post_data.get("permalink", "")
                    
                    full_text = f"{title} {selftext}"
                    
                    # 过滤：只保留与B2B/采购相关的帖子
                    buyer_signals = ["looking for", "need supplier", "import", "export", 
                                    "sourcing", "buying", "wholesale", "distributor needed",
                                    "supplier needed", "looking to buy", "manufacturer needed",
                                    "auto parts", "engine parts", "diesel"]
                    
                    has_signal = any(s in full_text.lower() for s in buyer_signals)
                    if not has_signal:
                        continue
                    
                    if author in seen_users or author in ["AutoModerator", "[deleted]"]:
                        continue
                    seen_users.add(author)
                    
                    # Extract company hints
                    company = _extract_company(full_text) or f"Reddit u/{author}"
                    
                    # Extract email
                    email = ""
                    email_m = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", full_text)
                    if email_m:
                        email = email_m.group(0)
                    
                    # Score
                    score = 3
                    for s in buyer_signals:
                        if s in full_text.lower():
                            score += 1
                    score = min(8, score)  # Reddit 分数上限较低
                    
                    results.append({
                        "company": company,
                        "website": "",
                        "contact": author,
                        "email": email,
                        "country": country,
                        "source": f"reddit/r/{subreddit}",
                        "score": score,
                        "snippet": title[:200],
                        "permalink": f"https://reddit.com{permalink}" if permalink else ""
                    })
                    
                    if len(results) >= max_results:
                        break
                
                time.sleep(1)
            except Exception as e:
                print(f"[reddit_crawler] Error r/{subreddit} '{kw}': {e}")
                continue
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def _extract_company(text):
    """从文本中提取公司名"""
    patterns = [
        r"(?:from|at|with|company called|company is|work at|work for)\s+([A-Z][A-Za-z0-9\s&.-]{3,40})(?:\.|,|\s+and|\s+in|\s+we)",
        r"(?:I (?:run|own|represent))\s+([A-Z][A-Za-z0-9\s&.-]{3,40})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return ""


if __name__ == "__main__":
    results = crawl_reddit("diesel engine parts importer", "UAE", 5)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nFound {len(results)} results")
