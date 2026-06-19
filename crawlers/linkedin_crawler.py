#!/usr/bin/env python3
"""LinkedIn 针对性爬虫 — 搜索海外公司"""
import re, time, json, urllib.parse
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def crawl_linkedin(keywords, country="", max_results=10):
    """
    LinkedIn 公共页面搜索公司
    搜索: site:linkedin.com/company "{keywords}" {country}
    (通过 Google 间接搜索 LinkedIn 公开页面)
    """
    results = []
    query = f'site:linkedin.com/company "{keywords}" {country}'
    
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&num={max_results}&hl=en"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        
        if resp.status_code != 200:
            return results
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        company_links = []
        for a in soup.select("a[href^='http']"):
            href = a.get("href", "")
            # Extract real URL from Google redirect
            if href.startswith("/url?"):
                m = re.search(r"url=([^&]+)", href)
                href = urllib.parse.unquote(m.group(1)) if m else href
            
            if "linkedin.com/company/" in href and href not in company_links:
                company_links.append(href)
        
        for link in company_links[:max_results]:
            try:
                time.sleep(1)
                
                # Extract company slug
                m = re.search(r"linkedin\.com/company/([^/?]+)", link)
                slug = m.group(1) if m else ""
                company_name = slug.replace("-", " ").title() if slug else "Unknown"
                
                # Try to fetch company page (public version)
                page_resp = requests.get(link, headers=HEADERS, timeout=10)
                if page_resp.status_code != 200:
                    results.append({
                        "company": company_name,
                        "website": link,
                        "contact": "",
                        "email": "",
                        "country": country,
                        "source": "linkedin",
                        "score": 4,
                        "snippet": f"LinkedIn company: {company_name}"
                    })
                    continue
                
                page_soup = BeautifulSoup(page_resp.text, "html.parser")
                
                # Extract meta description
                meta = page_soup.select_one("meta[name='description']")
                desc = meta.get("content", "") if meta else ""
                
                # Extract industry hints
                industry = ""
                for tag in page_soup.select("[class*='industry'], [class*='sector']"):
                    t = tag.get_text(strip=True)
                    if t and len(t) > 2:
                        industry = t
                        break
                
                # Score
                score = 4
                score_kw = ["auto", "diesel", "engine", "parts", "truck", "automotive",
                           "manufacturing", "import", "export", "distribution"]
                for kw in score_kw:
                    if kw.lower() in desc.lower():
                        score += 1
                score = min(10, score)
                
                results.append({
                    "company": company_name,
                    "website": link,
                    "contact": "",
                    "email": "",
                    "phone": "",
                    "industry": industry,
                    "country": country,
                    "source": "linkedin",
                    "score": score,
                    "snippet": desc[:200]
                })
                
            except Exception:
                continue
                
    except Exception as e:
        print(f"[linkedin_crawler] Error: {e}")
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


if __name__ == "__main__":
    results = crawl_linkedin("diesel engine parts", "UAE", 5)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nFound {len(results)} results")
