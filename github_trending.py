"""
GitHub Trending 热门项目爬虫 - ThreatPulse
抓取 GitHub Trending 中 AI Agent / 大模型相关的热门项目
支持每日(daily)和每周(weekly)两个维度
"""
import os
import json
import logging
import time
import re
import urllib.request
import urllib.error
import pymysql
from datetime import datetime, date
from contextlib import contextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("github_trending")

# ============== 数据库配置 ==============
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": os.environ.get("DB_USER", "threatpulse"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "threatpulse"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

# GitHub Token
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ============== 搜索关键词 ==============
# 用于从 GitHub 搜索 AI Agent / 大模型方向的热门项目
SEARCH_QUERIES = [
    # Agent 方向
    "AI agent framework",
    "autonomous agent",
    "multi-agent system",
    "MCP server",
    "agent tool use",
    "agentic AI",
    # 大模型方向
    "large language model",
    "LLM inference",
    "LLM fine-tuning",
    "RAG retrieval augmented",
    "prompt engineering",
    "open source LLM",
    "multimodal model",
    "reasoning model",
    # AI 安全
    "AI security tool",
    "LLM security",
]

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


def init_table():
    """创建 github_trending 表"""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS github_trending (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    repo_full_name VARCHAR(255) NOT NULL,
                    repo_name VARCHAR(255) NOT NULL,
                    owner VARCHAR(128) NOT NULL,
                    description TEXT,
                    description_cn TEXT,
                    language VARCHAR(64),
                    stars INT DEFAULT 0,
                    forks INT DEFAULT 0,
                    stars_today INT DEFAULT 0,
                    stars_week INT DEFAULT 0,
                    topics JSON,
                    url VARCHAR(512),
                    avatar_url VARCHAR(512),
                    period ENUM('daily', 'weekly') NOT NULL DEFAULT 'daily',
                    snapshot_date DATE NOT NULL,
                    rank_score DOUBLE DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_repo_period_date (repo_full_name, period, snapshot_date),
                    INDEX idx_period_date (period, snapshot_date),
                    INDEX idx_rank_score (rank_score DESC)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            logger.info("✅ github_trending 表已就绪")


def github_api_request(url, retries=3):
    """带重试的 GitHub API 请求"""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ThreatPulse-Trending/1.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 403:
                # Rate limit
                logger.warning(f"GitHub API 限流，等待 60s (attempt {attempt+1})")
                time.sleep(60)
            elif e.code == 422:
                logger.warning(f"GitHub API 422: {url}")
                return None
            else:
                logger.error(f"GitHub API HTTP {e.code}: {url}")
                time.sleep(5)
        except Exception as e:
            logger.error(f"GitHub API 请求失败: {e}")
            time.sleep(5)
    return None


def search_trending_repos(query, sort="stars", order="desc", per_page=30, created_after=None):
    """
    通过 GitHub Search API 搜索热门仓库
    sort: stars | forks | updated
    """
    q = query
    if created_after:
        q += f" created:>{created_after}"

    url = (
        f"https://api.github.com/search/repositories"
        f"?q={urllib.parse.quote(q)}"
        f"&sort={sort}&order={order}&per_page={per_page}"
    )
    data = github_api_request(url)
    if data and "items" in data:
        return data["items"]
    return []


def get_repo_stars_history(owner, repo):
    """获取仓库最近的 star 增长（通过 stargazers API 近似）"""
    # 简化：直接用 watchers_count 和 stargazers_count
    url = f"https://api.github.com/repos/{owner}/{repo}"
    data = github_api_request(url)
    if data:
        return {
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "watchers": data.get("watchers_count", 0),
            "description": data.get("description", ""),
            "topics": data.get("topics", []),
            "language": data.get("language", ""),
            "avatar_url": data.get("owner", {}).get("avatar_url", ""),
        }
    return None


def translate_description(text):
    """用 DeepSeek 翻译描述为中文"""
    if not text:
        return ""

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return ""

    try:
        url = "https://api.deepseek.com/chat/completions"
        payload = json.dumps({
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是一个翻译助手。将以下GitHub项目描述翻译为简洁的中文，不超过100字。只输出翻译结果，不要任何解释。"},
                {"role": "user", "content": text}
            ],
            "temperature": 0.3,
            "max_tokens": 200,
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {api_key}")

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"翻译失败: {e}")
        return ""


def fetch_trending_data(period="daily"):
    """
    获取热门项目数据
    period: daily | weekly
    """
    logger.info(f"📊 开始获取 {period} 热门项目...")

    all_repos = {}  # repo_full_name -> repo_data

    # 根据 period 决定时间范围
    if period == "daily":
        # 搜索最近 7 天创建或更新的高星项目
        from datetime import timedelta
        created_after = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        sort_by = "stars"
    else:
        # weekly: 搜索最近 30 天
        from datetime import timedelta
        created_after = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        sort_by = "stars"

    for query in SEARCH_QUERIES:
        logger.info(f"  搜索: {query}")
        repos = search_trending_repos(
            query, sort=sort_by, order="desc", per_page=15,
            created_after=created_after if period == "daily" else None
        )

        for repo in repos:
            full_name = repo.get("full_name", "")
            if full_name in all_repos:
                # 已存在，累加 rank_score
                all_repos[full_name]["rank_score"] += 1
                continue

            stars = repo.get("stargazers_count", 0)
            forks = repo.get("forks_count", 0)

            # 计算热度分数：stars 权重最高，forks 次之，匹配多个关键词加分
            rank_score = stars * 1.0 + forks * 0.5 + 1  # +1 for this keyword match

            all_repos[full_name] = {
                "repo_full_name": full_name,
                "repo_name": repo.get("name", ""),
                "owner": repo.get("owner", {}).get("login", ""),
                "description": repo.get("description", "") or "",
                "language": repo.get("language", "") or "",
                "stars": stars,
                "forks": forks,
                "topics": repo.get("topics", []),
                "url": repo.get("html_url", ""),
                "avatar_url": repo.get("owner", {}).get("avatar_url", ""),
                "rank_score": rank_score,
            }

        time.sleep(3)  # 避免触发限流

    # 按 rank_score 排序，取 Top 20（多存一些，前端展示 Top 10）
    sorted_repos = sorted(all_repos.values(), key=lambda x: x["rank_score"], reverse=True)[:20]

    # 为 Top 10 翻译描述
    for i, repo in enumerate(sorted_repos[:10]):
        if repo["description"]:
            desc_cn = translate_description(repo["description"])
            repo["description_cn"] = desc_cn
            logger.info(f"  [{i+1}] ⭐{repo['stars']} {repo['repo_full_name']}: {desc_cn[:50]}...")
            time.sleep(1)
        else:
            repo["description_cn"] = ""

    return sorted_repos


def save_trending(repos, period="daily"):
    """保存热门项目到数据库"""
    today = date.today()
    saved = 0

    with get_connection() as conn:
        with conn.cursor() as cursor:
            for repo in repos:
                try:
                    cursor.execute("""
                        INSERT INTO github_trending
                        (repo_full_name, repo_name, owner, description, description_cn,
                         language, stars, forks, stars_today, stars_week,
                         topics, url, avatar_url, period, snapshot_date, rank_score)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            stars = VALUES(stars),
                            forks = VALUES(forks),
                            rank_score = VALUES(rank_score),
                            description = VALUES(description),
                            description_cn = VALUES(description_cn),
                            topics = VALUES(topics)
                    """, (
                        repo["repo_full_name"],
                        repo["repo_name"],
                        repo["owner"],
                        repo["description"],
                        repo.get("description_cn", ""),
                        repo["language"],
                        repo["stars"],
                        repo["forks"],
                        0,  # stars_today placeholder
                        0,  # stars_week placeholder
                        json.dumps(repo.get("topics", []), ensure_ascii=False),
                        repo["url"],
                        repo.get("avatar_url", ""),
                        period,
                        today,
                        repo["rank_score"],
                    ))
                    saved += 1
                except Exception as e:
                    logger.error(f"保存失败 [{repo['repo_full_name']}]: {e}")

    logger.info(f"✅ 保存 {saved} 个 {period} 热门项目")
    return saved


def run():
    """主运行函数"""
    logger.info("=" * 60)
    logger.info("🚀 GitHub Trending 热门项目爬虫启动")
    logger.info("=" * 60)

    # 初始化表
    init_table()

    # 获取每日热门
    daily_repos = fetch_trending_data("daily")
    save_trending(daily_repos, "daily")

    # 获取每周热门
    weekly_repos = fetch_trending_data("weekly")
    save_trending(weekly_repos, "weekly")

    logger.info("🎉 GitHub Trending 爬虫完成")


if __name__ == "__main__":
    import urllib.parse
    run()
