"""
CN-SEC 数据库操作层 - ThreatPulse 安全情报聚合平台
复用 intel_items 表，使用 tweet_id 字段存储 "cnsec_<article_id>" 作为唯一标识
"""
import json
import logging
import pymysql
from contextlib import contextmanager

logger = logging.getLogger("cnsec_db")

# 数据库配置 - 与 db.py 保持一致
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "YOUR_DB_USER",
    "password": "YOUR_DB_PASSWORD_HERE",
    "database": "threatpulse",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


@contextmanager
def get_connection():
    """获取数据库连接"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def article_exists(article_id: str) -> bool:
    """
    检查文章是否已入库
    使用 tweet_id 字段存储 "cnsec_{article_id}" 格式的唯一标识
    """
    unique_id = f"cnsec_{article_id}"
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM intel_items WHERE tweet_id = %s LIMIT 1",
                    (unique_id,)
                )
                return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"检查文章是否存在失败 [{article_id}]: {e}")
        return False


def insert_cnsec_article(article: dict) -> bool:
    """
    将 CN-SEC 文章插入 intel_items 表
    复用现有表结构，tweet_id 存 "cnsec_{article_id}"

    article 字段:
      - article_id: CN-SEC 文章 ID
      - title: 标题
      - summary: 摘要
      - full_text: 全文
      - category: 分类
      - severity: 严重等级
      - source: 来源显示名
      - source_icon: 图标 class
      - tags: 标签列表
      - heat: 热度（浏览量）
      - link: 原文链接
      - publish_time: 发布时间
    """
    unique_id = f"cnsec_{article['article_id']}"

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                INSERT IGNORE INTO intel_items
                (tweet_id, title, summary, full_text, category, severity,
                 source, source_icon, tags, heat, comments, ioc, link,
                 keyword, user_name, user_screen_name, user_followers,
                 retweet_count, favorite_count, reply_count, quote_count,
                 lang, tweet_created_at)
                VALUES
                (%s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s)
                """
                params = (
                    unique_id,
                    article.get("title", ""),
                    article.get("summary", ""),
                    article.get("full_text", ""),
                    article.get("category", "general"),
                    article.get("severity", "low"),
                    article.get("source", "CN-SEC"),
                    article.get("source_icon", "ri-newspaper-line"),
                    json.dumps(article.get("tags", []), ensure_ascii=False),
                    article.get("heat", 0),
                    0,  # comments
                    json.dumps([], ensure_ascii=False),  # ioc
                    article.get("link", ""),
                    "cn-sec",  # keyword 字段标识来源
                    "CN-SEC 中文网",  # user_name
                    "cn-sec.com",  # user_screen_name
                    0,  # user_followers
                    0,  # retweet_count
                    0,  # favorite_count
                    0,  # reply_count
                    0,  # quote_count
                    "zh",  # lang
                    article.get("publish_time", ""),  # tweet_created_at
                )
                cursor.execute(sql, params)
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"插入文章失败 [{unique_id}]: {e}")
        return False
