#!/usr/bin/env python3
"""
ThreatPulse 部署初始化脚本
功能：
  1. 生成 .auth_config.json（登录账密配置，仅存 hash）
  2. 生成 .jwt_secret（JWT 签名密钥，持久化）
  3. 初始化 MySQL 数据库和表结构
  4. 生成 systemd 服务文件
  5. 生成 Nginx 配置文件

用法：python3 setup.py
"""
import os
import sys
import json
import secrets
import hashlib
import getpass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def step_banner(n, title):
    print(f"\n{'='*50}")
    print(f"  Step {n}: {title}")
    print(f"{'='*50}")


def generate_auth_config():
    """生成认证配置文件"""
    step_banner(1, "生成登录认证配置")
    config_path = os.path.join(BASE_DIR, ".auth_config.json")

    if os.path.exists(config_path):
        overwrite = input("  ⚠️  .auth_config.json 已存在，是否覆盖？(y/N): ").strip().lower()
        if overwrite != 'y':
            print("  ⏭️  跳过")
            return

    username = input("  请输入管理员用户名: ").strip()
    if not username:
        print("  ❌ 用户名不能为空")
        sys.exit(1)

    password = getpass.getpass("  请输入管理员密码: ")
    if not password:
        print("  ❌ 密码不能为空")
        sys.exit(1)

    password_confirm = getpass.getpass("  请再次确认密码: ")
    if password != password_confirm:
        print("  ❌ 两次输入的密码不一致")
        sys.exit(1)

    salt = secrets.token_hex(16)
    password_hash = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()

    config = {
        "admin_username": username,
        "password_salt": salt,
        "password_hash": password_hash,
        "jwt_expire_hours": 24,
        "rate_limit": {
            "max_attempts": 5,
            "window_seconds": 300,
            "lockout_seconds": 900
        }
    }

    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    os.chmod(config_path, 0o600)
    print(f"  ✅ 已生成 {config_path}（权限 600）")


def generate_jwt_secret():
    """生成 JWT 密钥文件"""
    step_banner(2, "生成 JWT Secret")
    secret_path = os.path.join(BASE_DIR, ".jwt_secret")

    if os.path.exists(secret_path):
        overwrite = input("  ⚠️  .jwt_secret 已存在，是否覆盖？(y/N): ").strip().lower()
        if overwrite != 'y':
            print("  ⏭️  跳过")
            return

    jwt_secret = secrets.token_hex(32)
    with open(secret_path, 'w') as f:
        f.write(jwt_secret)
    os.chmod(secret_path, 0o600)
    print(f"  ✅ 已生成 {secret_path}（权限 600）")


