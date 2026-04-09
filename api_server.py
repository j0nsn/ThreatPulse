"""
Flask API 后端 - ThreatPulse 安全情报聚合平台 v4
安全加固版：IP频率限制 / JWT密钥持久化 / 登录响应不返回Token / 密码外部配置
"""
import logging
import re
import json
import hashlib
import hmac
import base64
import os
import time
import threading
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, jsonify, request, send_from_directory, redirect, make_response
from flask_cors import CORS
from db import (
    query_intel, get_stats, get_hot_keywords,
    get_tag_cloud, get_hot_attacks, search_suggest,
    get_github_trending, get_hot_topics
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ============== 安全配置加载 ==============

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_auth_config():
    """从外部配置文件加载认证信息（密码不再写在源码中）"""
    config_path = os.path.join(BASE_DIR, ".auth_config.json")
    if not os.path.exists(config_path):
        logger.critical(f"认证配置文件不存在: {config_path}")
        raise SystemExit("FATAL: .auth_config.json not found")
    with open(config_path, "r") as f:
        config = json.load(f)
    required_keys = ["admin_username", "password_salt", "password_hash"]
    for key in required_keys:
        if key not in config:
            raise SystemExit(f"FATAL: .auth_config.json missing key: {key}")
    logger.info("✅ 认证配置已从 .auth_config.json 加载")
    return config

def load_jwt_secret():
    """从持久化文件或环境变量加载 JWT Secret"""
    # 优先从环境变量读取
    secret = os.environ.get("TP_JWT_SECRET")
    if secret:
        logger.info("✅ JWT Secret 从环境变量加载")
        return secret
    # 其次从文件读取
    secret_path = os.path.join(BASE_DIR, ".jwt_secret")
    if os.path.exists(secret_path):
        with open(secret_path, "r") as f:
            secret = f.read().strip()
        if secret:
            logger.info("✅ JWT Secret 从 .jwt_secret 文件加载（持久化）")
            return secret
    # 都没有则报错退出
    logger.critical("JWT Secret 未配置！请创建 .jwt_secret 文件或设置 TP_JWT_SECRET 环境变量")
    raise SystemExit("FATAL: JWT Secret not configured")

# 加载配置
AUTH_CONFIG = load_auth_config()
JWT_SECRET = load_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = AUTH_CONFIG.get("jwt_expire_hours", 24)

ADMIN_USERNAME = AUTH_CONFIG["admin_username"]
ADMIN_PASSWORD_SALT = AUTH_CONFIG["password_salt"]
ADMIN_PASSWORD_HASH = AUTH_CONFIG["password_hash"]

# ============== IP 级登录频率限制 ==============

RATE_LIMIT_CONFIG = AUTH_CONFIG.get("rate_limit", {})
MAX_LOGIN_ATTEMPTS = RATE_LIMIT_CONFIG.get("max_attempts", 5)       # 窗口内最大尝试次数
RATE_WINDOW_SECONDS = RATE_LIMIT_CONFIG.get("window_seconds", 300)  # 滑动窗口（5分钟）
LOCKOUT_SECONDS = RATE_LIMIT_CONFIG.get("lockout_seconds", 900)     # 锁定时间（15分钟）

class LoginRateLimiter:
    """基于 IP 的登录频率限制器（线程安全）"""

    def __init__(self):
        self._lock = threading.Lock()
        # {ip: [timestamp1, timestamp2, ...]}  记录每个IP的失败时间戳
        self._attempts: dict[str, list[float]] = {}
        # {ip: lockout_until_timestamp}  记录锁定截止时间
        self._lockouts: dict[str, float] = {}

    def _cleanup_old_attempts(self, ip: str, now: float):
        """清理过期的尝试记录"""
        if ip in self._attempts:
            cutoff = now - RATE_WINDOW_SECONDS
            self._attempts[ip] = [t for t in self._attempts[ip] if t > cutoff]
            if not self._attempts[ip]:
                del self._attempts[ip]

    def is_locked(self, ip: str) -> tuple[bool, int]:
        """检查 IP 是否被锁定，返回 (是否锁定, 剩余秒数)"""
        now = time.time()
        with self._lock:
            if ip in self._lockouts:
                remaining = self._lockouts[ip] - now
                if remaining > 0:
                    return True, int(remaining)
                else:
                    del self._lockouts[ip]
            return False, 0

    def record_failure(self, ip: str) -> tuple[bool, int]:
        """
        记录一次失败尝试。
        返回 (是否触发锁定, 剩余尝试次数)
        """
        now = time.time()
        with self._lock:
            self._cleanup_old_attempts(ip, now)

            if ip not in self._attempts:
                self._attempts[ip] = []
            self._attempts[ip].append(now)

            attempt_count = len(self._attempts[ip])
            remaining = MAX_LOGIN_ATTEMPTS - attempt_count

            if attempt_count >= MAX_LOGIN_ATTEMPTS:
                # 触发锁定
                self._lockouts[ip] = now + LOCKOUT_SECONDS
                self._attempts.pop(ip, None)
                logger.warning(f"🔒 IP {ip} 登录失败 {attempt_count} 次，已锁定 {LOCKOUT_SECONDS}s")
                return True, 0

            return False, max(remaining, 0)

    def record_success(self, ip: str):
        """登录成功后清除该 IP 的失败记录"""
        with self._lock:
            self._attempts.pop(ip, None)
            self._lockouts.pop(ip, None)

    def cleanup_all(self):
        """定期清理所有过期数据（防内存泄漏）"""
        now = time.time()
        with self._lock:
            # 清理过期锁定
            expired_locks = [ip for ip, t in self._lockouts.items() if t <= now]
            for ip in expired_locks:
                del self._lockouts[ip]
            # 清理过期尝试记录
            for ip in list(self._attempts.keys()):
                self._cleanup_old_attempts(ip, now)

rate_limiter = LoginRateLimiter()

def _start_cleanup_timer():
    """每10分钟清理一次过期数据"""
    rate_limiter.cleanup_all()
    timer = threading.Timer(600, _start_cleanup_timer)
    timer.daemon = True
    timer.start()

_start_cleanup_timer()

# ============== 工具函数 ==============

def get_client_ip():
    """获取真实客户端 IP（支持 Nginx 反代）"""
    # 优先从 X-Real-IP 获取（Nginx 配置中已设置）
    ip = request.headers.get("X-Real-IP")
    if ip:
        return ip
    # 其次从 X-Forwarded-For 获取第一个 IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"

def strip_invisible(s: str) -> str:
    """去除零宽字符、不可见Unicode字符等隐藏字符"""
    import unicodedata
    cleaned = ''.join(c for c in s if unicodedata.category(c) not in ('Cf', 'Cc', 'Cs', 'Co'))
    return cleaned.strip()

def verify_password(plain_password: str) -> bool:
    """验证密码（恒定时间比较）"""
    input_hash = hashlib.sha256(
        (ADMIN_PASSWORD_SALT + plain_password).encode("utf-8")
    ).hexdigest()
    return hmac.compare_digest(input_hash, ADMIN_PASSWORD_HASH)

def create_jwt_token(username: str) -> str:
    """创建 JWT Token"""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": JWT_ALGORITHM, "typ": "JWT"}).encode()
    ).decode().rstrip("=")
    payload_data = {
        "sub": username,
        "exp": int((datetime.now() + timedelta(hours=JWT_EXPIRE_HOURS)).timestamp()),
        "iat": int(datetime.now().timestamp()),
    }
    payload = base64.urlsafe_b64encode(
        json.dumps(payload_data).encode()
    ).decode().rstrip("=")
    signature_input = f"{header}.{payload}"
    signature = base64.urlsafe_b64encode(
        hmac.new(JWT_SECRET.encode(), signature_input.encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def verify_jwt_token(token: str):
    """验证 JWT Token"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, signature = parts
        signature_input = f"{header}.{payload}"
        expected_sig = base64.urlsafe_b64encode(
            hmac.new(JWT_SECRET.encode(), signature_input.encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected_sig):
            return None
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        payload_data = json.loads(base64.urlsafe_b64decode(payload))
        if payload_data.get("exp", 0) < int(datetime.now().timestamp()):
            return None
        return payload_data.get("sub")
    except Exception:
        return None

def login_required(f):
    """登录认证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("tp_auth_token")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
        if not token or not verify_jwt_token(token):
            return jsonify({"code": 401, "msg": "未登录或登录已过期"}), 401
        return f(*args, **kwargs)
    return decorated

# ============== Flask 应用 ==============
app = Flask(__name__, static_folder="frontend", static_url_path="/static")
CORS(app, supports_credentials=True)

# ===== 认证相关路由（无需登录） =====

@app.route("/")
def root():
    """根路径：检查登录状态，未登录跳转登录页"""
    token = request.cookies.get("tp_auth_token")
    if token and verify_jwt_token(token):
        return send_from_directory("frontend", "index.html")
    return redirect("login")

@app.route("/login")
def login_page():
    """登录页面"""
    return send_from_directory("frontend", "login.html")

@app.route("/login.js")
def login_js():
    return send_from_directory("frontend", "login.js")

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    """登录接口（含 IP 频率限制）"""
    client_ip = get_client_ip()

    # ===== 检查 IP 是否被锁定 =====
    locked, remaining_seconds = rate_limiter.is_locked(client_ip)
    if locked:
        logger.warning(f"🚫 IP {client_ip} 处于锁定状态，剩余 {remaining_seconds}s")
        return jsonify({
            "success": False,
            "message": f"登录尝试过于频繁，请 {remaining_seconds} 秒后再试",
            "locked": True,
            "retry_after": remaining_seconds
        }), 429

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "请求数据格式错误"}), 400

    username = data.get("username", "")
    password = data.get("password", "")

    clean_username = strip_invisible(username)
    clean_password = strip_invisible(password)

    username_match = hmac.compare_digest(clean_username.encode(), ADMIN_USERNAME.encode())
    password_match = verify_password(clean_password)

    if not username_match or not password_match:
        # ===== 记录失败并检查是否触发锁定 =====
        just_locked, attempts_left = rate_limiter.record_failure(client_ip)
        time.sleep(0.5)  # 防时序攻击

        if just_locked:
            logger.warning(f"登录失败+锁定: IP={client_ip}, username={repr(clean_username)}")
            return jsonify({
                "success": False,
                "message": f"登录失败次数过多，账户已锁定 {LOCKOUT_SECONDS // 60} 分钟",
                "locked": True,
                "retry_after": LOCKOUT_SECONDS
            }), 429
        else:
            logger.warning(f"登录失败: IP={client_ip}, username={repr(clean_username)}, 剩余尝试={attempts_left}")
            msg = "用户名或密码错误"
            if attempts_left <= 2:
                msg += f"（还可尝试 {attempts_left} 次）"
            return jsonify({"success": False, "message": msg}), 401

    # ===== 登录成功 =====
    rate_limiter.record_success(client_ip)
    token = create_jwt_token(clean_username)
    logger.info(f"✅ 用户 {clean_username} 从 IP {client_ip} 登录成功")

    # 【安全加固】响应中不返回 Token 明文，仅通过 HttpOnly Cookie 传递
    resp = make_response(jsonify({
        "success": True,
        "message": "登录成功",
        "username": ADMIN_USERNAME,
        "expires_in": JWT_EXPIRE_HOURS * 3600,
    }))
    resp.set_cookie(
        key="tp_auth_token",
        value=token,
        httponly=True,
        samesite="Lax",
        max_age=JWT_EXPIRE_HOURS * 3600,
        path="/",
    )
    return resp

