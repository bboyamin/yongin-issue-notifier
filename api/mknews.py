from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import sys
import os
import requests
import urllib3
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

MK_RSS_SECTIONS = [
    ("종합", "https://www.mk.co.kr/rss/30000001/"),
    ("정치", "https://www.mk.co.kr/rss/30200030/"),
    ("경제", "https://www.mk.co.kr/rss/30100041/"),
    ("증권", "https://www.mk.co.kr/rss/50200011/"),
    ("부동산", "https://www.mk.co.kr/rss/50300009/"),
    ("문화·연예", "https://www.mk.co.kr/rss/30000023/")
]

def fetch_single_mk_rss(section_tuple):
    section_title, rss_url = section_tuple
    sec_articles = []
    formatted_date = datetime.now(timezone(timedelta(hours=9))).strftime("%Y/%m/%d")
    try:
        res = requests.get(rss_url, headers=headers, verify=False, timeout=6)
        if res.status_code == 200 and len(res.text) > 300:
            soup = BeautifulSoup(res.text, "xml")
            items = soup.find_all("item")
            for idx, item in enumerate(items):
                title = item.title.text.strip() if item.title else ""
                link = item.link.text.strip() if item.link else ""
                if not title or not link:
                    continue
                
                clean_title = BeautifulSoup(title, "html.parser").text.strip()
                desc = item.description.text.strip() if item.description else clean_title
                clean_desc = BeautifulSoup(desc, "html.parser").text.strip()

                pub_date = item.pubDate.text.strip() if item.pubDate else ""
                if pub_date:
                    try:
                        # e.g. Mon, 24 Sep 2026 08:00:00 +0900
                        pub_time = datetime.strptime(pub_date[:16], "%a, %d %b %Y").strftime("%Y/%m/%d")
                    except Exception:
                        pub_time = formatted_date
                else:
                    pub_time = formatted_date

                article_obj = {
                    "id": f"mknews_{section_title}_{idx}_{int(datetime.now().timestamp())}",
                    "keyword": "매일경제",
                    "type": "news",
                    "badge": f"📈 매일경제 · {section_title}",
                    "publisher": "매일경제",
                    "title": clean_title,
                    "time": pub_time,
                    "url": link,
                    "content": clean_desc,
                    "section": section_title
                }
                sec_articles.append(article_obj)
    except Exception as e:
        print(f"MK RSS section ({section_title}) fetch error: {e}")
    return section_title, sec_articles

def fetch_mknews_from_rss():
    categorized = {}
    all_articles = []

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = executor.map(fetch_single_mk_rss, MK_RSS_SECTIONS)
        for section_title, sec_articles in results:
            if sec_articles:
                categorized[section_title] = sec_articles
                all_articles.extend(sec_articles)

    if all_articles:
        sections = list(categorized.keys())
        return {
            "sections": sections,
            "categorized": categorized,
            "articles": all_articles
        }

    return None

def categorize_mk_title(clean_title):
    if any(k in clean_title for k in ["증권", "주식", "코스피", "코스닥", "서학개미", "상장", "공모"]):
        return "증권"
    elif any(k in clean_title for k in ["부동산", "아파트", "분양", "건설", "전세", "월세", "청약", "재개발", "한강뷰"]):
        return "부동산"
    elif any(k in clean_title for k in ["금리", "금융", "환율", "적금", "은행", "물가", "소비자"]):
        return "경제"
    elif any(k in clean_title for k in ["정부", "대통령", "국회", "정치", "검찰", "군", "육군", "사단", "DMZ", "북한", "외교"]):
        return "정치"
    elif any(k in clean_title for k in ["연예", "가수", "배우", "드라마", "영화", "스포츠", "금메달", "예능", "방송"]):
        return "문화·연예"
    return "종합"

def fetch_mknews_from_naver():
    client_id = (os.getenv("NAVER_CLIENT_ID") or "MKJiyEIjWKeda674OX9l").strip('"\'')
    client_secret = (os.getenv("NAVER_CLIENT_SECRET") or "Q313QS0JpL").strip('"\'')
    if not client_id or not client_secret:
        return None

    url = f"https://openapi.naver.com/v1/search/news.json?query={urllib.parse.quote('매일경제')}&display=50&sort=date"
    headers_naver = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }

    try:
        res = requests.get(url, headers=headers_naver, timeout=6)
        if res.status_code == 200:
            items = res.json().get("items", [])
            categorized = {}
            all_articles = []
            today_str = datetime.now(timezone(timedelta(hours=9))).strftime("%Y/%m/%d")

            for idx, item in enumerate(items):
                clean_title = BeautifulSoup(item.get("title", ""), "html.parser").text.strip()
                clean_desc = BeautifulSoup(item.get("description", ""), "html.parser").text.strip()
                link = item.get("originallink") or item.get("link")

                section = categorize_mk_title(clean_title)

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

def fetch_mknews_for_past_date(ymd_str):
    try:
        dt = datetime.strptime(ymd_str, "%Y%m%d")
        dt_next = dt + timedelta(days=1)
        after_str = dt.strftime("%Y-%m-%d")
        before_str = dt_next.strftime("%Y-%m-%d")
        formatted_date = dt.strftime("%Y/%m/%d")

        rss_url = f"https://news.google.com/rss/search?q=site:mk.co.kr+after:{after_str}+before:{before_str}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(rss_url, headers=headers, verify=False, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "xml")
            items = soup.find_all("item")
            categorized = {}
            all_articles = []

            for idx, item in enumerate(items):
                raw_title = item.title.text.strip() if item.title else ""
                clean_title = raw_title.replace(" - 매일경제", "").strip()
                link = item.link.text.strip() if item.link else ""
                if not clean_title or not link:
                    continue

                section = categorize_mk_title(clean_title)

                article_obj = {
                    "id": f"mknews_past_{ymd_str}_{idx}",
                    "keyword": "매일경제",
                    "type": "news",
                    "badge": f"📈 매일경제 · {section}",
                    "publisher": "매일경제",
                    "title": clean_title,
                    "time": formatted_date,
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
        print(f"MKNews past date ({ymd_str}) fetch error:", e)

    return None

def fetch_mknews_by_date(ymd_str=None):
    kst = timezone(timedelta(hours=9))
    today_ymd = datetime.now(kst).strftime("%Y%m%d")
    
    clean_ymd = (ymd_str or "").replace("-", "").strip()

    # If a past date is requested from date picker
    if clean_ymd and len(clean_ymd) == 8 and clean_ymd != today_ymd:
        past_res = fetch_mknews_for_past_date(clean_ymd)
        if past_res and past_res.get("articles"):
            return past_res

    # 1st tier: Official MK RSS (Parallel)
    result = fetch_mknews_from_rss()

    # 2nd tier: Naver News API search for MK
    if not result or not result.get("articles"):
        result = fetch_mknews_from_naver()

    return result or {"sections": [], "categorized": {}, "articles": []}

def get_mknews_article_body(url):
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
    res = fetch_mknews_by_date()
    print("MK Articles:", len(res.get("articles", [])))
