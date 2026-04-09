"""
CN-SEC 中文网爬虫 - ThreatPulse 安全情报聚合平台
从 cn-sec.com 采集 Web安全/AI安全/漏洞 相关文章

分类覆盖：
  - 安全漏洞: https://cn-sec.com/archives/category/安全漏洞
  - 安全新闻: https://cn-sec.com/archives/category/安全新闻
  - 安全文章: https://cn-sec.com/archives/category/安全文章
  - 人工智能安全: https://cn-sec.com/archives/category/安全文章/人工智能安全
  - 安全博客: https://cn-sec.com/archives/category/安全博客
"""

import re
import json
import time
import random
import hashlib
import logging
import requests
from urllib.parse import quote, urljoin
from datetime import datetime

from db_cnsec import insert_cnsec_article, article_exists

# ============ 配置 ============

# 要爬取的分类（中文名 → URL路径）
CATEGORIES = {
    "安全漏洞": "https://cn-sec.com/archives/category/%e5%ae%89%e5%85%a8%e6%bc%8f%e6%b4%9e",
    "安全新闻": "https://cn-sec.com/archives/category/%e5%ae%89%e5%85%a8%e6%96%b0%e9%97%bb",
    "安全文章": "https://cn-sec.com/archives/category/%e5%ae%89%e5%85%a8%e6%96%87%e7%ab%a0",
    "人工智能安全": "https://cn-sec.com/archives/category/%e5%ae%89%e5%85%a8%e6%96%87%e7%ab%a0/%e4%ba%ba%e5%b7%a5%e6%99%ba%e8%83%bd%e5%ae%89%e5%85%a8",
    "安全博客": "https://cn-sec.com/archives/category/%e5%ae%89%e5%85%a8%e5%8d%9a%e5%ae%a2",
}

# 每个分类最多爬几页（每页约10篇）
MAX_PAGES_PER_CATEGORY = 2

# 每次爬虫最多采集多少篇文章详情（防止耗时过长）
MAX_ARTICLES_TOTAL = 60

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
logger = logging.getLogger("cnsec_scraper")


# ============ HTTP 请求 ============

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
})