@app.route("/api/auth/check", methods=["GET"])
def api_auth_check():
    """检查登录状态"""
    token = request.cookies.get("tp_auth_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if token:
        username = verify_jwt_token(token)
        if username:
            return jsonify({"authenticated": True, "username": username})
    return jsonify({"authenticated": False})

@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    """退出登录"""
    resp = make_response(jsonify({"success": True, "message": "已退出登录"}))
    resp.delete_cookie("tp_auth_token", path="/")
    return resp

# ===== 静态文件（需要认证检查） =====

@app.route("/<path:filename>")
def static_files(filename):
    """静态文件服务 - 登录相关资源无需认证，其他需要认证"""
    # 【安全加固】阻止访问隐藏文件（.auth_config.json, .jwt_secret 等）
    if filename.startswith('.') or '/.' in filename:
        return jsonify({"code": 403, "msg": "禁止访问"}), 403

    # 登录页相关资源直接放行
    login_whitelist = ["login.html", "login.js", "style.css"]
    if filename in login_whitelist:
        return send_from_directory("frontend", filename)

    # 其他静态资源需要认证
    token = request.cookies.get("tp_auth_token")
    if not token or not verify_jwt_token(token):
        if filename.endswith(('.js', '.css', '.png', '.ico', '.svg', '.woff', '.woff2')):
            return jsonify({"code": 401, "msg": "未登录"}), 401
        return redirect("login")
    return send_from_directory("frontend", filename)

# ===== API 路由（需要登录） =====

@app.route("/api/intel", methods=["GET"])
@login_required
def api_intel():
    """查询情报列表"""
    category = request.args.get("category", "all")
    severity = request.args.get("severity")
    keyword = request.args.get("keyword")
    search = request.args.get("search")
    time_filter = request.args.get("time_filter", "all")
    sort_by = request.args.get("sort_by", "latest")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))

    result = query_intel(
        category=category, severity=severity, keyword=keyword,
        search=search, time_filter=time_filter, sort_by=sort_by,
        page=page, page_size=page_size
    )
    return jsonify({"code": 0, "data": result})

