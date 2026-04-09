"""
数据库操作层 - ThreatPulse 安全情报聚合平台
"""
import os
import json
import logging
import pymysql
from contextlib import contextmanager

logger = logging.getLogger(__name__)

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
    """获取数据库连接（上下文管理器）"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def classify_tweet(keyword: str, text: str) -> dict:
    """
    根据关键词和推文内容自动分类 + 评估严重等级
    返回 { category, severity, tags }
    """
    kw_lower = keyword.lower()
    text_lower = text.lower()
    combined = f"{kw_lower} {text_lower}"

    # ---- 分类 ----
    ddos_kw = ["ddos", "botnet", "volumetric", "layer 7", "api abuse", "flood", "amplification"]
    agent_kw = ["agent", "agentic", "mcp protocol", "multi-agent", "autonomous", "tool use", "browser use", "computer use"]
    llm_kw = ["gpt", "claude", "gemini", "llm", "reasoning", "chain of thought", "multimodal",
              "fine-tuning", "fine tuning", "rag ", "retrieval augmented", "mixture of experts",
              "long context", "benchmark", "open source llm", "deepseek", "mistral", "anthropic", "openai"]
    vuln_kw = ["cve-", "vulnerability", "exploit", "0day", "zero-day", "rce", "patch"]
    malware_kw = ["malware", "ransomware", "trojan", "backdoor", "c2", "cobalt strike"]

    category = "general"
    if any(k in combined for k in ddos_kw):
        category = "ddos"
    elif any(k in combined for k in vuln_kw):
        category = "vuln"
    elif any(k in combined for k in malware_kw):
        category = "malware"
    elif any(k in combined for k in agent_kw):
        category = "agent"
    elif any(k in combined for k in llm_kw):
        category = "llm"

    # ---- 严重等级 ----
    severity = "info"
    critical_kw = ["critical", "0day", "zero-day", "rce", "actively exploited", "emergency"]
    high_kw = ["high", "severe", "major attack", "breach", "data leak", "1tbps", "ddos attack"]
    medium_kw = ["medium", "moderate", "new release", "breakthrough", "launch"]

    if any(k in combined for k in critical_kw):
        severity = "critical"
    elif any(k in combined for k in high_kw):
        severity = "high"
    elif any(k in combined for k in medium_kw):
        severity = "medium"
    else:
        severity = "low"

    # ---- 标签 ----
    tags = []
    tag_map = {
        "DDoS": ["ddos"], "Botnet": ["botnet"], "AI Agent": ["ai agent", "agent framework"],
        "LLM": ["llm", "large language"], "GPT": ["gpt-5", "gpt5", "openai"],
        "Claude": ["claude"], "Gemini": ["gemini"], "DeepSeek": ["deepseek"],
        "RAG": ["rag ", "retrieval augmented"], "MCP": ["mcp protocol", "mcp "],
        "Multi-Agent": ["multi-agent"], "Open Source": ["open source"],
        "Reasoning": ["reasoning", "chain of thought"], "Fine-tuning": ["fine-tun", "fine tun"],
        "Multimodal": ["multimodal"], "Benchmark": ["benchmark"],
        "Vulnerability": ["cve-", "vulnerability"], "Exploit": ["exploit", "0day"],
    }
    for tag, keywords_list in tag_map.items():
        if any(k in combined for k in keywords_list):
            tags.append(tag)

    # 添加关键词本身作为标签
    if keyword.strip() and keyword.strip() not in tags:
        tags.append(keyword.strip()[:30])

    return {"category": category, "severity": severity, "tags": tags[:8]}


def insert_tweet(tweet: dict, keyword: str) -> bool:
    """
    将单条推文插入数据库
    返回 True 表示新插入，False 表示已存在（跳过）
    """
    tweet_id = tweet.get("tweet_id", "")
    if not tweet_id:
        return False

    full_text = tweet.get("full_text", "")
    user = tweet.get("user", {})

    # 自动分类
    classify = classify_tweet(keyword, full_text)

    # 构造 title: 取前80字符
    title = full_text[:80].replace("\n", " ").strip()
    if len(full_text) > 80:
        title += "..."

    # 计算热度 = retweet * 3 + favorite * 2 + reply + quote
    heat = (tweet.get("retweet_count", 0) * 3 +
            tweet.get("favorite_count", 0) * 2 +
            tweet.get("reply_count", 0) +
            tweet.get("quote_count", 0))

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
                    tweet_id, title, full_text,
                    tweet.get("summary_cn", None),
                    full_text,
                    classify["category"], classify["severity"],
                    f"Twitter @{user.get('screen_name', 'unknown')}",
                    "ri-twitter-x-line",
                    json.dumps(classify["tags"], ensure_ascii=False),
                    heat,
                    tweet.get("reply_count", 0),
                    json.dumps([], ensure_ascii=False),
                    tweet.get("url", ""),
                    keyword,
                    user.get("name", ""),
                    user.get("screen_name", ""),
                    user.get("followers_count", 0),
                    tweet.get("retweet_count", 0),
                    tweet.get("favorite_count", 0),
                    tweet.get("reply_count", 0),
                    tweet.get("quote_count", 0),
                    tweet.get("lang", ""),
                    tweet.get("created_at", ""),
                )
                cursor.execute(sql, params)
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"插入推文失败 [{tweet_id}]: {e}")
        return False


def batch_insert_tweets(tweets: list, keyword: str) -> int:
    """批量插入推文，返回新增条数"""
    new_count = 0
    for tweet in tweets:
        if insert_tweet(tweet, keyword):
            new_count += 1
    return new_count


def query_intel(category=None, severity=None, keyword=None, search=None,
                time_filter="today", sort_by="latest", page=1, page_size=20):
    """
    查询情报数据
    """
    conditions = []
    params = []

    if category and category != "all":
        conditions.append("category = %s")
        params.append(category)

    if severity:
        conditions.append("severity = %s")
        params.append(severity)

    if keyword:
        conditions.append("keyword LIKE %s")
        params.append(f"%{keyword}%")

    if search:
        # 支持多关键词 AND 搜索（空格分隔）
        keywords_list = [kw.strip() for kw in search.split() if kw.strip()]
        if keywords_list:
            kw_conditions = []
            for kw in keywords_list:
                kw_conditions.append("(title LIKE %s OR summary LIKE %s OR summary_cn LIKE %s OR full_text LIKE %s)")
                params.extend([f"%{kw}%"] * 4)
            conditions.append("(" + " AND ".join(kw_conditions) + ")")

    # 时间过滤
    time_sql = {
        "today": "DATE(crawl_time) = CURDATE()",
        "3days": "crawl_time >= DATE_SUB(NOW(), INTERVAL 3 DAY)",
        "week": "crawl_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)",
        "month": "crawl_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)",
        "all": "1=1",
    }
    conditions.append(time_sql.get(time_filter, "1=1"))

    where = " AND ".join(conditions) if conditions else "1=1"

    # 排序
    order_map = {
        "latest": "crawl_time DESC",
        "hot": "heat DESC",
        "critical": "FIELD(severity, 'critical', 'high', 'medium', 'low', 'info')",
    }
    order = order_map.get(sort_by, "crawl_time DESC")

    offset = (page - 1) * page_size

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                # 查询总数
                cursor.execute(f"SELECT COUNT(*) AS total FROM intel_items WHERE {where}", params)
                total = cursor.fetchone()["total"]

                # 查询数据
                cursor.execute(
                    f"SELECT * FROM intel_items WHERE {where} ORDER BY {order} LIMIT %s OFFSET %s",
                    params + [page_size, offset]
                )
                items = cursor.fetchall()

                # 处理 JSON 字段
                for item in items:
                    # 保留原文摘要(summary)和中文摘要(summary_cn)两个字段
                    # 前端列表展示用 summary_cn，详情弹窗同时展示两者
                    if isinstance(item.get("tags"), str):
                        try:
                            item["tags"] = json.loads(item["tags"])
                        except:
                            item["tags"] = []
                    if isinstance(item.get("ioc"), str):
                        try:
                            item["ioc"] = json.loads(item["ioc"])
                        except:
                            item["ioc"] = []
                    # datetime 转字符串
                    for dt_field in ["crawl_time", "created_at", "updated_at"]:
                        if item.get(dt_field):
                            item[dt_field] = str(item[dt_field])

                return {"total": total, "items": items, "page": page, "page_size": page_size}
    except Exception as e:
        logger.error(f"查询情报失败: {e}")
        return {"total": 0, "items": [], "page": page, "page_size": page_size}


def get_stats(time_filter="today"):
    """获取统计数据"""
    time_sql = {
        "today": "DATE(crawl_time) = CURDATE()",
        "3days": "crawl_time >= DATE_SUB(NOW(), INTERVAL 3 DAY)",
        "week": "crawl_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)",
        "month": "crawl_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)",
        "all": "1=1",
    }
    time_cond = time_sql.get(time_filter, "1=1")

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                stats = {}

                # 总情报数
                cursor.execute(f"SELECT COUNT(*) AS cnt FROM intel_items WHERE {time_cond}")
                stats["total"] = cursor.fetchone()["cnt"]

                # 各严重等级数量
                cursor.execute(f"""
                    SELECT severity, COUNT(*) AS cnt
                    FROM intel_items WHERE {time_cond}
                    GROUP BY severity
                """)
                severity_counts = {r["severity"]: r["cnt"] for r in cursor.fetchall()}
                stats["critical"] = severity_counts.get("critical", 0)
                stats["high"] = severity_counts.get("high", 0)
                stats["medium"] = severity_counts.get("medium", 0)
                stats["low"] = severity_counts.get("low", 0)
                stats["info"] = severity_counts.get("info", 0)

                # 各分类数量
                cursor.execute(f"""
                    SELECT category, COUNT(*) AS cnt
                    FROM intel_items WHERE {time_cond}
                    GROUP BY category
                """)
                stats["categories"] = {r["category"]: r["cnt"] for r in cursor.fetchall()}

                # 来源数（不同的 keyword）
                cursor.execute(f"SELECT COUNT(DISTINCT keyword) AS cnt FROM intel_items WHERE {time_cond}")
                stats["sources"] = cursor.fetchone()["cnt"]

                return stats
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        return {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "categories": {}, "sources": 0}


def get_hot_keywords(time_filter="today", limit=10):
    """获取热门关键词"""
    time_sql = {
        "today": "DATE(crawl_time) = CURDATE()",
        "3days": "crawl_time >= DATE_SUB(NOW(), INTERVAL 3 DAY)",
        "week": "crawl_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)",
        "month": "crawl_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)",
        "all": "1=1",
    }
    time_cond = time_sql.get(time_filter, "1=1")

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"""
                    SELECT keyword, COUNT(*) AS cnt, SUM(heat) AS total_heat
                    FROM intel_items WHERE {time_cond}
                    GROUP BY keyword
                    ORDER BY cnt DESC
                    LIMIT %s
                """, (limit,))
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"获取热门关键词失败: {e}")
        return []


def get_tag_cloud(time_filter="today", limit=25):
    """获取标签云数据"""
    time_sql = {
        "today": "DATE(crawl_time) = CURDATE()",
        "3days": "crawl_time >= DATE_SUB(NOW(), INTERVAL 3 DAY)",
        "week": "crawl_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)",
        "month": "crawl_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)",
        "all": "1=1",
    }
    time_cond = time_sql.get(time_filter, "1=1")

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                # 解析 JSON tags 并统计
                cursor.execute(f"""
                    SELECT jt.tag AS name, COUNT(*) AS weight
                    FROM intel_items,
                    JSON_TABLE(tags, '$[*]' COLUMNS (tag VARCHAR(100) PATH '$')) AS jt
                    WHERE {time_cond}
                    GROUP BY jt.tag
                    ORDER BY weight DESC
                    LIMIT %s
                """, (limit,))
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"获取标签云失败: {e}")
        return []


def get_hot_attacks(time_filter="today", limit=8):
    """获取热点攻击榜"""
    time_sql = {
        "today": "DATE(crawl_time) = CURDATE()",
        "3days": "crawl_time >= DATE_SUB(NOW(), INTERVAL 3 DAY)",
        "week": "crawl_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)",
        "month": "crawl_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)",
        "all": "1=1",
    }
    time_cond = time_sql.get(time_filter, "1=1")

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"""
                    SELECT title AS name, heat, category
                    FROM intel_items
                    WHERE {time_cond}
                    ORDER BY heat DESC
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
                result = []
                for i, r in enumerate(rows, 1):
                    result.append({
                        "rank": i,
                        "name": r["name"][:30],
                        "heat": r["heat"],
                        "trend": "up",
                        "category": r["category"],
                    })
                return result
    except Exception as e:
        logger.error(f"获取热点攻击失败: {e}")
        return []


