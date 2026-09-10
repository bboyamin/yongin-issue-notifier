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

# Add project root to sys.path so we can import src.local_issue_collector
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from src.local_issue_collector import collect_all_issues
except ImportError:
    def collect_all_issues(keywords=None):
        return []

def fetch_etnews_from_pdf(ymd_str):
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
            res = session.get(url, headers=headers, verify=False, timeout=6)
            if res.status_code == 200 and len(res.text) > 2000:
                html_text = res.text
                break
        except Exception as e:
            print(f"ETNews PDF fetch error for {url}: {e}")
            continue
            
    if not html_text:
        return None
        
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        boxes = soup.find_all("div", class_="box") or soup.find_all("dl", class_="box") or soup.find_all("div", class_="pdf_box")
        
        if not boxes:
            return None
            
        categorized = {}
        all_articles = []
        formatted_date = f"{ymd_str[:4]}/{ymd_str[4:6]}/{ymd_str[6:8]}" if len(ymd_str) == 8 else ymd_str
        
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
        if all_articles:
            return {
                "sections": sections,
                "categorized": categorized,
                "articles": all_articles
            }
    except Exception as e:
        print(f"ETNews PDF parse error: {e}")
        
    return None

def fetch_etnews_from_rss():
    rss_url = "https://news.google.com/rss/search?q=site:etnews.com+when:3d&hl=ko&gl=KR&ceid=KR:ko"
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
                clean_title = raw_title.replace(" - 전자신문", "").strip()
                link = item.link.text.strip() if item.link else ""
                
                section = "전자·산업"
                if any(k in clean_title for k in ["AI", "SW", "소프트웨어", "보안", "클라우드", "데이터"]):
                    section = "AI·SW·보안"
                elif any(k in clean_title for k in ["반도체", "디스플레이", "삼성", "SK", "LG", "모바일", "스마트폰"]):
                    section = "IT·반도체"
                elif any(k in clean_title for k in ["정부", "정책", "정치", "국회", "부처", "금융"]):
                    section = "정치·금융·정책"
                elif any(k in clean_title for k in ["게임", "통신", "방송", "콘텐츠", "플랫폼"]):
                    section = "통신·방송·게임"

                article_obj = {
                    "id": f"etnews_rss_{idx}_{int(datetime.now().timestamp())}",
                    "keyword": "전자신문",
                    "type": "news",
                    "badge": f"📰 전자신문 · {section}",
                    "publisher": "전자신문",
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

            sections = list(categorized.keys())
            return {
                "sections": sections,
                "categorized": categorized,
                "articles": all_articles
            }
    except Exception as e:
        print("ETNews RSS fallback error:", e)

    return {"sections": [], "categorized": {}, "articles": []}

def fetch_etnews_by_date(ymd_str):
    result = fetch_etnews_from_pdf(ymd_str)
    if not result or not result.get("articles"):
        try:
            dt_obj = datetime.strptime(ymd_str, "%Y%m%d")
            for i in range(1, 4):
                prev_ymd = (dt_obj - timedelta(days=i)).strftime("%Y%m%d")
                fallback = fetch_etnews_from_pdf(prev_ymd)
                if fallback and fallback.get("articles"):
                    result = fallback
                    break
        except Exception:
            pass

    if not result or not result.get("articles"):
        result = fetch_etnews_from_rss()

    return result

def get_etnews_article_body(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://pdf.etnews.com/"
    }
    try:
        res = requests.get(url, headers=headers, verify=False, timeout=8)
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

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path_str = parsed.path.lower()
        params = urllib.parse.parse_qs(parsed.query)

        # --------------------------------------------------
        # 1. Route for ETNews (전자신문 지면 기사)
        # --------------------------------------------------
        is_etnews = ("etnews" in path_str) or ("date" in params) or ("ymd" in params) or (params.get('mode', [None])[0] == 'etnews') or ("url" in params)
        if is_etnews:
            article_url = params.get('url', [None])[0]
            if article_url:
                content = get_etnews_article_body(article_url)
                response_data = {"url": article_url, "content": content or ""}
            else:
                date_param = params.get('date', [None])[0] or params.get('ymd', [None])[0]
                if not date_param:
                    kst = timezone(timedelta(hours=9))
                    date_param = datetime.now(kst).strftime("%Y%m%d")
                
                ymd_str = date_param.replace("-", "").strip()
                result = fetch_etnews_by_date(ymd_str)
                response_data = result

            body = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 's-maxage=300, stale-while-revalidate=600')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # --------------------------------------------------
        # 2. Route for Yongin Live Issues (/api/collect)
        # --------------------------------------------------
        kw_str = params.get('keywords', ['용인시,처인구'])[0]
        keywords = [k.strip() for k in kw_str.split(',') if k.strip()]
        
        static_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "public", "data", "issues.json"))
        if not os.path.exists(static_file):
            static_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "LocalIssueNotifier", "data", "issues.json"))

        static_issues = []
        if os.path.exists(static_file):
            try:
                with open(static_file, 'r', encoding='utf-8') as f:
                    static_issues = json.load(f)
            except Exception:
                pass

        try:
            live_issues = collect_all_issues(keywords=keywords)
            if len(live_issues) >= 10:
                issues = live_issues
            else:
                issues = static_issues if len(static_issues) > len(live_issues) else live_issues
        except Exception as e:
            print("Vercel collect error:", e)
            issues = static_issues

        body = json.dumps(issues, ensure_ascii=False).encode('utf-8')
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
