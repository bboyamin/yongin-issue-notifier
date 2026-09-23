import os
import sys
import json
import urllib.parse
import requests
import urllib3
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Ensure api directory is in python module path for Vercel
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def fetch_paper_news(provider="etnews", ymd_str=None):
    if not ymd_str:
        kst = timezone(timedelta(hours=9))
        ymd_str = datetime.now(kst).strftime("%Y%m%d")

    clean_ymd = ymd_str.replace("-", "").strip()
    provider = (provider or "etnews").lower().strip()

    # 1. ETNews (전자신문) -> Direct PDF paper fetcher (pdf.etnews.com)
    if provider == "etnews":
        try:
            try:
                from etnews import fetch_etnews_by_date
            except ImportError:
                from api.etnews import fetch_etnews_by_date
            res = fetch_etnews_by_date(clean_ymd)
            if res and res.get("articles"):
                return res
        except Exception as e:
            print("etnews paper fetch error:", e)

    # 2. MKNews (매일경제) -> Direct MK paper fetcher (mk.co.kr)
    elif provider == "mknews":
        try:
            try:
                from mknews import fetch_mknews_by_date
            except ImportError:
                from api.mknews import fetch_mknews_by_date
            res = fetch_mknews_by_date(clean_ymd)
            if res and res.get("articles"):
                return res
        except Exception as e:
            print("mknews paper fetch error:", e)

    # 3. Chosun (조선일보), Joongang (중앙일보), Donga (동아일보) -> Date-aware Paper Edition Engine
    press_map = {
        "chosun": ("023", "조선일보", "🗞️ 조선일보", "chosun.com"),
        "joongang": ("025", "중앙일보", "🏢 중앙일보", "joongang.co.kr"),
        "donga": ("020", "동아일보", "📰 동아일보", "donga.com")
    }

    if provider not in press_map:
        provider = "chosun"

    press_code, press_name, press_badge, press_domain = press_map[provider]

    try:
        dt_obj = datetime.strptime(clean_ymd, "%Y%m%d")
    except Exception:
        dt_obj = datetime.now(timezone(timedelta(hours=9)))
        clean_ymd = dt_obj.strftime("%Y%m%d")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://media.naver.com/",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"'
    })

    # Step A: Naver Media Paper Edition Scraper by requested date (and previous 4 days if Sunday/holiday)
    try_dates = [clean_ymd]
    for i in range(1, 5):
        try_dates.append((dt_obj - timedelta(days=i)).strftime("%Y%m%d"))

    for current_ymd in try_dates:
        url = f"https://media.naver.com/press/{press_code}/newspaper?date={current_ymd}"
        try:
            res = session.get(url, timeout=5, verify=False)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                pages = soup.select(".newspaper_inner")
                if not pages:
                    continue

                cur_fmt_date = f"{current_ymd[:4]}/{current_ymd[4:6]}/{current_ymd[6:8]}"
                categorized = {}
                all_articles = []
                article_idx = 0

                for page in pages:
                    page_elem = page.select_one(".page_notation")
                    section = page_elem.text.strip() if page_elem else "지면"
                    if not section.endswith("면") and "면" not in section:
                        section += "면"

                    items = page.select("ul.newspaper_article_lst li a")
                    for item in items:
                        title_elem = item.select_one("strong") or item
                        clean_title = title_elem.text.strip()
                        href = item.get("href", "")
                        if not clean_title or not href:
                            continue

                        if href.startswith("//"):
                            href = "https:" + href

                        article_obj = {
                            "id": f"{provider}_{current_ymd}_{article_idx}",
                            "keyword": press_name,
                            "type": "news",
                            "badge": f"{press_badge} · {section}",
                            "publisher": press_name,
                            "title": clean_title,
                            "time": cur_fmt_date,
                            "url": href,
                            "content": clean_title,
                            "section": section
                        }
                        all_articles.append(article_obj)
                        if section not in categorized:
                            categorized[section] = []
                        categorized[section].append(article_obj)
                        article_idx += 1

                if all_articles:
                    return {
                        "requested_date": clean_ymd,
                        "actual_date": current_ymd,
                        "is_holiday_fallback": (current_ymd != clean_ymd),
                        "sections": list(categorized.keys()),
                        "categorized": categorized,
                        "articles": all_articles
                    }
        except Exception as e:
            print(f"Paper print fetch error for {provider} ({current_ymd}):", e)

    # Step B: Fallback - Google News Date Range Search (after:YYYY-MM-DD before:YYYY-MM-DD)
    dt_next = dt_obj + timedelta(days=1)
    after_str = dt_obj.strftime("%Y-%m-%d")
    before_str = dt_next.strftime("%Y-%m-%d")
    fmt_target_date = dt_obj.strftime("%Y/%m/%d")

    g_url = f"https://news.google.com/rss/search?q=site:{press_domain}+after:{after_str}+before:{before_str}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        r = session.get(g_url, timeout=5, verify=False)
        if r.status_code == 200 and len(r.content) > 200:
            root = ET.fromstring(r.content)
            items = root.findall('.//item')
            categorized = {}
            all_articles = []

            for idx, item in enumerate(items):
                t_el = item.find('title')
                l_el = item.find('link')
                title = t_el.text.strip() if t_el is not None and t_el.text else ""
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0].strip()
                if not title or len(title) < 4:
                    continue

                link = l_el.text.strip() if l_el is not None and l_el.text else "#"
                section = "주요뉴스"
                if any(w in title for w in ['정치', '대통령', '국회', '정당', '여당', '야당']): section = "정치면"
                elif any(w in title for w in ['경제', '금융', '증시', '주식', '금리', '부동산', '기업']): section = "경제면"
                elif any(w in title for w in ['사회', '검찰', '경찰', '법원', '사건', '사고']): section = "사회면"
                elif any(w in title for w in ['IT', 'AI', '과학', '반도체', '기술']): section = "IT·과학면"

                art = {
                    "id": f"{provider}_gdate_{idx}",
                    "keyword": press_name,
                    "type": "news",
                    "badge": f"{press_badge} · {section}",
                    "publisher": press_name,
                    "title": title,
                    "time": fmt_target_date,
                    "url": link,
                    "content": title,
                    "section": section
                }
                all_articles.append(art)
                if section not in categorized: categorized[section] = []
                categorized[section].append(art)

            if all_articles:
                return {
                    "requested_date": clean_ymd,
                    "actual_date": clean_ymd,
                    "is_holiday_fallback": False,
                    "sections": list(categorized.keys()),
                    "categorized": categorized,
                    "articles": all_articles
                }
    except Exception as e:
        print(f"Google date search fallback error for {provider}:", e)

    return {
        "requested_date": clean_ymd,
        "actual_date": clean_ymd,
        "is_holiday_fallback": False,
        "sections": [],
        "categorized": {},
        "articles": []
    }

from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        provider = params.get('provider', ['chosun'])[0]
        date_param = params.get('date', [None])[0] or params.get('ymd', [None])[0]

        if not date_param:
            kst = timezone(timedelta(hours=9))
            date_param = datetime.now(kst).strftime("%Y%m%d")

        result = fetch_paper_news(provider=provider, ymd_str=date_param)

        body = json.dumps(result, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
