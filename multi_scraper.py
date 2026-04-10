"""
多源安全情报爬虫 - ThreatPulse 安全情报聚合平台
数据源：FreeBuf、安全客(Anquanke)、The Hacker News、奇安信 XLab

聚焦方向：
  - AI Agent 新技术
  - 大模型(LLM)新技术
  - AI + DDoS
  - AI + 渗透测试
  - AI + Web 防护
"""

import os
import re
import json
import time
import random
import hashlib
import logging
import requests
import xml.etree.ElementTree as ET
from html import unescape
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from db_cnsec import insert_cnsec_article, article_exists
from db import check_duplicate_by_summary_cn
from deepseek_summarizer import generate_summary

# ============ 配置 ============

# 每个数据源最多采集多少篇
MAX_ARTICLES_PER_SOURCE = 30

# 只接收最近 N 天内发布的文章
MAX_AGE_DAYS = 3

# 请求配置
REQUEST_TIMEOUT = 30
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
MIN_DELAY = 1.0
MAX_DELAY = 3.0

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("multi_scraper")

# HTTP 会话
session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
})


def polite_delay():
    """礼貌延迟"""
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


def is_article_too_old(publish_time: str, max_age_days: int = MAX_AGE_DAYS) -> bool:
    """
    检查文章是否超过最大允许天数
    支持多种时间格式：
      - "2026-04-09 08:06:06"
      - "2026-04-09T08:06:06Z"
      - "2026-04-09"
    返回 True 表示文章太旧，应该跳过
    """
    if not publish_time:
        return False  # 没有时间信息，不过滤

    cutoff = datetime.now() - timedelta(days=max_age_days)

    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S+00:00"]:
        try:
            pub_dt = datetime.strptime(publish_time[:26], fmt)
            if pub_dt.tzinfo:
                pub_dt = pub_dt.replace(tzinfo=None)
            return pub_dt < cutoff
        except ValueError:
            continue

    # 尝试 RFC 2822 格式 (RSS feeds)
    try:
        pub_dt = parsedate_to_datetime(publish_time)
        pub_dt = pub_dt.replace(tzinfo=None)
        return pub_dt < cutoff
    except Exception:
        pass

    return False  # 解析失败不过滤


