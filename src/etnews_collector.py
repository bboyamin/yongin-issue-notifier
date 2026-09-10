import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime

def fetch_etnews_by_date(ymd_str):
    """
    Fetch categorized ETNews (전자신문 지면 기사) by date (YYYYMMDD).
    Returns dict: { "sections": ["1면", ...], "categorized": { "1면": [...] }, "articles": [...] }
    """
    urls = [
        f"https://pdf.etnews.com/pdf_today.html?ymd={ymd_str}",
        f"https://pdf.etnews.com/index.html?ymd={ymd_str}"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://pdf.etnews.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache"
    }
    
    session = requests.Session()
    html_text = None
    for url in urls:
        try:
            res = session.get(url, headers=headers, timeout=8)
            if res.status_code == 200 and len(res.text) > 2000:
                html_text = res.text
                break
        except Exception as e:
            print(f"ETNews fetch error for {url}: {e}")
            continue
            
    if not html_text:
        return {"sections": [], "categorized": {}, "articles": []}
        
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        boxes = soup.find_all("div", class_="box") or soup.find_all("dl", class_="box") or soup.find_all("div", class_="pdf_box")
        
        if not boxes:
            return {"sections": [], "categorized": {}, "articles": []}
            
        categorized = {}
        all_articles = []
        
        formatted_date = f"{ymd_str[:4]}/{ymd_str[4:6]}/{ymd_str[6:8]}"
        
        for b_idx, box in enumerate(boxes):
            section_title_el = box.find("dt") or box.find("strong") or box.find("h3")
            if not section_title_el:
                continue
            section_title = section_title_el.text.strip()
            if not section_title:
                section_title = f"지면 {b_idx + 1}"
            
            links = box.find_all("a", target="_blank") or box.find_all("a")
            articles = []
            for a_idx, link in enumerate(links):
                title = link.text.strip()
                href = link.get("href", "")
                if not href or href == "#" or "javascript" in href:
                    continue
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = "https://pdf.etnews.com" + href
                
                if title and href:
                    article_obj = {
                        "id": f"etnews_{ymd_str}_{b_idx}_{a_idx}",
                        "keyword": "전자신문",
                        "type": "news",
                        "badge": f"📰 전자신문 · {section_title}",
                        "publisher": "전자신문",
                        "title": title,
                        "time": formatted_date,
                        "url": href,
                        "content": title,
                        "section": section_title
                    }
                    articles.append(article_obj)
                    all_articles.append(article_obj)
                    
            if articles:
                if section_title in categorized:
                    categorized[section_title].extend(articles)
                else:
                    categorized[section_title] = articles
                
        sections = list(categorized.keys())
        return {
            "sections": sections,
            "categorized": categorized,
            "articles": all_articles
        }
    except Exception as e:
        print(f"ETNews parse error: {e}")
        return {"sections": [], "categorized": {}, "articles": []}

def get_etnews_article_body(url):
    """
    Fetch the article body text from an ETNews article URL for AI summarization.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://pdf.etnews.com/"
    }
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code != 200:
            return None
            
        soup = BeautifulSoup(res.text, "html.parser")
        content_div = soup.find("article") or soup.find("div", class_="article_txt") or soup.find("div", class_="article_body") or soup.find("div", id="articleBody")
        
        if content_div:
            for s in content_div(["script", "style", "iframe", "ins", "button"]):
                s.extract()
            return content_div.text.strip()
        else:
            return soup.text[:3000].strip()
    except Exception as e:
        print(f"ETNews article body fetch error: {e}")
        return None
