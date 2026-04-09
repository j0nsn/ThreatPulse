# ThreatPulse 安全情报聚合平台

> 多源安全情报自动化采集、AI 摘要、分类评级与可视化展示平台

![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-API-green?logo=flask)
![MySQL](https://img.shields.io/badge/MySQL-8.0-orange?logo=mysql)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 📋 目录

- [项目概述](#项目概述)
- [系统架构](#系统架构)
- [核心功能](#核心功能)
- [数据源](#数据源)
- [目录结构](#目录结构)
- [快速部署](#快速部署)
- [配置说明](#配置说明)
- [安全机制](#安全机制)
- [定时任务](#定时任务)
- [技术实现细节](#技术实现细节)
- [注意事项与踩坑记录](#注意事项与踩坑记录)
- [维护指南](#维护指南)

---

## 项目概述

ThreatPulse 是一个全自动的安全情报聚合平台，聚焦 **AI 安全**、**DDoS 防护**、**渗透测试**、**Web 安全**、**大模型安全** 五大方向，从 **7 个数据源** 持续采集情报并通过 DeepSeek AI 生成统一的中文摘要，提供深色风格的可视化展示界面。

**完整数据流：**

```
7大数据源爬虫 → DeepSeek AI 中文摘要 → MySQL 存储 → Flask API → 前端展示平台
```

**核心能力：**
- 🌐 **7 源情报采集**：Twitter/X、CN-SEC、GitHub、FreeBuf、安全客、The Hacker News、奇安信 XLab
- 🤖 **AI 中文摘要**：DeepSeek 自动为所有情报生成简洁的中文摘要
- 📊 **智能分类**：自动分类（10+ 类别）+ 严重等级评估（5 级）+ 标签提取
- 🔍 **模糊搜索**：支持多关键词 AND 搜索 + 搜索建议 + 关键词高亮
- 🎨 **深色风格 UI**：现代化情报展示界面，支持筛选、排序、详情查看
- 🔐 **安全认证**：JWT + HttpOnly Cookie + 防暴力破解

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                           用户浏览器                                 │
│  http://YOUR_SERVER/Th/  →  login.html → index.html                 │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ HTTP
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Nginx (反向代理)                                                    │
│  /Th/ → proxy_pass http://127.0.0.1:5000/                           │
│  隐藏文件(.开头) → deny all (403)                                    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Flask API Server (api_server.py)  port:5000                         │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  │
│  │ 认证中间件  │  │ 情报查询 API │  │ 搜索建议 API │  │ 统计 API │  │
│  │ JWT+Cookie │  │ 分页/筛选    │  │ 模糊匹配     │  │ 热词/标签│  │
│  └────────────┘  └──────┬───────┘  └──────────────┘  └──────────┘  │
│                         │                                            │
│  ┌──────────────────────▼──────────────────────────────────────┐    │
│  │  db.py (数据库操作层)                                        │    │
│  │  PyMySQL · 连接池 · 分类/统计/查询 · 多关键词搜索            │    │
│  └──────────────────────┬──────────────────────────────────────┘    │
└─────────────────────────┼───────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MySQL 数据库 (threatpulse)                                          │
│  表: intel_items                                                     │
│  字段: title, summary, summary_cn, full_text, category, severity...  │
│  索引: category, severity, crawl_time, keyword, heat, FULLTEXT       │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▲
     ┌─────────┬───────────┼───────────┬──────────────┐
     │         │           │           │              │
┌────┴───┐ ┌──┴────┐ ┌───┴───┐ ┌────┴─────┐ ┌──────┴──────────────────────┐
│Twitter │ │CN-SEC │ │GitHub │ │ 多源爬虫  │ │  DeepSeek AI 中文摘要       │
│ :00    │ │ :30   │ │ :15   │ │   :45    │ │  deepseek-chat model        │
│GraphQL │ │网页    │ │API   │ │FreeBuf   │ │  统一生成中文情报摘要        │
│52词    │ │5分类   │ │18词  │ │安全客    │ └─────────────────────────────┘
└────────┘ └───────┘ └──────┘ │THN       │
                               │XLab      │
                               └──────────┘
```

---

## 核心功能

### 情报采集
| 数据源 | 采集方式 | 频率 | 覆盖方向 |
|--------|---------|------|---------|
| **Twitter/X** | GraphQL API + 反爬签名 | 每小时 :00 | 52 个安全关键词 |
| **GitHub Repo** | GitHub Search API | 每小时 :15 | 18 个搜索词 |
| **GitHub Advisory** | Security Advisory API | 每小时 :15 | 官方 CVE/GHSA |
| **CN-SEC** | 网页爬虫 + BeautifulSoup | 每小时 :30 | 5 个安全分类 |
| **FreeBuf** 🆕 | API + JSON 回退 | 每小时 :45 | AI 安全 + 全站文章 |
| **安全客** 🆕 | REST API | 每小时 :45 | 安全资讯全覆盖 |
| **The Hacker News** 🆕 | RSS Feed | 每小时 :45 | 国际安全新闻 |
| **奇安信 XLab** 🆕 | RSS Feed | 每小时 :45 | 安全研究 & 威胁分析 |

### AI 中文摘要
- 使用 DeepSeek Chat API 自动生成中文情报摘要
- 所有 7 个来源的情报统一生成 ≤150 字的中文摘要
- 情报详情同时展示中文摘要和原文摘要

### 智能分类
- **10+ 分类**: DDoS, Web安全, 恶意软件, APT, 漏洞, 钓鱼, 勒索, AI Agent, 大模型, 渗透测试, 综合
- **5 级严重度**: Critical, High, Medium, Low, Info
- **自动标签**: 基于内容提取关键标签

### 模糊搜索
- 多关键词 AND 搜索（空格分隔）
- 搜索范围：标题 + 原文摘要 + 中文摘要 + 全文
- 实时搜索建议下拉（显示匹配字段标记）
- 搜索关键词高亮

---

## 数据源

### 1. Twitter/X 情报
通过 `twscrape` 引擎调用 Twitter GraphQL API，采集安全相关推文。

**关键词方向（52 个搜索词）：**
- **DDoS**: DDoS attack, botnet, volumetric attack, DDoS mitigation...
- **AI Agent**: AI agent security, MCP vulnerability, autonomous agent...
- **LLM 安全**: prompt injection, LLM jailbreak, model poisoning...
- **Web 安全**: WAF bypass, XSS, SQL injection, SSRF...
- **综合安全**: zero-day, ransomware, APT, supply chain attack...

### 2. CN-SEC 中文安全社区
爬取 cn-sec.com 的 5 个分类页面：
- 安全漏洞、安全新闻、安全文章、人工智能安全、安全博客

### 3. GitHub 安全情报
**仓库搜索（18 个搜索词，5 大方向）：**
- **Agent 新技术**: AI agent security tool, MCP server security, autonomous agent framework...
- **大模型新技术**: LLM security vulnerability, prompt injection defense...
- **AI + DDoS**: AI DDoS detection defense, machine learning DDoS mitigation...
- **AI + 渗透测试**: AI penetration testing tool, AI automated exploit...
- **AI + Web 防护**: AI WAF web application firewall, AI web security protection...

**安全公告：** GitHub Security Advisory Database（CVE/GHSA）

### 4. FreeBuf 🆕
国内最大的安全媒体平台，通过 FreeBuf 前端 API 采集文章。

- **采集方式**: 优先使用 FreeBuf API；若服务器 IP 被 WAF 封锁，自动回退到 JSON 文件导入模式
- **覆盖范围**: AI 安全标签 + 全站安全文章
- **ID 前缀**: `freebuf_`
- **来源图标**: 🔥 `ri-fire-line`

### 5. 安全客 (Anquanke) 🆕
360 旗下安全资讯平台，通过官方 REST API 采集。

- **API 地址**: `https://api.anquanke.com/data/v1/posts`
- **覆盖范围**: 安全资讯全覆盖（漏洞分析、威胁情报、安全研究）
- **ID 前缀**: `anquanke_`
- **来源图标**: 🛡️ `ri-shield-star-line`

### 6. The Hacker News 🆕
全球知名的网络安全新闻平台，通过 RSS Feed 采集。

- **RSS 地址**: `https://feeds.feedburner.com/TheHackersNews`
- **覆盖范围**: 国际安全新闻、漏洞披露、攻击事件
- **ID 前缀**: `thn_`
- **来源图标**: 📰 `ri-newspaper-line`

### 7. 奇安信 XLab 🆕
奇安信安全实验室官方博客，通过 RSS Feed 采集。

- **RSS 地址**: `https://blog.xlab.qianxin.com/rss/`
- **覆盖范围**: 高质量安全研究报告、威胁分析、恶意软件分析
- **ID 前缀**: `xlab_`
- **来源图标**: 🔬 `ri-microscope-line`

---

## 目录结构

```
ThreatPulse/
├── api_server.py            # Flask API 服务（认证、查询、搜索、统计）
├── db.py                    # 数据库操作层（查询、分类、统计、搜索建议）
├── db_cnsec.py              # CN-SEC 数据入库模块
├── main.py                  # Twitter 爬虫主入口
├── scraper.py               # Twitter GraphQL 爬虫引擎
├── cnsec_scraper.py         # CN-SEC 中文安全社区爬虫
├── github_scraper.py        # GitHub 仓库 + Advisory 爬虫
├── multi_scraper.py         # 🆕 多源爬虫（FreeBuf + 安全客 + THN + XLab）
├── deepseek_summarizer.py   # DeepSeek AI 中文摘要生成器
├── backfill_summary.py      # 存量情报中文摘要回填脚本
├── config.py                # 全局配置
├── keywords.yml             # Twitter 搜索关键词配置（52 词）
├── account_manager.py       # Twitter 账户管理
├── transaction_id.py        # Twitter x-client-transaction-id 签名生成
├── import_test.py           # 数据导入测试脚本
├── setup.py                 # 一键部署初始化脚本
├── requirements.txt         # Python 依赖
├── .env.example             # 环境变量配置模板
├── .gitignore               # Git 忽略规则
├── deploy/
│   └── .auth_config.json.template  # 认证配置模板
└── frontend/
    ├── index.html           # 情报展示主页面
    ├── login.html           # 登录页面
    ├── main.js              # 主逻辑（情报流、搜索、筛选、分页）
    ├── components.js        # UI 组件（卡片、详情弹窗、高亮、搜索建议）
    ├── data.js              # 数据层（API 调用）
    ├── login.js             # 登录逻辑
    └── style.css            # 深色主题样式
```

---

## 快速部署

### 前置要求
- Python 3.9+
- MySQL 8.0+
- Nginx（反向代理）
- 外部 API 密钥：DeepSeek API Key、GitHub Personal Access Token

### 1. 克隆项目

```bash
git clone https://github.com/j0nsn/ThreatPulse.git
cd ThreatPulse
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
vim .env
# 填入实际的数据库密码、DeepSeek API Key、GitHub Token
```

### 3. 运行初始化脚本

```bash
python3 setup.py
```

初始化脚本会自动完成：
- 生成 `.auth_config.json`（管理员账密，仅存 hash）
- 生成 `.jwt_secret`（JWT 签名密钥）
- 初始化 MySQL 数据库和表结构
- 生成 systemd 服务文件
- 生成 Nginx 配置文件

### 4. 加载环境变量

```bash
# 方式一：直接 export
export $(cat .env | grep -v '^#' | xargs)

# 方式二：在 systemd 服务中配置 EnvironmentFile
# 在 [Service] 段添加：EnvironmentFile=/path/to/ThreatPulse/.env
```

### 5. 启动服务

```bash
# 启动 API 服务
systemctl start threatpulse
systemctl enable threatpulse

# 配置 Nginx 反向代理
# 参考 setup.py 生成的配置文件

# 配置定时爬虫（4 组错峰调度）
crontab -e
# 添加以下四行：
# 0  * * * * cd /path/to/ThreatPulse && python3 main.py >> cron.log 2>&1
# 15 * * * * cd /path/to/ThreatPulse && python3 github_scraper.py >> github_cron.log 2>&1
# 30 * * * * cd /path/to/ThreatPulse && python3 cnsec_scraper.py >> cnsec_cron.log 2>&1
# 45 * * * * cd /path/to/ThreatPulse && python3 multi_scraper.py >> multi_cron.log 2>&1
```

### 6. 添加 Twitter 账户

```bash
python3 account_manager.py
# 选择 Cookies 方式添加账户（推荐）
# 需要提供：auth_token, ct0, 用户名
```

### 7. 访问平台

```
http://YOUR_SERVER/Th/
```

---

## 配置说明

### 环境变量（.env）

| 变量名 | 说明 | 必填 |
|--------|------|------|
| `DB_HOST` | MySQL 主机地址 | 否（默认 127.0.0.1） |
| `DB_PORT` | MySQL 端口 | 否（默认 3306） |
| `DB_USER` | MySQL 用户名 | 否（默认 threatpulse） |
| `DB_PASSWORD` | MySQL 密码 | **是** |
| `DB_NAME` | 数据库名 | 否（默认 threatpulse） |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | **是** |
| `GITHUB_TOKEN` | GitHub Personal Access Token | **是** |
| `TP_JWT_SECRET` | JWT 签名密钥 | 否（可用 .jwt_secret 文件） |

### 关键词配置（keywords.yml）

```yaml
groups:
  - name: DDoS & Botnet
    keywords:
      - "DDoS attack"
      - "botnet C2"
      - "volumetric attack"
      # ...

  - name: AI Agent Security
    keywords:
      - "AI agent exploit"
      - "MCP vulnerability"
      # ...
```

---

## 安全机制

### 认证系统
- **密码存储**: SHA-256(salt + password)，仅存 hash，不存明文
- **JWT Token**: HttpOnly Cookie，防 XSS 窃取
- **防暴力破解**: 5 次失败锁定 15 分钟
- **隐藏文件保护**: Nginx 层拦截所有 `.` 开头文件的访问

### 密钥管理
- 所有密钥通过环境变量注入，不在代码中硬编码
- `.env`、`.auth_config.json`、`.jwt_secret` 均在 `.gitignore` 中排除
- `cookies.json`（Twitter 凭证）不纳入版本控制

---

## 定时任务

四组爬虫错峰运行，避免资源争抢：

| 时间 | 爬虫 | 脚本 | 日志 |
|------|------|------|------|
| `:00` 整点 | Twitter/X | `main.py` | `cron.log` |
| `:15` | GitHub（仓库 + Advisory） | `github_scraper.py` | `github_cron.log` |
| `:30` | CN-SEC | `cnsec_scraper.py` | `cnsec_cron.log` |
| `:45` | FreeBuf + 安全客 + THN + XLab | `multi_scraper.py` | `multi_cron.log` |

---

## 技术实现细节

### Twitter 爬虫反爬策略
- **GraphQL API**: 直接调用 Twitter 内部 GraphQL 接口，非第三方 API
- **x-client-transaction-id**: 自行实现的签名生成器（`transaction_id.py`）
- **Cookie 持久化**: `cookies.json` 存储真实账户 Session
- **多账户轮换**: 支持多账户自动切换
- **随机延迟 + 指数退避**: 防触发频率限制

### CN-SEC 爬虫
- BeautifulSoup 解析 + 分类页面遍历
- 自动提取文章正文、标签、发布时间
- `INSERT IGNORE` 去重（基于 `tweet_id = cnsec_{article_id}`）

### GitHub 爬虫
- **仓库搜索**: 18 个关键词 × 5 大方向，自动获取 README 作为全文
- **安全公告**: GitHub Advisory Database，包含 CVE 编号和受影响包
- **质量过滤**: MIN_STARS=3 过滤低质量仓库，RECENT_DAYS=30 保证时效性
- `INSERT IGNORE` 去重（基于 `tweet_id = github_repo_{id}` / `github_adv_{ghsa_id}`）

### 多源爬虫（multi_scraper.py）
- **FreeBuf**: 优先调用前端 API 获取文章列表；若服务器 IP 被阿里云 WAF 封锁（返回 405），自动回退到 `freebuf_articles.json` 文件导入
- **安全客**: 调用 `api.anquanke.com` REST API，获取文章标题、摘要、分类、标签
- **The Hacker News**: 解析 RSS Feed（Feedburner），提取文章标题、描述、发布时间
- **奇安信 XLab**: 解析 Ghost 博客 RSS Feed，支持 `content:encoded` 获取完整正文
- **通用分类引擎**: 基于关键词匹配的自动分类（agent/llm/ddos/pentest/webdef/vuln/malware）+ 严重等级评估
- **安全相关性过滤**: 通过关键词过滤非安全内容，确保情报质量

### DeepSeek AI 摘要
- 模型: `deepseek-chat`，temperature=0.3
- 统一生成 ≤150 字中文摘要
- 支持批量回填存量情报（`backfill_summary.py`）
- 中文摘要前 30 字模糊匹配去重

### 模糊搜索
- 后端: 多关键词 AND 搜索，覆盖 title/summary/summary_cn/full_text
- 前端: 200ms 防抖搜索建议 + 500ms 防抖实际搜索
- 高亮: 搜索关键词在卡片标题和摘要中高亮显示
- 建议下拉: 显示匹配字段标记（中文摘要/原文摘要/标题）

---

## 注意事项与踩坑记录

### Twitter 相关
1. **GraphQL queryId 会变更**: Twitter 会不定期更新 queryId，需要从浏览器 Network 面板抓取最新值
2. **x-client-transaction-id**: 2024 年新增的反爬验证，缺少会返回 403
3. **Cookie 有效期**: auth_token 有效期约 1 年，ct0 较短，建议定期更新
4. **cf_clearance**: Cloudflare 验证 Cookie，需从浏览器获取

### GitHub 相关
1. **Search API 限制**: 未认证 10 次/分钟，认证后 30 次/分钟
2. **README 获取**: 部分仓库无 README 或 README 过大，需做容错处理

### FreeBuf 相关
1. **WAF 封锁**: 某些服务器 IP 会被阿里云 WAF 封锁（返回 405），需要使用 JSON 文件回退方案
2. **JSON 回退**: 从可访问 FreeBuf 的机器抓取数据生成 `freebuf_articles.json`，上传到服务器后由爬虫自动读取入库

### 数据库相关
1. **FULLTEXT 索引**: 需要 MySQL 5.7+ 的 InnoDB 引擎
2. **字符集**: 确保使用 `utf8mb4` 以支持 emoji 和特殊字符

---

## 维护指南

### 日常检查

```bash
# 检查服务状态
systemctl status threatpulse

# 查看爬虫日志
tail -f cron.log           # Twitter
tail -f github_cron.log    # GitHub
tail -f cnsec_cron.log     # CN-SEC
tail -f multi_cron.log     # FreeBuf + 安全客 + THN + XLab

# 查看情报统计
mysql -u threatpulse -p threatpulse -e "
  SELECT
    CASE
      WHEN tweet_id LIKE 'github_repo_%' THEN 'GitHub Repo'
      WHEN tweet_id LIKE 'github_adv_%' THEN 'GitHub Advisory'
      WHEN tweet_id LIKE 'cnsec_%'       THEN 'CN-SEC'
      WHEN tweet_id LIKE 'freebuf_%'     THEN 'FreeBuf'
      WHEN tweet_id LIKE 'anquanke_%'    THEN '安全客'
      WHEN tweet_id LIKE 'thn_%'         THEN 'The Hacker News'
      WHEN tweet_id LIKE 'xlab_%'        THEN '奇安信 XLab'
      ELSE 'Twitter'
    END AS source,
    COUNT(*) AS count
  FROM intel_items
  GROUP BY source
  ORDER BY count DESC;
"
```

### 更新 Twitter Cookie

```bash
python3 account_manager.py
# 选择更新 Cookie 选项
```

### 回填中文摘要

```bash
# 对缺少中文摘要的存量情报进行回填
python3 backfill_summary.py
```

### 手动触发爬虫

```bash
python3 main.py              # Twitter 爬虫
python3 github_scraper.py    # GitHub 爬虫
python3 cnsec_scraper.py     # CN-SEC 爬虫
python3 multi_scraper.py     # FreeBuf + 安全客 + THN + XLab
```

### FreeBuf JSON 文件更新

当服务器 IP 被 FreeBuf WAF 封锁时，需从外部机器手动抓取：

```bash
# 在可访问 FreeBuf 的机器上运行
curl -s -H "Referer: https://www.freebuf.com/articles" \
  "https://www.freebuf.com/fapi/frontend/category/list?name=articles&tag=&limit=20&page=1" \
  | python3 -c "import sys,json; ..." > freebuf_articles.json

# 上传到服务器
scp freebuf_articles.json user@server:/path/to/ThreatPulse/
```

---

## License

MIT License
