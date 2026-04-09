"""
DeepSeek 中文情报摘要生成器 - ThreatPulse
使用 DeepSeek Chat API 为安全情报生成精炼的中文摘要
"""
import os
import json
import logging
import time
import urllib.request
import urllib.error

logger = logging.getLogger("deepseek")

# DeepSeek API 配置
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-chat"

# 系统提示词
SYSTEM_PROMPT = """你是一名专业的网络安全情报分析师。你的任务是将安全情报内容总结为精炼的中文摘要。

要求：
1. 摘要长度控制在50-150字之间
2. 必须使用中文输出
3. 保留关键技术术语（如CVE编号、攻击手法名称、工具名称等可保留英文原文）
4. 突出情报的核心要点：什么威胁/技术、影响范围、严重程度
5. 语言简洁专业，适合安全从业人员快速阅读
6. 不要添加任何前缀如"摘要："、"总结："等
7. 直接输出摘要内容"""


def generate_summary(title: str, content: str, max_retries: int = 2) -> str:
    """
    调用 DeepSeek API 生成中文摘要
    
    Args:
        title: 情报标题
        content: 情报正文（会被截断到2000字符以控制token）
        max_retries: 最大重试次数
    
    Returns:
        中文摘要字符串，失败返回 None
    """
    # 截断内容，控制 token 消耗
    content_truncated = content[:2000] if content else ""
    
    user_message = f"请为以下安全情报生成中文摘要：\n\n标题：{title}\n\n内容：{content_truncated}"
    
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        "max_tokens": 300,
        "temperature": 0.3,  # 低温度，保证输出稳定
    }
    
    for attempt in range(max_retries + 1):
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                DEEPSEEK_API_URL,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                },
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                summary = result["choices"][0]["message"]["content"].strip()
                
                # 去除可能的前缀
                for prefix in ["摘要：", "摘要:", "总结：", "总结:", "概要：", "概要:"]:
                    if summary.startswith(prefix):
                        summary = summary[len(prefix):].strip()
                
                logger.debug(f"DeepSeek 摘要生成成功 ({len(summary)}字)")
                return summary
                
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # 速率限制，等待后重试
                wait_time = (attempt + 1) * 3
                logger.warning(f"DeepSeek API 速率限制，{wait_time}s 后重试 ({attempt+1}/{max_retries+1})")
                time.sleep(wait_time)
                continue
            elif e.code == 402:
                logger.error("DeepSeek API 余额不足")
                return None
            else:
                logger.error(f"DeepSeek API HTTP 错误 {e.code}: {e.read().decode('utf-8', errors='ignore')[:200]}")
                if attempt < max_retries:
                    time.sleep(2)
                    continue
                return None
        except Exception as e:
            logger.error(f"DeepSeek API 调用异常: {e}")
            if attempt < max_retries:
                time.sleep(2)
                continue
            return None
    
    return None


def batch_generate_summaries(items: list, delay: float = 0.5) -> dict:
    """
    批量生成摘要
    
    Args:
        items: [{"id": int, "title": str, "content": str}, ...]
        delay: 每次调用间隔（秒），避免速率限制
    
    Returns:
        {id: summary_cn} 字典
    """
    results = {}
    total = len(items)
    
    for i, item in enumerate(items, 1):
        item_id = item["id"]
        title = item.get("title", "")
        content = item.get("content", "")
        
        logger.info(f"  生成摘要 [{i}/{total}] {title[:40]}...")
        summary = generate_summary(title, content)
        
        if summary:
            results[item_id] = summary
            logger.info(f"    ✅ {summary[:60]}...")
        else:
            logger.warning(f"    ❌ 摘要生成失败")
        
        # 请求间隔，避免速率限制
        if i < total and delay > 0:
            time.sleep(delay)
    
    return results


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.DEBUG)
    result = generate_summary(
        "Critical RCE Vulnerability in Apache Struts CVE-2024-53677",
        "A critical remote code execution vulnerability has been discovered in Apache Struts framework. The vulnerability, tracked as CVE-2024-53677, allows unauthenticated attackers to execute arbitrary code on affected servers. All versions prior to 6.4.0 are affected. Apache has released an emergency patch."
    )
    print(f"\n生成的摘要: {result}")
