#!/usr/bin/env python3
"""Google 针对性爬虫 — 搜索海外汽车配件买家"""
import re, time, json, urllib.parse
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

def crawl_google(keywords, country="", max_results=10):
    """
    Google 搜索潜在买家
    搜索策略: "{keywords} importer {country}" / "{keywords} distributor {country}"
    返回: [{company, website, snippet, contact, email, source, score}]
    """
    queries = [
        f'"{keywords}" importer {country} -alibaba -made-in-china',
        f'"{keywords}" distributor {country} -alibaba',
        f'"{keywords}" auto parts {country} company -alibaba',
    ]
    
    results = []
    seen_domains = set()
    
    for query in queries[:2]:  # 限2个查询避免超时
        try:
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&num={max_results}&hl=en"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Parse search result blocks
            for g in soup.select("div.g, div[data-sokoban-container], div.MjjYud"):
                try:
                    # Title + link
                    link_el = g.select_one("a[href^='http']") or g.select_one("a[href^='/url?']")
                    title_el = g.select_one("h3")
                    snippet_el = g.select_one("div.VwiC3b, span.aCOpRe, div[data-sncf]")
                    
                    href = ""
                    if link_el:
                        href = link_el.get("href", "")
                        if href.startswith("/url?"):
                            m = re.search(r"url=([^&]+)", href)
                            href = urllib.parse.unquote(m.group(1)) if m else href
                    
                    title = title_el.get_text(strip=True) if title_el else ""
                    snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                    
                    # Extract domain
                    domain = ""
                    if href:
                        m = re.search(r"https?://([^/]+)", href)
                        domain = m.group(1) if m else ""
                    
                    # Skip if already seen or unwanted domains
                    if domain in seen_domains:
                        continue
                    skip_domains = ["alibaba.com", "made-in-china.com", "globalsources.com", 
                                   "google.com", "youtube.com", "facebook.com", "linkedin.com",
                                   "wikipedia.org", "amazon.com", "ebay.com"]
                    if any(s in domain for s in skip_domains):
                        continue
                    
                    if not domain or not title:
                        continue
                    
                    seen_domains.add(domain)
                    
                    # Extract company name
                    company = title.split(" - ")[0].split(" | ")[0].split("–")[0].strip()[:80]
                    if len(company) < 3:
                        company = domain.split(".")[0].replace("-", " ").title()
                    
                    # Extract possible email from snippet
                    email = ""
                    email_m = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", snippet)
                    if email_m:
                        email = email_m.group(0)
                    
                    # Score based on keywords in snippet
                    score = 3
                    score_keywords = ["importer", "distributor", "dealer", "wholesale", "supplier",
                                     "auto parts", "diesel", "engine", "truck", "commercial vehicle"]
                    for kw in score_keywords:
                        if kw.lower() in (title + snippet).lower():
                            score += 1
                    score = min(10, score)
                    
                    results.append({
                        "company": company,
                        "website": f"https://{domain}" if not href.startswith("http") else href,
                        "contact": _extract_role(snippet),
                        "email": email,
                        "phone": _extract_phone(snippet),
                        "country": country,
                        "source": "google",
                        "score": score,
                        "snippet": snippet[:200]
                    })
                    
                    if len(results) >= max_results:
                        break
                        
                except Exception:
                    continue
                    
            time.sleep(1.5)  # 礼貌爬取
        except Exception as e:
            print(f"[google_crawler] Error on query '{query[:50]}...': {e}")
            continue
    
    # Sort by score desc
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def _extract_role(snippet):
    """从片段提取可能的职位"""
    roles = ["Purchasing Manager", "Procurement", "Supply Chain", "General Manager",
             "CEO", "Director", "Import Manager", "Sales Manager", "Buyer"]
    for role in roles:
        if role.lower() in snippet.lower():
            return role
    return ""


def _extract_phone(text):
    """提取电话号码"""
    m = re.search(r"\+?[\d\s\(\)-]{7,20}", text)
    return m.group(0).strip() if m else ""


# 测试
if __name__ == "__main__":
    results = crawl_google("diesel engine parts", "UAE", 5)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nFound {len(results)} results")
