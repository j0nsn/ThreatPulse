# ThreatPulse 安全情报聚合平台

> 多源安全情报自动化采集、智能摘要、分类评级、多维筛选与可视化展示平台

![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-API-green?logo=flask)
![MySQL](https://img.shields.io/badge/MySQL-8.0-orange?logo=mysql)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 📋 目录

- [项目概述](#项目概述)
- [v8.0 更新日志](#v80-更新日志)
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

ThreatPulse 是一个全自动的安全情报聚合平台，聚焦 **AI 安全**、**DDoS 防护**、**渗透测试**、**Web 安全**、**大模型安全** 五大方向，从 **7 个数据源** 持续采集情报，通过 **零成本智能摘要方案**（Google 翻译 + 中文智能截取）生成统一的中文摘要，提供深色风格的可视化展示界面。

**完整数据流：**

```
7大数据源爬虫 → 智能摘要（Google翻译/中文截取）→ MySQL 存储 → Flask API → 前端展示平台
```

**核心能力：**
- 🌐 **7 源情报采集**：Twitter/X、CN-SEC、GitHub、FreeBuf、安全客、The Hacker News、奇安信 XLab
- 🤖 **零成本智能摘要**：英文情报 → Google 翻译；中文情报 → 智能截取（保留 DeepSeek 备用）
- 📊 **智能分类**：自动分类（10+ 类别）+ 严重等级评估（5 级）+ 标签提取
- 🔍 **模糊搜索**：支持多关键词 AND 搜索 + 搜索建议 + 关键词高亮
- 🎯 **多维筛选**：情报源筛选 + 严重等级筛选 + 分类导航，三维度自由组合
- 🔥 **热点聚合**：基于 Jaccard 相似度的热点情报聚合 Top10（支持今日/本周）
- ⭐ **GitHub Trending**：AI Agent / 大模型热门项目 Top10 日榜/周榜
- 🎨 **深色风格 UI**：现代化情报展示界面，支持筛选、排序、详情查看
- 🔐 **安全认证**：JWT + HttpOnly Cookie + 防暴力破解
- 🔄 **主从同步**：支持多节点部署（TCP 9901 端口数据同步）

---

## v8.0 更新日志

### 🆕 新增功能
- **情报源筛选**：前端新增情报源筛选栏，支持按 Twitter / CN-SEC / GitHub Repo / GitHub Advisory / The Hacker News / FreeBuf / 安全客 / 奇安信 XLab 过滤，每个按钮显示对应数量角标
- **多维度过滤**：情报源 + 严重等级 + 分类导航三维度可自由组合（如：只看 Twitter 的高危 DDoS 情报）
- **热点话题详情展开**：点击热点话题可展开关联情报列表，显示来源图标、标题（可跳转原文）、来源名称，支持手风琴模式
- **主从同步架构**：新增 `sync_server.py`，支持多节点部署通过 TCP 9901 端口同步数据

### 💰 成本优化
- **DeepSeek API → 免费方案**：所有摘要生成从 DeepSeek API 切换为零成本方案
  - 英文内容（Twitter / THN / GitHub）→ Google 翻译免费 API
  - 中文内容（CN-SEC / FreeBuf / 安全客 / XLab）→ 智能截取原文前 150 字（句号处截断）
  - GitHub Trending 翻译 → Google 翻译免费 API
  - **保留 `generate_summary_deepseek()` 备用**，一行代码即可切换回来
- **Twitter 爬虫去重优化**：先用 tweet_id 查库去重，确认是新推文才生成摘要（避免无效调用）
- **内存缓存机制**：进程内 hash 缓存（最大 500 条），避免同一进程重复处理

### 🛠️ 优化改进
- **GitHub 仓库搜索时效**：RECENT_DAYS 调整为 14 天（兼顾时效性和覆盖面）
- **情报源 API**：新增 `GET /api/sources` 接口，返回各情报源分组列表（含图标和数量）
- **情报查询 API**：`GET /api/intel` 新增 `source` 参数支持按源过滤

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
│  │ 认证中间件  │  │ 情报查询 API │  │ 情报源 API   │  │ 统计 API │  │
│  │ JWT+Cookie │  │ 分页/多维筛选│  │ 分组/计数    │  │ 热词/标签│  │
│  └────────────┘  └──────┬───────┘  └──────────────┘  └──────────┘  │
│                         │                                            │
│  ┌──────────────────────▼──────────────────────────────────────┐    │
│  │  db.py (数据库操作层)                                        │    │
│  │  PyMySQL · 连接池 · 多维筛选 · 热点聚合 · 模糊搜索          │    │
│  └──────────────────────┬──────────────────────────────────────┘    │
└─────────────────────────┼───────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MySQL 数据库 (threatpulse)                                          │
│  表: intel_items · github_trending                                   │
│  字段: title, summary, summary_cn, full_text, category, severity...  │
│  索引: category, severity, crawl_time, keyword, heat, FULLTEXT       │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▲
     ┌─────────┬───────────┼───────────┬──────────────┐
     │         │           │           │              │
┌────┴───┐ ┌──┴────┐ ┌───┴───┐ ┌────┴─────┐ ┌──────┴──────────────────────┐
│Twitter │ │CN-SEC │ │GitHub │ │ 多源爬虫  │ │  智能摘要引擎               │
│ :00    │ │ :30   │ │ :15   │ │   :45    │ │  Google翻译 + 中文智能截取   │
│GraphQL │ │网页    │ │API   │ │FreeBuf   │ │  (DeepSeek备用)             │
│52词    │ │5分类   │ │18词  │ │安全客    │ └─────────────────────────────┘
└────────┘ └───────┘ └──────┘ │THN       │
                               │XLab      │         ┌──────────────────┐
                               └──────────┘    ◄────│ GitHub Trending  │
                                                     │ 8:00 / 20:00    │
                                                     └──────────────────┘
```

### 主从同步架构

```
┌──────────────────────┐         TCP 9901          ┌──────────────────────┐
│   主节点（香港）       │ ◄──────────────────────── │   从节点（广州等）    │
│   运行所有爬虫        │     sync_server.py        │   只运行 API 服务     │
│   MySQL 主库          │ ──────────────────────►   │   MySQL 从库          │
│   sync_server.py      │     数据增量同步          │   sync_client.py      │
└──────────────────────┘                            └──────────────────────┘
```

---

## 核心功能

### 情报采集
| 数据源 | 采集方式 | 频率 | 覆盖方向 |
|--------|---------|------|---------|
| **Twitter/X** | GraphQL API + 反爬签名 | 每小时 :00 | 52 个安全关键词 |
| **GitHub Repo** | GitHub Search API | 每小时 :15 | 18 个搜索词，RECENT_DAYS=14 |
| **GitHub Advisory** | Security Advisory API | 每小时 :15 | 官方 CVE/GHSA |
| **CN-SEC** | 网页爬虫 + BeautifulSoup | 每小时 :30 | 5 个安全分类 |
| **FreeBuf** | API + JSON 回退 | 每小时 :45 | AI 安全 + 全站文章 |
| **安全客** | REST API | 每小时 :45 | 安全资讯全覆盖 |
| **The Hacker News** | RSS Feed | 每小时 :45 | 国际安全新闻 |
| **奇安信 XLab** | RSS Feed | 每小时 :45 | 安全研究 & 威胁分析 |
| **GitHub Trending** | GitHub Search API | 每天 8:00/20:00 | AI Agent / 大模型热门项目 |

### 智能摘要（零成本方案）
- **英文情报**（Twitter / THN / GitHub）→ Google 翻译免费 API 翻译为中文，截取前 150 字
- **中文情报**（CN-SEC / FreeBuf / 安全客 / XLab）→ 直接截取原文前 150 字，在句号处智能截断
- **GitHub Trending** → Google 翻译免费 API 翻译项目描述
- **备用方案**: `generate_summary_deepseek()` 函数保留，一行代码切换回 DeepSeek AI 摘要
- **内存缓存**: 进程内 hash 缓存（最大 500 条），避免重复处理
- **智能去重**: 先用 tweet_id 查库去重，确认是新内容才生成摘要

### 多维筛选
- **情报源筛选**: 按数据源过滤（Twitter / CN-SEC / GitHub 等），按钮显示各源数量角标
- **严重等级筛选**: Critical / High / Medium / Low / Info
- **分类导航**: DDoS / AI Agent / 大模型 / 漏洞 / 恶意软件 / 综合 等
- **三维度自由组合**: 如"只看 Twitter 来源的高危 DDoS 情报"

### 热点聚合
- 基于中文摘要前 30 字的 Jaccard 相似度（阈值 0.45）聚合同一事件
- 关键实体匹配（CVE 编号、产品名）增强聚合精度
- 热度公式: `count*100 + source_count*50 + log2(total_heat+1)*10`
- 支持今日 / 本周切换，点击展开关联情报详情

### GitHub Trending
- 16 个搜索关键词覆盖 AI Agent + 大模型方向
- 日榜（最近 7 天）/ 周榜（最近 30 天）
- 自动翻译项目描述为中文
- 首页左侧栏展示 Top10

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
爬取 cn-sec.com 的 5 个分类页面：安全漏洞、安全新闻、安全文章、人工智能安全、安全博客

### 3. GitHub 安全情报
**仓库搜索（18 个搜索词，5 大方向）：**
- Agent 新技术 / 大模型新技术 / AI + DDoS / AI + 渗透测试 / AI + Web 防护

**安全公告：** GitHub Security Advisory Database（CVE/GHSA）

### 4. FreeBuf
国内安全媒体平台，通过 API 采集（WAF 封锁时自动回退到 JSON 文件导入）

### 5. 安全客 (Anquanke)
360 旗下安全资讯平台，通过官方 REST API 采集

### 6. The Hacker News
全球知名网络安全新闻平台，通过 RSS Feed 采集

### 7. 奇安信 XLab
奇安信安全实验室官方博客，通过 RSS Feed 采集

---

## 目录结构

```
ThreatPulse/
├── api_server.py            # Flask API 服务（认证、查询、搜索、统计、情报源）
├── db.py                    # 数据库操作层（查询、分类、统计、热点聚合、情报源列表）
├── db_cnsec.py              # CN-SEC 数据入库模块
├── main.py                  # Twitter 爬虫主入口（含 DB 去重优化）
├── scraper.py               # Twitter GraphQL 爬虫引擎
├── cnsec_scraper.py         # CN-SEC 中文安全社区爬虫
├── github_scraper.py        # GitHub 仓库 + Advisory 爬虫
├── multi_scraper.py         # 多源爬虫（FreeBuf + 安全客 + THN + XLab）
├── github_trending.py       # GitHub Trending 热门项目爬虫
├── deepseek_summarizer.py   # 智能摘要引擎（免费方案 + DeepSeek 备用）
├── backfill_summary.py      # 存量情报摘要回填脚本
├── sync_server.py           # 🆕 主从同步服务端（TCP 9901）
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
    ├── index.html           # 情报展示主页面（含情报源筛选栏）
    ├── login.html           # 登录页面
    ├── main.js              # 主逻辑（情报流、搜索、多维筛选、热点展开）
    ├── components.js        # UI 组件（卡片、详情弹窗、高亮、搜索建议）
    ├── data.js              # 数据层（API 调用、情报源列表）
    ├── login.js             # 登录逻辑
    └── style.css            # 深色主题样式（含情报源筛选按钮样式）
```

---

## 快速部署

### 前置要求
- Python 3.9+
- MySQL 8.0+
- Nginx（反向代理）
- 外部 API 密钥：GitHub Personal Access Token
- 可选：DeepSeek API Key（默认使用免费方案，无需配置）

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
# 必填：DB_PASSWORD, GITHUB_TOKEN
# 可选：DEEPSEEK_API_KEY（默认使用免费方案）
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

# 配置定时爬虫（5 组错峰调度）
crontab -e
# 0  * * * * cd /path/to/ThreatPulse && python3 main.py >> cron.log 2>&1
# 15 * * * * cd /path/to/ThreatPulse && python3 github_scraper.py >> github_cron.log 2>&1
# 30 * * * * cd /path/to/ThreatPulse && python3 cnsec_scraper.py >> cnsec_cron.log 2>&1
# 45 * * * * cd /path/to/ThreatPulse && python3 multi_scraper.py >> multi_cron.log 2>&1
# 0 8,20 * * * cd /path/to/ThreatPulse && python3 github_trending.py >> trending_cron.log 2>&1
```

### 6. 添加 Twitter 账户

```bash
python3 account_manager.py
# 选择 Cookies 方式添加账户（推荐）
```

### 7. 访问平台

```
http://YOUR_SERVER/Th/
```

### 8. 可选：部署从节点

```bash
# 在主节点启动同步服务
python3 sync_server.py  # 监听 TCP 9901

# 在从节点配置 sync_client.py 定时同步
# 从节点只需部署 api_server.py + 前端，不需要爬虫
```

---

## 配置说明

### 环境变量（.env）

| 变量名 | 说明 | 必填 |
|--------|------|------|
| `DB_PASSWORD` | MySQL 密码 | **是** |
| `GITHUB_TOKEN` | GitHub Personal Access Token | **是** |
| `DB_HOST` | MySQL 主机地址 | 否（默认 127.0.0.1） |
| `DB_PORT` | MySQL 端口 | 否（默认 3306） |
| `DB_USER` | MySQL 用户名 | 否（默认 threatpulse） |
| `DB_NAME` | 数据库名 | 否（默认 threatpulse） |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | 否（默认使用免费方案） |
| `TP_JWT_SECRET` | JWT 签名密钥 | 否（可用 .jwt_secret 文件） |

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

五组爬虫错峰运行，避免资源争抢：

| 时间 | 爬虫 | 脚本 | 日志 |
|------|------|------|------|
| `:00` 整点 | Twitter/X | `main.py` | `cron.log` |
| `:15` | GitHub（仓库 + Advisory） | `github_scraper.py` | `github_cron.log` |
| `:30` | CN-SEC | `cnsec_scraper.py` | `cnsec_cron.log` |
| `:45` | FreeBuf + 安全客 + THN + XLab | `multi_scraper.py` | `multi_cron.log` |
| `8:00 / 20:00` | GitHub Trending | `github_trending.py` | `trending_cron.log` |

---

## 技术实现细节

### 智能摘要引擎（deepseek_summarizer.py）

v8.0 版本默认使用零成本方案，不再调用 DeepSeek API：

```python
# 核心函数映射
generate_summary = generate_summary_free  # 默认免费方案

# 免费方案逻辑
def generate_summary_free(title, content):
    if _is_chinese(combined):
        # 中文 → 截取前150字，在句号处智能截断
        return _truncate_chinese_summary(source_text, max_len=150)
    else:
        # 英文 → Google翻译为中文 → 截取前150字
        translated = _translate_google(source_text[:500])
        return _truncate_chinese_summary(translated, max_len=150)

# 一行代码切换回 DeepSeek
# generate_summary = generate_summary_deepseek
```

**关键函数：**
- `generate_summary_free()` — 免费摘要（Google 翻译 + 中文截取）
- `generate_summary_deepseek()` — DeepSeek API 备用
- `translate_text_free()` — 免费翻译（GitHub Trending 等）
- `_is_chinese()` — 语言检测（中文字符占比 > 15%）
- `_truncate_chinese_summary()` — 智能截取（优先在句号处截断）

### Twitter 爬虫优化
- **先去重再生成摘要**: `tweet_exists_in_db()` 先查 DB，确认是新推文才调摘要引擎
- **GraphQL API**: 直接调用 Twitter 内部接口，非第三方 API
- **x-client-transaction-id**: 自行实现的签名生成器
- **Cookie 持久化 + 多账户轮换 + 随机延迟 + 指数退避**

### 热点聚合算法
- 基于中文摘要前 30 字做 Jaccard 相似度计算
- 相似度 > 45% 认为是同一话题
- 关键实体匹配（CVE 编号、产品名）增强精度
- 热度公式: `count*100 + source_count*50 + log2(total_heat+1)*10`

### 情报源筛选
- 后端 `get_source_list()` 按 source 字段聚合分组
- 前端情报源按钮动态渲染，显示数量角标
- 支持 source + severity + category 三维度组合过滤

### 多源爬虫（multi_scraper.py）
- **FreeBuf**: API 优先，WAF 封锁时自动回退 JSON 文件导入
- **安全客**: REST API 采集
- **The Hacker News**: RSS Feed 解析
- **奇安信 XLab**: Ghost 博客 RSS Feed
- **通用分类引擎**: 关键词匹配自动分类 + 严重等级评估

### 主从同步
- **sync_server.py**: 主节点监听 TCP 9901，提供增量数据查询
- **sync_client.py**: 从节点定时连接主节点拉取新数据
- 从节点只需部署 API 服务和前端，不需要运行爬虫

---

## 注意事项与踩坑记录

### Twitter 相关
1. **GraphQL queryId 会变更**: 需从浏览器 Network 面板抓取最新值
2. **x-client-transaction-id**: 2024 年新增的反爬验证，缺少会返回 403
3. **Cookie 有效期**: auth_token ~1 年，ct0 较短，建议定期更新

### GitHub 相关
1. **Search API 限制**: 未认证 10 次/分钟，认证后 30 次/分钟
2. **RECENT_DAYS=14**: 仓库搜索最近 14 天内更新的项目

### FreeBuf 相关
1. **WAF 封锁**: 某些 IP 被阿里云 WAF 封锁（返回 405），自动回退 JSON 文件方案

### Google 翻译相关
1. **可用性**: 需要服务器能访问 `translate.googleapis.com`
2. **国内服务器**: 可能无法直接访问，建议在可访问 Google 的服务器上运行爬虫

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
tail -f trending_cron.log  # GitHub Trending

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

### 切换摘要方案

```python
# 在 deepseek_summarizer.py 中修改：

# 使用免费方案（默认）
generate_summary = generate_summary_free

# 切换回 DeepSeek AI 摘要
# generate_summary = generate_summary_deepseek
```

### 手动触发爬虫

```bash
python3 main.py              # Twitter 爬虫
python3 github_scraper.py    # GitHub 爬虫
python3 cnsec_scraper.py     # CN-SEC 爬虫
python3 multi_scraper.py     # FreeBuf + 安全客 + THN + XLab
python3 github_trending.py   # GitHub Trending
```

---

## 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| v8.0 | 2026-04-10 | 情报源筛选、多维度过滤、热点详情展开、DeepSeek→免费方案、主从同步、去重优化 |
| v7.0 | 2026-04-09 | GitHub Trending 热门项目、热点情报聚合 Top10、前端双栏布局 |
| v6.0 | 2026-04-09 | 新增 FreeBuf/安全客/THN/XLab 四大数据源 |
| v5.0 | 2026-04-09 | 多源情报聚合 + DeepSeek AI 摘要 + 模糊搜索 |
| v4.0 | 2026-04-09 | GitHub 仓库 + Advisory 爬虫、CN-SEC 爬虫 |

---

## License

MIT License
