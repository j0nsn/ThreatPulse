/**
 * 安全情报聚合平台 - 数据模块（API 版本 v2）
 * 新增翻译 API 调用
 */

const API_BASE = window.location.pathname.replace(/\/$/, '') + '/api';

// 颜色映射
export const colorMap = {
    blue: { bg: 'rgba(59,130,246,0.1)', border: 'rgba(59,130,246,0.2)', text: '#60a5fa', gradient: 'from-blue-500/20 to-blue-600/5' },
    red: { bg: 'rgba(239,68,68,0.1)', border: 'rgba(239,68,68,0.2)', text: '#f87171', gradient: 'from-red-500/20 to-red-600/5' },
    orange: { bg: 'rgba(245,158,11,0.1)', border: 'rgba(245,158,11,0.2)', text: '#fbbf24', gradient: 'from-amber-500/20 to-amber-600/5' },
    purple: { bg: 'rgba(139,92,246,0.1)', border: 'rgba(139,92,246,0.2)', text: '#a78bfa', gradient: 'from-purple-500/20 to-purple-600/5' },
    cyan: { bg: 'rgba(6,182,212,0.1)', border: 'rgba(6,182,212,0.2)', text: '#22d3ee', gradient: 'from-cyan-500/20 to-cyan-600/5' },
    green: { bg: 'rgba(16,185,129,0.1)', border: 'rgba(16,185,129,0.2)', text: '#34d399', gradient: 'from-emerald-500/20 to-emerald-600/5' },
};

// 默认分类
const defaultCategories = [
    { id: 'all', name: '全部情报', icon: 'ri-dashboard-line' },
    { id: 'ddos', name: 'DDoS 攻击', icon: 'ri-flood-line' },
    { id: 'agent', name: 'AI Agent', icon: 'ri-robot-line' },
    { id: 'llm', name: '大模型技术', icon: 'ri-brain-line' },
    { id: 'vuln', name: '漏洞情报', icon: 'ri-shield-keyhole-line' },
    { id: 'malware', name: '恶意软件', icon: 'ri-bug-line' },
    { id: 'general', name: '综合情报', icon: 'ri-file-shield-2-line' },
];

async function apiFetch(endpoint, params = {}, options = {}) {
    const url = new URL(API_BASE + endpoint, window.location.origin);
    Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
    });
    try {
        const fetchOptions = { ...options };
        const resp = await fetch(url.toString(), { ...fetchOptions, credentials: 'same-origin' });
        if (resp.status === 401) {
            window.location.href = window.location.pathname.replace(/\/$/, '') + '/login';
            return null;
        }
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const json = await resp.json();
        return json.data;
    } catch (e) {
        console.error(`API Error [${endpoint}]:`, e);
        return null;
    }
}

async function apiPost(endpoint, body = {}) {
    const url = new URL(API_BASE + endpoint, window.location.origin);
    try {
        const resp = await fetch(url.toString(), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(body),
        });
        if (resp.status === 401) {
            window.location.href = window.location.pathname.replace(/\/$/, '') + '/login';
            return null;
        }
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const json = await resp.json();
        return json.data;
    } catch (e) {
        console.error(`API POST Error [${endpoint}]:`, e);
        return null;
    }
}

// ===== 导出的 API 函数 =====

export async function fetchIntel({ category, severity, source, keyword, search, time_filter, sort_by, page, page_size } = {}) {
    const data = await apiFetch('/intel', { category, severity, source, keyword, search, time_filter, sort_by, page, page_size });
    return data || { total: 0, items: [], page: 1, page_size: 20 };
}

export async function fetchStats(time_filter) {
    const data = await apiFetch('/stats', { time_filter });
    return data || { total: 0, critical: 0, high: 0, medium: 0, low: 0, info: 0, categories: {}, sources: 0 };
}

export async function fetchHotAttacks(time_filter, limit = 8) {
    const data = await apiFetch('/hot-attacks', { time_filter, limit });
    return data || [];
}

export async function fetchTags(time_filter, limit = 25) {
    const data = await apiFetch('/tags', { time_filter, limit });
    return data || [];
}

export async function fetchKeywords(time_filter, limit = 10) {
    const data = await apiFetch('/keywords', { time_filter, limit });
    return data || [];
}

export async function fetchSummary(time_filter) {
    const data = await apiFetch('/summary', { time_filter });
    return data ? data.text : '暂无数据，等待爬虫采集...';
}

// 🆕 翻译 API
export async function fetchTranslation(text) {
    const data = await apiPost('/translate', { text });
    return data ? data.translated : null;
}

// 🆕 GitHub 热门项目 API
export async function fetchGithubTrending(period = 'daily', limit = 10) {
    const data = await apiFetch('/github-trending', { period, limit });
    return data || [];
}

// 🆕 热点情报聚合 API
export async function fetchHotTopics(time_range = 'daily', limit = 10) {
    const data = await apiFetch('/hot-topics', { time_range, limit });
    return data || [];
}

// 🆕 情报源列表 API
export async function fetchSources() {
    const data = await apiFetch('/sources');
    return data || [];
}

export function buildCategories(categoryCounts, total) {
    return defaultCategories.map(cat => ({
        ...cat,
        count: cat.id === 'all' ? total : (categoryCounts[cat.id] || 0),
    }));
}

export function buildStatsCards(stats) {
    return [
        { label: '情报总数', value: stats.total, change: `${stats.total}`, icon: 'ri-file-shield-2-line', color: 'blue', trend: 'up' },
        { label: '严重', value: stats.critical, change: `${stats.critical}`, icon: 'ri-error-warning-line', color: 'red', trend: stats.critical > 0 ? 'up' : 'down' },
        { label: '高危', value: stats.high, change: `${stats.high}`, icon: 'ri-alarm-warning-line', color: 'orange', trend: stats.high > 0 ? 'up' : 'down' },
        { label: '中危', value: stats.medium, change: `${stats.medium}`, icon: 'ri-shield-line', color: 'purple', trend: 'up' },
        { label: '情报来源', value: stats.sources, change: `${stats.sources}`, icon: 'ri-database-2-line', color: 'cyan', trend: 'up' },
        { label: '低危/信息', value: stats.low + stats.info, change: `${stats.low + stats.info}`, icon: 'ri-shield-check-line', color: 'green', trend: 'up' },
    ];
}

export function buildThreatLevels(stats) {
    const total = stats.total || 1;
    return [
        { level: '严重', count: stats.critical, percent: Math.round(stats.critical / total * 100), color: '#ef4444' },
        { level: '高危', count: stats.high, percent: Math.round(stats.high / total * 100), color: '#f59e0b' },
        { level: '中危', count: stats.medium, percent: Math.round(stats.medium / total * 100), color: '#3b82f6' },
        { level: '低危', count: stats.low, percent: Math.round(stats.low / total * 100), color: '#10b981' },
        { level: '信息', count: stats.info, percent: Math.round(stats.info / total * 100), color: '#6b7280' },
    ];
}
