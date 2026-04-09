"""
Twitter 关键词爬虫 - 主入口（MySQL 版本）
从 keywords.yml 读取关键词，爬取推文并保存到 MySQL + output 目录
"""
import os
import sys
import json
import logging
import yaml
from datetime import datetime
from itertools import product

from config import KEYWORDS_FILE, OUTPUT_DIR, MAX_TWEETS_PER_KEYWORD
from scraper import TwitterScraper
from db import batch_insert_tweets

# === 日志配置 ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


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

    try:
        for i, keyword in enumerate(keywords, 1):
            logger.info(f"\n[{i}/{len(keywords)}] 搜索: {keyword}")

            tweets = scraper.search(keyword, MAX_TWEETS_PER_KEYWORD)

            if tweets:
                # 保存到 JSON 文件
                save_results(keyword, tweets, OUTPUT_DIR)

                # 写入 MySQL
                new_count = batch_insert_tweets(tweets, keyword)
                total_new_db += new_count
                logger.info(f"  📊 MySQL: 新增 {new_count} 条, 跳过 {len(tweets) - new_count} 条(已存在)")

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
    logger.info(f"  输出目录: {OUTPUT_DIR}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
