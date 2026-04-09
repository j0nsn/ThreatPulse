// ===== 搜索关键词高亮工具 =====
export function highlightText(text, query) {
    if (!query || !text) return text;
    const keywords = query.split(/\s+/).filter(k => k.length > 0);
    if (keywords.length === 0) return text;
    const escaped = keywords.map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const regex = new RegExp(`(${escaped.join('|')})`, 'gi');
    return text.replace(regex, '<mark class="search-highlight">$1</mark>');
}

// ===== 搜索建议下拉组件 =====
export function renderSearchSuggestions(items, query) {
    if (!items || items.length === 0) return '';
    const severityLabels = { critical: '严重', high: '高危', medium: '中危', low: '低危', info: '信息' };
    const categoryLabels = { ddos: 'DDoS', web: 'Web安全', malware: '恶意软件', apt: 'APT', vuln: '漏洞', phishing: '钓鱼', ransomware: '勒索', agent: 'AI Agent', llm: '大模型', general: '综合' };

    return `<div class="search-suggestions">
        <div class="search-suggestions-header">
            <i class="ri-sparkling-line text-accent-cyan"></i>
            <span>搜索建议 · 共 ${items.length} 条匹配</span>
        </div>
        ${items.map((item, idx) => {
            const title = highlightText(item.title || '', query);
            const snippet = item.summary_cn_snippet
                ? highlightText(item.summary_cn_snippet, query)
                : highlightText(item.summary_snippet || '', query);
            const qLower = query.toLowerCase();
            const matchField = (item.summary_cn_snippet && item.summary_cn_snippet.toLowerCase().includes(qLower))
                ? '中文摘要' : (item.summary_snippet && item.summary_snippet.toLowerCase().includes(qLower))
                ? '原文摘要' : '标题';
            return `<div class="search-suggestion-item" data-id="${item.id}" data-index="${idx}">
                <div class="suggestion-title">${title}</div>
                <div class="suggestion-snippet">${snippet}...</div>
                <div class="suggestion-meta">
                    <span class="severity-badge severity-${item.severity}" style="font-size:9px;padding:1px 5px;">${severityLabels[item.severity] || item.severity}</span>
                    <span class="suggestion-category">${categoryLabels[item.category] || item.category}</span>
                    <span class="suggestion-match-field"><i class="ri-focus-3-line"></i>匹配: ${matchField}</span>
                </div>
            </div>`;
        }).join('')}
    </div>`;
}

/**
 * 安全情报聚合平台 - 组件渲染模块 v2
 * 新增：情报详情增强（来源链接、中文翻译按钮）
 */

import { colorMap } from './data.js';

/**
 * 渲染统计卡片
 */
export function renderStatCards(container, stats) {
    container.innerHTML = stats.map((stat, index) => {
        const c = colorMap[stat.color];
        return `
        <div class="stat-card bg-dark-800 border border-white/5 rounded-xl p-3 cursor-pointer animate-slide-up" style="animation-delay: ${index * 60}ms">
            <div class="flex items-center justify-between mb-2">
                <div class="w-8 h-8 rounded-lg flex items-center justify-center" style="background: ${c.bg}">
                    <i class="${stat.icon}" style="color: ${c.text}"></i>
                </div>
                <span class="text-[10px] px-1.5 py-0.5 rounded ${stat.trend === 'up' ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'}">
                    ${stat.trend === 'up' ? '↑' : '↓'} ${stat.change}
                </span>
            </div>
            <div class="text-xl font-bold animate-count-up" style="color: ${c.text}; animation-delay: ${index * 60 + 200}ms">${stat.value}</div>
            <div class="text-[11px] text-gray-500 mt-0.5">${stat.label}</div>
        </div>`;
    }).join('');
}

/**
 * 渲染分类导航
 */
export function renderCategories(container, categories, activeId) {
    container.innerHTML = categories.map(cat => `
        <div class="category-item flex items-center gap-2.5 px-3 py-2 cursor-pointer ${cat.id === activeId ? 'active' : ''}" data-category="${cat.id}">
            <i class="${cat.icon} text-sm ${cat.id === activeId ? 'text-accent-blue' : 'text-gray-500'}"></i>
            <span class="text-sm flex-1 truncate">${cat.name}</span>
            <span class="text-[10px] ${cat.id === activeId ? 'text-accent-blue bg-accent-blue/10' : 'text-gray-600 bg-dark-600'} px-1.5 py-0.5 rounded-full">${cat.count}</span>
        </div>
    `).join('');
}

/**
 * 渲染热点攻击榜
 */
