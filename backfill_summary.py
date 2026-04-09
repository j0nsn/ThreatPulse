#!/usr/bin/env python3
"""
存量情报中文摘要回填脚本
为已入库但没有 summary_cn 的情报批量生成 DeepSeek 中文摘要
"""
import sys
import time
import logging

sys.path.insert(0, "/data/Th")

from db import get_items_without_summary_cn, update_summary_cn
from deepseek_summarizer import generate_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("backfill")

# 每批处理数量
BATCH_SIZE = 50
# 每次 API 调用间隔（秒）
API_DELAY = 0.5
# 最大处理总量（0 = 不限制）
MAX_TOTAL = 0


def backfill():
    """执行存量回填"""
    total_processed = 0
    total_success = 0
    total_failed = 0
    batch_num = 0

    logger.info("=" * 60)
    logger.info("🔄 存量情报中文摘要回填开始")
    logger.info(f"   每批: {BATCH_SIZE} 条, API间隔: {API_DELAY}s")
    logger.info("=" * 60)

    while True:
        batch_num += 1
        items = get_items_without_summary_cn(BATCH_SIZE)

        if not items:
            logger.info("✅ 所有情报已有中文摘要，回填完成！")
            break

        logger.info(f"\n📦 第 {batch_num} 批，共 {len(items)} 条待处理")

        for i, item in enumerate(items, 1):
            item_id = item["id"]
            title = item.get("title", "")
            # 优先用 full_text，其次用 summary
            content = item.get("full_text", "") or item.get("summary", "")

            if not content:
                logger.warning(f"  [{i}] ID={item_id} 无内容，跳过")
                total_failed += 1
                continue

            logger.info(f"  [{i}/{len(items)}] ID={item_id} | {title[:50]}")

            summary_cn = generate_summary(title, content)

            if summary_cn:
                if update_summary_cn(item_id, summary_cn):
                    total_success += 1
                    logger.info(f"    ✅ {summary_cn[:60]}...")
                else:
                    total_failed += 1
                    logger.warning(f"    ❌ 数据库更新失败")
            else:
                total_failed += 1
                logger.warning(f"    ❌ DeepSeek 摘要生成失败")

            total_processed += 1

            # 检查是否达到最大处理量
            if MAX_TOTAL > 0 and total_processed >= MAX_TOTAL:
                logger.info(f"⚠️ 已达最大处理量 {MAX_TOTAL}，停止")
                break

            # API 调用间隔
            if i < len(items):
                time.sleep(API_DELAY)

        if MAX_TOTAL > 0 and total_processed >= MAX_TOTAL:
            break

        # 批次间休息
        logger.info(f"  批次完成，休息 2 秒...")
        time.sleep(2)

    # 汇总
    logger.info("\n" + "=" * 60)
    logger.info("📊 回填完成汇总:")
    logger.info(f"  总处理: {total_processed}")
    logger.info(f"  成功: {total_success}")
    logger.info(f"  失败: {total_failed}")
    logger.info("=" * 60)

    return total_success


if __name__ == "__main__":
    backfill()
