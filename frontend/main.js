/**
 * 安全情报聚合平台 - 主入口模块（API 版本 v2）
 * 新增：严重等级筛选、中文翻译功能
 */

import {
    fetchIntel, fetchStats, fetchHotAttacks, fetchTags,
    fetchKeywords, fetchSummary, fetchTranslation,
    buildCategories, buildStatsCards,
    buildThreatLevels, colorMap
} from './data.js';

import {
    renderStatCards, renderCategories, renderHotAttacks,
    renderTagCloud, renderKeywordTrends, renderThreatLevels,
    renderIntelCard, renderIntelDetail, renderSkeletons
} from './components.js';

// ===== 应用状态 =====
const state = {
    activeCategory: 'all',
    activeSeverity: 'all',   // 🆕 严重等级筛选
    activeTag: null,
    activeSortBy: 'latest',
    timeFilter: 'all',
    autoRefresh: false,
    autoRefreshTimer: null,
    currentPage: 1,
    pageSize: 20,
    totalCount: 0,
    searchQuery: '',
    isRefreshing: false,
    newDataCount: 0,
    lastTotal: 0,
    intelItems: [],
};

// ===== DOM 引用 =====
const dom = {};

function cacheDom() {
    dom.summarySection = document.querySelector('#summarySection .grid');
    dom.summaryText = document.getElementById('summaryText');
    dom.summaryTime = document.getElementById('summaryTime');
    dom.categoryNav = document.getElementById('categoryNav');
    dom.hotAttackList = document.getElementById('hotAttackList');
    dom.tagCloud = document.getElementById('tagCloud');
    dom.keywordTrends = document.getElementById('keywordTrends');
    dom.threatLevelChart = document.getElementById('threatLevelChart');
    dom.intelFeed = document.getElementById('intelFeed');
    dom.intelCount = document.getElementById('intelCount');
    dom.searchInput = document.getElementById('searchInput');
    dom.timeFilterBtn = document.getElementById('timeFilterBtn');
    dom.timeFilterLabel = document.getElementById('timeFilterLabel');
    dom.timeFilterDropdown = document.getElementById('timeFilterDropdown');
    dom.timeFilterWrap = document.getElementById('timeFilterWrap');
    dom.refreshBtn = document.getElementById('refreshBtn');
    dom.refreshIcon = document.getElementById('refreshIcon');
    dom.autoRefreshToggle = document.getElementById('autoRefreshToggle');
    dom.loadMoreBtn = document.getElementById('loadMoreBtn');
    dom.newDataBanner = document.getElementById('newDataBanner');
    dom.newDataText = document.getElementById('newDataText');
    dom.detailModal = document.getElementById('detailModal');
    dom.modalOverlay = document.getElementById('modalOverlay');
    dom.modalPanel = document.getElementById('modalPanel');
    dom.modalTitle = document.getElementById('modalTitle');
    dom.modalBody = document.getElementById('modalBody');
    dom.modalClose = document.getElementById('modalClose');
    dom.modalSource = document.getElementById('modalSource');
    dom.modalLink = document.getElementById('modalLink');
    dom.severityFilterBar = document.getElementById('severityFilterBar');
    dom.logoutBtn = document.getElementById('logoutBtn');
    dom.currentUser = document.getElementById('currentUser');
}

// ===== 获取情报列表的参数构建 =====
function buildIntelParams(page = 1) {
    return {
        category: state.activeCategory,
        severity: state.activeSeverity === 'all' ? undefined : state.activeSeverity,
        search: state.searchQuery,
        time_filter: state.timeFilter,
        sort_by: state.activeSortBy,
        page: page,
        page_size: state.pageSize,
    };
}

// ===== 渲染函数 =====
async function renderAll() {
    // 并行获取所有数据
    const [stats, hotAttacks, tags, keywords, summary, intelResult] = await Promise.all([
        fetchStats(state.timeFilter),
        fetchHotAttacks(state.timeFilter),
        fetchTags(state.timeFilter),
        fetchKeywords(state.timeFilter),
        fetchSummary(state.timeFilter),
        fetchIntel(buildIntelParams(1)),
    ]);

    // 渲染统计卡片
    const statsCards = buildStatsCards(stats);
    renderStatCards(dom.summarySection, statsCards);

    // 渲染 AI 摘要
    renderSummaryText(summary);

    // 渲染分类导航
    const categories = buildCategories(stats.categories, stats.total);
    renderCategories(dom.categoryNav, categories, state.activeCategory);

    // 渲染热点攻击榜
    renderHotAttacks(dom.hotAttackList, hotAttacks);

    // 渲染标签云
    const tagData = tags.map(t => ({ name: t.name, weight: Math.min(5, Math.max(2, Math.ceil(t.weight / 5))) }));
    renderTagCloud(dom.tagCloud, tagData, state.activeTag);

    // 渲染关键词趋势
    const kwData = keywords.map(k => ({
        keyword: k.keyword,
        count: k.cnt,
        percent: k.percent,
        trend: 'up',
        change: `+${k.cnt}`,
    }));
    renderKeywordTrends(dom.keywordTrends, kwData);

    // 渲染威胁等级分布
    const threatLevels = buildThreatLevels(stats);
    renderThreatLevels(dom.threatLevelChart, threatLevels);

    // 渲染情报流
    state.intelItems = intelResult.items;
    state.totalCount = intelResult.total;
    state.currentPage = 1;
    renderIntelFeed();

    // 记录当前总数用于检测新数据
    state.lastTotal = stats.total;
}

