"""
Twitter 爬虫核心模块
使用 httpx 直接调用 Twitter GraphQL API 搜索推文
"""
import json
import time
import random
import httpx
import logging
from urllib.parse import urlparse
from typing import Optional

from config import (
    COOKIES_FILE, BEARER_TOKEN, SEARCH_ENDPOINT,
    REQUEST_TIMEOUT, MAX_RETRIES, RETRY_BACKOFF,
    MAX_TWEETS_PER_KEYWORD, MIN_DELAY, MAX_DELAY, USER_AGENT
)
from transaction_id import get_generator

logger = logging.getLogger(__name__)


class TwitterScraper:
    """Twitter GraphQL API 爬虫"""

    def __init__(self):
        self.cookies = self._load_cookies()
        self.client = self._build_client()
        self._request_count = 0
        # 初始化 transaction-id 生成器
        self._tid_gen = get_generator()

    def _load_cookies(self) -> dict:
        """加载 cookies.json"""
        with open(COOKIES_FILE, "r") as f:
            return json.load(f)

    def _build_client(self) -> httpx.Client:
        """构建 HTTP 客户端"""
        return httpx.Client(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            http2=True,
        )

    def _get_headers(self, method: str = "GET", path: str = "/") -> dict:
        """构建请求头（每次请求都重新生成 transaction-id）"""
        ct0 = self.cookies.get("ct0", "")
        tid = self._tid_gen.generate(method, path)
        return {
            "authorization": f"Bearer {BEARER_TOKEN}",
            "x-csrf-token": ct0,
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "en",
            "x-client-transaction-id": tid,
            "user-agent": USER_AGENT,
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "referer": "https://x.com/search",
            "origin": "https://x.com",
        }

    def _get_cookie_header(self) -> str:
        """将 cookies dict 转为 Cookie header 字符串"""
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())

    def _build_search_variables(self, query: str, cursor: Optional[str] = None) -> str:
        """构建 GraphQL 搜索变量"""
        variables = {
            "rawQuery": query,
            "count": 20,
            "querySource": "typed_query",
            "product": "Latest",
        }
        if cursor:
            variables["cursor"] = cursor
        return json.dumps(variables, separators=(",", ":"))

    def _build_search_features(self) -> str:
        """构建 GraphQL features 参数"""
        features = {
            "rweb_tipjar_consumption_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "communities_web_enable_tweet_community_results_fetch": True,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "articles_preview_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "tweet_awards_web_tipping_enabled": False,
            "creator_subscriptions_quote_tweet_preview_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "rweb_video_timestamps_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "responsive_web_enhance_cards_enabled": False,
        }
        return json.dumps(features, separators=(",", ":"))

    def _random_delay(self):
        """随机延迟，防止触发速率限制"""
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        logger.debug(f"延迟 {delay:.1f}s")
        time.sleep(delay)

    def _parse_tweets(self, data: dict) -> tuple[list[dict], Optional[str]]:
        """
        从 GraphQL 响应中解析推文数据
        返回: (推文列表, 下一页 cursor)
        """
        tweets = []
        next_cursor = None

        try:
            instructions = (
                data.get("data", {})
                .get("search_by_raw_query", {})
                .get("search_timeline", {})
                .get("timeline", {})
                .get("instructions", [])
            )

            for instruction in instructions:
                if instruction.get("type") == "TimelineAddEntries":
                    entries = instruction.get("entries", [])
                    for entry in entries:
                        entry_id = entry.get("entryId", "")

                        # 提取 cursor
                        if "cursor-bottom" in entry_id:
                            content = entry.get("content", {})
                            next_cursor = content.get("value") or content.get("itemContent", {}).get("value")
                            continue

                        # 提取推文
                        if entry_id.startswith("tweet-"):
                            tweet_data = self._extract_tweet(entry)
                            if tweet_data:
                                tweets.append(tweet_data)

                # 处理 TimelineReplaceEntry（翻页时可能出现）
                elif instruction.get("type") == "TimelineReplaceEntry":
                    entry = instruction.get("entry", {})
                    entry_id = entry.get("entryId", "")
                    if "cursor-bottom" in entry_id:
                        content = entry.get("content", {})
                        next_cursor = content.get("value") or content.get("itemContent", {}).get("value")

        except Exception as e:
            logger.error(f"解析推文失败: {e}")

        return tweets, next_cursor

    def _extract_tweet(self, entry: dict) -> Optional[dict]:
        """从单个 entry 中提取推文信息"""
        try:
            item_content = (
                entry.get("content", {})
                .get("itemContent", {})
                .get("tweet_results", {})
                .get("result", {})
            )

            # 处理 tweet with visibility results
            if item_content.get("__typename") == "TweetWithVisibilityResults":
                item_content = item_content.get("tweet", {})

            if not item_content or item_content.get("__typename") not in ("Tweet", None):
                if item_content.get("__typename") != "Tweet" and "__typename" in item_content:
                    return None

            legacy = item_content.get("legacy", {})
            core = item_content.get("core", {})
            user_results = core.get("user_results", {}).get("result", {})
            user_legacy = user_results.get("legacy", {})
            # Twitter 2026: name/screen_name 移到了 user_results.core 下
            user_core = user_results.get("core", {})

            tweet_id = legacy.get("id_str") or item_content.get("rest_id", "")
            if not tweet_id:
                return None

            # 优先从 user_core 取 name/screen_name，兼容旧结构从 user_legacy 取
            screen_name = user_core.get("screen_name") or user_legacy.get("screen_name", "")
            name = user_core.get("name") or user_legacy.get("name", "")
            followers_count = user_legacy.get("followers_count", 0)

            return {
                "tweet_id": tweet_id,
                "created_at": user_core.get("created_at") or legacy.get("created_at", ""),
                "full_text": legacy.get("full_text", ""),
                "user": {
                    "id": user_results.get("rest_id", ""),
                    "name": name,
                    "screen_name": screen_name,
                    "followers_count": followers_count,
                    "verified": user_results.get("is_blue_verified", False),
                },
                "retweet_count": legacy.get("retweet_count", 0),
                "favorite_count": legacy.get("favorite_count", 0),
                "reply_count": legacy.get("reply_count", 0),
                "quote_count": legacy.get("quote_count", 0),
                "lang": legacy.get("lang", ""),
                "url": f"https://x.com/{screen_name or '_'}/status/{tweet_id}",
            }
        except Exception as e:
            logger.debug(f"提取推文失败: {e}")
            return None

    def search(self, query: str, max_count: int = MAX_TWEETS_PER_KEYWORD) -> list[dict]:
        """
        搜索推文
        :param query: 搜索关键词
        :param max_count: 最大获取条数
        :return: 推文列表
        """
        all_tweets = []
        cursor = None
        page = 0

        # 计算 API path 用于生成 transaction-id
        api_path = urlparse(SEARCH_ENDPOINT).path

        logger.info(f"🔍 搜索: '{query}' (最多 {max_count} 条)")

        while len(all_tweets) < max_count:
            page += 1
            retry_count = 0

            while retry_count < MAX_RETRIES:
                try:
                    params = {
                        "variables": self._build_search_variables(query, cursor),
                        "features": self._build_search_features(),
                    }

                    headers = self._get_headers(method="GET", path=api_path)
                    headers["cookie"] = self._get_cookie_header()

                    response = self.client.get(
                        SEARCH_ENDPOINT,
                        params=params,
                        headers=headers,
                    )

                    self._request_count += 1

                    if response.status_code == 200:
                        data = response.json()
                        tweets, next_cursor = self._parse_tweets(data)

                        if not tweets:
                            logger.info(f"  第 {page} 页无更多结果")
                            return all_tweets

                        all_tweets.extend(tweets)
                        logger.info(f"  第 {page} 页: +{len(tweets)} 条 (累计 {len(all_tweets)})")

                        cursor = next_cursor
                        if not cursor:
                            logger.info("  无更多分页")
                            return all_tweets

                        self._random_delay()
                        break

                    elif response.status_code == 429:
                        wait = RETRY_BACKOFF ** (retry_count + 2)
                        logger.warning(f"  ⚠️ 速率限制 (429)，等待 {wait}s...")
                        time.sleep(wait)
                        retry_count += 1

                    elif response.status_code == 403:
                        logger.error("  ❌ 403 Forbidden - Cookie 可能已失效")
                        return all_tweets

                    else:
                        logger.warning(f"  ⚠️ HTTP {response.status_code}，重试 {retry_count + 1}/{MAX_RETRIES}")
                        retry_count += 1
                        time.sleep(RETRY_BACKOFF ** retry_count)

                except httpx.TimeoutException:
                    logger.warning(f"  ⚠️ 请求超时，重试 {retry_count + 1}/{MAX_RETRIES}")
                    retry_count += 1
                    time.sleep(RETRY_BACKOFF ** retry_count)

                except Exception as e:
                    logger.error(f"  ❌ 请求异常: {e}")
                    retry_count += 1
                    time.sleep(RETRY_BACKOFF ** retry_count)

            if retry_count >= MAX_RETRIES:
                logger.error(f"  ❌ 达到最大重试次数，停止搜索 '{query}'")
                break

        return all_tweets[:max_count]

    def close(self):
        """关闭 HTTP 客户端"""
        self.client.close()
        logger.info(f"📊 本次共发送 {self._request_count} 次请求")