def strip_html(text: str) -> str:
    """去掉 HTML 标签"""
    if not text:
        return ""
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</p>', '\n', text)
    text = re.sub(r'</div>', '\n', text)
    text = re.sub(r'</li>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ============ 通用分类与评级 ============

# 关注的关键词方向（用于过滤和分类）
FOCUS_KEYWORDS = {
    "agent": [
        "ai agent", "智能体", "mcp", "autonomous agent", "agent security",
        "agentic", "tool use", "function calling", "agent framework",
        "crewai", "autogen", "langchain agent", "agent exploit",
        "agent vulnerability", "multi-agent", "agent orchestration",
    ],
    "llm": [
        "llm", "大模型", "大语言模型", "gpt", "claude", "gemini", "deepseek",
        "prompt injection", "jailbreak", "model poisoning", "rag",
        "fine-tuning", "rlhf", "transformer", "token", "embedding",
        "openai", "anthropic", "mistral", "llama", "qwen",
        "model security", "ai safety", "alignment",
    ],
    "ddos": [
        "ddos", "botnet", "僵尸网络", "流量攻击", "拒绝服务",
        "volumetric", "amplification", "反射攻击", "cc攻击",
        "ai ddos", "ai检测ddos", "机器学习ddos", "智能防护",
    ],
    "pentest": [
        "渗透测试", "penetration test", "红队", "red team", "漏洞利用",
        "exploit", "metasploit", "cobalt strike", "ai渗透",
        "自动化渗透", "ai exploit", "ai红队", "ai攻防",
    ],
    "webdef": [
        "waf", "web防护", "web安全", "xss", "sql injection", "csrf",
        "ssrf", "ai waf", "智能waf", "web application firewall",
        "api安全", "api security", "web攻防",
    ],
    "vuln": [
        "漏洞", "cve", "0day", "零日", "rce", "远程代码执行",
        "权限提升", "privilege escalation", "缓冲区溢出",
        "反序列化", "注入", "supply chain", "供应链",
    ],
    "malware": [
        "恶意软件", "勒索", "木马", "后门", "c2", "挖矿",
        "蠕虫", "ransomware", "malware", "trojan", "backdoor",
        "apt", "apt28", "apt29", "lazarus",
    ],
}


def classify_article(title: str, summary: str, tags: list = None, source_hint: str = "") -> dict:
    """根据文章内容自动分类和评级"""
    combined = f"{title} {summary} {' '.join(tags or [])} {source_hint}".lower()

    # 分类（按优先级）
    cat = "general"
    for category, keywords in FOCUS_KEYWORDS.items():
        if any(k in combined for k in keywords):
            cat = category
            break

    # 严重等级
    severity = "low"
    if any(k in combined for k in ["严重", "critical", "0day", "零日", "rce", "远程代码执行", "紧急", "在野利用", "actively exploited", "zero-day"]):
        severity = "critical"
    elif any(k in combined for k in ["高危", "high", "数据泄露", "breach", "重大", "大规模攻击", "cvss.*[89]"]):
        severity = "high"
    elif any(k in combined for k in ["中危", "medium", "新版本", "发布", "更新", "moderate"]):
        severity = "medium"

    return {"category": cat, "severity": severity}


def is_relevant(title: str, summary: str) -> bool:
    """
    判断文章是否与关注方向相关
    放宽过滤：安全相关的都收录
    """
    combined = f"{title} {summary}".lower()
    # 安全相关的通用关键词
    security_keywords = [
        "安全", "漏洞", "攻击", "防护", "恶意", "威胁", "exploit", "vulnerability",
        "malware", "attack", "security", "hack", "breach", "ransomware", "phishing",
        "botnet", "ddos", "apt", "cve", "zero-day", "backdoor", "trojan",
        "ai", "llm", "agent", "大模型", "智能", "机器学习", "深度学习",
        "渗透", "红队", "waf", "web安全", "防火墙",
    ]
    return any(k in combined for k in security_keywords)


# ============ FreeBuf 爬虫 ============

class FreeBufScraper:
    """FreeBuf 安全媒体爬虫 - 使用官方 API"""

    SOURCE_NAME = "FreeBuf"
    SOURCE_ICON = "ri-fire-line"
    ID_PREFIX = "freebuf_"
    BASE_URL = "https://www.freebuf.com"
    API_URL = "https://www.freebuf.com/fapi/frontend/category/list"

    # FreeBuf 的 AI 安全标签
    TAGS_TO_CRAWL = ["AI", ""]  # 空字符串 = 全部文章

    # FreeBuf WAF 可能封锁某些 IP，支持从预抓取的 JSON 文件读取
    JSON_FALLBACK = "freebuf_articles.json"

    def fetch_articles(self) -> list:
        """从 FreeBuf API 获取文章列表（支持 JSON 文件回退）"""
        all_articles = []
        seen_ids = set()

        # 先尝试 API
        api_success = False
        for tag in self.TAGS_TO_CRAWL:
            for page in range(1, 4):  # 最多3页
                try:
                    params = {
                        "name": "articles",
                        "tag": tag,
                        "limit": 20,
                        "page": page,
                        "select": 0,
                        "order": 0,
                    }
                    headers = {
                        "Referer": "https://www.freebuf.com/articles",
                        "Accept": "application/json, text/plain, */*",
                    }
                    resp = session.get(self.API_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
                    resp.raise_for_status()
                    data = resp.json()

                    items = data.get("data", {}).get("data_list", [])
                    if not items:
                        break

                    tag_label = tag if tag else "全部"
                    logger.info(f"  📄 [FreeBuf/{tag_label}] 第{page}页: {len(items)} 篇")

                    for item in items:
                        article_id = str(item.get("ID", ""))
                        if not article_id or article_id in seen_ids:
                            continue
                        seen_ids.add(article_id)

                        title = item.get("post_title", "")
                        summary = item.get("content", "")  # FreeBuf API 的 content 是摘要
                        read_count = item.get("read_count", 0)
                        category = item.get("category", "")
                        post_date = item.get("post_date", "")
                        nickname = item.get("nickname", "")
                        url = f"{self.BASE_URL}{item.get('url', '')}"

                        if not is_relevant(title, summary):
                            continue

                        all_articles.append({
                            "article_id": article_id,
                            "title": title,
                            "summary": strip_html(summary),
                            "full_text": strip_html(summary),
                            "heat": read_count,
                            "tags": [category] if category else [],
                            "link": url,
                            "publish_time": post_date,
                            "author": nickname,
                        })

                    polite_delay()
                    api_success = True
                except Exception as e:
                    logger.warning(f"  ⚠️ FreeBuf API 请求失败: {e}")
                    break

        # 如果 API 失败（如被 WAF 封锁），尝试从 JSON 文件读取
        if not all_articles and not api_success:
            json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.JSON_FALLBACK)
            if os.path.exists(json_path):
                logger.info(f"  📂 API 不可用，从 {self.JSON_FALLBACK} 读取")
                try:
                    with open(json_path, "r") as f:
                        raw_articles = json.load(f)
                    for item in raw_articles:
                        article_id = str(item.get("id", ""))
                        if not article_id or article_id in seen_ids:
                            continue
                        seen_ids.add(article_id)
                        title = item.get("title", "")
                        summary = strip_html(item.get("summary", ""))
                        if not is_relevant(title, summary):
                            continue
                        all_articles.append({
                            "article_id": article_id,
                            "title": title,
                            "summary": summary,
                            "full_text": summary,
                            "heat": item.get("read_count", 0),
                            "tags": [item.get("category", "")] if item.get("category") else [],
                            "link": item.get("url", ""),
                            "publish_time": item.get("date", ""),
                            "author": item.get("nickname", ""),
                        })
                except Exception as e:
                    logger.warning(f"  ⚠️ JSON 文件读取失败: {e}")
            else:
                logger.warning(f"  ⚠️ FreeBuf API 不可用且无 JSON 回退文件")

        logger.info(f"  📊 FreeBuf 共采集 {len(all_articles)} 篇相关文章")
        return all_articles[:MAX_ARTICLES_PER_SOURCE]

    def run(self) -> int:
        """运行 FreeBuf 爬虫"""
        logger.info("🔵 FreeBuf 爬虫启动")
        articles = self.fetch_articles()
        return self._save_articles(articles)

    def _save_articles(self, articles: list) -> int:
        success = 0
        for i, art in enumerate(articles, 1):
            unique_id = f"{self.ID_PREFIX}{art['article_id']}"
            if article_exists_by_tweet_id(unique_id):
                continue

            # 时间过滤：跳过超过 MAX_AGE_DAYS 天前发布的文章
            if is_article_too_old(art.get("publish_time", "")):
                logger.info(f"  🕐 [FreeBuf] 跳过旧文章: {art['title'][:40]} (发布于 {art.get('publish_time', '?')})")
                continue

            logger.info(f"  📰 [{i}/{len(articles)}] {art['title'][:50]}")

            classify = classify_article(art["title"], art["summary"], art.get("tags", []))

            # DeepSeek 中文摘要
            summary_cn = generate_summary(art["title"], art.get("full_text", "") or art["summary"])
            if summary_cn and check_duplicate_by_summary_cn(summary_cn):
                logger.info(f"    🔄 中文摘要去重: 跳过")
                continue

            article_data = {
                "article_id": unique_id,  # 直接传完整 ID
                "title": art["title"][:80],
                "summary": art["summary"],
                "summary_cn": summary_cn,
                "full_text": art.get("full_text", ""),
                "category": classify["category"],
                "severity": classify["severity"],
                "source": f"FreeBuf",
                "source_icon": self.SOURCE_ICON,
                "tags": art.get("tags", []),
                "heat": art.get("heat", 0),
                "link": art["link"],
                "publish_time": art.get("publish_time", ""),
            }

            if insert_article_generic(article_data):
                success += 1
                logger.info(f"    ✅ 入库 [{classify['category']}/{classify['severity']}]")
            else:
                logger.info(f"    ⏭️ 跳过")

            polite_delay()

        return success


# ============ 安全客爬虫 ============

class AnquankeScraper:
    """安全客(360)爬虫 - 使用官方 API"""

    SOURCE_NAME = "安全客"
    SOURCE_ICON = "ri-shield-star-line"
    ID_PREFIX = "anquanke_"
    API_URL = "https://api.anquanke.com/data/v1/posts"

    def fetch_articles(self) -> list:
        """从安全客 API 获取文章列表"""
        all_articles = []
        seen_ids = set()

        for page in range(1, 4):  # 最多3页
            try:
                params = {"size": 20, "page": page}
                resp = session.get(self.API_URL, params=params, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()

                items = data.get("data", [])
                if not items:
                    break

                logger.info(f"  📄 [安全客] 第{page}页: {len(items)} 篇")

                for item in items:
                    article_id = str(item.get("id", ""))
                    if not article_id or article_id in seen_ids:
                        continue
                    seen_ids.add(article_id)

                    title = item.get("title", "")
                    desc = item.get("desc", "")
                    category_name = item.get("category_name", "")
                    tags = item.get("tags", [])
                    pv = item.get("pv", 0)
                    date = item.get("date", "")
                    author = item.get("author", {}).get("nickname", "")
                    url = f"https://www.anquanke.com/post/id/{article_id}"

                    # 安全客内容都是安全相关，全部收录
                    all_articles.append({
                        "article_id": article_id,
                        "title": title,
                        "summary": desc or title,
                        "full_text": desc or title,
                        "heat": pv,
                        "tags": tags + ([category_name] if category_name else []),
                        "link": url,
                        "publish_time": date,
                        "author": author,
                    })

                polite_delay()
            except Exception as e:
                logger.warning(f"  ⚠️ 安全客 API 请求失败: {e}")
                break

        logger.info(f"  📊 安全客 共采集 {len(all_articles)} 篇文章")
        return all_articles[:MAX_ARTICLES_PER_SOURCE]

    def run(self) -> int:
        """运行安全客爬虫"""
        logger.info("🟢 安全客爬虫启动")
        articles = self.fetch_articles()
        return self._save_articles(articles)

    def _save_articles(self, articles: list) -> int:
        success = 0
        for i, art in enumerate(articles, 1):
            unique_id = f"{self.ID_PREFIX}{art['article_id']}"
            if article_exists_by_tweet_id(unique_id):
                continue

            # 时间过滤：跳过超过 MAX_AGE_DAYS 天前发布的文章
            if is_article_too_old(art.get("publish_time", "")):
                logger.info(f"  🕐 [安全客] 跳过旧文章: {art['title'][:40]} (发布于 {art.get('publish_time', '?')})")
                continue

            logger.info(f"  📰 [{i}/{len(articles)}] {art['title'][:50]}")

            classify = classify_article(art["title"], art["summary"], art.get("tags", []))

            summary_cn = generate_summary(art["title"], art.get("full_text", "") or art["summary"])
            if summary_cn and check_duplicate_by_summary_cn(summary_cn):
                logger.info(f"    🔄 中文摘要去重: 跳过")
                continue

            article_data = {
                "article_id": unique_id,
                "title": art["title"][:80],
                "summary": art["summary"],
                "summary_cn": summary_cn,
                "full_text": art.get("full_text", ""),
                "category": classify["category"],
                "severity": classify["severity"],
                "source": "安全客",
                "source_icon": self.SOURCE_ICON,
                "tags": art.get("tags", []),
                "heat": art.get("heat", 0),
                "link": art["link"],
                "publish_time": art.get("publish_time", ""),
            }

            if insert_article_generic(article_data):
                success += 1
                logger.info(f"    ✅ 入库 [{classify['category']}/{classify['severity']}]")
            else:
                logger.info(f"    ⏭️ 跳过")

            polite_delay()

        return success


# ============ The Hacker News 爬虫 ============

class HackerNewsScraper:
    """The Hacker News 爬虫 - 使用 RSS Feed"""

    SOURCE_NAME = "The Hacker News"
    SOURCE_ICON = "ri-newspaper-line"
    ID_PREFIX = "thn_"
    RSS_URL = "https://feeds.feedburner.com/TheHackersNews"

    def fetch_articles(self) -> list:
        """从 RSS 获取文章列表"""
        all_articles = []

        try:
            resp = session.get(self.RSS_URL, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            items = root.findall('.//item')
            logger.info(f"  📄 [The Hacker News] RSS 获取 {len(items)} 篇")

            for item in items:
                title = item.find('title')
                title = title.text if title is not None else ""
                link = item.find('link')
                link = link.text if link is not None else ""
                description = item.find('description')
                desc_text = description.text if description is not None else ""
                pub_date = item.find('pubDate')
                pub_date_text = pub_date.text if pub_date is not None else ""

                # 从 link 提取唯一 ID
                # https://thehackernews.com/2026/04/xxx.html → xxx
                article_id = link.rstrip('/').split('/')[-1].replace('.html', '') if link else ""
                if not article_id:
                    continue

                # 解析发布时间
                publish_time = ""
                if pub_date_text:
                    try:
                        dt = parsedate_to_datetime(pub_date_text)
                        publish_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        publish_time = pub_date_text

                summary = strip_html(desc_text)

                if not is_relevant(title, summary):
                    continue

                all_articles.append({
                    "article_id": article_id,
                    "title": title,
                    "summary": summary,
                    "full_text": summary,
                    "heat": 0,
                    "tags": ["The Hacker News"],
                    "link": link,
                    "publish_time": publish_time,
                    "author": "The Hacker News",
                })

        except Exception as e:
            logger.warning(f"  ⚠️ The Hacker News RSS 获取失败: {e}")

        logger.info(f"  📊 The Hacker News 共采集 {len(all_articles)} 篇相关文章")
        return all_articles[:MAX_ARTICLES_PER_SOURCE]

    def run(self) -> int:
        """运行 The Hacker News 爬虫"""
        logger.info("🔴 The Hacker News 爬虫启动")
        articles = self.fetch_articles()
        return self._save_articles(articles)

    def _save_articles(self, articles: list) -> int:
        success = 0
        for i, art in enumerate(articles, 1):
            unique_id = f"{self.ID_PREFIX}{art['article_id']}"
            if article_exists_by_tweet_id(unique_id):
                continue

            # 时间过滤：跳过超过 MAX_AGE_DAYS 天前发布的文章
            if is_article_too_old(art.get("publish_time", "")):
                logger.info(f"  🕐 [THN] 跳过旧文章: {art['title'][:40]} (发布于 {art.get('publish_time', '?')})")
                continue

            logger.info(f"  📰 [{i}/{len(articles)}] {art['title'][:60]}")

            classify = classify_article(art["title"], art["summary"], art.get("tags", []))

            summary_cn = generate_summary(art["title"], art.get("full_text", "") or art["summary"])
            if summary_cn and check_duplicate_by_summary_cn(summary_cn):
                logger.info(f"    🔄 中文摘要去重: 跳过")
                continue

            article_data = {
                "article_id": unique_id,
                "title": art["title"][:80],
                "summary": art["summary"],
                "summary_cn": summary_cn,
                "full_text": art.get("full_text", ""),
                "category": classify["category"],
                "severity": classify["severity"],
                "source": "The Hacker News",
                "source_icon": self.SOURCE_ICON,
                "tags": art.get("tags", []),
                "heat": art.get("heat", 0),
                "link": art["link"],
                "publish_time": art.get("publish_time", ""),
            }

            if insert_article_generic(article_data):
                success += 1
                logger.info(f"    ✅ 入库 [{classify['category']}/{classify['severity']}]")
            else:
                logger.info(f"    ⏭️ 跳过")

            polite_delay()

        return success


# ============ 奇安信 XLab 爬虫 ============

class QianxinXLabScraper:
    """奇安信 XLab 博客爬虫 - 使用 RSS Feed"""

    SOURCE_NAME = "奇安信 XLab"
    SOURCE_ICON = "ri-microscope-line"
    ID_PREFIX = "xlab_"
    RSS_URL = "https://blog.xlab.qianxin.com/rss/"
    BASE_URL = "https://blog.xlab.qianxin.com"

    def fetch_articles(self) -> list:
        """从 RSS 获取文章列表"""
        all_articles = []

        try:
            resp = session.get(self.RSS_URL, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            items = root.findall('.//item')
            logger.info(f"  📄 [奇安信 XLab] RSS 获取 {len(items)} 篇")

            for item in items:
                title = item.find('title')
                title = title.text if title is not None else ""
                link = item.find('link')
                link = link.text if link is not None else ""
                description = item.find('description')
                desc_html = description.text if description is not None else ""
                pub_date = item.find('pubDate')
                pub_date_text = pub_date.text if pub_date is not None else ""

                # content:encoded 包含完整正文
                content_encoded = item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
                full_html = content_encoded.text if content_encoded is not None else desc_html

                # 从 link 提取唯一 ID
                article_id = link.rstrip('/').split('/')[-1] if link else ""
                if not article_id:
                    continue

                # 解析发布时间
                publish_time = ""
                if pub_date_text:
                    try:
                        dt = parsedate_to_datetime(pub_date_text)
                        publish_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        publish_time = pub_date_text

                summary = strip_html(desc_html)[:500]
                full_text = strip_html(full_html)

                # XLab 内容都是安全研究，全部收录
                all_articles.append({
                    "article_id": article_id,
                    "title": title,
                    "summary": summary,
                    "full_text": full_text[:5000],  # 限制全文长度
                    "heat": 0,
                    "tags": ["奇安信", "XLab"],
                    "link": link,
                    "publish_time": publish_time,
                    "author": "奇安信 XLab",
                })

        except Exception as e:
            logger.warning(f"  ⚠️ 奇安信 XLab RSS 获取失败: {e}")

        logger.info(f"  📊 奇安信 XLab 共采集 {len(all_articles)} 篇文章")
        return all_articles[:MAX_ARTICLES_PER_SOURCE]

    def run(self) -> int:
        """运行奇安信 XLab 爬虫"""
        logger.info("🟠 奇安信 XLab 爬虫启动")
        articles = self.fetch_articles()
        return self._save_articles(articles)

    def _save_articles(self, articles: list) -> int:
        success = 0
        for i, art in enumerate(articles, 1):
            unique_id = f"{self.ID_PREFIX}{art['article_id']}"
            if article_exists_by_tweet_id(unique_id):
                continue

            # 时间过滤：跳过超过 MAX_AGE_DAYS 天前发布的文章
            if is_article_too_old(art.get("publish_time", "")):
                logger.info(f"  🕐 [XLab] 跳过旧文章: {art['title'][:40]} (发布于 {art.get('publish_time', '?')})")
                continue

            logger.info(f"  📰 [{i}/{len(articles)}] {art['title'][:50]}")

            classify = classify_article(art["title"], art["summary"], art.get("tags", []))

            summary_cn = generate_summary(art["title"], art.get("full_text", "") or art["summary"])
            if summary_cn and check_duplicate_by_summary_cn(summary_cn):
                logger.info(f"    🔄 中文摘要去重: 跳过")
                continue

            article_data = {
                "article_id": unique_id,
                "title": art["title"][:80],
                "summary": art["summary"],
                "summary_cn": summary_cn,
                "full_text": art.get("full_text", ""),
                "category": classify["category"],
                "severity": classify["severity"],
                "source": "奇安信 XLab",
                "source_icon": self.SOURCE_ICON,
                "tags": art.get("tags", []),
                "heat": art.get("heat", 0),
                "link": art["link"],
                "publish_time": art.get("publish_time", ""),
            }

            if insert_article_generic(article_data):
                success += 1
                logger.info(f"    ✅ 入库 [{classify['category']}/{classify['severity']}]")
            else:
                logger.info(f"    ⏭️ 跳过")

            polite_delay()

        return success


# ============ 通用数据库操作 ============

import pymysql
from contextlib import contextmanager

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": os.environ.get("DB_USER", "threatpulse"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "threatpulse"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


@contextmanager
def get_connection():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def article_exists_by_tweet_id(tweet_id: str) -> bool:
    """检查文章是否已入库"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM intel_items WHERE tweet_id = %s LIMIT 1",
                    (tweet_id,)
                )
                return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"检查文章是否存在失败 [{tweet_id}]: {e}")
        return False


def insert_article_generic(article: dict) -> bool:
    """通用文章入库函数"""
    tweet_id = article["article_id"]  # 已经是完整的带前缀 ID

    # 判断语言
    title = article.get("title", "")
    is_chinese = bool(re.search(r'[\u4e00-\u9fff]', title))
    lang = "zh" if is_chinese else "en"

    # 来源标识
    source_map = {
        "freebuf_": "freebuf",
        "anquanke_": "anquanke",
        "thn_": "thehackernews",
        "xlab_": "xlab",
    }
    keyword = "multi-source"
    for prefix, kw in source_map.items():
        if tweet_id.startswith(prefix):
            keyword = kw
            break

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                INSERT IGNORE INTO intel_items
                (tweet_id, title, summary, summary_cn, full_text, category, severity,
                 source, source_icon, tags, heat, comments, ioc, link,
                 keyword, user_name, user_screen_name, user_followers,
                 retweet_count, favorite_count, reply_count, quote_count,
                 lang, tweet_created_at)
                VALUES
                (%s, %s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s)
                """
                params = (
                    tweet_id,
                    article.get("title", ""),
                    article.get("summary", ""),
                    article.get("summary_cn", None),
                    article.get("full_text", ""),
                    article.get("category", "general"),
                    article.get("severity", "low"),
                    article.get("source", ""),
                    article.get("source_icon", "ri-newspaper-line"),
                    json.dumps(article.get("tags", []), ensure_ascii=False),
                    article.get("heat", 0),
                    0,
                    json.dumps([], ensure_ascii=False),
                    article.get("link", ""),
                    keyword,
                    article.get("source", ""),
                    article.get("source", ""),
                    0, 0, 0, 0, 0,
                    lang,
                    article.get("publish_time", ""),
                )
                cursor.execute(sql, params)
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"插入文章失败 [{tweet_id}]: {e}")
        return False


# ============ 主入口 ============

def run_all():
    """运行所有爬虫"""
    logger.info("=" * 60)
    logger.info("🚀 多源安全情报爬虫启动")
    logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    results = {}

    scrapers = [
        ("FreeBuf", FreeBufScraper()),
        ("安全客", AnquankeScraper()),
        ("The Hacker News", HackerNewsScraper()),
        ("奇安信 XLab", QianxinXLabScraper()),
    ]

    for name, scraper in scrapers:
        try:
            count = scraper.run()
            results[name] = count
            logger.info(f"  ✅ {name}: 新增 {count} 篇\n")
        except Exception as e:
            logger.error(f"  ❌ {name} 爬虫异常: {e}")
            results[name] = -1

    logger.info("=" * 60)
    logger.info("🎉 多源爬虫完成！汇总：")
    total = 0
    for name, count in results.items():
        status = f"新增 {count} 篇" if count >= 0 else "❌ 异常"
        logger.info(f"  {name}: {status}")
        if count > 0:
            total += count
    logger.info(f"  总计新增: {total} 篇")
    logger.info("=" * 60)

    return total


if __name__ == "__main__":
    run_all()