@app.route("/api/stats", methods=["GET"])
@login_required
def api_stats():
    """获取统计数据"""
    time_filter = request.args.get("time_filter", "all")
    stats = get_stats(time_filter)
    return jsonify({"code": 0, "data": stats})

@app.route("/api/hot-attacks", methods=["GET"])
@login_required
def api_hot_attacks():
    """获取热点攻击榜"""
    time_filter = request.args.get("time_filter", "all")
    limit = int(request.args.get("limit", 8))
    attacks = get_hot_attacks(time_filter, limit)
    return jsonify({"code": 0, "data": attacks})

@app.route("/api/tags", methods=["GET"])
@login_required
def api_tags():
    """获取标签云"""
    time_filter = request.args.get("time_filter", "all")
    limit = int(request.args.get("limit", 25))
    tags = get_tag_cloud(time_filter, limit)
    return jsonify({"code": 0, "data": tags})

@app.route("/api/keywords", methods=["GET"])
@login_required
def api_keywords():
    """获取热门关键词趋势"""
    time_filter = request.args.get("time_filter", "all")
    limit = int(request.args.get("limit", 10))
    keywords = get_hot_keywords(time_filter, limit)

    if keywords:
        max_cnt = keywords[0]["cnt"]
        for kw in keywords:
            kw["percent"] = int(kw["cnt"] / max_cnt * 100) if max_cnt > 0 else 0
            kw["trend"] = "up"
            kw["change"] = f"+{kw['cnt']}"
    return jsonify({"code": 0, "data": keywords})