export function renderHotAttacks(container, attacks) {
    container.innerHTML = attacks.map(attack => {
        const rankColors = { 1: 'text-red-400 bg-red-500/15', 2: 'text-orange-400 bg-orange-500/15', 3: 'text-yellow-400 bg-yellow-500/15' };
        const rankClass = rankColors[attack.rank] || 'text-gray-500 bg-dark-600';
        const trendIcon = attack.trend === 'up' ? 'ri-arrow-up-s-line text-red-400' : attack.trend === 'down' ? 'ri-arrow-down-s-line text-green-400' : 'ri-subtract-line text-gray-500';
        return `
        <div class="hot-attack-item flex items-center gap-2 px-3 py-1.5 cursor-pointer" data-category="${attack.category}">
            <span class="w-5 h-5 rounded text-[10px] font-bold flex items-center justify-center shrink-0 ${rankClass}">${attack.rank}</span>
            <span class="text-xs text-gray-300 flex-1 truncate">${attack.name}</span>
            <i class="${trendIcon} text-xs"></i>
        </div>`;
    }).join('');
}

/**
 * 渲染标签云
 */
export function renderTagCloud(container, tags, activeTag) {
    container.innerHTML = tags.map(tag => {
        const sizeMap = { 5: 'text-sm font-semibold', 4: 'text-xs font-medium', 3: 'text-xs', 2: 'text-[11px]' };
        const sizeClass = sizeMap[tag.weight] || 'text-xs';
        const isActive = activeTag === tag.name;
        return `
        <span class="tag-item inline-block ${sizeClass} px-2 py-1 rounded-md border ${isActive ? 'active' : 'bg-dark-700 border-white/5 text-gray-400'}" data-tag="${tag.name}">
            ${tag.name}
        </span>`;
    }).join('');
}

/**
 * 渲染关键词趋势
 */
export function renderKeywordTrends(container, trends) {
    container.innerHTML = trends.map(item => {
        const trendIcon = item.trend === 'up' ? 'ri-arrow-up-s-line text-red-400' : item.trend === 'down' ? 'ri-arrow-down-s-line text-green-400' : 'ri-subtract-line text-gray-500';
        const barColor = item.trend === 'up' ? 'bg-gradient-to-r from-red-500/30 to-red-500/5' : item.trend === 'down' ? 'bg-gradient-to-r from-green-500/30 to-green-500/5' : 'bg-gradient-to-r from-gray-500/30 to-gray-500/5';
        return `
        <div class="group cursor-pointer">
            <div class="flex items-center justify-between mb-1">
                <span class="text-xs text-gray-300 group-hover:text-white transition-colors">${item.keyword}</span>
                <div class="flex items-center gap-1">
                    <span class="text-[10px] text-gray-500">${item.count}</span>
                    <i class="${trendIcon} text-xs"></i>
                    <span class="text-[10px] ${item.trend === 'up' ? 'text-red-400' : item.trend === 'down' ? 'text-green-400' : 'text-gray-500'}">${item.change}</span>
                </div>
            </div>
            <div class="h-1.5 bg-dark-600 rounded-full overflow-hidden">
                <div class="trend-bar h-full rounded-full ${barColor}" style="width: ${item.percent}%"></div>
            </div>
        </div>`;
    }).join('');
}

/**
 * 渲染威胁等级分布
 */
export function renderThreatLevels(container, levels) {
    const total = levels.reduce((sum, l) => sum + l.count, 0);
    const barHtml = `
        <div class="flex h-3 rounded-full overflow-hidden mb-3">
            ${levels.map(l => `<div class="h-full transition-all duration-500" style="width: ${l.percent}%; background: ${l.color}" title="${l.level}: ${l.count}"></div>`).join('')}
        </div>`;
    const legendHtml = levels.map(l => `
        <div class="flex items-center justify-between py-1">
            <div class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full" style="background: ${l.color}"></span>
                <span class="text-xs text-gray-400">${l.level}</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="text-xs font-medium text-gray-300">${l.count}</span>
                <span class="text-[10px] text-gray-600">${l.percent}%</span>
            </div>
        </div>
    `).join('');
    container.innerHTML = barHtml + legendHtml;
}

/**
 * 渲染情报卡片
 */
