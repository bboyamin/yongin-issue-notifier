from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import sys
import os
import requests
import urllib3
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MK_RSS_SECTIONS = [
    ("종합", "https://www.mk.co.kr/rss/30000001/"),
    ("경제·증권", "https://www.mk.co.kr/rss/30100041/"),
    ("기업·부동산", "https://www.mk.co.kr/rss/30200030/"),
    ("IT·과학", "https://www.mk.co.kr/rss/50300009/"),
    ("정치·사회", "https://www.mk.co.kr/rss/30000023/")
]

def fetch_mknews_from_rss():
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    categorized = {}
    all_articles = []
    formatted_date = datetime.now().strftime("%Y/%m/%d")

    for section_title, rss_url in MK_RSS_SECTIONS:
        try:
            res = requests.get(rss_url, headers=headers, verify=False, timeout=6)
            if res.status_code == 200 and len(res.text) > 300:
                soup = BeautifulSoup(res.text, "xml")
                items = soup.find_all("item")[:20]
                sec_articles = []

                for idx, item in enumerate(items):
                    title = item.title.text.strip() if item.title else ""
                    link = item.link.text.strip() if item.link else ""
                    if not title or not link:
                        continue
                    
                    clean_title = BeautifulSoup(title, "html.parser").text.strip()
                    desc = item.description.text.strip() if item.description else clean_title
                    clean_desc = BeautifulSoup(desc, "html.parser").text.strip()

                    article_obj = {
                        "id": f"mknews_{section_title}_{idx}_{int(datetime.now().timestamp())}",
                        "keyword": "매일경제",
                        "type": "news",
                        "badge": f"📈 매일경제 · {section_title}",
                        "publisher": "매일경제",
                        "title": clean_title,
                        "time": formatted_date,
                        "url": link,
                        "content": clean_desc,
                        "section": section_title
                    }
                    sec_articles.append(article_obj)
                    all_articles.append(article_obj)

                if sec_articles:
                    categorized[section_title] = sec_articles
        except Exception as e:
            print(f"MK RSS section ({section_title}) fetch error: {e}")

    if all_articles:
        sections = list(categorized.keys())
        return {
            "sections": sections,
            "categorized": categorized,
            "articles": all_articles
        }

    return None

def fetch_mknews_from_naver():
    client_id = (os.getenv("NAVER_CLIENT_ID") or "").strip('"\'')
    client_secret = (os.getenv("NAVER_CLIENT_SECRET") or "").strip('"\'')
    if not client_id or not client_secret:
        return None

    url = f"https://openapi.naver.com/v1/search/news.json?query={urllib.parse.quote('매일경제')}&display=40&sort=date"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }

    try:
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            items = res.json().get("items", [])
            categorized = {}
            all_articles = []
            today_str = datetime.now().strftime("%Y/%m/%d")

            for idx, item in enumerate(items):
                clean_title = BeautifulSoup(item.get("title", ""), "html.parser").text.strip()
                clean_desc = BeautifulSoup(item.get("description", ""), "html.parser").text.strip()
                link = item.get("originallink") or item.get("link")

                section = "종합"
                if any(k in clean_title for k in ["증권", "주식", "금리", "금융", "코스피", "코스닥", "환율"]):
                    section = "경제·증권"
                elif any(k in clean_title for k in ["부동산", "아파트", "분양", "건설", "기업", "경영", "재계"]):
                    section = "기업·부동산"
                elif any(k in clean_title for k in ["AI", "반도체", "IT", "기술", "스마트폰", "플랫폼", "통신"]):
                    section = "IT·과학"
                elif any(k in clean_title for k in ["정부", "대통령", "국회", "정치", "검찰", "사회"]):
                    section = "정치·사회"

                article_obj = {
                    "id": f"mknews_naver_{idx}_{int(datetime.now().timestamp())}",
                    "keyword": "매일경제",
                    "type": "news",
                    "badge": f"📈 매일경제 · {section}",
                    "publisher": "매일경제",
                    "title": clean_title,
                    "time": today_str,
                    "url": link,
                    "content": clean_desc,
                    "section": section
                }
                all_articles.append(article_obj)
                if section not in categorized:
                    categorized[section] = []
                categorized[section].append(article_obj)

            if all_articles:
                return {
                    "sections": list(categorized.keys()),
                    "categorized": categorized,
                    "articles": all_articles
                }
    except Exception as e:
        print("Naver MKNews fallback error:", e)

    return None