def init_database():
    """初始化 MySQL 数据库"""
    step_banner(3, "初始化 MySQL 数据库")

    db_host = input("  MySQL 主机 (默认 localhost): ").strip() or "localhost"
    db_port = input("  MySQL 端口 (默认 3306): ").strip() or "3306"
    db_root_user = input("  MySQL root 用户名 (默认 root): ").strip() or "root"
    db_root_pass = getpass.getpass("  MySQL root 密码: ")

    db_name = input("  要创建的数据库名 (默认 threatpulse): ").strip() or "threatpulse"
    db_user = input("  要创建的数据库用户名 (默认 threatpulse): ").strip() or "threatpulse"
    db_pass = getpass.getpass("  为该用户设置密码: ")
    if not db_pass:
        print("  ❌ 密码不能为空")
        sys.exit(1)

    try:
        import pymysql
    except ImportError:
        print("  ❌ 请先安装 pymysql: pip3 install pymysql")
        sys.exit(1)

    try:
        conn = pymysql.connect(
            host=db_host, port=int(db_port),
            user=db_root_user, password=db_root_pass,
            charset='utf8mb4'
        )
        cursor = conn.cursor()

        # 创建数据库
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"  ✅ 数据库 {db_name} 已创建")

        # 创建用户
        try:
            cursor.execute(f"CREATE USER '{db_user}'@'localhost' IDENTIFIED BY '{db_pass}'")
        except pymysql.err.OperationalError:
            cursor.execute(f"ALTER USER '{db_user}'@'localhost' IDENTIFIED BY '{db_pass}'")
        cursor.execute(f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_user}'@'localhost'")
        cursor.execute("FLUSH PRIVILEGES")
        print(f"  ✅ 用户 {db_user} 已创建并授权")

        # 创建表
        cursor.execute(f"USE `{db_name}`")
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS intel_items (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            tweet_id VARCHAR(64) UNIQUE,
            title VARCHAR(512) NOT NULL DEFAULT '',
            summary TEXT,
            full_text TEXT,
            category VARCHAR(32) NOT NULL DEFAULT 'general',
            severity VARCHAR(16) NOT NULL DEFAULT 'low',
            source VARCHAR(256) DEFAULT '',
            source_icon VARCHAR(64) DEFAULT 'ri-twitter-x-line',
            tags JSON,
            heat INT DEFAULT 0,
            comments INT DEFAULT 0,
            ioc JSON,
            link VARCHAR(1024) DEFAULT '',
            keyword VARCHAR(256) DEFAULT '',
            user_name VARCHAR(256) DEFAULT '',
            user_screen_name VARCHAR(256) DEFAULT '',
            user_followers INT DEFAULT 0,
            retweet_count INT DEFAULT 0,
            favorite_count INT DEFAULT 0,
            reply_count INT DEFAULT 0,
            quote_count INT DEFAULT 0,
            lang VARCHAR(16) DEFAULT '',
            tweet_created_at VARCHAR(64) DEFAULT '',
            crawl_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_category (category),
            INDEX idx_severity (severity),
            INDEX idx_crawl_time (crawl_time),
            INDEX idx_keyword (keyword),
            INDEX idx_heat (heat),
            FULLTEXT INDEX ft_content (title, full_text)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        cursor.execute(create_table_sql)
        print(f"  ✅ 表 intel_items 已创建")

        conn.commit()
        conn.close()

        # 更新 db.py 中的配置
        db_py_path = os.path.join(BASE_DIR, "db.py")
        with open(db_py_path, 'r') as f:
            content = f.read()
        content = content.replace('YOUR_DB_USER', db_user)
        content = content.replace('YOUR_DB_PASSWORD_HERE', db_pass)
        with open(db_py_path, 'w') as f:
            f.write(content)
        print(f"  ✅ db.py 数据库配置已更新")

    except Exception as e:
        print(f"  ❌ 数据库初始化失败: {e}")
        sys.exit(1)


def generate_systemd_service():
    """生成 systemd 服务文件"""
    step_banner(4, "生成 systemd 服务文件")
    project_dir = os.path.abspath(BASE_DIR)
    python_path = sys.executable

    service_content = f"""[Unit]
Description=ThreatPulse API Server
After=network.target mysqld.service
Wants=mysqld.service

[Service]
Type=simple
User=root
WorkingDirectory={project_dir}
ExecStart={python_path} {project_dir}/api_server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""
    service_path = os.path.join(BASE_DIR, "deploy", "threatpulse.service")
    with open(service_path, 'w') as f:
        f.write(service_content)
    print(f"  ✅ 已生成 {service_path}")
    print(f"  📋 请执行以下命令安装服务:")
    print(f"     sudo cp {service_path} /etc/systemd/system/")
    print(f"     sudo systemctl daemon-reload")
    print(f"     sudo systemctl enable --now threatpulse.service")


def generate_nginx_config():
    """生成 Nginx 配置文件"""
    step_banner(5, "生成 Nginx 配置文件")
    url_path = input("  URL 路径前缀 (默认 /Th): ").strip() or "/Th"

    nginx_content = f"""server {{
    listen 80;
    server_name _;

    # 阻止访问隐藏文件
    location ~ /\\. {{
        deny all;
        return 403;
    }}

    # ThreatPulse 安全情报聚合平台
    location {url_path}/ {{
        proxy_pass http://127.0.0.1:5000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location {url_path}/api/ {{
        proxy_pass http://127.0.0.1:5000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""
    nginx_path = os.path.join(BASE_DIR, "deploy", "threatpulse.conf")
    with open(nginx_path, 'w') as f:
        f.write(nginx_content)
    print(f"  ✅ 已生成 {nginx_path}")
    print(f"  📋 请执行以下命令安装 Nginx 配置:")
    print(f"     sudo cp {nginx_path} /etc/nginx/conf.d/")
    print(f"     sudo nginx -t && sudo nginx -s reload")

    # 同步更新 login.js 中的 BASE_PATH
    login_js = os.path.join(BASE_DIR, "frontend", "login.js")
    with open(login_js, 'r') as f:
        content = f.read()
    import re
    content = re.sub(
        r'const BASE_PATH = "[^"]*"',
        f'const BASE_PATH = "{url_path}"',
        content
    )
    with open(login_js, 'w') as f:
        f.write(content)
    print(f"  ✅ login.js BASE_PATH 已更新为 {url_path}")


def setup_crontab():
    """提示设置定时任务"""
    step_banner(6, "设置定时爬虫任务")
    project_dir = os.path.abspath(BASE_DIR)
    python_path = sys.executable
    print(f"  📋 请手动添加 crontab 定时任务:")
    print(f"     crontab -e")
    print(f"     # 每小时执行一次爬虫")
    print(f"     0 * * * * cd {project_dir} && {python_path} {project_dir}/main.py >> {project_dir}/cron.log 2>&1")


def setup_cookies():
    """提示配置 Twitter Cookies"""
    step_banner(7, "配置 Twitter Cookies")
    print("  ⚠️  爬虫需要有效的 Twitter 账户 Cookie 才能工作")
    print("  📋 请按以下步骤获取 Cookie:")
    print("     1. 在浏览器中登录 Twitter/X")
    print("     2. 打开开发者工具 (F12) → Application → Cookies → x.com")
    print("     3. 复制以下字段的值:")
    print("        - auth_token")
    print("        - ct0")
    print("        - twid")
    print("        - 其他 Cookie 字段（可选）")
    print("     4. 创建 cookies.json 文件，格式如下:")
    print('        {')
    print('          "auth_token": "你的auth_token",')
    print('          "ct0": "你的ct0",')
    print('          "twid": "你的twid"')
    print('        }')
    print(f"     5. 保存到: {os.path.join(BASE_DIR, 'cookies.json')}")


def main():
    print("""
╔══════════════════════════════════════════════════╗
║     ThreatPulse 安全情报聚合平台 - 部署向导      ║
║                  v4.0 Hardened                   ║
╚══════════════════════════════════════════════════╝
    """)

    generate_auth_config()
    generate_jwt_secret()
    init_database()
    generate_systemd_service()
    generate_nginx_config()
    setup_crontab()
    setup_cookies()

    print(f"\n{'='*50}")
    print("  🎉 初始化完成！")
    print(f"{'='*50}")
    print("""
  后续步骤:
    1. 安装 Python 依赖:  pip3 install -r requirements.txt
    2. 配置 Twitter Cookies (cookies.json)
    3. 安装 systemd 服务并启动
    4. 安装 Nginx 配置并重载
    5. 添加 crontab 定时任务
    6. 访问 http://YOUR_SERVER_IP/Th/ 验证
    """)


if __name__ == "__main__":
    main()