export function renderIntelCard(intel) {
    const severityLabels = { critical: '严重', high: '高危', medium: '中危', low: '低危', info: '信息' };
    const categoryLabels = { ddos: 'DDoS', web: 'Web安全', malware: '恶意软件', apt: 'APT', vuln: '漏洞', phishing: '钓鱼', ransomware: '勒索', agent: 'AI Agent', llm: '大模型', general: '综合' };
    const categoryIcons = { ddos: 'ri-flood-line', web: 'ri-global-line', malware: 'ri-bug-line', apt: 'ri-spy-line', vuln: 'ri-shield-keyhole-line', phishing: 'ri-mail-forbid-line', ransomware: 'ri-lock-2-line', agent: 'ri-robot-line', llm: 'ri-brain-line', general: 'ri-file-shield-2-line' };

    return `
    <article class="intel-card bg-dark-800 border border-white/5 rounded-xl p-4 cursor-pointer threat-${intel.severity}" data-id="${intel.id}">
        <div class="flex items-start gap-3">
            <div class="w-9 h-9 rounded-lg bg-dark-600 flex items-center justify-center shrink-0 mt-0.5">
                <i class="${categoryIcons[intel.category] || 'ri-file-line'} text-gray-400"></i>
            </div>
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                    <span class="severity-badge severity-${intel.severity}">${severityLabels[intel.severity] || intel.severity}</span>
                    <span class="text-[10px] text-gray-600 bg-dark-600 px-1.5 py-0.5 rounded">${categoryLabels[intel.category] || intel.category}</span>
                    ${intel.isNew ? '<span class="text-[10px] bg-accent-blue/15 text-accent-blue px-1.5 py-0.5 rounded font-medium animate-pulse">NEW</span>' : ''}
                    <span class="text-[10px] text-gray-600 ml-auto shrink-0"><i class="ri-time-line mr-0.5"></i>${intel.time.dateTime || intel.time}<span class="ml-1 text-gray-700">${intel.time.relative ? " · " + intel.time.relative : ""}</span></span>
                </div>
                <h3 class="text-sm font-medium text-gray-200 leading-snug mb-2 line-clamp-2 hover:text-white transition-colors">${intel.title}</h3>
                <p class="text-xs text-gray-500 leading-relaxed mb-2.5 line-clamp-2">${intel.summary}</p>
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-1.5 flex-wrap">
                        ${intel.tags.slice(0, 4).map(tag => `<span class="intel-tag">${tag}</span>`).join('')}
                    </div>
                    <div class="flex items-center gap-3 text-[10px] text-gray-600 shrink-0 ml-2">
                        <span class="flex items-center gap-0.5"><i class="ri-fire-line text-orange-500/60"></i>${intel.heat}</span>
                        <span class="flex items-center gap-0.5"><i class="ri-chat-3-line"></i>${intel.comments}</span>
                        <span class="flex items-center gap-0.5"><i class="${intel.sourceIcon}"></i>${intel.source}</span>
                    </div>
                </div>
            </div>
        </div>
    </article>`;
}

/**
 * 渲染情报详情弹窗内容 - v2 增强版
 * 新增：情报来源链接区块、中文情报摘要与原文摘要双栏展示
 */
