# ThreatPulse 安全情报聚合平台

> 基于 Twitter/X 公开情报的自动化安全情报采集、分类、展示平台

## 📋 目录

- [项目概述](#项目概述)
- [系统架构](#系统架构)
- [目录结构](#目录结构)
- [核心功能](#核心功能)
- [技术实现细节](#技术实现细节)
- [快速部署指南](#快速部署指南)
- [配置说明](#配置说明)
- [安全机制](#安全机制)
- [注意事项与踩坑记录](#注意事项与踩坑记录)
- [维护指南](#维护指南)

---

## 项目概述

ThreatPulse 是一个全自动的安全情报聚合平台，完整链路为：

```
Twitter/X 爬虫 → MySQL 存储 → Flask API → 前端展示平台
```

**核心能力：**
- 定时从 Twitter/X 采集安全相关推文（DDoS、漏洞、AI Agent、LLM 等方向）
- 自动分类（6 大类）+ 严重等级评估（4 级）+ 标签提取
- 深色风格的 Web 情报展示平台，支持筛选、搜索、翻译
- 完整的登录认证系统（JWT + HttpOnly Cookie）

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户浏览器                                │
│  http://YOUR_SERVER/Th/  →  login.html → index.html             │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Nginx (反向代理)                                                │
│  /Th/ → proxy_pass http://127.0.0.1:5000/                       │
│  隐藏文件(.开头) → deny all (403)                                │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Flask API Server (api_server.py)  port:5000                     │
│  ┌────────────┐  ┌──────────────┐  ┌───────────────────┐        │
│  │ 认证中间件  │  │ 情报查询 API │  │ 翻译/统计/标签 API│        │
│  │ JWT+Cookie │  │ 分页/筛选    │  │ Google翻译+术语库 │        │
│  └────────────┘  └──────┬───────┘  └───────────────────┘        │
│                         │                                        │
│  ┌──────────────────────▼──────────────────────────────┐        │
│  │  db.py (数据库操作层)                                │        │
│  │  PyMySQL · 连接池 · 分类/统计/查询                   │        │
│  └──────────────────────┬──────────────────────────────┘        │
└─────────────────────────┼───────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│  MySQL 数据库 (threatpulse)                                      │
│  表: intel_items                                                 │
│  索引: category, severity, crawl_time, keyword, heat, FULLTEXT   │
└──────────────────────────┬──────────────────────────────────────┘
                           ▲
                           │ INSERT
┌──────────────────────────┴──────────────────────────────────────┐
│  Twitter 爬虫 (crontab 每小时执行)                               │
│  main.py → scraper.py → Twitter GraphQL API                     │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐     │
│  │ keywords.yml │  │ cookies.json  │  │ transaction_id.py│     │
│  │ 52个搜索词   │  │ 账户凭证      │  │ 反爬签名生成     │     │
│  └──────────────┘  └───────────────┘  └──────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 目录结构

```
ThreatPulse/
├── README.md                  # 本文档
├── setup.py                   # 交互式部署初始化脚本
├── requirements.txt           # Python 依赖
│
├── # ===== 爬虫层 =====
├── main.py                    # 爬虫入口（crontab 调用）
├── scraper.py                 # Twitter GraphQL 爬虫核心
├── config.py                  # 全局配置（API端点/延迟/UA等）
├── transaction_id.py          # x-client-transaction-id 生成器
├── account_manager.py         # Twitter Cookie 账户管理工具
├── keywords.yml               # 搜索关键词配置（52个词）
│
├── # ===== 数据层 =====
├── db.py                      # MySQL 操作层（CRUD/分类/统计）
├── import_test.py             # 数据导入测试脚本
│
├── # ===== API 层 =====
├── api_server.py              # Flask API 服务（认证/查询/翻译）
│
├── # ===== 前端 =====
├── frontend/
│   ├── index.html             # 主页面（情报仪表盘）
│   ├── login.html             # 登录页面
│   ├── login.js               # 登录逻辑（含锁定倒计时）
│   ├── main.js                # 主页核心逻辑
│   ├── data.js                # API 数据层
│   ├── components.js          # UI 组件（情报卡片/详情弹窗等）
│   └── style.css              # 全局样式（深色主题）
│
├── # ===== 部署 =====
├── deploy/
│   ├── .auth_config.json.template  # 认证配置模板
│   ├── threatpulse.service         # systemd 服务模板（setup.py 生成）
│   └── threatpulse.conf            # Nginx 配置模板（setup.py 生成）
│
├── # ===== 运行时生成（不包含在源码包中） =====
├── .auth_config.json          # 登录账密配置（setup.py 生成）
├── .jwt_secret                # JWT 签名密钥（setup.py 生成）
├── cookies.json               # Twitter Cookie（手动配置）
├── output/                    # 爬虫原始输出
└── cron.log                   # 定时任务日志
```

---

## 核心功能

### 1. Twitter 爬虫引擎

| 特性 | 说明 |
|------|------|
| **采集方式** | 直接调用 Twitter GraphQL 内部 API（非官方 API） |
| **认证方式** | 真实账户 Session Cookie（auth_token + ct0） |
| **搜索词** | 52 个关键词，覆盖 DDoS/Agent/LLM/漏洞/恶意软件 5 大方向 |
| **反爬策略** | 随机延迟(2-5s)、指数退避、x-client-transaction-id 签名 |
| **去重机制** | 基于 tweet_id 的 `INSERT IGNORE`，天然去重 |
| **定时执行** | crontab 每整点运行一次 |

### 2. 自动分类与评级

**6 大分类：**
- `ddos` — DDoS/僵尸网络/流量攻击
- `vuln` — 漏洞情报/CVE/Exploit
- `malware` — 恶意软件/勒索软件/后门
- `agent` — AI Agent/自主智能体/MCP
- `llm` — 大语言模型/GPT/Claude/DeepSeek
- `general` — 综合情报

**4 级严重等级：**
- 🔴 `critical` — 零日漏洞/RCE/正在被利用
- 🟠 `high` — 重大攻击/数据泄露
- 🟡 `medium` — 新版本发布/技术突破
- 🟢 `low` — 一般信息

**自动标签：** 从内容中提取最多 8 个标签（DDoS、Botnet、LLM、RAG 等）

### 3. Web 情报平台

- **仪表盘：** 情报总数、严重/高危计数、来源数、AI 态势摘要
- **情报流：** 分页展示，支持分类筛选、严重等级筛选、关键词搜索、时间范围筛选
- **情报详情弹窗：** 摘要全文、中文翻译（Google 翻译 API + 术语库备用）、来源链接、互动数据
- **热点攻击榜 / 标签云 / 关键词趋势**
- **每条情报显示具体日期时间 + 相对时间**

### 4. 认证系统

- JWT Token + HttpOnly Cookie（Token 不在响应中返回）
- IP 级登录频率限制（5 次失败 → 锁定 15 分钟）
- 密码 SHA256+Salt 哈希存储（配置文件中无明文密码）
- JWT Secret 持久化（服务重启不影响已登录用户）

---

## 技术实现细节

### 爬虫核心 (scraper.py)

```python
# Twitter GraphQL API 调用流程
1. 从 cookies.json 加载 auth_token + ct0
2. 构造请求头（Bearer Token + Cookie + x-csrf-token + transaction-id）
3. 发送 GraphQL 查询到 SearchTimeline 端点
4. 解析嵌套 JSON 提取推文数据（full_text/user/metrics）
5. 调用 db.py 的分类函数 + 写入 MySQL
```

**关键技术点：**

- **GraphQL queryId**: Twitter 会定期更换 queryId，当前有效值在 `config.py` 的 `SEARCH_QUERY_ID` 中
- **x-client-transaction-id**: Twitter 新增的反爬验证头，由 `transaction_id.py` 生成
- **Bearer Token**: Twitter 公开的固定 Bearer Token（所有客户端共用），在 `config.py` 中
- **Cookie 有效期**: 通常 1-3 个月，失效后需手动更新

### 数据库设计 (db.py)

核心表 `intel_items` 字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| tweet_id | VARCHAR(64) UNIQUE | 推文唯一ID，用于去重 |
| title | VARCHAR(512) | 标题（前80字符） |
| full_text | TEXT | 推文全文 |
| category | VARCHAR(32) | 分类（6选1） |
| severity | VARCHAR(16) | 严重等级（4选1） |
| tags | JSON | 标签数组（最多8个） |
| heat | INT | 热度值 = RT×3 + Fav×2 + Reply + Quote |
| keyword | VARCHAR(256) | 匹配的搜索关键词 |
| user_screen_name | VARCHAR(256) | 推文作者 |
| link | VARCHAR(1024) | 原文链接 |
| crawl_time | DATETIME | 爬取时间 |

索引策略：category、severity、crawl_time、keyword、heat 均有索引，title+full_text 有全文索引。

### API 服务 (api_server.py)

| 端点 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/api/auth/login` | POST | ❌ | 登录（含 IP 频率限制） |
| `/api/auth/check` | GET | ❌ | 检查登录状态 |
| `/api/auth/logout` | POST | ❌ | 退出登录 |
| `/api/intel` | GET | ✅ | 查询情报列表（分页/筛选） |
| `/api/stats` | GET | ✅ | 统计数据 |
| `/api/hot-attacks` | GET | ✅ | 热点攻击榜 |
| `/api/tags` | GET | ✅ | 标签云 |
| `/api/keywords` | GET | ✅ | 关键词趋势 |
| `/api/summary` | GET | ✅ | AI 态势摘要 |
| `/api/translate` | POST | ✅ | 文本翻译（Google翻译） |

### 前端架构

- **纯原生 JS**，无框架依赖
- **CDN 依赖**: TailwindCSS、RemixIcon、Google Fonts
- **深色主题**: 基于 `#0f172a` 背景色系
- **响应式设计**: 适配桌面端

---

## 快速部署指南

### 环境要求

| 组件 | 版本要求 |
|------|---------|
| **操作系统** | Linux (CentOS/Ubuntu/Debian) |
| **Python** | 3.8+ |
| **MySQL** | 5.7+ / 8.0+ |
| **Nginx** | 1.18+ |
| **网络** | 需要能访问 x.com（Twitter） |

### 一键部署

```bash
# 1. 解压项目
unzip ThreatPulse.zip -d /data/
cd /data/ThreatPulse

# 2. 安装 Python 依赖
pip3 install -r requirements.txt

# 3. 运行交互式部署向导
python3 setup.py
# 按提示输入：管理员账密、MySQL配置、URL路径等

# 4. 配置 Twitter Cookie（参见下方说明）
# 编辑 cookies.json

# 5. 安装 systemd 服务
cp deploy/threatpulse.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now threatpulse.service

# 6. 安装 Nginx 配置
cp deploy/threatpulse.conf /etc/nginx/conf.d/
nginx -t && nginx -s reload

# 7. 添加定时任务
crontab -e
# 添加: 0 * * * * cd /data/ThreatPulse && python3 main.py >> cron.log 2>&1

# 8. 手动执行一次爬虫（首次采集数据）
cd /data/ThreatPulse && python3 main.py

# 9. 访问平台
# http://YOUR_SERVER_IP/Th/
```

### 手动部署（不使用 setup.py）

如果不想使用交互式向导，可手动完成以下步骤：

#### Step 1: MySQL 初始化

```sql
CREATE DATABASE threatpulse CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'threatpulse'@'localhost' IDENTIFIED BY '你的密码';
GRANT ALL PRIVILEGES ON threatpulse.* TO 'threatpulse'@'localhost';
FLUSH PRIVILEGES;

USE threatpulse;
CREATE TABLE intel_items (
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
```

#### Step 2: 修改配置

编辑 `db.py`，填入真实的数据库连接信息：
```python
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "你的数据库用户名",
    "password": "你的数据库密码",
    "database": "threatpulse",
    ...
}
```

#### Step 3: 生成认证文件

```python
# 生成 .auth_config.json
python3 -c "
import json, hashlib, secrets
salt = secrets.token_hex(16)
password = input('输入管理员密码: ')
config = {
    'admin_username': input('输入管理员用户名: '),
    'password_salt': salt,
    'password_hash': hashlib.sha256((salt + password).encode()).hexdigest(),
    'jwt_expire_hours': 24,
    'rate_limit': {'max_attempts': 5, 'window_seconds': 300, 'lockout_seconds': 900}
}
with open('.auth_config.json', 'w') as f:
    json.dump(config, f, indent=2)
import os; os.chmod('.auth_config.json', 0o600)
print('Done')
"

# 生成 .jwt_secret
python3 -c "import secrets; open('.jwt_secret','w').write(secrets.token_hex(32)); import os; os.chmod('.jwt_secret', 0o600); print('Done')"
```

---

## 配置说明

### keywords.yml — 搜索关键词

```yaml
categories:
  ddos:
    - "DDoS attack"
    - "botnet"
    - ...
  agent:
    - "AI agent security"
    - "MCP protocol"
    - ...
  llm:
    - "GPT-5"
    - "Claude AI"
    - ...
```

每个关键词对应一次 Twitter 搜索请求。关键词越多，每次爬取耗时越长（受反爬延迟影响）。建议总数控制在 50-80 个。

### config.py — 全局配置

| 配置项 | 说明 | 建议值 |
|--------|------|--------|
| `BEARER_TOKEN` | Twitter 公开 Bearer Token | 固定值，一般不变 |
| `SEARCH_QUERY_ID` | GraphQL queryId | Twitter 更新后需同步更新 |
| `MAX_TWEETS_PER_KEYWORD` | 每个关键词最大采集数 | 40 |
| `MIN_DELAY` / `MAX_DELAY` | 请求间随机延迟 | 2.0 / 5.0 秒 |
| `REQUEST_TIMEOUT` | 请求超时 | 30 秒 |
| `MAX_RETRIES` | 最大重试次数 | 3 |

### .auth_config.json — 登录认证

```json
{
  "admin_username": "管理员用户名",
  "password_salt": "随机盐值",
  "password_hash": "SHA256(salt+password) 的哈希值",
  "jwt_expire_hours": 24,
  "rate_limit": {
    "max_attempts": 5,
    "window_seconds": 300,
    "lockout_seconds": 900
  }
}
```

⚠️ **此文件不应包含明文密码**，仅存储哈希值。

---

## 安全机制

### 认证安全

| 措施 | 说明 |
|------|------|
| 密码哈希 | SHA256 + 随机 Salt，不可逆 |
| 恒定时间比较 | `hmac.compare_digest` 防时序攻击 |
| HttpOnly Cookie | Token 不暴露给前端 JS |
| Token 不返回 | 登录响应中不包含 Token 明文 |
| JWT Secret 持久化 | 从文件/环境变量加载，重启不变 |
| 登录延迟 | 失败后 0.5s 延迟，防暴力破解 |

### IP 频率限制

| 参数 | 默认值 |
|------|--------|
| 窗口内最大尝试次数 | 5 次 |
| 滑动窗口时长 | 300 秒（5分钟） |
| 锁定时长 | 900 秒（15分钟） |
| 剩余次数提示 | ≤2 次时提示 |

### 文件保护

- `.auth_config.json` 和 `.jwt_secret` 文件权限 `600`
- Nginx 层 `location ~ /\. { deny all; }` 阻止下载隐藏文件
- Flask 层对 `.` 开头路径返回 403（双重防护）
- 源码中不包含明文密码

---

## 注意事项与踩坑记录

### 🔴 高优先级

1. **Twitter Cookie 有效期有限**
   - Cookie 通常 1-3 个月失效
   - 失效表现：爬虫日志中出现 401/403 错误
   - 解决：重新登录 Twitter 获取新 Cookie，更新 `cookies.json`

2. **GraphQL queryId 会变更**
   - Twitter 不定期更新 queryId
   - 失效表现：爬虫返回空数据或报错
   - 解决：从 Twitter 网页版开发者工具中抓取最新的 queryId，更新 `config.py` 中的 `SEARCH_QUERY_ID`
   - 获取方法：在 Twitter 搜索页面，F12 → Network → 搜索 `SearchTimeline` → 从 URL 中提取 queryId

3. **x-client-transaction-id 验证**
   - Twitter 新增的反爬机制
   - `transaction_id.py` 实现了该签名的生成逻辑
   - 如果 Twitter 更新签名算法，需要同步更新此文件

### 🟡 中优先级

4. **服务器需要能访问 Twitter**
   - 国内服务器通常无法直接访问 x.com
   - 解决方案：使用海外服务器，或配置代理

5. **MySQL 全文索引**
   - `intel_items` 表使用了 `FULLTEXT INDEX`
   - 需要 MySQL 5.7+ 或 8.0+ 的 InnoDB 引擎
   - 中文全文搜索需要额外配置 ngram parser（当前以英文为主，影响不大）

6. **Google 翻译 API**
   - 使用的是免费的 `translate.googleapis.com` 端点
   - 有请求频率限制，大量翻译可能被限流
   - 备用方案：内置术语级翻译（`translate_simple` 函数）

### 🟢 低优先级

7. **前端 CDN 依赖**
   - TailwindCSS、RemixIcon、Google Fonts 从 CDN 加载
   - 内网环境需要改为本地引用或私有 CDN

8. **日志管理**
   - `cron.log` 会持续增长，建议定期清理或配置 logrotate

---

## 维护指南

### 日常运维

```bash
# 查看服务状态
systemctl status threatpulse.service

# 查看 API 日志
journalctl -u threatpulse.service -f

# 查看爬虫日志
tail -f /data/ThreatPulse/cron.log

# 手动执行爬虫
cd /data/ThreatPulse && python3 main.py

# 重启 API 服务
systemctl restart threatpulse.service

# 查看数据库情报数量
mysql -u threatpulse -p threatpulse -e "SELECT COUNT(*) FROM intel_items;"
```

### 更新 Twitter Cookie

```bash
# 1. 使用账户管理工具查看当前状态
python3 account_manager.py show

# 2. 测试 Cookie 是否有效
python3 account_manager.py test

# 3. 如果失效，手动编辑 cookies.json
vim cookies.json
```

### 更新 GraphQL queryId

```bash
# 编辑 config.py，修改 SEARCH_QUERY_ID
vim config.py
# 修改后手动测试
python3 main.py
```

### 添加/修改搜索关键词

```bash
# 编辑关键词配置
vim keywords.yml
# 修改后下次定时任务自动生效
```

---

## 依赖说明

### Python 包

| 包名 | 用途 |
|------|------|
| flask | Web API 框架 |
| flask-cors | 跨域支持 |
| pymysql | MySQL 连接 |
| pyyaml | YAML 配置解析 |

### 系统依赖

| 组件 | 用途 |
|------|------|
| MySQL 5.7+ | 数据存储 |
| Nginx | 反向代理 |
| crontab | 定时任务 |
| systemd | 服务管理 |

---

## 许可证

本项目仅供学习和研究使用。Twitter 数据采集请遵守相关平台的使用条款。