def update_summary_cn(item_id: int, summary_cn: str) -> bool:
    """更新指定情报的中文摘要"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE intel_items SET summary_cn = %s WHERE id = %s",
                    (summary_cn, item_id)
                )
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"更新中文摘要失败 [id={item_id}]: {e}")
        return False


def get_items_without_summary_cn(limit: int = 50) -> list:
    """获取没有中文摘要的情报（用于存量回填）"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """SELECT id, title, summary, full_text
                       FROM intel_items
                       WHERE summary_cn IS NULL OR summary_cn = ''
                       ORDER BY id DESC
                       LIMIT %s""",
                    (limit,)
                )
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"查询无中文摘要情报失败: {e}")
        return []


def check_duplicate_by_summary_cn(summary_cn: str) -> bool:
    """通过中文摘要检查是否重复（模糊匹配）"""
    if not summary_cn or len(summary_cn) < 10:
        return False
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                # 取摘要的核心部分（前30字）做模糊匹配
                core = summary_cn[:30]
                cursor.execute(
                    "SELECT 1 FROM intel_items WHERE summary_cn LIKE %s LIMIT 1",
                    (f"%{core}%",)
                )
                return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"中文摘要去重检查失败: {e}")
        return False


def search_suggest(query, limit=8):
    """搜索建议：基于 title、summary_cn、summary 模糊匹配"""
    if not query or len(query) < 2:
        return []
    try:
        with get_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("""
                    SELECT id, title,
                           LEFT(COALESCE(summary_cn, ''), 80) AS summary_cn_snippet,
                           LEFT(COALESCE(summary, ''), 80) AS summary_snippet,
                           category, severity
                    FROM intel_items
                    WHERE title LIKE %s OR summary_cn LIKE %s OR summary LIKE %s
                    ORDER BY crawl_time DESC
                    LIMIT %s
                """, [f"%{query}%", f"%{query}%", f"%{query}%", limit])
                results = cursor.fetchall()
                return results
    except Exception as e:
        logging.error(f"search_suggest error: {e}")
        return []


def get_github_trending(period="daily", limit=10):
    """
    获取 GitHub 热门项目
    period: daily | weekly
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                # 获取最新的快照日期
                cursor.execute("""
                    SELECT MAX(snapshot_date) AS latest
                    FROM github_trending
                    WHERE period = %s
                """, (period,))
                row = cursor.fetchone()
                if not row or not row["latest"]:
                    return []

                latest_date = row["latest"]

                cursor.execute("""
                    SELECT repo_full_name, repo_name, owner, description,
                           description_cn, language, stars, forks,
                           topics, url, avatar_url, rank_score
                    FROM github_trending
                    WHERE period = %s AND snapshot_date = %s
                    ORDER BY rank_score DESC
                    LIMIT %s
                """, (period, latest_date, limit))

                items = cursor.fetchall()
                for item in items:
                    if isinstance(item.get("topics"), str):
                        try:
                            item["topics"] = json.loads(item["topics"])
                        except:
                            item["topics"] = []
                    # 转换 date 为字符串
                    for f in ["snapshot_date"]:
                        if item.get(f):
                            item[f] = str(item[f])
                return items
    except Exception as e:
        logger.error(f"获取 GitHub Trending 失败: {e}")
        return []