def fetch_page(url: str, retries: int = 3) -> str:
    """获取页面 HTML，带重试"""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except Exception as e:
            logger.warning(f"请求失败 [{attempt+1}/{retries}] {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return ""


def polite_delay():
    """礼貌延迟，避免对目标站造成压力"""
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


# ============ 列表页解析 ============

def parse_article_list(html: str) -> list:
    """
    从分类列表页提取文章基本信息
    返回: [{ article_id, title, url, summary, tags, relative_time }]
    """
    articles = []

    # 匹配每篇文章的 <article> 块
    article_pattern = re.compile(
        r'<article\s+id="post-(\d+)".*?</article>',
        re.DOTALL
    )

    for match in article_pattern.finditer(html):
        block = match.group(0)
        article_id = match.group(1)

        # 标题和链接
        title_match = re.search(
            r'<h2 class="entry-title[^"]*">\s*<a href="([^"]+)"[^>]*>([^<]+)</a>',
            block
        )
        if not title_match:
            continue
        url = title_match.group(1)
        title = title_match.group(2).strip()

        # 摘要
        summary = ""
        summary_match = re.search(
            r'<div class="archive-content">\s*(.*?)\s*</div>',
            block, re.DOTALL
        )
        if summary_match:
            summary = re.sub(r'<[^>]+>', '', summary_match.group(1)).strip()

        # 标签
        tags = []
        tag_pattern = re.compile(r'class="tag-cloud-link[^"]*"[^>]*>([^<]+)</a>')
        for tag_match in tag_pattern.finditer(block):
            tag_text = tag_match.group(1).strip()
            if tag_text:
                tags.append(tag_text)

        # 相对时间
        relative_time = ""
        time_match = re.search(r'<span class="date">([^<]+)</span>', block)
        if time_match:
            relative_time = time_match.group(1).strip()

        # 浏览量
        views = 0
        views_match = re.search(r'(\d+)\s*views', block)
        if views_match:
            views = int(views_match.group(1))

        articles.append({
            "article_id": article_id,
            "title": title,
            "url": url,
            "summary": summary,
            "tags": tags,
            "relative_time": relative_time,
            "views": views,
        })

    return articles


# ============ 详情页解析 ============

def parse_article_detail(html: str) -> dict:
    """
    从文章详情页提取完整信息
    返回: { full_text, publish_time, views, word_count }
    """
    result = {
        "full_text": "",
        "publish_time": "",
        "views": 0,
        "word_count": 0,
    }

    # 发布时间: <meta property="og:release_date" content="2026年4月9日08:06:06" />
    time_match = re.search(
        r'<meta\s+property="og:release_date"\s+content="([^"]+)"',
        html
    )
    if time_match:
        raw_time = time_match.group(1)
        # 转为标准格式: "2026年4月9日08:06:06" → "2026-04-09 08:06:06"
        result["publish_time"] = normalize_cn_datetime(raw_time)

    # 备选：从 my-date span 提取
    if not result["publish_time"]:
        time_match2 = re.search(
            r'<span class="my-date">.*?(\d{4})年(\d{1,2})月(\d{1,2})日.*?(\d{2}:\d{2}:\d{2})',
            html, re.DOTALL
        )
        if time_match2:
            y, m, d, t = time_match2.groups()
            result["publish_time"] = f"{y}-{int(m):02d}-{int(d):02d} {t}"

    # 浏览量
    views_match = re.search(r'(\d+)\s*views', html)
    if views_match:
        result["views"] = int(views_match.group(1))

    # 字数
    word_match = re.search(r'字数\s*(\d+)', html)
    if word_match:
        result["word_count"] = int(word_match.group(1))

    # 正文内容: <div class="entry-content"> ... </div><!-- .entry-content -->
    content_match = re.search(
        r'<div class="entry-content">(.*?)</div><!-- \.entry-content -->',
        html, re.DOTALL
    )
    if content_match:
        raw_content = content_match.group(1)
        # 去掉 script / style
        raw_content = re.sub(r'<script[^>]*>.*?</script>', '', raw_content, flags=re.DOTALL)
        raw_content = re.sub(r'<style[^>]*>.*?</style>', '', raw_content, flags=re.DOTALL)
        # 保留段落换行
        raw_content = re.sub(r'<br\s*/?>', '\n', raw_content)
        raw_content = re.sub(r'</p>', '\n', raw_content)
        raw_content = re.sub(r'</div>', '\n', raw_content)
        raw_content = re.sub(r'</li>', '\n', raw_content)
        # 去掉所有 HTML 标签
        text = re.sub(r'<[^>]+>', '', raw_content)
        # 清理多余空白
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        result["full_text"] = text.strip()

    return result


def normalize_cn_datetime(raw: str) -> str:
    """
    将中文日期时间转为标准格式
    "2026年4月9日08:06:06" → "2026-04-09 08:06:06"
    """
    m = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{2}:\d{2}:\d{2})', raw)
    if m:
        y, mo, d, t = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d} {t}"
    # 尝试不带时间
    m2 = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', raw)
    if m2:
        y, mo, d = m2.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d} 00:00:00"
    return raw


# ============ 分类与评级 ============

def classify_article(title: str, summary: str, tags: list, category_name: str) -> dict:
    """
    根据文章内容自动分类和评级
    返回 { category, severity, tags }
    """
    combined = f"{title} {summary} {' '.join(tags)} {category_name}".lower()

    # 分类
    cat = "general"
    if any(k in combined for k in ["漏洞", "cve", "exploit", "0day", "零日", "rce", "注入", "xss", "csrf", "ssrf", "反序列化"]):
        cat = "vuln"
    elif any(k in combined for k in ["ddos", "僵尸网络", "botnet", "流量攻击", "拒绝服务"]):
        cat = "ddos"
    elif any(k in combined for k in ["恶意软件", "勒索", "木马", "后门", "c2", "挖矿", "蠕虫", "ransomware", "malware"]):
        cat = "malware"
    elif any(k in combined for k in ["ai agent", "智能体", "mcp", "大模型安全", "人工智能安全", "ai安全", "llm安全", "prompt injection"]):
        cat = "agent"
    elif any(k in combined for k in ["gpt", "claude", "gemini", "llm", "大模型", "大语言", "deepseek", "openai", "anthropic", "人工智能"]):
        cat = "llm"

    # 严重等级
    severity = "low"
    if any(k in combined for k in ["严重", "critical", "0day", "零日", "rce", "远程代码执行", "紧急", "在野利用"]):
        severity = "critical"
    elif any(k in combined for k in ["高危", "high", "数据泄露", "breach", "重大", "大规模攻击"]):
        severity = "high"
    elif any(k in combined for k in ["中危", "medium", "新版本", "发布", "更新"]):
        severity = "medium"

    # 标签处理
    final_tags = list(tags)  # 保留原始标签
    if category_name and category_name not in final_tags:
        final_tags.insert(0, category_name)
    # 限制标签数
    final_tags = final_tags[:8]

    return {"category": cat, "severity": severity, "tags": final_tags}


