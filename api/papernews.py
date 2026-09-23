import os
import sys
import json
import urllib.parse
import requests
import urllib3
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

    # 1. ETNews (전자신문) -> Direct PDF paper fetcher
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

    # 2. MKNews (매일경제) -> Direct MK paper fetcher
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

    # 3. Chosun (조선일보), Joongang (중앙일보), Donga (동아일보)
    press_map = {
        "chosun": ("023", "조선일보", "🗞️ 조선일보"),
        "joongang": ("025", "중앙일보", "🏢 중앙일보"),
        "donga": ("020", "동아일보", "📰 동아일보")
    }

    if provider not in press_map:
        provider = "chosun"

    press_code, press_name, press_badge = press_map[provider]

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://media.naver.com/",
        "Cache-Control": "no-cache"
    }

    try_dates = [clean_ymd]
    try:
        dt_obj = datetime.strptime(clean_ymd, "%Y%m%d")
        for i in range(1, 5):
            try_dates.append((dt_obj - timedelta(days=i)).strftime("%Y%m%d"))
    except Exception:
        pass

    # Also add current KST date if clean_ymd is different
    kst_now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")
    if kst_now not in try_dates:
        try_dates.append(kst_now)

    categorized = {}
    all_articles = []

    for current_ymd in try_dates:
        url = f"https://media.naver.com/press/{press_code}/newspaper?date={current_ymd}"
        try:
            res = requests.get(url, headers=headers, verify=False, timeout=6)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                pages = soup.select(".newspaper_inner")
                if not pages:
                    continue

                cur_fmt_date = f"{current_ymd[:4]}/{current_ymd[4:6]}/{current_ymd[6:8]}"
                article_idx = 0

                for page in pages:
                    page_elem = page.select_one(".page_notation")
                    section = page_elem.text.strip() if page_elem else "지면"
                    if not section.endswith("면") and "면" not in section:
                        section += "면"

                    items = page.select("ul.newspaper_article_lst li a")
                    for item in items:
                        title_elem = item.select_one("strong") or item
                        clean_title = BeautifulSoup(title_elem.text, "html.parser").text.strip()
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
                        "sections": list(categorized.keys()),
                        "categorized": categorized,
                        "articles": all_articles
                    }
        except Exception as e:
            print(f"Paper print fetch error for {provider} ({current_ymd}):", e)

    # Fallback to Press Main page if newspaper edition is not found or empty
    if not all_articles:
        try:
            main_url = f"https://media.naver.com/press/{press_code}"
            res_main = requests.get(main_url, headers=headers, verify=False, timeout=6)
            if res_main.status_code == 200:
                soup_main = BeautifulSoup(res_main.text, "html.parser")
                main_items = soup_main.select("a.press_edit_news_link, a.cjs_news_a, li.cjs_news_item a")
                cur_fmt_date = datetime.now(timezone(timedelta(hours=9))).strftime("%Y/%m/%d")
                article_idx = 0
                for item in main_items:
                    clean_title = item.text.strip()
                    href = item.get("href", "")
                    if not clean_title or not href or len(clean_title) < 5:
                        continue
                    if href.startswith("//"):
                        href = "https:" + href

                    section = "주요뉴스"
                    article_obj = {
                        "id": f"{provider}_main_{article_idx}",
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
        except Exception as e:
            print(f"Fallback press main fetch error for {provider}:", e)

    return {
        "sections": list(categorized.keys()),
        "categorized": categorized,
        "articles": all_articles
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