def get_hot_topics(time_range="daily", limit=10):
    """
    获取热点情报聚合 Top N
    基于 summary_cn 的前30字做聚合，相似情报累积热度
    time_range: daily | weekly
    """
    time_sql = {
        "daily": "DATE(crawl_time) = CURDATE()",
        "weekly": "crawl_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)",
    }
    time_cond = time_sql.get(time_range, "DATE(crawl_time) = CURDATE()")

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                # 获取有中文摘要的情报
                cursor.execute(f"""
                    SELECT id, title, summary_cn, category, severity,
                           source, source_icon, heat, crawl_time, link
                    FROM intel_items
                    WHERE {time_cond}
                      AND summary_cn IS NOT NULL
                      AND summary_cn != ''
                    ORDER BY crawl_time DESC
                    LIMIT 500
                """)
                items = cursor.fetchall()

                if not items:
                    return []

                # 基于中文摘要前 30 字做聚合
                topic_groups = {}  # key: summary_cn[:30] -> group

                for item in items:
                    summary_cn = item.get("summary_cn", "")
                    if not summary_cn or len(summary_cn) < 10:
                        continue

                    # 提取核心摘要（前30字）作为聚合键
                    core_key = summary_cn[:30].strip()

                    # 尝试找到已有的相似组
                    matched_key = None
                    for existing_key in topic_groups:
                        # 计算字符重叠度
                        overlap = _calc_overlap(core_key, existing_key)
                        if overlap > 0.45:  # 45% 以上重叠认为是同一话题
                            matched_key = existing_key
                            break
                        # 额外检查：如果两个摘要包含相同的关键实体名
                        if _share_key_entity(core_key, existing_key):
                            matched_key = existing_key
                            break

                    if matched_key:
                        group = topic_groups[matched_key]
                        group["count"] += 1
                        group["total_heat"] += (item.get("heat", 0) or 0)
                        group["sources"].add(item.get("source", ""))
                        group["items"].append({
                            "id": item["id"],
                            "title": item["title"],
                            "source": item.get("source", ""),
                        })
                        # 如果新情报的 severity 更高，更新
                        sev_order = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
                        if sev_order.get(item.get("severity", ""), 0) > sev_order.get(group["severity"], 0):
                            group["severity"] = item["severity"]
                    else:
                        topic_groups[core_key] = {
                            "title": item.get("title", ""),
                            "summary_cn": summary_cn,
                            "category": item.get("category", "general"),
                            "severity": item.get("severity", "info"),
                            "count": 1,
                            "total_heat": item.get("heat", 0) or 0,
                            "sources": {item.get("source", "")},
                            "first_time": str(item.get("crawl_time", "")),
                            "link": item.get("link", ""),
                            "items": [{
                                "id": item["id"],
                                "title": item["title"],
                                "source": item.get("source", ""),
                            }],
                        }

                # 计算综合热度分数并排序
                result = []
                for key, group in topic_groups.items():
                    # 热度公式优化：
                    # - 多篇报道权重最高（count * 100）
                    # - 多源报道加权（source_count * 50）
                    # - 原始heat归一化（log scale避免单一高heat值主导）
                    import math
                    heat_normalized = math.log2(group["total_heat"] + 1) * 10
                    hot_score = round(
                        group["count"] * 100 +
                        len(group["sources"]) * 50 +
                        heat_normalized
                    )
                    result.append({
                        "title": group["title"],
                        "summary_cn": group["summary_cn"][:100],
                        "category": group["category"],
                        "severity": group["severity"],
                        "count": group["count"],
                        "hot_score": hot_score,
                        "source_count": len(group["sources"]),
                        "sources": list(group["sources"])[:5],
                        "first_time": group["first_time"],
                        "link": group["link"],
                        "related_count": len(group["items"]),
                        "related_items": group["items"][:5],
                    })

                result.sort(key=lambda x: x["hot_score"], reverse=True)
                return result[:limit]

    except Exception as e:
        logger.error(f"获取热点情报失败: {e}")
        return []


