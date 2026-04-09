"""导入测试数据到 MySQL"""
import sys
sys.path.insert(0, '/data/Th')
from db import insert_tweet

test_tweets = [
    {
        "tweet_id": "test001",
        "full_text": "Massive DDoS attack targeting AI infrastructure providers. Multiple LLM API endpoints down for hours. Cloudflare reports 2.5 Tbps peak traffic. This is the largest attack on AI services this year.",
        "user": {"id": "1001", "name": "CyberSecNews", "screen_name": "cybersecnews", "followers_count": 85000, "verified": True},
        "retweet_count": 234, "favorite_count": 567, "reply_count": 89, "quote_count": 45,
        "lang": "en", "created_at": "2026-04-09T10:00:00Z",
        "url": "https://x.com/cybersecnews/status/test001"
    },
    {
        "tweet_id": "test002",
        "full_text": "OpenAI just released GPT-5 with breakthrough reasoning capabilities. The model achieves superhuman performance on math olympiad problems and shows emergent planning abilities.",
        "user": {"id": "1002", "name": "AI Research Daily", "screen_name": "airesearchdaily", "followers_count": 120000, "verified": True},
        "retweet_count": 1500, "favorite_count": 4200, "reply_count": 320, "quote_count": 180,
        "lang": "en", "created_at": "2026-04-09T09:30:00Z",
        "url": "https://x.com/airesearchdaily/status/test002"
    },
    {
        "tweet_id": "test003",
        "full_text": "New autonomous AI agent framework just dropped - supports multi-agent collaboration with MCP protocol. Built-in tool use and browser automation. Open source on GitHub.",
        "user": {"id": "1003", "name": "DevTools Weekly", "screen_name": "devtoolsweekly", "followers_count": 45000, "verified": False},
        "retweet_count": 89, "favorite_count": 230, "reply_count": 34, "quote_count": 12,
        "lang": "en", "created_at": "2026-04-09T08:15:00Z",
        "url": "https://x.com/devtoolsweekly/status/test003"
    },
    {
        "tweet_id": "test004",
        "full_text": "Critical vulnerability CVE-2026-1234 found in popular LLM serving framework. Remote code execution possible through crafted prompt injection. Patch immediately!",
        "user": {"id": "1004", "name": "VulnDB", "screen_name": "vulndb", "followers_count": 67000, "verified": True},
        "retweet_count": 456, "favorite_count": 890, "reply_count": 123, "quote_count": 67,
        "lang": "en", "created_at": "2026-04-09T07:00:00Z",
        "url": "https://x.com/vulndb/status/test004"
    },
    {
        "tweet_id": "test005",
        "full_text": "DeepSeek releases new open source LLM with 671B parameters. Beats GPT-4o on most benchmarks while being 10x cheaper to run. The open source AI revolution continues!",
        "user": {"id": "1005", "name": "Open Source AI", "screen_name": "opensourceai", "followers_count": 93000, "verified": True},
        "retweet_count": 2100, "favorite_count": 5600, "reply_count": 450, "quote_count": 230,
        "lang": "en", "created_at": "2026-04-09T06:00:00Z",
        "url": "https://x.com/opensourceai/status/test005"
    },
    {
        "tweet_id": "test006",
        "full_text": "Botnet leveraging IoT devices launches record-breaking DDoS attack against gaming platforms. Peak traffic exceeds 3 Tbps. Mirai variant with new evasion techniques detected.",
        "user": {"id": "1006", "name": "ThreatIntel", "screen_name": "threatintel", "followers_count": 78000, "verified": True},
        "retweet_count": 345, "favorite_count": 678, "reply_count": 56, "quote_count": 34,
        "lang": "en", "created_at": "2026-04-08T22:00:00Z",
        "url": "https://x.com/threatintel/status/test006"
    },
    {
        "tweet_id": "test007",
        "full_text": "Anthropic Claude 4 achieves new SOTA on agentic benchmarks. The model can now autonomously complete complex multi-step tasks with 95% success rate. Computer use capabilities significantly improved.",
        "user": {"id": "1007", "name": "Anthropic News", "screen_name": "anthropicnews", "followers_count": 156000, "verified": True},
        "retweet_count": 3200, "favorite_count": 8900, "reply_count": 670, "quote_count": 340,
        "lang": "en", "created_at": "2026-04-08T20:00:00Z",
        "url": "https://x.com/anthropicnews/status/test007"
    },
    {
        "tweet_id": "test008",
        "full_text": "New RAG (Retrieval Augmented Generation) technique reduces hallucination by 80%. Combines graph-based knowledge retrieval with chain-of-thought reasoning for more accurate LLM outputs.",
        "user": {"id": "1008", "name": "ML Research", "screen_name": "mlresearch", "followers_count": 110000, "verified": True},
        "retweet_count": 890, "favorite_count": 2300, "reply_count": 145, "quote_count": 78,
        "lang": "en", "created_at": "2026-04-08T18:00:00Z",
        "url": "https://x.com/mlresearch/status/test008"
    },
    {
        "tweet_id": "test009",
        "full_text": "Layer 7 DDoS attacks against API endpoints increased 300% in Q1 2026. AI-powered attack tools making it easier for low-skill attackers. Traditional WAFs struggling to keep up.",
        "user": {"id": "1009", "name": "SecurityWeek", "screen_name": "securityweek", "followers_count": 200000, "verified": True},
        "retweet_count": 567, "favorite_count": 1200, "reply_count": 89, "quote_count": 56,
        "lang": "en", "created_at": "2026-04-08T15:00:00Z",
        "url": "https://x.com/securityweek/status/test009"
    },
    {
        "tweet_id": "test010",
        "full_text": "Google Gemini 2.5 Pro introduces native multi-agent orchestration. Can spawn and coordinate specialized sub-agents for complex reasoning tasks. Available now via API.",
        "user": {"id": "1010", "name": "Google AI", "screen_name": "googleai", "followers_count": 500000, "verified": True},
        "retweet_count": 4500, "favorite_count": 12000, "reply_count": 890, "quote_count": 560,
        "lang": "en", "created_at": "2026-04-08T12:00:00Z",
        "url": "https://x.com/googleai/status/test010"
    },
    {
        "tweet_id": "test011",
        "full_text": "Major DDoS mitigation breakthrough: new ML-based detection system can identify and block attacks within 50ms. Open-sourced by Cloudflare research team.",
        "user": {"id": "1011", "name": "CloudflareEng", "screen_name": "cloudflareeng", "followers_count": 180000, "verified": True},
        "retweet_count": 780, "favorite_count": 2100, "reply_count": 120, "quote_count": 90,
        "lang": "en", "created_at": "2026-04-08T10:00:00Z",
        "url": "https://x.com/cloudflareeng/status/test011"
    },
    {
        "tweet_id": "test012",
        "full_text": "LLM fine-tuning just got 100x cheaper with new LoRA++ technique. Train a domain-specific model on a single GPU in under an hour. Paper and code released.",
        "user": {"id": "1012", "name": "Papers With Code", "screen_name": "paperswithcode", "followers_count": 250000, "verified": True},
        "retweet_count": 1800, "favorite_count": 4500, "reply_count": 230, "quote_count": 150,
        "lang": "en", "created_at": "2026-04-07T20:00:00Z",
        "url": "https://x.com/paperswithcode/status/test012"
    },
]

keywords = [
    "DDoS attack", "GPT-5", "AI agent framework", "LLM vulnerability",
    "deepseek open source", "botnet DDoS", "Claude 4", "RAG retrieval augmented",
    "layer 7 DDoS", "Gemini 2.5", "DDoS mitigation", "LLM fine-tuning"
]

total_new = 0
for i, tweet in enumerate(test_tweets):
    kw = keywords[i % len(keywords)]
    result = insert_tweet(tweet, kw)
    if result:
        total_new += 1
        print(f"  OK: {tweet['tweet_id']} (keyword: {kw})")
    else:
        print(f"  SKIP: {tweet['tweet_id']}")

print(f"\nTotal new: {total_new}")
