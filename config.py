"""
配置文件 - Twitter 爬虫全局配置
"""
import os

# === 路径配置 ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(BASE_DIR, "cookies.json")
KEYWORDS_FILE = os.path.join(BASE_DIR, "keywords.yml")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# === Twitter API 配置 ===
BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

# GraphQL 搜索端点（最新 queryId，2026-04 验证有效）
SEARCH_QUERY_ID = "pCd62NDD9dlCDgEGgEVHMg"
SEARCH_ENDPOINT = f"https://x.com/i/api/graphql/{SEARCH_QUERY_ID}/SearchTimeline"

# === 请求配置 ===
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # 指数退避基数（秒）

# 每个关键词最大爬取条数
MAX_TWEETS_PER_KEYWORD = 40

# === 反爬配置 ===
MIN_DELAY = 2.0   # 请求间最小延迟（秒）
MAX_DELAY = 5.0   # 请求间最大延迟（秒）

# === User-Agent ===
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