def _calc_overlap(s1, s2):
    """计算两个字符串的字符重叠度（Jaccard 相似度）"""
    if not s1 or not s2:
        return 0
    set1 = set(s1)
    set2 = set(s2)
    intersection = set1 & set2
    union = set1 | set2
    return len(intersection) / len(union) if union else 0


def _share_key_entity(s1, s2):
    """
    检查两个摘要是否包含相同的关键实体（产品名/CVE编号/公司名等）
    """
    import re
    # 提取 CVE 编号
    cve_pattern = re.compile(r'CVE-\d{4}-\d+', re.IGNORECASE)
    cves1 = set(cve_pattern.findall(s1))
    cves2 = set(cve_pattern.findall(s2))
    if cves1 and cves2 and cves1 & cves2:
        return True

    # 提取关键产品/公司名（英文词 >= 4 字母）
    word_pattern = re.compile(r'[A-Z][a-zA-Z]{3,}')
    words1 = set(word_pattern.findall(s1))
    words2 = set(word_pattern.findall(s2))
    # 排除常见通用词
    stopwords = {'This', 'That', 'These', 'Those', 'With', 'From', 'About', 'Have', 'Been', 'Will', 'Could', 'Should'}
    words1 -= stopwords
    words2 -= stopwords
    shared = words1 & words2
    if len(shared) >= 2:  # 至少2个相同的专有名词
        return True

    return False
