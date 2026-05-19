/**
 * DOUMITT Precision Ag - Frontend Logic
 * This script handles authentication, dashboard data fetching, 
 * language translation, and RTL support.
 */

// 🌟 توجيه الرابط للسيرفر المحلي تبعك
const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? 'http://localhost:8000' : '';

// --- DOM References ---
const loginForm = document.getElementById('login-form');
const logoutBtn = document.getElementById('logout-btn');
const authSection = document.getElementById('auth-section');
const dashSection = document.getElementById('dashboard-section');
const loginBtn = document.getElementById('login-btn');
const usernameInput = document.getElementById('username');
const passwordInput = document.getElementById('password');

// Lang Toggles
const langToggleAuth = document.getElementById('lang-toggle-auth');
const langToggleDash = document.getElementById('lang-toggle-dash');

// Metrics
const revenueEl = document.getElementById('metric-revenue');
const expensesEl = document.getElementById('metric-expenses');
const profitEl = document.getElementById('metric-profit');

// Invoice Table
const invoiceTableBody = document.getElementById('invoice-table-body');

// --- Translations ---
const translations = {
    en: {
        dir: 'ltr',
        toggleLabel: 'العربية',
        portalDesc: 'Precision Ag Portal',
        username: 'Username',
        password: 'Password',
        signIn: 'Sign In',
        invalidAuth: 'Invalid username or password',
        navAg: 'Precision Ag',
        navDash: 'Dashboard',
        navInv: 'Invoices',
        navExp: 'Expenses',
        navRep: 'Crop Reports',
        navSet: 'Settings',
        navOut: 'Log Out',
        role: 'Senior Agronomist',
        searchPlaceholder: 'Search data, reports, or invoices...',
        btnAddInv: 'Add New Invoice',
        revTitle: 'Total Revenue',
        expTitle: 'Total Expenses',
        profTitle: 'Net Profit',
        unit: 'USD',
        chartTitle: 'Monthly Crop Sales',
        chartDesc: 'Performance analysis across primary produce categories',
        streamStatus: 'Live Data Stream Active',
        tableTitle: 'Recent Invoices',
        viewAll: 'View All',
        thDate: 'Date',
        thCrop: 'Crop Name',
        thWeight: 'Net Weight',
        thPrice: 'Total Price',
        thStatus: 'Status',
        footerSensors: 'Active Sensors',
        footerMoisture: 'Avg. Moisture',
        footerTemp: 'Field Temp',
        unitsOnline: 'Units Online'
    },
    ar: {
        dir: 'rtl',
        toggleLabel: 'English',
        portalDesc: 'بوابة الزراعة الدقيقة',
        username: 'اسم المستخدم',
        password: 'كلمة المرور',
        signIn: 'تسجيل الدخول',
        invalidAuth: 'اسم مستخدم أو كلمة مرور غير صحيحة',
        navAg: 'الزراعة الدقيقة',
        navDash: 'لوحة التحكم',
        navInv: 'الفواتير',
        navExp: 'المصاريف',
        navRep: 'تقارير المحاصيل',
        navSet: 'الإعدادات',
        navOut: 'تسجيل الخروج',
        role: 'خبير زراعي أول',
        searchPlaceholder: 'ابحث في البيانات، التقارير أو الفواتير...',
        btnAddInv: 'إضافة فاتورة جديدة',
        revTitle: 'إجمالي الإيرادات',
        expTitle: 'إجمالي المصاريف',
        profTitle: 'صافي الربح',
        unit: 'دولار',
        chartTitle: 'مبيعات المحاصيل الشهرية',
        chartDesc: 'تحليل الأداء عبر فئات المنتجات الأساسية',
        streamStatus: 'بث البيانات المباشر نشط',
        tableTitle: 'الفواتير الأخيرة',
        viewAll: 'عرض الكل',
        thDate: 'التاريخ',
        thCrop: 'اسم المحصول',
        thWeight: 'الوزن الصافي',
        thPrice: 'السعر الإجمالي',
        thStatus: 'الحالة',
        footerSensors: 'المستشعرات النشطة',
        footerMoisture: 'متوسط الرطوبة',
        footerTemp: 'درجة حرارة الحقل',
        unitsOnline: 'وحدة متصلة'
    }
};

let currentLang = localStorage.getItem('agro_lang') || 'en';

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    applyLanguage(currentLang);
    checkAuth();
});

function checkAuth() {
    const token = localStorage.getItem('agro_token');
    if (token) {
        showDashboard();
        fetchDashboardData();
    } else {
        showLogin();
    }
}

function showLogin() {
    if (authSection) authSection.classList.remove('hidden');
    if (dashSection) dashSection.classList.add('hidden');
}

function showDashboard() {
    if (authSection) authSection.classList.add('hidden');
    if (dashSection) dashSection.classList.remove('hidden');
}

