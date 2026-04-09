"""
GitHub 安全情报爬虫 - ThreatPulse 安全情报聚合平台
从 GitHub 采集 AI Agent/LLM/DDoS/渗透测试/Web防护 相关的安全情报

数据源：
  1. GitHub Search API - 搜索热门/最新的安全相关仓库和代码
  2. GitHub Security Advisories - 官方安全公告 (CVE/GHSA)
"""

import os
import re
import json
import time
import random
import hashlib
import logging
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# ============ 配置 ============

# GitHub Personal Access Token
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# 搜索关键词分组（按你的关注方向）
SEARCH_QUERIES = {
    # Agent 新技术
    "agent": [
        "AI agent security tool",
        "MCP server security",
        "autonomous agent framework",
        "AI agent red team",
    ],
    # 大模型新技术
    "llm": [
        "LLM security vulnerability",
        "prompt injection defense",
        "LLM jailbreak bypass",
        "large language model safety",
    ],
    # AI + DDoS
    "ddos": [
        "AI DDoS detection defense",
        "machine learning DDoS mitigation",
        "AI botnet detection",
    ],
    # AI + 渗透测试
    "pentest": [
        "AI penetration testing tool",
        "AI automated exploit",
        "LLM vulnerability scanner",
        "AI red team pentest",
    ],
    # AI + Web 防护
    "webdef": [
        "AI WAF web application firewall",
        "AI web security protection",
        "machine learning intrusion detection",
    ],
}

# 每个搜索词最多获取多少个仓库
MAX_REPOS_PER_QUERY = 10

# 最小 star 数过滤（过滤低质量仓库）
MIN_STARS = 3

# 仅获取最近 N 天内更新的仓库（保证情报时效性）
RECENT_DAYS = 30

# GitHub Advisory 每次获取条数
ADVISORY_PER_PAGE = 20

# API 请求间隔（秒）
API_DELAY_MIN = 1.0
API_DELAY_MAX = 2.0

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("github_scraper")


# ============ HTTP 请求 ============

