"""
DeepSeek 中文情报摘要生成器 - ThreatPulse
已优化：默认使用免费方案（Google翻译 + 中文截取），DeepSeek 仅作为备用
"""
import json
import logging
import re
import time
import urllib.request
import urllib.error
import urllib.parse

logger = logging.getLogger("deepseek")

# DeepSeek API 配置（备用）
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-chat"

# 系统提示词（精简版，节省 input token）
SYSTEM_PROMPT = """你是网络安全情报分析师。将以下安全情报总结为50-150字的中文摘要。
要求：保留CVE编号、攻击手法、工具名等关键术语；突出威胁要点和影响范围；语言简洁专业；直接输出摘要，不加前缀。"""

# 内存缓存：避免同一进程内重复调用
_summary_cache = {}
_CACHE_MAX_SIZE = 500


def _cache_key(title: str, content: str) -> str:
    """生成缓存键（基于内容前200字的hash）"""
    import hashlib
    raw = f"{title}|{content[:200]}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _is_chinese(text: str) -> bool:
    """判断文本是否以中文为主"""
    if not text:
        return False
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    total_chars = len(text.strip())
    if total_chars == 0:
        return False
    return chinese_chars / total_chars > 0.15


def _translate_google(text: str, target_lang: str = "zh-CN") -> str:
    """使用 Google 翻译免费 API 进行翻译"""
    if not text or not text.strip():
        return ""
    try:
        text = text[:2000]
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target_lang,
            "dt": "t",
            "q": text,
        }
        full_url = url + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(full_url)
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            translated_parts = []
            if data and data[0]:
                for part in data[0]:
                    if part[0]:
                        translated_parts.append(part[0])
            result = "".join(translated_parts)
            return result.strip() if result else ""
    except Exception as e:
        logger.warning(f"Google 翻译失败: {e}")
        return ""


def _truncate_chinese_summary(text: str, max_len: int = 150) -> str:
    """
    从中文文本中截取摘要（取前 max_len 字，尽量在句号/分号处截断）
    """
    if not text:
        return ""
    # 去掉多余空白
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= max_len:
        return text

    # 尝试在句号、分号、感叹号处截断
    truncated = text[:max_len]
    for sep in ['。', '；', '！', '？', '. ', '; ']:
        last_pos = truncated.rfind(sep)
        if last_pos > max_len * 0.4:  # 至少保留40%内容
            return truncated[:last_pos + len(sep)].strip()

    # 没有找到合适的截断点，直接截断
    return truncated.strip() + "..."


def generate_summary_free(title: str, content: str) -> str:
    """
    免费摘要生成方案：
    - 中文内容 → 截取前150字作为摘要
    - 英文内容 → Google翻译为中文作为摘要
    
    Args:
        title: 情报标题
        content: 情报正文
    
    Returns:
        中文摘要字符串，失败返回 None
    """
    # 检查缓存
    ck = _cache_key(title, content or "")
    if ck in _summary_cache:
        logger.debug("命中摘要缓存，跳过翻译调用")
        return _summary_cache[ck]

    combined = f"{title}。{content}" if content else title
    if not combined or not combined.strip():
        return None

    summary = None

    if _is_chinese(combined):
        # 中文内容：截取前150字作为摘要
        # 优先使用正文，正文太短则用标题+正文
        source_text = content if content and len(content) > 50 else combined
        summary = _truncate_chinese_summary(source_text, max_len=150)
        logger.debug(f"中文截取摘要 ({len(summary)}字)")
    else:
        # 英文内容：用 Google 翻译
        # 先截取合理长度再翻译（节省翻译量）
        source_text = combined[:500]  # 英文500字符大约200-300词，足够生成摘要
        translated = _translate_google(source_text)
        if translated:
            summary = _truncate_chinese_summary(translated, max_len=150)
            logger.debug(f"Google翻译摘要 ({len(summary)}字)")
        else:
            # Google翻译失败，尝试直接截取英文
            summary = source_text[:200].strip()
            if summary:
                summary += "..."
            logger.debug("Google翻译失败，使用英文截取")

    # 写入缓存
    if summary and len(_summary_cache) < _CACHE_MAX_SIZE:
        _summary_cache[ck] = summary

    return summary if summary else None


def generate_summary_deepseek(title: str, content: str, max_retries: int = 2) -> str:
    """
    调用 DeepSeek API 生成中文摘要（备用方案，仅在需要高质量摘要时使用）
    """
    # 检查缓存
    ck = _cache_key(title, content or "")
    if ck in _summary_cache:
        logger.debug("命中摘要缓存，跳过 API 调用")
        return _summary_cache[ck]

    content_truncated = content[:1000] if content else ""
    user_message = f"标题：{title}\n内容：{content_truncated}"

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        "max_tokens": 200,
        "temperature": 0.3,
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

                for prefix in ["摘要：", "摘要:", "总结：", "总结:", "概要：", "概要:"]:
                    if summary.startswith(prefix):
                        summary = summary[len(prefix):].strip()

                logger.debug(f"DeepSeek 摘要生成成功 ({len(summary)}字)")

                if len(_summary_cache) < _CACHE_MAX_SIZE:
                    _summary_cache[ck] = summary

                return summary

        except urllib.error.HTTPError as e:
            if e.code == 429:
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


# ===== 默认使用免费方案 =====
generate_summary = generate_summary_free


def translate_text_free(text: str) -> str:
    """
    免费翻译函数（替代 DeepSeek 翻译）
    用于 GitHub Trending 等场景的简短翻译
    """
    if not text:
        return ""
    if _is_chinese(text):
        return text  # 已经是中文
    translated = _translate_google(text[:200])
    return translated if translated else ""


def batch_generate_summaries(items: list, delay: float = 0.3) -> dict:
    """
    批量生成摘要（使用免费方案）
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

        # Google翻译也需要间隔，避免被封
        if i < total and delay > 0:
            time.sleep(delay)

    return results


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.DEBUG)

    print("=== 测试英文情报（Google翻译方案）===")
    result1 = generate_summary(
        "Critical RCE Vulnerability in Apache Struts CVE-2024-53677",
        "A critical remote code execution vulnerability has been discovered in Apache Struts framework. The vulnerability, tracked as CVE-2024-53677, allows unauthenticated attackers to execute arbitrary code on affected servers. All versions prior to 6.4.0 are affected. Apache has released an emergency patch."
    )
    print(f"英文摘要: {result1}\n")

    print("=== 测试中文情报（截取方案）===")
    result2 = generate_summary(
        "Apache Struts 严重远程代码执行漏洞 CVE-2024-53677",
        "Apache Struts框架被发现存在严重的远程代码执行漏洞，编号CVE-2024-53677。该漏洞允许未经身份验证的攻击者在受影响的服务器上执行任意代码。所有6.4.0之前的版本均受影响。Apache已发布紧急补丁，建议用户立即更新。目前已有在野利用报告，多个安全团队确认该漏洞的危害性极高。"
    )
    print(f"中文摘要: {result2}\n")

    print("=== 测试翻译函数 ===")
    result3 = translate_text_free("A lightweight framework for building AI agents with tool use capabilities")
    print(f"翻译结果: {result3}")