def fetch_mknews_from_google_rss():
    rss_url = "https://news.google.com/rss/search?q=site:mk.co.kr+when:3d&hl=ko&gl=KR&ceid=KR:ko"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
    try:
        res = requests.get(rss_url, headers=headers, verify=False, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "xml")
            items = soup.find_all("item")
            categorized = {}
            all_articles = []
            today_str = datetime.now().strftime("%Y/%m/%d")

            for idx, item in enumerate(items):
                raw_title = item.title.text.strip() if item.title else ""
                clean_title = raw_title.replace(" - 매일경제", "").strip()
                link = item.link.text.strip() if item.link else ""

                section = "종합"
                if any(k in clean_title for k in ["증권", "주식", "금융", "코스피"]):
                    section = "경제·증권"
                elif any(k in clean_title for k in ["부동산", "아파트", "기업"]):
                    section = "기업·부동산"
                elif any(k in clean_title for k in ["AI", "반도체", "IT", "기술"]):
                    section = "IT·과학"
                elif any(k in clean_title for k in ["정부", "국회", "정치", "사회"]):
                    section = "정치·사회"

                article_obj = {
                    "id": f"mknews_gnews_{idx}_{int(datetime.now().timestamp())}",
                    "keyword": "매일경제",
                    "type": "news",
                    "badge": f"📈 매일경제 · {section}",
                    "publisher": "매일경제",
                    "title": clean_title,
                    "time": today_str,
                    "url": link,
                    "content": clean_title,
                    "section": section
                }
                all_articles.append(article_obj)
                if section not in categorized:
                    categorized[section] = []
                categorized[section].append(article_obj)

            if all_articles:
                return {
                    "sections": list(categorized.keys()),
                    "categorized": categorized,
                    "articles": all_articles
                }
    except Exception as e:
        print("MKNews Google RSS fallback error:", e)

    return None

def fetch_mknews_by_date(ymd_str):
    # 1st tier: Official MK RSS
    result = fetch_mknews_from_rss()

    # 2nd tier: Naver News API search for MK
    if not result or not result.get("articles"):
        result = fetch_mknews_from_naver()

    # 3rd tier: Google News RSS for MK
    if not result or not result.get("articles"):
        result = fetch_mknews_from_google_rss()

    return result or {"sections": [], "categorized": {}, "articles": []}

def get_mknews_article_body(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://www.mk.co.kr/"
    }
    try:
        res = requests.get(url, headers=headers, verify=False, timeout=8)
        if res.status_code != 200:
            return None
            
        soup = BeautifulSoup(res.text, "html.parser")
        content_div = soup.find("div", class_="news_cnt_detail_wrap") or soup.find("div", class_="art_txt") or soup.find("article") or soup.find("div", id="article_body")
        
        if content_div:
            for s in content_div(["script", "style", "iframe", "ins", "button"]):
                s.extract()
            return content_div.text.strip()
        else:
            return soup.text[:3000].strip()
    except Exception as e:
        print(f"MKNews article body fetch error: {e}")
        return None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        article_url = params.get('url', [None])[0]
        if article_url:
            content = get_mknews_article_body(article_url)
            response_data = {"url": article_url, "content": content or ""}
        else:
            date_param = params.get('date', [None])[0] or params.get('ymd', [None])[0]
            if not date_param:
                kst = timezone(timedelta(hours=9))
                date_param = datetime.now(kst).strftime("%Y%m%d")
            
            ymd_str = date_param.replace("-", "").strip()
            result = fetch_mknews_by_date(ymd_str)
            response_data = result

        body = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 's-maxage=300, stale-while-revalidate=600')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

if __name__ == "__main__":
    res = fetch_mknews_by_date(datetime.now().strftime("%Y%m%d"))
    print("MK Articles:", len(res.get("articles", [])))
