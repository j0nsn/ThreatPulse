"""
Twitter 关键词爬虫 - 主入口（MySQL 版本）
从 keywords.yml 读取关键词，爬取推文并保存到 MySQL + output 目录
"""
import os
import sys
import json
import logging
import yaml
from datetime import datetime, timedelta
from itertools import product
from email.utils import parsedate_to_datetime as _parse_rfc2822

from config import KEYWORDS_FILE, OUTPUT_DIR, MAX_TWEETS_PER_KEYWORD
from scraper import TwitterScraper
from db import batch_insert_tweets, update_summary_cn, check_duplicate_by_summary_cn
from deepseek_summarizer import generate_summary

# === 时间过滤配置 ===
MAX_AGE_DAYS = 3  # 只接收最近 N 天内发布的推文

# === 日志配置 ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def is_tweet_too_old(tweet: dict, max_age_days: int = MAX_AGE_DAYS) -> bool:
    """
    检查推文是否超过最大允许天数
    Twitter created_at 格式: "Wed Apr 09 12:34:56 +0000 2026"
    返回 True 表示推文太旧，应该跳过
    """
    created_at = tweet.get("created_at", "")
    if not created_at:
        return False  # 没有时间信息，不过滤（保守策略）

    try:
        # 解析 Twitter 时间格式 (RFC 2822 兼容)
        tweet_dt = _parse_rfc2822(created_at)
        cutoff = datetime.now(tweet_dt.tzinfo) - timedelta(days=max_age_days)
        if tweet_dt < cutoff:
            return True
    except Exception:
        # 如果解析失败，尝试其他格式
        try:
            # 尝试 "Wed Apr 09 12:34:56 +0000 2026" 格式
            from email.utils import parsedate_tz, mktime_tz
            parsed = parsedate_tz(created_at)
            if parsed:
                ts = mktime_tz(parsed)
                tweet_dt = datetime.utcfromtimestamp(ts)
                cutoff = datetime.utcnow() - timedelta(days=max_age_days)
                if tweet_dt < cutoff:
                    return True
        except Exception:
            pass

    return False


def tweet_exists_in_db(tweet_id: str) -> bool:
    """检查 tweet_id 是否已存在于数据库中（避免重复调用 DeepSeek）"""
    try:
        import pymysql
        conn = pymysql.connect(
            host="localhost", port=3306,
            user="threatpulse", password=os.environ.get("DB_PASSWORD", ""),
            database="threatpulse", charset="utf8mb4",
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM intel_items WHERE tweet_id = %s LIMIT 1", (tweet_id,))
                return cursor.fetchone() is not None
        finally:
            conn.close()
    except Exception:
        return False


def load_keywords() -> list[str]:
    """
    从 keywords.yml 加载 Twitter 搜索关键词
    支持两种模式：
    - custome: 直接搜索
    - keyword1 × keyword2: 笛卡尔积拼接搜索
    """
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    twitter_config = config.get("twitter", {})
    keywords = []

    # custome 直接搜索
    custome = twitter_config.get("custome", [])
    for kw in custome:
        if isinstance(kw, str) and kw.strip():
            keywords.append(kw.strip())

    # keyword1 × keyword2 笛卡尔积
    kw1_list = twitter_config.get("keyword1", [])
    kw2_list = twitter_config.get("keyword2", [])
    if kw1_list and kw2_list:
        for k1, k2 in product(kw1_list, kw2_list):
            if isinstance(k1, str) and isinstance(k2, str):
                combined = f"{k1.strip()} {k2.strip()}"
                keywords.append(combined)

    # 去重但保持顺序
    seen = set()
    unique = []
    for kw in keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            unique.append(kw)

    return unique


def save_results(keyword: str, tweets: list[dict], output_dir: str):
    """保存单个关键词的爬取结果到 JSON 文件"""
    if not tweets:
        return

    safe_name = keyword.replace(" ", "_").replace("/", "_").replace("\\", "_")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "_-")[:80]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_name}_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)

    data = {
        "keyword": keyword,
        "crawl_time": datetime.now().isoformat(),
        "count": len(tweets),
        "tweets": tweets,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"💾 JSON保存 {len(tweets)} 条 → {filename}")