function renderSummaryText(text) {
    dom.summaryText.textContent = '';
    typeWriter(dom.summaryText, text, 0);
    const now = new Date();
    dom.summaryTime.textContent = `更新于 ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
}

function typeWriter(element, text, index) {
    if (index < text.length) {
        element.textContent += text.charAt(index);
        setTimeout(() => typeWriter(element, text, index + 1), 15);
    }
}

function renderIntelFeed() {
    const items = state.intelItems;

    dom.intelFeed.innerHTML = items.map((intel, i) => {
        // 转换后端数据格式到前端组件格式
        const cardData = {
            id: intel.id,
            title: intel.title,
            summary: intel.summary || intel.full_text || '',
            category: intel.category,
            severity: intel.severity,
            source: intel.source || 'Twitter',
            sourceIcon: intel.source_icon || 'ri-twitter-x-line',
            time: formatTime(intel.crawl_time),
            tags: intel.tags || [],
            heat: intel.heat || 0,
            comments: intel.comments || 0,
            ioc: intel.ioc || [],
            link: intel.link || '#',
            isNew: intel.is_new === 1,
        };
        const card = renderIntelCard(cardData);
        return `<div class="animate-slide-up" style="animation-delay: ${i * 50}ms">${card}</div>`;
    }).join('');

    if (items.length === 0) {
        dom.intelFeed.innerHTML = `
            <div class="text-center py-16">
                <i class="ri-inbox-line text-4xl text-gray-600 mb-3 block"></i>
                <p class="text-gray-500 text-sm">暂无情报数据</p>
                <p class="text-gray-600 text-xs mt-1">当前筛选条件下无匹配结果，请尝试调整筛选</p>
            </div>`;
    }

    dom.intelCount.textContent = `${state.totalCount} 条`;

    // 更新加载更多按钮
    const loaded = state.intelItems.length;
    if (loaded >= state.totalCount) {
        dom.loadMoreBtn.innerHTML = '<i class="ri-check-line mr-1"></i>已显示全部情报';
        dom.loadMoreBtn.disabled = true;
        dom.loadMoreBtn.classList.add('opacity-50', 'cursor-not-allowed');
    } else {
        dom.loadMoreBtn.innerHTML = `<i class="ri-arrow-down-line mr-1"></i>加载更多情报 (${state.totalCount - loaded} 条)`;
        dom.loadMoreBtn.disabled = false;
        dom.loadMoreBtn.classList.remove('opacity-50', 'cursor-not-allowed');
    }
}

function formatTime(timeStr) {
    if (!timeStr) return { dateTime: '', relative: '' };
    const d = new Date(timeStr);
    const now = new Date();
    const diff = (now - d) / 1000;

    // 具体日期时间：2026-04-09 14:55
    const Y = d.getFullYear();
    const M = String(d.getMonth() + 1).padStart(2, '0');
    const D = String(d.getDate()).padStart(2, '0');
    const h = String(d.getHours()).padStart(2, '0');
    const m = String(d.getMinutes()).padStart(2, '0');
    const dateTime = `${Y}-${M}-${D} ${h}:${m}`;

    // 相对时间
    let relative = '';
    if (diff < 60) relative = '刚刚';
    else if (diff < 3600) relative = `${Math.floor(diff / 60)}分钟前`;
    else if (diff < 86400) relative = `${Math.floor(diff / 3600)}小时前`;
    else if (diff < 604800) relative = `${Math.floor(diff / 86400)}天前`;
    else relative = dateTime;

    return { dateTime, relative };
}

// ===== 事件绑定 =====
function bindEvents() {
    // 搜索
    let searchTimer = null;
    dom.searchInput.addEventListener('input', (e) => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
            state.searchQuery = e.target.value.trim();
            state.currentPage = 1;
            refreshData();
        }, 500);
    });

    // 键盘快捷键
    document.addEventListener('keydown', (e) => {
        if (e.key === '/' && document.activeElement !== dom.searchInput) {
            e.preventDefault();
            dom.searchInput.focus();
        }
        if (e.key === 'Escape') {
            closeModal();
            dom.searchInput.blur();
        }
    });

    // 时间筛选
    dom.timeFilterBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        dom.timeFilterDropdown.classList.toggle('hidden');
    });

    dom.timeFilterWrap.addEventListener('click', (e) => {
        const option = e.target.closest('.time-option');
        if (option) {
            const labels = { today: '今日', '3days': '近3天', week: '本周', month: '本月', all: '全部' };
            state.timeFilter = option.dataset.value;
            dom.timeFilterLabel.textContent = labels[state.timeFilter];
            dom.timeFilterDropdown.classList.add('hidden');
            refreshData();
        }
    });

    document.addEventListener('click', () => {
        dom.timeFilterDropdown.classList.add('hidden');
    });

    // 刷新
    dom.refreshBtn.addEventListener('click', () => {
        refreshData();
    });

    // 自动刷新
    dom.autoRefreshToggle.addEventListener('click', () => {
        state.autoRefresh = !state.autoRefresh;
        dom.autoRefreshToggle.classList.toggle('active', state.autoRefresh);
        if (state.autoRefresh) {
            startAutoRefresh();
        } else {
            stopAutoRefresh();
        }
    });

    // 分类导航
    dom.categoryNav.addEventListener('click', (e) => {
        const item = e.target.closest('.category-item');
        if (item) {
            state.activeCategory = item.dataset.category;
            state.currentPage = 1;
            refreshData();
        }
    });

    // 热点攻击点击
    dom.hotAttackList.addEventListener('click', (e) => {
        const item = e.target.closest('.hot-attack-item');
        if (item) {
            state.activeCategory = item.dataset.category;
            state.currentPage = 1;
            refreshData();
        }
    });

    // 标签云点击
    dom.tagCloud.addEventListener('click', (e) => {
        const tagEl = e.target.closest('.tag-item');
        if (tagEl) {
            const tagName = tagEl.dataset.tag;
            if (state.activeTag === tagName) {
                state.activeTag = null;
                state.searchQuery = '';
                dom.searchInput.value = '';
            } else {
                state.activeTag = tagName;
                state.searchQuery = tagName;
                dom.searchInput.value = tagName;
            }
            state.currentPage = 1;
            refreshData();
        }
    });

    // 排序按钮
    document.querySelectorAll('.sort-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.activeSortBy = btn.dataset.sort;
            state.currentPage = 1;
            refreshData();
        });
    });

    // 🆕 严重等级筛选按钮
    dom.severityFilterBar.addEventListener('click', (e) => {
        const btn = e.target.closest('.severity-filter-btn');
        if (btn) {
            dom.severityFilterBar.querySelectorAll('.severity-filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.activeSeverity = btn.dataset.severity;
            state.currentPage = 1;
            refreshIntelOnly();
        }
    });

    // 加载更多
    dom.loadMoreBtn.addEventListener('click', async () => {
        if (dom.loadMoreBtn.disabled) return;
        state.currentPage++;
        const result = await fetchIntel(buildIntelParams(state.currentPage));
        state.intelItems = state.intelItems.concat(result.items);
        renderIntelFeed();
    });

    // 情报卡片点击
    dom.intelFeed.addEventListener('click', (e) => {
        const card = e.target.closest('.intel-card');
        if (card) {
            const id = parseInt(card.dataset.id);
            const intel = state.intelItems.find(item => item.id === id);
            if (intel) {
                openModal(intel);
            }
        }
    });

    // 弹窗关闭
    dom.modalClose.addEventListener('click', closeModal);
    dom.modalOverlay.addEventListener('click', closeModal);

    // 新数据横幅
    dom.newDataBanner.addEventListener('click', () => {
        hideNewDataBanner();
        refreshData();
    });

    // 🆕 弹窗内翻译按钮（事件委托）
    document.addEventListener('click', async (e) => {
        const translateBtn = e.target.closest('.translate-btn');
        if (translateBtn) {
            const text = translateBtn.dataset.text;
            const targetEl = document.getElementById(translateBtn.dataset.target);
            if (!text || !targetEl) return;

            // 防止重复点击
            if (translateBtn.classList.contains('translating')) return;
            translateBtn.classList.add('translating');
            translateBtn.innerHTML = '<i class="ri-loader-4-line animate-spin mr-1"></i>翻译中...';

            const translated = await fetchTranslation(text);
            if (translated) {
                targetEl.innerHTML = `<p class="text-sm text-gray-300 leading-relaxed">${translated}</p>`;
                targetEl.classList.remove('hidden');
                translateBtn.innerHTML = '<i class="ri-check-line mr-1"></i>已翻译';
                translateBtn.classList.add('translated');
            } else {
                translateBtn.innerHTML = '<i class="ri-translate-2 mr-1"></i>翻译失败，点击重试';
                translateBtn.classList.remove('translating');
            }
        }
    });

    // 登出按钮
    if (dom.logoutBtn) {
        dom.logoutBtn.addEventListener('click', async () => {
            try {
                await fetch(window.location.pathname.replace(/\/$/, '') + '/api/auth/logout', {
                    method: 'POST', credentials: 'same-origin'
                });
            } catch (_) {}
            localStorage.removeItem('tp_auth_user');
            localStorage.removeItem('tp_auth_time');
            window.location.href = window.location.pathname.replace(/\/$/, '') + '/login';
        });
    }
}

// ===== 弹窗控制 =====
function openModal(intel) {
    const detail = {
        id: intel.id,
        title: intel.title,
        summary: intel.full_text || intel.summary || '',
        category: intel.category,
        severity: intel.severity,
        source: intel.source || 'Twitter',
        sourceIcon: intel.source_icon || 'ri-twitter-x-line',
        time: formatTime(intel.crawl_time),
        tags: intel.tags || [],
        heat: intel.heat || 0,
        comments: intel.comments || 0,
        ioc: intel.ioc || [],
        link: intel.link || '#',
        userName: intel.user_name || '',
        userScreenName: intel.user_screen_name || '',
        userFollowers: intel.user_followers || 0,
        retweetCount: intel.retweet_count || 0,
        favoriteCount: intel.favorite_count || 0,
    };
    dom.modalTitle.textContent = intel.title;
    dom.modalBody.innerHTML = renderIntelDetail(detail);
    dom.modalSource.textContent = `来源: ${intel.source || 'Twitter'}`;
    dom.modalLink.href = intel.link || '#';
    dom.detailModal.classList.remove('hidden');
    requestAnimationFrame(() => {
        dom.modalPanel.classList.add('open');
    });
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    dom.modalPanel.classList.remove('open');
    setTimeout(() => {
        dom.detailModal.classList.add('hidden');
        document.body.style.overflow = '';
    }, 300);
}

// ===== 刷新逻辑 =====
async function refreshData() {
    if (state.isRefreshing) return;
    state.isRefreshing = true;

    dom.refreshIcon.classList.add('refreshing');
    renderSkeletons(dom.intelFeed, 3);

    state.currentPage = 1;
    state.newDataCount = 0;
    hideNewDataBanner();

    await renderAll();

    dom.refreshIcon.classList.remove('refreshing');
    state.isRefreshing = false;
}

// 🆕 仅刷新情报流（不重新加载侧边栏等）
async function refreshIntelOnly() {
    renderSkeletons(dom.intelFeed, 3);
    state.currentPage = 1;
    const result = await fetchIntel(buildIntelParams(1));
    state.intelItems = result.items;
    state.totalCount = result.total;
    renderIntelFeed();
}

function startAutoRefresh() {
    stopAutoRefresh();
    state.autoRefreshTimer = setInterval(async () => {
        // 检查是否有新数据
        const stats = await fetchStats(state.timeFilter);
        if (stats && stats.total > state.lastTotal) {
            state.newDataCount = stats.total - state.lastTotal;
            showNewDataBanner(state.newDataCount);
        }
    }, 30000); // 每30秒检查一次
}

function stopAutoRefresh() {
    if (state.autoRefreshTimer) {
        clearInterval(state.autoRefreshTimer);
        state.autoRefreshTimer = null;
    }
}

function showNewDataBanner(count) {
    dom.newDataText.textContent = `发现 ${count} 条新情报，点击刷新查看`;
    dom.newDataBanner.classList.add('show');
}

function hideNewDataBanner() {
    dom.newDataBanner.classList.remove('show');
}

// ===== 初始化 =====
async function init() {
    cacheDom();
    bindEvents();

    // 显示骨架屏
    renderSkeletons(dom.intelFeed, 4);

    // 加载真实数据
    await renderAll();

    // 显示当前登录用户名
    const user = localStorage.getItem('tp_auth_user');
    if (user && dom.currentUser) {
        dom.currentUser.textContent = user;
    }
}

document.addEventListener('DOMContentLoaded', init);