@app.route("/api/summary", methods=["GET"])
@login_required
def api_summary():
    """获取 AI 态势摘要"""
    time_filter = request.args.get("time_filter", "all")
    stats = get_stats(time_filter)
    total = stats["total"]
    critical = stats["critical"]
    high = stats["high"]
    cats = stats["categories"]

    parts = []
    if total > 0:
        parts.append(f"当前共收录 {total} 条安全情报")
        if critical > 0:
            parts.append(f"其中严重级别 {critical} 条")
        if high > 0:
            parts.append(f"高危级别 {high} 条")

        cat_parts = []
        cat_labels = {
            "ddos": "DDoS攻击", "agent": "AI Agent", "llm": "大模型技术",
            "vuln": "漏洞情报", "malware": "恶意软件", "general": "综合情报"
        }
        for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
            label = cat_labels.get(cat, cat)
            cat_parts.append(f"{label}({cnt}条)")
        if cat_parts:
            parts.append("分类分布：" + "、".join(cat_parts[:5]))

        parts.append("数据来源于 Twitter 公开情报采集，请关注高危情报并及时响应。")
    else:
        parts.append("暂无情报数据。爬虫运行后数据将自动展示在此平台。")

    summary = "。".join(parts)
    return jsonify({"code": 0, "data": {"text": summary}})

