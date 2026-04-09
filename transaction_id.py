"""
x-client-transaction-id 生成器
使用 XClientTransaction 库正确生成 Twitter 所需的 transaction ID
需要从 x.com 主页提取 SVG 动画数据和 ondemand.s JS 文件
"""
import logging
import bs4
import httpx
from urllib.parse import urlparse
from x_client_transaction import ClientTransaction
from x_client_transaction.utils import get_ondemand_file_url

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


class TransactionIDGenerator:
    """Twitter x-client-transaction-id 生成器"""

    def __init__(self):
        self._ct = None
        self._initialized = False

    def initialize(self):
        """初始化：获取 x.com 主页和 ondemand.s 文件"""
        if self._initialized:
            return

        logger.info("🔑 初始化 x-client-transaction-id 生成器...")

        headers = {
            "Authority": "x.com",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Referer": "https://x.com",
            "User-Agent": USER_AGENT,
            "X-Twitter-Active-User": "yes",
            "X-Twitter-Client-Language": "en",
        }

        client = httpx.Client(
            timeout=30,
            follow_redirects=True,
            http2=True,
            headers=headers,
        )

        try:
            # Step 1: 获取 x.com 主页
            home_resp = client.get("https://x.com")
            home_page = bs4.BeautifulSoup(home_resp.content, "html.parser")
            logger.info(f"  主页获取成功 (HTTP {home_resp.status_code})")

            # Step 2: 获取 ondemand.s 文件
            ondemand_url = get_ondemand_file_url(response=home_page)
            logger.info(f"  ondemand URL: ...{ondemand_url[-40:]}")

            ondemand_resp = client.get(ondemand_url)
            ondemand_file = bs4.BeautifulSoup(ondemand_resp.content, "html.parser")
            logger.info(f"  ondemand 文件获取成功 (HTTP {ondemand_resp.status_code})")

            # Step 3: 创建 ClientTransaction 实例
            self._ct = ClientTransaction(
                home_page_response=home_page,
                ondemand_file_response=ondemand_file,
            )

            self._initialized = True
            logger.info("✅ transaction-id 生成器初始化完成")

        except Exception as e:
            logger.error(f"❌ transaction-id 生成器初始化失败: {e}")
            raise
        finally:
            client.close()

    def generate(self, method: str, path: str) -> str:
        """
        生成 x-client-transaction-id
        :param method: HTTP 方法 (GET/POST)
        :param path: API 路径 (如 /i/api/graphql/xxx/SearchTimeline)
        :return: transaction ID 字符串
        """
        if not self._initialized:
            self.initialize()

        tid = self._ct.generate_transaction_id(method=method, path=path)
        return tid


# 全局单例
_generator = None


def get_generator() -> TransactionIDGenerator:
    """获取全局 TransactionIDGenerator 实例"""
    global _generator
    if _generator is None:
        _generator = TransactionIDGenerator()
        _generator.initialize()
    return _generator


def generate_transaction_id(method: str = "GET", path: str = "/") -> str:
    """便捷函数：生成 transaction ID"""
    gen = get_generator()
    return gen.generate(method, path)