def main():
    """主流程"""
    logger.info("=" * 60)
    logger.info("🐦 Twitter 关键词爬虫启动（MySQL 版本）")
    logger.info("=" * 60)

    # 加载关键词
    keywords = load_keywords()
    if not keywords:
        logger.error("❌ 未找到关键词，请检查 keywords.yml")
        sys.exit(1)

    logger.info(f"📋 共 {len(keywords)} 个搜索词")

    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 初始化爬虫
    scraper = TwitterScraper()
    total_tweets = 0
    total_new_db = 0
    success_count = 0
    fail_count = 0
    deepseek_calls = 0       # 统计 DeepSeek 实际调用次数
    skipped_existing = 0     # 统计跳过的已存在推文

    try:
        for i, keyword in enumerate(keywords, 1):
            logger.info(f"\n[{i}/{len(keywords)}] 搜索: {keyword}")

            tweets = scraper.search(keyword, MAX_TWEETS_PER_KEYWORD)

            if tweets:
                # 保存到 JSON 文件
                save_results(keyword, tweets, OUTPUT_DIR)

                # 时间过滤：跳过超过 MAX_AGE_DAYS 天前发布的推文
                fresh_tweets = []
                skipped_old = 0
                for t in tweets:
                    if is_tweet_too_old(t, MAX_AGE_DAYS):
                        skipped_old += 1
                        continue
                    fresh_tweets.append(t)
                if skipped_old > 0:
                    logger.info(f"  🕐 时间过滤: 跳过 {skipped_old} 条超过 {MAX_AGE_DAYS} 天的旧推文")
                tweets = fresh_tweets

                # 🆕 优化：先用 tweet_id 去重，再调 DeepSeek（避免浪费 token）
                new_tweets = []
                for t in tweets:
                    tid = t.get("tweet_id", "")
                    if tid and tweet_exists_in_db(tid):
                        skipped_existing += 1
                        continue
                    new_tweets.append(t)

                if skipped_existing > 0 and len(new_tweets) < len(tweets):
                    logger.info(f"  🔄 DB去重: 跳过 {len(tweets) - len(new_tweets)} 条已入库推文（节省 DeepSeek 调用）")

                # 仅为新推文生成 DeepSeek 中文摘要
                final_tweets = []
                for t in new_tweets:
                    title = t.get("full_text", "")[:80]
                    content_text = t.get("full_text", "")
                    if content_text:
                        # 🆕 截断内容到 800 字符（推文通常很短，不需要 2000）
                        summary_cn = generate_summary(title, content_text[:800])
                        deepseek_calls += 1
                        if summary_cn:
                            # 用中文摘要做去重检查（防止不同 tweet_id 但内容相似的情报）
                            if check_duplicate_by_summary_cn(summary_cn):
                                logger.info(f"  🔄 中文摘要去重: 跳过相似情报")
                                continue
                            t["summary_cn"] = summary_cn
                    final_tweets.append(t)

                # 写入 MySQL
                new_count = batch_insert_tweets(final_tweets, keyword)
                total_new_db += new_count
                logger.info(f"  📊 MySQL: 新增 {new_count} 条, 跳过 {len(final_tweets) - new_count} 条(已存在)")

                total_tweets += len(tweets)
                success_count += 1
            else:
                logger.warning(f"  ⚠️ '{keyword}' 无结果")
                fail_count += 1

    except KeyboardInterrupt:
        logger.info("\n⏹️ 用户中断")
    finally:
        scraper.close()

    # 汇总
    logger.info("\n" + "=" * 60)
    logger.info("📊 爬取完成汇总:")
    logger.info(f"  关键词总数: {len(keywords)}")
    logger.info(f"  成功: {success_count}, 失败/无结果: {fail_count}")
    logger.info(f"  总推文数: {total_tweets}")
    logger.info(f"  MySQL 新增: {total_new_db}")
    logger.info(f"  DeepSeek 实际调用: {deepseek_calls} 次")
    logger.info(f"  DB去重跳过(节省调用): {skipped_existing} 次")
    logger.info(f"  输出目录: {OUTPUT_DIR}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