# ===== 翻译 API =====

def translate_google(text, target_lang="zh-CN"):
    """使用 Google 翻译免费 API 进行翻译"""
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
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            translated_parts = []
            if data and data[0]:
                for part in data[0]:
                    if part[0]:
                        translated_parts.append(part[0])
            return "".join(translated_parts)
    except Exception as e:
        logger.error(f"Google 翻译失败: {e}")
        return None

def translate_simple(text):
    """简单的术语级翻译（备用方案）"""
    terms = {
        "DDoS attack": "DDoS攻击", "botnet": "僵尸网络", "vulnerability": "漏洞",
        "exploit": "漏洞利用", "zero-day": "零日漏洞", "0day": "零日漏洞",
        "ransomware": "勒索软件", "malware": "恶意软件", "phishing": "钓鱼攻击",
        "backdoor": "后门", "remote code execution": "远程代码执行", "RCE": "远程代码执行",
        "patch": "补丁", "threat intelligence": "威胁情报", "breach": "数据泄露",
        "data leak": "数据泄露", "AI agent": "AI智能体", "autonomous agent": "自主智能体",
        "multi-agent": "多智能体", "large language model": "大语言模型", "LLM": "大语言模型",
        "fine-tuning": "微调", "reasoning": "推理", "chain of thought": "思维链",
        "retrieval augmented generation": "检索增强生成", "RAG": "检索增强生成",
        "benchmark": "基准测试", "open source": "开源", "multimodal": "多模态",
        "inference": "推理", "training": "训练", "deployment": "部署",
        "framework": "框架", "breakthrough": "突破", "state-of-the-art": "最先进的",
        "SOTA": "最先进的", "mitigation": "缓解/防护", "amplification": "放大攻击",
        "volumetric": "流量型", "layer 7": "应用层(L7)", "API abuse": "API滥用",
        "traffic": "流量", "peak": "峰值", "Tbps": "Tbps(太比特每秒)",
        "infrastructure": "基础设施", "detection": "检测", "evasion": "逃逸/绕过",
    }
    result = text
    for en, zh in terms.items():
        result = re.sub(re.escape(en), f"{en}({zh})", result, flags=re.IGNORECASE)
    return result

@app.route("/api/translate", methods=["POST"])
@login_required
def api_translate():
    """翻译文本为中文"""
    data = request.get_json()
    if not data or not data.get("text"):
        return jsonify({"code": -1, "msg": "缺少 text 参数", "data": None})

    text = data["text"][:3000]
    translated = translate_google(text)
    if not translated:
        translated = translate_simple(text)
        logger.info("使用备用术语翻译")

    return jsonify({
        "code": 0,
        "data": {
            "translated": translated,
            "source_lang": "en",
            "target_lang": "zh-CN",
        }
    })


@app.route("/api/search/suggest", methods=["GET"])
@login_required
def api_search_suggest():
    """搜索建议接口：基于 summary_cn 和 summary 做模糊匹配"""
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify({"code": 0, "data": []})

    results = search_suggest(q, limit=8)
    return jsonify({"code": 0, "data": results})


@app.route("/api/github-trending", methods=["GET"])
@login_required
def api_github_trending():
    """获取 GitHub 热门 Agent/大模型项目"""
    period = request.args.get("period", "daily")  # daily | weekly
    limit = int(request.args.get("limit", 10))
    if period not in ("daily", "weekly"):
        period = "daily"
    items = get_github_trending(period, limit)
    return jsonify({"code": 0, "data": items})


@app.route("/api/hot-topics", methods=["GET"])
@login_required
def api_hot_topics():
    """获取热点情报聚合 Top N"""
    time_range = request.args.get("time_range", "daily")  # daily | weekly
    limit = int(request.args.get("limit", 10))
    if time_range not in ("daily", "weekly"):
        time_range = "daily"
    topics = get_hot_topics(time_range, limit)
    return jsonify({"code": 0, "data": topics})


if __name__ == "__main__":
    logger.info("🚀 ThreatPulse API Server v4 (Hardened) starting on port 5000...")
    app.run(host="127.0.0.1", port=5000, debug=False)