def github_api_request(url: str, retries: int = 3) -> dict:
    """
    调用 GitHub API，带认证和重试
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ThreatPulse-SecurityIntel/1.0",
    }

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

                # 检查速率限制
                remaining = resp.headers.get("X-RateLimit-Remaining", "?")
                logger.debug(f"API remaining: {remaining}")

                return data

        except urllib.error.HTTPError as e:
            if e.code == 403:
                # 速率限制
                reset_time = e.headers.get("X-RateLimit-Reset", "")
                if reset_time:
                    wait = max(int(reset_time) - int(time.time()), 5)
                    logger.warning(f"GitHub API 速率限制，等待 {wait}s...")
                    time.sleep(min(wait, 60))
                    continue
                else:
                    logger.warning(f"GitHub API 403，等待 30s 后重试...")
                    time.sleep(30)
                    continue
            elif e.code == 422:
                logger.warning(f"GitHub API 422 (查询格式问题): {url}")
                return {}
            else:
                body = e.read().decode("utf-8", errors="ignore")[:200]
                logger.warning(f"GitHub API HTTP {e.code}: {body}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return {}
        except Exception as e:
            logger.warning(f"GitHub API 请求异常 [{attempt+1}/{retries}]: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            return {}

    return {}


def polite_delay():
    """请求间隔"""
    time.sleep(random.uniform(API_DELAY_MIN, API_DELAY_MAX))


# ============ 仓库搜索 ============

def search_repositories(query: str, sort: str = "updated", per_page: int = 10) -> list:
    """
    搜索 GitHub 仓库
    sort: stars / updated / forks
    """
    # 限制为最近 N 天内更新的
    since_date = (datetime.utcnow() - timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%d")
    full_query = f"{query} pushed:>={since_date}"

    url = (
        f"https://api.github.com/search/repositories"
        f"?q={urllib.request.quote(full_query)}"
        f"&sort={sort}&order=desc&per_page={per_page}"
    )

    data = github_api_request(url)
    if not data or "items" not in data:
        return []

    repos = []
    for item in data["items"]:
        # 过滤低 star
        if item.get("stargazers_count", 0) < MIN_STARS:
            continue

        repos.append({
            "repo_id": str(item["id"]),
            "full_name": item["full_name"],
            "name": item["name"],
            "owner": item["owner"]["login"],
            "description": item.get("description", "") or "",
            "url": item["html_url"],
            "stars": item.get("stargazers_count", 0),
            "forks": item.get("forks_count", 0),
            "watchers": item.get("watchers_count", 0),
            "language": item.get("language", ""),
            "topics": item.get("topics", []),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
            "pushed_at": item.get("pushed_at", ""),
            "license": (item.get("license") or {}).get("spdx_id", ""),
            "open_issues": item.get("open_issues_count", 0),
            "is_fork": item.get("fork", False),
        })

    return repos


def get_repo_readme(full_name: str) -> str:
    """
    获取仓库 README 内容（用于生成更好的摘要）
    """
    url = f"https://api.github.com/repos/{full_name}/readme"
    data = github_api_request(url)
    if not data or "content" not in data:
        return ""

    try:
        import base64
        content = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
        # 去掉 Markdown 图片和链接噪音
        content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
        content = re.sub(r'<img[^>]*>', '', content)
        content = re.sub(r'</?[a-zA-Z][^>]*>', '', content)
        # 截断
        return content[:3000]
    except Exception:
        return ""


# ============ Security Advisories ============

def fetch_security_advisories(per_page: int = 20) -> list:
    """
    获取 GitHub Security Advisories（官方安全公告）
    聚焦 AI/ML/Web 相关的漏洞
    """
    url = (
        f"https://api.github.com/advisories"
        f"?per_page={per_page}&type=reviewed"
    )

    data = github_api_request(url)
    if not data or not isinstance(data, list):
        return []

    advisories = []
    for adv in data:
        # 提取 CVE 编号
        cve_id = ""
        for identifier in adv.get("identifiers", []):
            if identifier.get("type") == "CVE":
                cve_id = identifier.get("value", "")
                break

        ghsa_id = adv.get("ghsa_id", "")
        severity = adv.get("severity", "unknown")
        summary = adv.get("summary", "")
        description = adv.get("description", "")
        published_at = adv.get("published_at", "")
        updated_at = adv.get("updated_at", "")

        # 受影响的包
        affected_packages = []
        for vuln in adv.get("vulnerabilities", []):
            pkg = vuln.get("package", {})
            pkg_name = pkg.get("name", "")
            ecosystem = pkg.get("ecosystem", "")
            if pkg_name:
                affected_packages.append(f"{ecosystem}/{pkg_name}")

        # CWE
        cwes = [cwe.get("cwe_id", "") for cwe in adv.get("cwes", [])]

        advisories.append({
            "ghsa_id": ghsa_id,
            "cve_id": cve_id,
            "severity": severity,
            "summary": summary,
            "description": description,
            "published_at": published_at,
            "updated_at": updated_at,
            "url": adv.get("html_url", ""),
            "affected_packages": affected_packages,
            "cwes": cwes,
            "references": [
                ref.get("url", "") if isinstance(ref, dict) else str(ref)
                for ref in adv.get("references", [])
            ],
        })

    return advisories


# ============ 分类与评级 ============

def classify_repo(repo: dict, query_category: str) -> dict:
    """
    对仓库进行分类和评级
    """
    combined = f"{repo['name']} {repo['description']} {' '.join(repo.get('topics', []))}".lower()

    # 分类（优先使用查询分类）
    cat = query_category
    if cat == "pentest" or cat == "webdef":
        # 细化分类
        if any(k in combined for k in ["ddos", "botnet", "flood"]):
            cat = "ddos"
        elif any(k in combined for k in ["agent", "mcp", "autonomous"]):
            cat = "agent"
        elif any(k in combined for k in ["llm", "gpt", "prompt", "language model"]):
            cat = "llm"
        elif any(k in combined for k in ["malware", "ransomware", "trojan", "backdoor"]):
            cat = "malware"
        elif any(k in combined for k in ["vuln", "cve", "exploit", "rce"]):
            cat = "vuln"

    # 严重等级（基于 star 数和内容关键词）
    severity = "low"
    stars = repo.get("stars", 0)

    if any(k in combined for k in ["critical", "0day", "rce", "remote code execution"]):
        severity = "critical"
    elif any(k in combined for k in ["exploit", "bypass", "injection"]) or stars >= 500:
        severity = "high"
    elif stars >= 100 or any(k in combined for k in ["scanner", "detector", "defense"]):
        severity = "medium"

    # 标签
    tags = list(repo.get("topics", []))[:5]
    if repo.get("language") and repo["language"] not in tags:
        tags.append(repo["language"])
    if query_category not in tags:
        tags.insert(0, query_category)

    return {"category": cat, "severity": severity, "tags": tags}


def classify_advisory(adv: dict) -> dict:
    """
    对安全公告进行分类和评级
    """
    combined = f"{adv['summary']} {adv['description']} {' '.join(adv.get('affected_packages', []))}".lower()

    # 分类
    cat = "vuln"  # Advisory 默认都是漏洞
    if any(k in combined for k in ["llm", "langchain", "openai", "prompt", "ai ", "ml ", "tensorflow", "pytorch"]):
        cat = "llm"
    elif any(k in combined for k in ["agent", "mcp", "autonomous"]):
        cat = "agent"
    elif any(k in combined for k in ["ddos", "dos", "denial of service"]):
        cat = "ddos"
    elif any(k in combined for k in ["malware", "ransomware", "trojan"]):
        cat = "malware"

    # 严重等级映射
    severity_map = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
    }
    severity = severity_map.get(adv.get("severity", "").lower(), "medium")

    # 标签
    tags = ["Security Advisory"]
    if adv.get("cve_id"):
        tags.append(adv["cve_id"])
    tags.extend(adv.get("cwes", [])[:3])
    tags.extend(adv.get("affected_packages", [])[:3])

    return {"category": cat, "severity": severity, "tags": tags[:8]}


# ============ 数据库操作 ============

def _get_db_module():
    """延迟导入数据库模块"""
    import sys
    sys.path.insert(0, "/data/Th")
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

    return get_connection, pymysql


def item_exists(unique_id: str) -> bool:
    """检查是否已入库"""
    get_connection, _ = _get_db_module()
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM intel_items WHERE tweet_id = %s LIMIT 1",
                    (unique_id,)
                )
                return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"检查是否存在失败 [{unique_id}]: {e}")
        return False


def insert_github_item(item: dict) -> bool:
    """
    将 GitHub 情报插入 intel_items 表
    tweet_id 存 "github_{type}_{id}" 格式
    """
    get_connection, _ = _get_db_module()

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
                    item["unique_id"],
                    item.get("title", ""),
                    item.get("summary", ""),
                    item.get("summary_cn", None),
                    item.get("full_text", ""),
                    item.get("category", "general"),
                    item.get("severity", "low"),
                    item.get("source", "GitHub"),
                    item.get("source_icon", "ri-github-line"),
                    json.dumps(item.get("tags", []), ensure_ascii=False),
                    item.get("heat", 0),
                    0,  # comments
                    json.dumps(item.get("ioc", []), ensure_ascii=False),
                    item.get("link", ""),
                    item.get("keyword", "github"),
                    item.get("user_name", ""),
                    item.get("user_screen_name", ""),
                    item.get("user_followers", 0),
                    item.get("retweet_count", 0),  # 用于存 forks
                    item.get("favorite_count", 0),  # 用于存 stars
                    0,  # reply_count
                    0,  # quote_count
                    item.get("lang", "en"),
                    item.get("publish_time", ""),
                )
                cursor.execute(sql, params)
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"插入 GitHub 情报失败 [{item.get('unique_id', '?')}]: {e}")
        return False


# ============ DeepSeek 摘要 ============

def generate_cn_summary(title: str, content: str) -> str:
    """调用 DeepSeek 生成中文摘要"""
    try:
        import sys
        sys.path.insert(0, "/data/Th")
        from deepseek_summarizer import generate_summary
        return generate_summary(title, content)
    except Exception as e:
        logger.error(f"DeepSeek 摘要生成失败: {e}")
        return None


def check_cn_duplicate(summary_cn: str) -> bool:
    """通过中文摘要检查去重"""
    try:
        import sys
        sys.path.insert(0, "/data/Th")
        from db import check_duplicate_by_summary_cn
        return check_duplicate_by_summary_cn(summary_cn)
    except Exception as e:
        logger.error(f"中文摘要去重检查失败: {e}")
        return False


# ============ 主流程 ============

def process_repositories():
    """
    爬取并处理仓库情报
    """
    logger.info("📦 开始爬取 GitHub 仓库情报...")

    all_repos = {}  # full_name → repo_data（去重）
    repo_categories = {}  # full_name → category

    for category, queries in SEARCH_QUERIES.items():
        for query in queries:
            logger.info(f"  🔍 [{category}] 搜索: {query}")

            # 按 star 排序获取热门
            repos_stars = search_repositories(query, sort="stars", per_page=MAX_REPOS_PER_QUERY)
            # 按更新时间获取最新
            repos_updated = search_repositories(query, sort="updated", per_page=MAX_REPOS_PER_QUERY)

            for repo in repos_stars + repos_updated:
                fn = repo["full_name"]
                if fn not in all_repos:
                    all_repos[fn] = repo
                    repo_categories[fn] = category
                    logger.info(f"    ⭐ {repo['stars']:>5} | {fn} | {repo['description'][:50]}")

            polite_delay()

    logger.info(f"\n📊 共发现 {len(all_repos)} 个不重复的仓库")

    # 过滤已入库的
    new_repos = []
    for fn, repo in all_repos.items():
        unique_id = f"github_repo_{repo['repo_id']}"
        if not item_exists(unique_id):
            repo["_unique_id"] = unique_id
            repo["_category"] = repo_categories[fn]
            new_repos.append(repo)

    logger.info(f"📊 其中 {len(new_repos)} 个为新仓库（未入库）")

    if not new_repos:
        logger.info("✅ 没有新仓库需要入库")
        return 0

    # 逐个处理：获取 README → 生成摘要 → 入库
    success_count = 0
    for i, repo in enumerate(new_repos, 1):
        fn = repo["full_name"]
        logger.info(f"\n📰 [{i}/{len(new_repos)}] {fn} (⭐{repo['stars']})")

        # 获取 README 作为全文
        readme = get_repo_readme(fn)
        polite_delay()

        # 构造全文
        full_text_parts = [
            f"Repository: {fn}",
            f"Description: {repo['description']}",
            f"Stars: {repo['stars']} | Forks: {repo['forks']} | Language: {repo['language']}",
            f"Topics: {', '.join(repo.get('topics', []))}",
            f"License: {repo.get('license', 'N/A')}",
            f"Last updated: {repo.get('pushed_at', '')}",
        ]
        if readme:
            full_text_parts.append(f"\n--- README ---\n{readme}")
        full_text = "\n".join(full_text_parts)

        # 分类评级
        classify = classify_repo(repo, repo["_category"])

        # 生成 DeepSeek 中文摘要
        summary_cn = generate_cn_summary(
            f"{fn} - {repo['description']}",
            full_text
        )

        if summary_cn and check_cn_duplicate(summary_cn):
            logger.info(f"  🔄 中文摘要去重: 跳过相似情报")
            continue

        # 构造入库数据
        title = f"[{fn}] {repo['description'][:100]}" if repo['description'] else fn
        if len(title) > 200:
            title = title[:197] + "..."

        item = {
            "unique_id": repo["_unique_id"],
            "title": title,
            "summary": repo["description"],
            "summary_cn": summary_cn,
            "full_text": full_text[:10000],  # 限制长度
            "category": classify["category"],
            "severity": classify["severity"],
            "source": "GitHub Repo",
            "source_icon": "ri-github-line",
            "tags": classify["tags"],
            "heat": repo["stars"],
            "ioc": [],
            "link": repo["url"],
            "keyword": f"github-{repo['_category']}",
            "user_name": repo["owner"],
            "user_screen_name": repo["full_name"],
            "user_followers": repo.get("watchers", 0),
            "retweet_count": repo["forks"],
            "favorite_count": repo["stars"],
            "lang": "en",
            "publish_time": repo.get("pushed_at", ""),
        }

        if insert_github_item(item):
            success_count += 1
            logger.info(f"  ✅ 入库成功 [{classify['category']}/{classify['severity']}]")
        else:
            logger.info(f"  ⏭️ 跳过（已存在或失败）")

        polite_delay()

    return success_count


def process_advisories():
    """
    爬取并处理 GitHub Security Advisories
    """
    logger.info("\n🛡️ 开始爬取 GitHub Security Advisories...")

    advisories = fetch_security_advisories(per_page=ADVISORY_PER_PAGE)
    logger.info(f"📊 获取到 {len(advisories)} 条安全公告")

    if not advisories:
        return 0

    # 过滤已入库的
    new_advisories = []
    for adv in advisories:
        unique_id = f"github_adv_{adv['ghsa_id']}"
        if not item_exists(unique_id):
            adv["_unique_id"] = unique_id
            new_advisories.append(adv)

    logger.info(f"📊 其中 {len(new_advisories)} 条为新公告")

    if not new_advisories:
        logger.info("✅ 没有新安全公告需要入库")
        return 0

    success_count = 0
    for i, adv in enumerate(new_advisories, 1):
        ghsa = adv["ghsa_id"]
        cve = adv.get("cve_id", "")
        logger.info(f"\n🛡️ [{i}/{len(new_advisories)}] {ghsa} {cve} | {adv['severity']}")

        # 分类评级
        classify = classify_advisory(adv)

        # 构造全文
        full_text_parts = [
            f"GHSA: {ghsa}",
            f"CVE: {cve}" if cve else "",
            f"Severity: {adv['severity']}",
            f"Summary: {adv['summary']}",
            f"Description: {adv['description']}",
            f"Affected: {', '.join(adv.get('affected_packages', []))}",
            f"CWEs: {', '.join(adv.get('cwes', []))}",
        ]
        full_text = "\n".join([p for p in full_text_parts if p])

        # 生成 DeepSeek 中文摘要
        title_text = f"{cve or ghsa}: {adv['summary']}"
        summary_cn = generate_cn_summary(title_text, full_text)

        if summary_cn and check_cn_duplicate(summary_cn):
            logger.info(f"  🔄 中文摘要去重: 跳过相似情报")
            continue

        # 构造标题
        title = f"[{cve or ghsa}] {adv['summary']}"
        if len(title) > 200:
            title = title[:197] + "..."

        item = {
            "unique_id": adv["_unique_id"],
            "title": title,
            "summary": adv["summary"],
            "summary_cn": summary_cn,
            "full_text": full_text,
            "category": classify["category"],
            "severity": classify["severity"],
            "source": "GitHub Advisory",
            "source_icon": "ri-shield-keyhole-line",
            "tags": classify["tags"],
            "heat": 0,
            "ioc": [cve] if cve else [],
            "link": adv.get("url", ""),
            "keyword": "github-advisory",
            "user_name": "GitHub Security",
            "user_screen_name": "github.com/advisories",
            "user_followers": 0,
            "retweet_count": 0,
            "favorite_count": 0,
            "lang": "en",
            "publish_time": adv.get("published_at", ""),
        }

        if insert_github_item(item):
            success_count += 1
            logger.info(f"  ✅ 入库成功 [{classify['category']}/{classify['severity']}]")
        else:
            logger.info(f"  ⏭️ 跳过（已存在或失败）")

        polite_delay()

    return success_count


def run_scraper():
    """
    主入口
    """
    logger.info("=" * 60)
    logger.info("🚀 GitHub 安全情报爬虫启动")
    logger.info(f"   搜索分组: {len(SEARCH_QUERIES)} 个")
    logger.info(f"   搜索词总数: {sum(len(v) for v in SEARCH_QUERIES.values())} 个")
    logger.info(f"   时效范围: 最近 {RECENT_DAYS} 天")
    logger.info(f"   最小 Star: {MIN_STARS}")
    logger.info("=" * 60)

    # 1. 爬取仓库
    repo_count = process_repositories()

    # 2. 爬取安全公告
    adv_count = process_advisories()

    total = repo_count + adv_count
    logger.info(f"\n{'=' * 60}")
    logger.info(f"🎉 GitHub 爬虫完成！")
    logger.info(f"   新增仓库情报: {repo_count} 条")
    logger.info(f"   新增安全公告: {adv_count} 条")
    logger.info(f"   合计新增: {total} 条")
    logger.info(f"{'=' * 60}")

    return total


if __name__ == "__main__":
    run_scraper()
