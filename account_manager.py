"""
账户管理工具 - 管理 Twitter Cookie 账户
用法:
  python3 account_manager.py show        # 查看当前账户信息
  python3 account_manager.py test        # 测试 Cookie 是否有效
  python3 account_manager.py update      # 交互式更新 Cookie
"""
import json
import sys
import httpx

from config import COOKIES_FILE, BEARER_TOKEN, USER_AGENT
from transaction_id import generate_transaction_id


def load_cookies() -> dict:
    with open(COOKIES_FILE, "r") as f:
        return json.load(f)


def show_account():
    """显示当前账户信息"""
    cookies = load_cookies()
    print("📋 当前 Cookie 账户信息:")
    print(f"  auth_token: {cookies.get('auth_token', 'N/A')[:20]}...")
    print(f"  ct0:        {cookies.get('ct0', 'N/A')[:20]}...")
    print(f"  twid:       {cookies.get('twid', 'N/A')}")
    print(f"  总字段数:   {len(cookies)}")


def test_cookie():
    """测试 Cookie 是否有效"""
    cookies = load_cookies()
    ct0 = cookies.get("ct0", "")
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())

    headers = {
        "authorization": f"Bearer {BEARER_TOKEN}",
        "x-csrf-token": ct0,
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-active-user": "yes",
        "x-client-transaction-id": generate_transaction_id(),
        "user-agent": USER_AGENT,
        "cookie": cookie_str,
    }

    # 用 Viewer API 测试（获取当前登录用户信息）
    url = "https://api.x.com/graphql/OXXUyHfKYZ-xGaVaEhfCVA/Viewer"
    params = {
        "variables": '{"withCommunitiesMemberships":false}',
        "features": '{"rweb_tipjar_consumption_enabled":true,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"responsive_web_graphql_timeline_navigation_enabled":true}',
    }

    print("🔍 测试 Cookie 有效性...")
    try:
        with httpx.Client(timeout=15, http2=True) as client:
            resp = client.get(url, headers=headers, params=params)

        if resp.status_code == 200:
            data = resp.json()
            user = data.get("data", {}).get("viewer", {}).get("user_results", {}).get("result", {})
            legacy = user.get("legacy", {})
            name = legacy.get("name", "未知")
            screen_name = legacy.get("screen_name", "未知")
            print(f"✅ Cookie 有效!")
            print(f"  用户: {name} (@{screen_name})")
            print(f"  粉丝: {legacy.get('followers_count', 0)}")
            return True
        elif resp.status_code == 403:
            print("❌ Cookie 已失效 (403 Forbidden)")
            return False
        else:
            print(f"⚠️ 未知状态: HTTP {resp.status_code}")
            print(f"  响应: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False


def update_cookie():
    """交互式更新关键 Cookie 字段"""
    cookies = load_cookies()
    print("🔧 更新 Cookie（直接回车跳过不修改）")

    for key in ["auth_token", "ct0", "twid", "kdt", "_twitter_sess"]:
        current = cookies.get(key, "")
        display = current[:30] + "..." if len(current) > 30 else current
        new_val = input(f"  {key} [{display}]: ").strip()
        if new_val:
            cookies[key] = new_val

    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f, indent=2, ensure_ascii=False)
    print("✅ Cookie 已更新")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 account_manager.py [show|test|update]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "show":
        show_account()
    elif cmd == "test":
        test_cookie()
    elif cmd == "update":
        update_cookie()
    else:
        print(f"未知命令: {cmd}")
        print("可用命令: show, test, update")