export function renderIntelDetail(intel) {
    const severityLabels = { critical: '严重', high: '高危', medium: '中危', low: '低危', info: '信息' };
    const categoryLabels = { ddos: 'DDoS 攻击', web: 'Web 安全', malware: '恶意软件', apt: 'APT 攻击', vuln: '漏洞情报', phishing: '钓鱼攻击', ransomware: '勒索软件', agent: 'AI Agent', llm: '大模型技术', general: '综合情报' };

    return `
    <div class="space-y-5">
        <!-- 基本信息 -->
        <div class="flex items-center gap-2 flex-wrap">
            <span class="severity-badge severity-${intel.severity}">${severityLabels[intel.severity] || intel.severity}</span>
            <span class="text-xs text-gray-500 bg-dark-600 px-2 py-0.5 rounded">${categoryLabels[intel.category] || intel.category}</span>
            <span class="text-xs text-gray-500 flex items-center gap-1"><i class="ri-calendar-line"></i>${intel.time.dateTime || intel.time}<span class="text-gray-600">${intel.time.relative ? " · " + intel.time.relative : ""}</span></span>
        </div>

        <!-- 中文情报摘要 -->
        ${intel.summaryCn ? `
        <div>
            <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <i class="ri-translate-2 text-accent-cyan"></i>中文情报摘要
            </h4>
            <div class="bg-dark-900/50 rounded-lg p-3 border border-accent-cyan/10">
                <p class="text-sm text-gray-200 leading-relaxed">${intel.summaryCn}</p>
            </div>
        </div>` : ''}

        <!-- 原文摘要 -->
        <div>
            <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <i class="ri-file-text-line text-gray-500"></i>原文摘要
            </h4>
            <div class="bg-dark-900/30 rounded-lg p-3 border border-white/5">
                <p class="text-sm text-gray-400 leading-relaxed" style="white-space: pre-wrap; word-break: break-word;">${intel.summary}</p>
            </div>
        </div>

        <!-- 🆕 情报来源详情 -->
        <div>
            <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">情报来源</h4>
            <div class="bg-dark-900/50 rounded-lg p-3 border border-white/5 space-y-2">
                <div class="flex items-center gap-2">
                    <i class="${intel.sourceIcon} text-accent-cyan"></i>
                    <span class="text-sm text-gray-300">${intel.source}</span>
                </div>
                ${intel.userName ? `
                <div class="flex items-center gap-2 text-xs text-gray-400">
                    <i class="ri-user-line"></i>
                    <span>${intel.userName}</span>
                    ${intel.userScreenName ? `<span class="text-gray-600">@${intel.userScreenName}</span>` : ''}
                    ${intel.userFollowers ? `<span class="text-gray-600">· ${formatFollowers(intel.userFollowers)} followers</span>` : ''}
                </div>` : ''}
                ${intel.link && intel.link !== '#' ? `
                <a href="${intel.link}" target="_blank" rel="noopener noreferrer" class="flex items-center gap-1.5 text-xs text-accent-blue hover:text-accent-cyan transition-colors group">
                    <i class="ri-external-link-line"></i>
                    <span class="group-hover:underline">${intel.link.length > 60 ? intel.link.substring(0, 60) + '...' : intel.link}</span>
                </a>` : ''}
            </div>
        </div>

        <!-- IOC 指标 -->
        ${intel.ioc && intel.ioc.length > 0 ? `
        <div>
            <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">IOC 威胁指标</h4>
            <div class="bg-dark-900 rounded-lg p-3 space-y-1.5">
                ${intel.ioc.map(ioc => `
                <div class="flex items-center gap-2 text-xs">
                    <i class="ri-terminal-box-line text-accent-cyan shrink-0"></i>
                    <code class="text-gray-400 font-mono break-all">${ioc}</code>
                </div>`).join('')}
            </div>
        </div>` : ''}

        <!-- 标签 -->
        <div>
            <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">关联标签</h4>
            <div class="flex flex-wrap gap-1.5">
                ${intel.tags.map(tag => `<span class="text-xs px-2.5 py-1 rounded-md bg-dark-600 text-gray-400 border border-white/5">${tag}</span>`).join('')}
            </div>
        </div>

        <!-- 互动数据 -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 border-t border-white/5">
            <div class="flex items-center gap-1.5 text-sm">
                <i class="ri-fire-line text-orange-400"></i>
                <span class="text-gray-400 text-xs">热度</span>
                <span class="font-medium text-gray-200">${intel.heat}</span>
            </div>
            <div class="flex items-center gap-1.5 text-sm">
                <i class="ri-chat-3-line text-accent-blue"></i>
                <span class="text-gray-400 text-xs">讨论</span>
                <span class="font-medium text-gray-200">${intel.comments}</span>
            </div>
            ${intel.retweetCount !== undefined ? `
            <div class="flex items-center gap-1.5 text-sm">
                <i class="ri-repeat-line text-green-400"></i>
                <span class="text-gray-400 text-xs">转发</span>
                <span class="font-medium text-gray-200">${intel.retweetCount}</span>
            </div>` : ''}
            ${intel.favoriteCount !== undefined ? `
            <div class="flex items-center gap-1.5 text-sm">
                <i class="ri-heart-line text-red-400"></i>
                <span class="text-gray-400 text-xs">点赞</span>
                <span class="font-medium text-gray-200">${intel.favoriteCount}</span>
            </div>` : ''}
        </div>
    </div>`;
}

function formatFollowers(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

/**
 * 渲染骨架屏
 */
export function renderSkeletons(container, count) {
    const skeletons = Array.from({ length: count }, () => `
        <div class="bg-dark-800 border border-white/5 rounded-xl p-4">
            <div class="flex items-start gap-3">
                <div class="skeleton w-9 h-9 shrink-0"></div>
                <div class="flex-1 space-y-2">
                    <div class="flex gap-2">
                        <div class="skeleton w-12 h-4"></div>
                        <div class="skeleton w-16 h-4"></div>
                    </div>
                    <div class="skeleton w-full h-4"></div>
                    <div class="skeleton w-3/4 h-4"></div>
                    <div class="skeleton w-full h-3"></div>
                    <div class="flex gap-2 mt-2">
                        <div class="skeleton w-14 h-5"></div>
                        <div class="skeleton w-14 h-5"></div>
                        <div class="skeleton w-14 h-5"></div>
                    </div>
                </div>
            </div>
        </div>
    `).join('');
    container.innerHTML = skeletons;
}
