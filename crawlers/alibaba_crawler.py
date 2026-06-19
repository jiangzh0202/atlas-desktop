#!/usr/bin/env python3
"""Alibaba 国际站针对性爬虫 — 搜索买家/供应商线索"""
import re, time, json, urllib.parse
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

ALIBABA_DOMAINS = {
    "AE": "https://www.alibaba.com",
    "default": "https://www.alibaba.com"
}


def crawl_alibaba(keywords, country="", max_results=10):
    """
    爬取 Alibaba.com 搜索相关供应商/买家
    返回: [{company, website, contact, email, source, score}]
    """
    results = []
    seen_companies = set()
    
    base_url = ALIBABA_DOMAINS.get(country.upper(), ALIBABA_DOMAINS["default"])
    
    queries = [
        f"{keywords}",
        f"{keywords} supplier",
    ]
    
    for query in queries[:1]:
        try:
            search_url = f"{base_url}/trade/search?SearchText={urllib.parse.quote(query)}&indexArea=product_en"
            resp = requests.get(search_url, headers=HEADERS, timeout=15)
            
            if resp.status_code != 200:
                continue
            
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Find supplier cards - Alibaba uses dynamic rendering, try multiple selectors
            cards = (
                soup.select("[class*='search-card']") or
                soup.select("[class*='product-item']") or
                soup.select("[class*='list-item']") or
                soup.select("div[data-ctrdot]")
            )
            
            for card in cards[:max_results]:
                try:
                    # Company name
                    company_el = (
                        card.select_one("[class*='company-name']") or
                        card.select_one("[class*='supplier-name']") or
                        card.select_one("a[title]")
                    )
                    company = company_el.get_text(strip=True) if company_el else ""
                    
                    # Link
                    link_el = card.select_one("a[href*='company']") or card.select_one("a[href]")
                    link = link_el.get("href", "") if link_el else ""
                    if link and not link.startswith("http"):
                        link = base_url + link
                    
                    if not company or company in seen_companies:
                        continue
                    if len(company) < 3:
                        continue
                    
                    seen_companies.add(company)
                    
                    # Products hint
                    product_el = card.select_one("[class*='product-name'], [class*='title']")
                    products = product_el.get_text(strip=True) if product_el else keywords
                    
                    # Location
                    loc_el = card.select_one("[class*='location'], [class*='country'], [class*='region']")
                    location = loc_el.get_text(strip=True) if loc_el else country
                    
                    # Score - Alibaba results are naturally relevant
                    score = 5
                    if country.lower() in location.lower():
                        score += 2
                    if any(kw in (company + products).lower() for kw in ["auto", "diesel", "engine", "parts", "truck"]):
                        score += 2
                    score = min(10, score)
                    
                    results.append({
                        "company": company[:80],
                        "website": link,
                        "contact": "",
                        "email": "",
                        "phone": "",
                        "country": location,
                        "source": "alibaba",
                        "score": score,
                        "snippet": products[:200]
                    })
                    
                    if len(results) >= max_results:
                        break
                        
                except Exception:
                    continue
            
            time.sleep(1.5)
        except Exception as e:
            print(f"[alibaba_crawler] Error: {e}")
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


if __name__ == "__main__":
    results = crawl_alibaba("diesel engine parts", "UAE", 5)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nFound {len(results)} results")