# ============ 主流程 ============

def scrape_category(cat_name: str, cat_url: str, max_pages: int = 2) -> list:
    """
    爬取单个分类的文章列表
    返回文章基本信息列表
    """
    all_articles = []

    for page in range(1, max_pages + 1):
        if page == 1:
            url = cat_url
        else:
            url = f"{cat_url}/page/{page}"

        logger.info(f"📄 [{cat_name}] 第{page}页: {url}")
        html = fetch_page(url)
        if not html:
            logger.warning(f"  ⚠️ 获取页面失败，跳过")
            break

        articles = parse_article_list(html)
        if not articles:
            logger.info(f"  ℹ️ 无更多文章，停止翻页")
            break

        for art in articles:
            art["category_name"] = cat_name

        all_articles.extend(articles)
        logger.info(f"  ✅ 解析到 {len(articles)} 篇文章")

        if page < max_pages:
            polite_delay()

    return all_articles


def scrape_article_detail(article: dict) -> dict:
    """
    爬取单篇文章详情，合并到 article 字典中
    """
    html = fetch_page(article["url"])
    if not html:
        return article

    detail = parse_article_detail(html)
    article.update(detail)
    return article


def run_scraper():
    """
    主入口：爬取所有分类 → 去重 → 获取详情 → 入库
    """
    logger.info("=" * 60)
    logger.info("🚀 CN-SEC 爬虫启动")
    logger.info("=" * 60)

    # Step 1: 爬取所有分类的文章列表
    all_articles = []
    seen_ids = set()

    for cat_name, cat_url in CATEGORIES.items():
        articles = scrape_category(cat_name, cat_url, MAX_PAGES_PER_CATEGORY)
        for art in articles:
            if art["article_id"] not in seen_ids:
                seen_ids.add(art["article_id"])
                all_articles.append(art)
        polite_delay()

    logger.info(f"\n📊 列表页共采集 {len(all_articles)} 篇文章（去重后）")

    # Step 2: 过滤已入库的文章
    new_articles = []
    for art in all_articles:
        if not article_exists(art["article_id"]):
            new_articles.append(art)

    logger.info(f"📊 其中 {len(new_articles)} 篇为新文章（未入库）")

    if not new_articles:
        logger.info("✅ 没有新文章需要采集，本次结束")
        return

    # 限制总量
    if len(new_articles) > MAX_ARTICLES_TOTAL:
        logger.info(f"⚠️ 新文章超过 {MAX_ARTICLES_TOTAL} 篇，仅采集前 {MAX_ARTICLES_TOTAL} 篇")
        new_articles = new_articles[:MAX_ARTICLES_TOTAL]

    # Step 3: 逐篇获取详情并入库
    success_count = 0
    for i, art in enumerate(new_articles, 1):
        logger.info(f"\n📰 [{i}/{len(new_articles)}] {art['title'][:50]}")

        # 获取详情
        scrape_article_detail(art)

        # 分类评级
        classify = classify_article(
            art["title"],
            art.get("summary", ""),
            art.get("tags", []),
            art.get("category_name", ""),
        )

        # 构造入库数据
        full_text = art.get("full_text", "") or art.get("summary", "")
        # 截取前80字作为 title（如果原标题太长）
        db_title = art["title"][:80]
        if len(art["title"]) > 80:
            db_title += "..."

        # 热度 = 浏览量
        heat = art.get("views", 0)

        article_data = {
            "article_id": art["article_id"],
            "title": db_title,
            "summary": art.get("summary", ""),
            "full_text": full_text,
            "category": classify["category"],
            "severity": classify["severity"],
            "source": f"CN-SEC · {art.get('category_name', '')}",
            "source_icon": "ri-newspaper-line",
            "tags": classify["tags"],
            "heat": heat,
            "link": art["url"],
            "publish_time": art.get("publish_time", ""),
        }

        if insert_cnsec_article(article_data):
            success_count += 1
            logger.info(f"  ✅ 入库成功 [{classify['category']}/{classify['severity']}]")
        else:
            logger.info(f"  ⏭️ 跳过（已存在或失败）")

        polite_delay()

    logger.info(f"\n{'=' * 60}")
    logger.info(f"🎉 CN-SEC 爬虫完成！新增 {success_count} 篇情报")
    logger.info(f"{'=' * 60}")

    return success_count


if __name__ == "__main__":
    run_scraper()
