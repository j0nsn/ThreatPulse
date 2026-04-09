/**
 * ThreatPulse 安全情报聚合平台 - 登录页脚本 v2
 * 安全加固版：支持 IP 锁定倒计时提示
 */

const BASE_PATH = "/Th";

// ============== 背景粒子效果 ==============
function createParticles() {
    const container = document.getElementById('particles');
    const colors = ['#06b6d4', '#3b82f6', '#10b981', '#ef4444', '#6366f1'];

    for (let i = 0; i < 25; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        const size = Math.random() * 6 + 2;
        const color = colors[Math.floor(Math.random() * colors.length)];
        particle.style.cssText = `
            width: ${size}px;
            height: ${size}px;
            background: ${color};
            left: ${Math.random() * 100}%;
            animation-duration: ${Math.random() * 15 + 10}s;
            animation-delay: ${Math.random() * 10}s;
        `;
        container.appendChild(particle);
    }
}

// ============== DOM元素 ==============
const loginForm = document.getElementById('loginForm');
const usernameInput = document.getElementById('username');
const passwordInput = document.getElementById('password');
const togglePwd = document.getElementById('togglePwd');
const pwdIcon = document.getElementById('pwdIcon');
const loginBtn = document.getElementById('loginBtn');
const loginIcon = document.getElementById('loginIcon');
const loginText = document.getElementById('loginText');
const errorMsg = document.getElementById('errorMsg');
const errorText = document.getElementById('errorText');

// ============== 锁定倒计时 ==============
let lockoutTimer = null;
let lockoutEndTime = null;

function startLockoutCountdown(seconds) {
    clearLockoutCountdown();
    lockoutEndTime = Date.now() + seconds * 1000;
    loginBtn.disabled = true;
    loginBtn.classList.add('opacity-60', 'cursor-not-allowed');
    usernameInput.disabled = true;
    passwordInput.disabled = true;

    lockoutTimer = setInterval(() => {
        const remaining = Math.max(0, Math.ceil((lockoutEndTime - Date.now()) / 1000));
        if (remaining <= 0) {
            clearLockoutCountdown();
            return;
        }
        const min = Math.floor(remaining / 60);
        const sec = remaining % 60;
        const timeStr = min > 0 ? `${min}分${sec}秒` : `${sec}秒`;
        loginIcon.className = 'ri-lock-line';
        loginText.textContent = `已锁定 ${timeStr}`;
        errorText.textContent = `登录尝试过于频繁，请 ${timeStr} 后再试`;
        errorMsg.classList.remove('hidden');
    }, 1000);
}

function clearLockoutCountdown() {
    if (lockoutTimer) {
        clearInterval(lockoutTimer);
        lockoutTimer = null;
    }
    lockoutEndTime = null;
    loginBtn.disabled = false;
    loginBtn.classList.remove('opacity-60', 'cursor-not-allowed');
    usernameInput.disabled = false;
    passwordInput.disabled = false;
    loginIcon.className = 'ri-login-box-line';
    loginText.textContent = '登 录';
    hideError();
}

// ============== 密码显示/隐藏切换 ==============
let pwdVisible = false;
togglePwd.addEventListener('click', () => {
    pwdVisible = !pwdVisible;
    passwordInput.type = pwdVisible ? 'text' : 'password';
    pwdIcon.className = pwdVisible ? 'ri-eye-line' : 'ri-eye-off-line';
});

// ============== 显示/隐藏错误信息 ==============
function showError(message) {
    errorText.textContent = message;
    errorMsg.classList.remove('hidden');
    const card = document.querySelector('.login-card');
    card.classList.add('shake');
    setTimeout(() => card.classList.remove('shake'), 500);
}

function hideError() {
    errorMsg.classList.add('hidden');
}

// ============== 设置按钮状态 ==============
function setLoading(loading) {
    if (lockoutEndTime) return; // 锁定中不改变状态
    loginBtn.disabled = loading;
    if (loading) {
        loginIcon.className = 'ri-loader-4-line spinner';
        loginText.textContent = '登录中...';
        loginBtn.classList.add('opacity-80', 'cursor-not-allowed');
    } else {
        loginIcon.className = 'ri-login-box-line';
        loginText.textContent = '登 录';
        loginBtn.classList.remove('opacity-80', 'cursor-not-allowed');
    }
}

// ============== 登录表单提交 ==============
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    // 如果处于锁定状态，阻止提交
    if (lockoutEndTime && Date.now() < lockoutEndTime) {
        return;
    }

    hideError();

    const username = usernameInput.value.trim();
    const password = passwordInput.value;

    if (!username) {
        showError('请输入用户名');
        usernameInput.focus();
        return;
    }
    if (!password) {
        showError('请输入密码');
        passwordInput.focus();
        return;
    }
    if (username.length > 50 || password.length > 100) {
        showError('输入内容超出长度限制');
        return;
    }

    setLoading(true);

    try {
        const res = await fetch(BASE_PATH + '/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ username, password })
        });

        const data = await res.json();

        if (res.ok && data.success) {
            // 登录成功 — Token 仅通过 HttpOnly Cookie 传递，前端无需处理
            localStorage.setItem('tp_auth_user', data.username);
            localStorage.setItem('tp_auth_time', new Date().toISOString());

            // 成功动画
            loginBtn.classList.remove('from-cyan-600', 'to-blue-600');
            loginBtn.classList.add('from-emerald-600', 'to-teal-600');
            loginIcon.className = 'ri-check-line';
            loginText.textContent = '登录成功';

            // 跳转到主页
            setTimeout(() => {
                window.location.href = BASE_PATH + '/';
            }, 600);
        } else if (res.status === 429 && data.locked) {
            // IP 被锁定，启动倒计时
            const retryAfter = data.retry_after || 900;
            startLockoutCountdown(retryAfter);
            passwordInput.value = '';
        } else {
            showError(data.message || '登录失败，请检查用户名和密码');
            setLoading(false);
            passwordInput.value = '';
            passwordInput.focus();
        }
    } catch (err) {
        console.error('[Login Error]', err);
        showError('网络连接失败，请检查网络后重试');
        setLoading(false);
    }
});

// ============== 检查是否已登录 ==============
async function checkAuth() {
    try {
        const res = await fetch(BASE_PATH + '/api/auth/check', { credentials: 'same-origin' });
        const data = await res.json();
        if (data.authenticated) {
            window.location.href = BASE_PATH + '/';
        }
    } catch (_) {
        // 未登录，继续显示登录页
    }
}

// ============== 键盘快捷键 ==============
document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && document.activeElement === passwordInput) {
        loginForm.dispatchEvent(new Event('submit'));
    }
});

// ============== 初始化 ==============
createParticles();
checkAuth();
usernameInput.focus();