// --- Language Logic ---
function applyLanguage(lang) {
    currentLang = lang;
    localStorage.setItem('agro_lang', lang);
    const t = translations[lang];

    document.documentElement.dir = t.dir;
    document.documentElement.lang = lang;

    updateText('toggle-label-auth', t.toggleLabel);
    updateText('toggle-label-dash', t.toggleLabel);
    updateText('portal-desc', t.portalDesc);
    updateText('label-username', t.username);
    updateText('label-password', t.password);
    updateText('login-btn', t.signIn);
    updateText('login-error', t.invalidAuth);
    updateText('nav-ag', t.navAg);
    updateText('nav-dash', t.navDash);
    updateText('nav-inv', t.navInv);
    updateText('nav-exp', t.navExp);
    updateText('nav-rep', t.navRep);
    updateText('nav-set', t.navSet);
    updateText('nav-out', t.navOut);
    updateText('user-role', t.role);

    const searchInput = document.getElementById('search-input');
    if (searchInput) searchInput.placeholder = t.searchPlaceholder;
    updateText('btn-add-inv', t.btnAddInv);

    updateText('metric-title-rev', t.revTitle);
    updateText('metric-title-exp', t.expTitle);
    updateText('metric-title-prof', t.profTitle);
    updateText('metric-unit-rev', t.unit);
    updateText('metric-unit-exp', t.unit);
    updateText('metric-unit-prof', t.unit);

    updateText('chart-title', t.chartTitle);
    updateText('chart-desc', t.chartDesc);
    updateText('stream-status', t.streamStatus);
    updateText('table-title', t.tableTitle);
    updateText('table-viewall', t.viewAll);
    updateText('th-date', t.thDate);
    updateText('th-crop', t.thCrop);
    updateText('th-weight', t.thWeight);
    updateText('th-price', t.thPrice);
    updateText('th-status', t.thStatus);

    updateText('metric-footer-sensors', t.footerSensors);
    updateText('metric-footer-moisture', t.footerMoisture);
    updateText('metric-footer-temp', t.footerTemp);

    if (!dashSection.classList.contains('hidden')) {
        fetchDashboardData();
    }
}

function updateText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function toggleLanguage() {
    const nextLang = currentLang === 'en' ? 'ar' : 'en';
    applyLanguage(nextLang);
}

function updateLoginButtonColor() {
    const userVal = usernameInput.value.trim();
    const passVal = passwordInput.value.trim();
    if (userVal && passVal) {
        loginBtn.style.backgroundColor = '#74bd9f';
        loginBtn.style.color = '#003824';
    } else {
        loginBtn.style.backgroundColor = '';
        loginBtn.style.color = '';
    }
}

// --- API Calls ---

async function handleLogin(event) {
    event.preventDefault();
    const username = usernameInput.value;
    const password = passwordInput.value;
    const errorEl = document.getElementById('login-error');

    // 🌟 التعديل الأول: تجهيز البيانات بصيغة Form Data متل ما بيطلبها FastAPI
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    try {
        const response = await fetch(`${API_BASE_URL}/api/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData
        });

        if (!response.ok) throw new Error(translations[currentLang].invalidAuth);

        const data = await response.json();
        // 🌟 التعديل الثاني: حفظ التوكن بالاسم الصحيح اللي بيرجعه الباك إند تبعنا
        localStorage.setItem('agro_token', data.access_token);

        showDashboard();
        fetchDashboardData();
    } catch (err) {
        if (errorEl) {
            errorEl.textContent = err.message;
            errorEl.classList.remove('hidden');
        }
    }
}

async function fetchSummary() {
    const token = localStorage.getItem('agro_token');
    try {
        const response = await fetch(`${API_BASE_URL}/api/summary`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error('Failed to fetch summary');
        const data = await response.json();
        updateSummaryUI(data);
    } catch (err) {
        console.error(err);
        if (err.message.includes('401')) handleLogout();
    }
}

function fetchDashboardData() {
    fetchSummary();
}

// --- UI Updates ---
function updateSummaryUI(data) {
    // 🌟 التعديل الثالث: استخدام الأسماء الصحيحة تبع الباك إند
    if (revenueEl) revenueEl.textContent = `$${(data.total_income || 0).toLocaleString()}`;
    if (expensesEl) expensesEl.textContent = `$${(data.total_expenses || 0).toLocaleString()}`;
    if (profitEl) profitEl.textContent = `$${(data.net_profit || 0).toLocaleString()}`;
}

function handleLogout() {
    localStorage.removeItem('agro_token');
    showLogin();
}

// Event Listeners
if (loginForm) loginForm.addEventListener('submit', handleLogin);
if (logoutBtn) logoutBtn.addEventListener('click', handleLogout);
if (langToggleAuth) langToggleAuth.addEventListener('click', toggleLanguage);
if (langToggleDash) langToggleDash.addEventListener('click', toggleLanguage);

if (usernameInput) usernameInput.addEventListener('input', updateLoginButtonColor);
if (passwordInput) passwordInput.addEventListener('input', updateLoginButtonColor);