const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();
tg.setHeaderColor('#0a0e14');
tg.setBackgroundColor('#0a0e14');

const initData = tg.initData;
const BOT_USERNAME = "SlotsGameFast_bot";

const BETS = [10, 50, 100, 500, 1000, 10000, 20000, 30000, 50000, 100000];
const PAY_PACKS = [10, 30, 50, 100, 250, 500];
const WITHDRAW_PACKS = [15, 50, 100, 250, 500, 1000];

let profile = { balance: 0, stats: {}, referral: {} };
let minesState = null;
let rocketInterval = null;
let rocketCanvasCtx = null;
let rocketAnimationId = null;
let rocketPoints = [];
let rocketHistoryArr = [1.24, 3.5, 1.08, 8.2, 1.5, 2.1, 12.4, 1.02, 2.8, 1.7];
let rrState = null;
let diceBet = null;
let penaltiState = null;
let coinBet = null;
let coinHistory = [];
let lastGame = null;
let lastBet = 0;

/* ═══ UTILS ═══ */

function fmt(n) {
    return (n || 0).toLocaleString('ru-RU').replace(/,/g, '.');
}

function toast(text, type = '') {
    const el = document.getElementById('toast');
    if (!el) { console.error('Toast element not found'); return; }
    el.textContent = text;
    el.className = 'toast show ' + type;
    setTimeout(() => el.className = 'toast', 2500);
}

function haptic(type = 'light') {
    try {
        if (type === 'success') tg.HapticFeedback.notificationOccurred('success');
        else if (type === 'error') tg.HapticFeedback.notificationOccurred('error');
        else tg.HapticFeedback.impactOccurred('light');
    } catch (e) {}
}

async function api(url, body = {}) {
    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ initData, ...body }),
    });
    if (!res.ok) {
        let msg = 'Ошибка';
        try { msg = (await res.json()).detail; } catch (e) {}
        throw new Error(msg);
    }
    return res.json();
}

/* ═══ ЭКРАН РЕЗУЛЬТАТА ═══ */

function showResult({ icon, title, titleClass, amount, details, game, bet }) {
    const iconEl = document.getElementById('resultIcon');
    const titleEl = document.getElementById('resultTitle');
    const amountEl = document.getElementById('resultAmount');
    const detailsEl = document.getElementById('resultDetails');

    if (!iconEl || !titleEl || !amountEl || !detailsEl) {
        console.error('Result screen elements missing in HTML!');
        return;
    }

    iconEl.textContent = icon;
    titleEl.textContent = title;
    titleEl.className = 'result-title ' + (titleClass || '');

    if (amount) {
        amountEl.textContent = amount;
        amountEl.style.display = 'block';
    } else {
        amountEl.style.display = 'none';
    }
    detailsEl.innerHTML = details || '';
    lastGame = game;
    lastBet = bet;
    haptic(titleClass === 'lose' ? 'error' : 'success');
    showScreen('result');
}

function playAgain() {
    haptic();
    if (!lastGame) { showScreen('home'); return; }
    openGame(lastGame);
}

/* ═══ UI ═══ */

function showScreen(name) {
    const screen = document.getElementById('screen-' + name);
    if (!screen) { console.error('Screen not found: screen-' + name); return; }
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    screen.classList.add('active');
    haptic();

    if (name === 'top') loadTop();
    if (name === 'ach') loadAch();
    if (name === 'ref') loadRef();
    if (name === 'withdraw') loadWithdrawStatus();
    if (name === 'pay') renderPay();
    if (name === 'admin') switchAdminTab('stats');
}

function updateBalance(b) {
    profile.balance = b;
    ['headerBalance', 'profileBalance', 'gameBalance', 'withdrawBalance'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = fmt(b);
    });
}

/* ═══ ПРОФИЛЬ ═══ */

async function loadProfile() {
    try {
        const d = await api('/api/profile');
        profile = d;
        updateBalance(d.balance);
        const statGames = document.getElementById('statGames');
        const statWagered = document.getElementById('statWagered');
        const statWon = document.getElementById('statWon');
        if (statGames) statGames.textContent = fmt(d.stats?.games || 0);
        if (statWagered) statWagered.textContent = fmt(d.stats?.wagered || 0);
        if (statWon) statWon.textContent = fmt(d.stats?.won || 0);

        const disc = document.getElementById('discountInfo');
        if (disc) {
            disc.innerHTML = d.discount > 0 ? `🎁 <b>Скидка ${d.discount}%</b> на пополнение` : '';
        }
        const adminBtn = document.getElementById('adminBtn');
        if (adminBtn && d.is_admin) adminBtn.classList.remove('hidden');
    } catch (e) {
        console.error('Profile load error:', e);
        toast('Ошибка загрузки профиля: ' + e.message, 'error');
    }
}

/* ═══ ИГРЫ ═══ */

function openGame(game) {
    haptic();
    const content = document.getElementById('content-' + game);
    if (!content) { console.error('Game not found: ' + game); toast('Игра не найдена', 'error'); return; }
    document.querySelectorAll('.game-content').forEach(c => c.classList.add('hidden'));
    content.classList.remove('hidden');

    const titles = {
        slots: '🎰 Слоты', mines: '⛏ Gold Mine',
        rocket: '🚀 Ракетка', dice: '🎲 Кости', rr: '🔫 Русская рулетка',
        plinko: '🎯 Plinko', penalti: '⚽ Penalti', coin: '🪙 Монетка',
    };
    const titleEl = document.getElementById('gameTitle');
    if (titleEl) titleEl.textContent = titles[game] || 'Игра';

    showScreen('game');

    minesState = null; rrState = null; diceBet = null; penaltiState = null; coinBet = null;

    if (game === 'slots') {
        document.getElementById('slotsBets').classList.remove('hidden');
        [0,1,2].forEach(i => document.getElementById('slot'+i).textContent = '❓');
        document.getElementById('slotsResult').textContent = 'Выберите ставку';
        document.getElementById('slotsResult').className = 'game-result';
        renderBets('slotsBets', spinSlots);
    }
    if (game === 'mines') {
        document.getElementById('minesBets').classList.remove('hidden');
        document.getElementById('minesInfo').classList.add('hidden');
        document.getElementById('minesGrid').classList.add('hidden');
        document.getElementById('minesCashout').classList.add('hidden');
        renderBets('minesBets', minesStart);
    }
    if (game === 'rocket') {
        if (rocketInterval) { clearInterval(rocketInterval); rocketInterval = null; }
        stopRocketCanvas();
        renderRocketHistory();
        document.getElementById('rocketBets').classList.remove('hidden');
        document.getElementById('rocketDisplay').classList.add('hidden');
        renderBets('rocketBets', rocketStart);
    }
    if (game === 'dice') {
        document.getElementById('diceBets').classList.remove('hidden');
        document.getElementById('diceDisplay').classList.add('hidden');
        renderBets('diceBets', diceStart);
    }
    if (game === 'rr') {
        document.getElementById('rrBets').classList.remove('hidden');
        document.getElementById('rrDisplay').classList.add('hidden');
        renderBets('rrBets', rrStart);
    }
    if (game === 'plinko') {
        document.getElementById('plinkoBets').classList.remove('hidden');
        initPlinko();
    }
    if (game === 'penalti') {
        document.getElementById('penaltiBets').classList.remove('hidden');
        document.getElementById('penaltiDisplay').classList.add('hidden');
        initPenalti();
    }
    if (game === 'coin') {
        document.getElementById('coinBets').classList.remove('hidden');
        document.getElementById('coinDisplay').classList.add('hidden');
        initCoin();
    }
}

function closeGame() {
    haptic();
    if (rocketInterval) clearInterval(rocketInterval);
    stopRocketCanvas();
    showScreen('home');
}

function renderBets(containerId, onPick) {
    const el = document.getElementById(containerId);
    if (!el) { console.error('Bets container not found: ' + containerId); return; }
    el.innerHTML = '';
    BETS.forEach(b => {
        const btn = document.createElement('button');
        btn.className = 'bet-btn';
        btn.textContent = fmt(b) + ' 🪙';
        if (b > profile.balance) btn.disabled = true;
        btn.onclick = () => onPick(b);
        el.appendChild(btn);
    });
    const all = document.createElement('button');
    all.className = 'bet-btn allin';
    all.textContent = '💯 Весь баланс';
    if (profile.balance <= 0) all.disabled = true;
    all.onclick = () => onPick(profile.balance);
    el.appendChild(all);
}

/* ═══ СЛОТЫ ═══ */

async function spinSlots(bet) {
    haptic();
    document.querySelectorAll('#slotsBets button').forEach(b => b.disabled = true);
    const reels = [0,1,2].map(i => document.getElementById('slot'+i));
    reels.forEach(el => el.classList.add('spinning'));
    const res = document.getElementById('slotsResult');
    res.textContent = 'Крутим...';
    res.className = 'game-result';

    const fake = ['🍒','🍋','🍊','💎','🤑','7️⃣'];
    const int = setInterval(() => {
        reels.forEach(el => el.textContent = fake[Math.floor(Math.random()*6)]);
    }, 80);

    try {
        const d = await api('/api/slots/spin', { bet });
        await new Promise(r => setTimeout(r, 900));
        clearInterval(int);
        reels.forEach(el => el.classList.remove('spinning'));
        d.result.forEach((s, i) => reels[i].textContent = s);
        updateBalance(d.balance);
        loadProfile();

        setTimeout(() => {
            if (d.jackpot) {
                showResult({ icon:'💥', title:'ДЖЕКПОТ!', titleClass:'jackpot',
                    amount:`+${fmt(d.win)} 🪙`, details:`Ставка: ${fmt(bet)} 🪙<br>Множитель: ×10`,
                    game:'slots', bet });
            } else if (d.win > 0) {
                showResult({ icon:'🎉', title:'Выигрыш!', titleClass:'win',
                    amount:`+${fmt(d.win)} 🪙`, details:`Ставка: ${fmt(bet)} 🪙<br>Баланс: ${fmt(d.balance)} 🪙`,
                    game:'slots', bet });
            } else {
                showResult({ icon:'😢', title:'Проигрыш', titleClass:'lose',
                    amount:`−${fmt(bet)} 🪙`, details:`Баланс: ${fmt(d.balance)} 🪙`,
                    game:'slots', bet });
            }
        }, 300);
    } catch (e) {
        clearInterval(int);
        reels.forEach(el => el.classList.remove('spinning'));
        toast(e.message, 'error');
        renderBets('slotsBets', spinSlots);
    }
}

/* ═══ GOLD MINE ═══ */

async function minesStart(bet) {
    haptic();
    try {
        const d = await api('/api/mines/start', { bet });
        minesState = { field: 5, bet, opened: new Set() };
        lastBet = bet;
        document.getElementById('minesBets').classList.add('hidden');
        document.getElementById('minesInfo').classList.remove('hidden');
        document.getElementById('minesGrid').classList.remove('hidden');
        updateBalance(d.balance);
        renderMinesGrid(5);
        loadProfile();
    } catch (e) { toast(e.message, 'error'); }
}

function renderMinesGrid(field) {
    const grid = document.getElementById('minesGrid');
    grid.innerHTML = '';
    grid.style.gridTemplateColumns = `repeat(${field}, 1fr)`;
    for (let i = 0; i < field * field; i++) {
        const cell = document.createElement('button');
        cell.className = 'mine-cell';
        cell.textContent = '🌑';
        cell.onclick = () => minesOpen(i, cell);
        grid.appendChild(cell);
    }
    document.getElementById('minesOpened').textContent = 0;
    document.getElementById('minesPrize').textContent = 0;
    document.getElementById('minesCashout').classList.add('hidden');
}

async function minesOpen(idx, cell) {
    haptic();
    if (!minesState || cell.classList.contains('opened')) return;
    cell.disabled = true;
    try {
        const d = await api('/api/mines/open', { idx });
        updateBalance(d.balance);

        if (d.hit_mine) {
            cell.textContent = '💥';
            cell.classList.add('mine');
            minesState = null;
            loadProfile();
            setTimeout(() => {
                showResult({ icon:'💥', title:'ВЗРЫВ!', titleClass:'lose',
                    amount:`−${fmt(d.bet || lastBet)} 🪙`, details:'Вы наткнулись на бомбу',
                    game:'mines', bet: d.bet || lastBet });
            }, 800);
            return;
        }
        if (d.won) {
            cell.textContent = '💎';
            cell.classList.add('opened');
            minesState = null;
            loadProfile();
            setTimeout(() => {
                showResult({ icon:'🏆', title:'Всё золото собрано!', titleClass:'win',
                    amount:`+${fmt(d.win)} 🪙`, details:'Все безопасные клетки открыты<br>Множитель: ×2.5',
                    game:'mines', bet: lastBet });
            }, 800);
            return;
        }
        cell.textContent = '💰';
        cell.classList.add('opened');
        minesState.opened.add(idx);
        document.getElementById('minesOpened').textContent = d.opened.length;
        document.getElementById('minesPrize').textContent = fmt(d.current_prize);
        document.getElementById('minesCashout').classList.remove('hidden');
    } catch (e) { toast(e.message, 'error'); }
}

async function minesCashout() {
    haptic();
    try {
        const d = await api('/api/mines/cashout');
        updateBalance(d.balance);
        minesState = null;
        loadProfile();
        setTimeout(() => {
            showResult({ icon:'💎', title:'Продано!', titleClass:'win',
                amount:`+${fmt(d.prize)} 🪙`, details:'Вы продали золото',
                game:'mines', bet: d.bet || lastBet });
        }, 500);
    } catch (e) { toast(e.message, 'error'); }
}

/* ═══ РАКЕТКА ═══ */

function renderRocketHistory() {
    const el = document.getElementById('rocketHistory');
    if (!el) return;
    el.innerHTML = '';
    rocketHistoryArr.slice(0, 15).forEach(m => {
        const div = document.createElement('div');
        div.className = 'rocket-hist-item ' + (m >= 10 ? 'orange' : m >= 2 ? 'purple' : 'blue');
        div.textContent = '×' + m.toFixed(2);
        el.appendChild(div);
    });
}

async function rocketStart(bet) {
    haptic();
    try {
        const d = await api('/api/rocket/start', { bet });
        updateBalance(d.balance);
        lastBet = bet;
        document.getElementById('rocketBets').classList.add('hidden');
        document.getElementById('rocketDisplay').classList.remove('hidden');
        document.getElementById('rocketDisplay').classList.remove('crashed');
        document.getElementById('rocketMult').classList.remove('crashed');

        const emoji = document.getElementById('rocketEmoji');
        const flame = document.getElementById('rocketFlame');
        emoji.style.left = '30px';
        emoji.style.bottom = '30px';
        emoji.style.opacity = '1';
        flame.style.left = '30px';
        flame.style.bottom = '30px';
        flame.style.opacity = '0.95';

        startRocketCanvas();
        pollRocket();
        loadProfile();
    } catch (e) { toast(e.message, 'error'); }
}

function startRocketCanvas() {
    const canvas = document.getElementById('rocketCanvas');
    const field = document.getElementById('rocketField');
    if (!canvas || !field) return;
    canvas.width = field.clientWidth;
    canvas.height = field.clientHeight;
    rocketCanvasCtx = canvas.getContext('2d');
    rocketPoints = [{ x: 30, y: canvas.height - 30 }];

    function draw() {
        if (!rocketCanvasCtx) return;
        const ctx = rocketCanvasCtx;
        const w = canvas.width, h = canvas.height;
        ctx.clearRect(0, 0, w, h);
        if (rocketPoints.length > 1) {
            ctx.beginPath();
            ctx.moveTo(rocketPoints[0].x, rocketPoints[0].y);
            for (let i = 1; i < rocketPoints.length; i++) ctx.lineTo(rocketPoints[i].x, rocketPoints[i].y);
            ctx.strokeStyle = 'rgba(255, 193, 7, 0.15)';
            ctx.lineWidth = 24; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
            ctx.stroke();

            ctx.beginPath();
            ctx.moveTo(rocketPoints[0].x, rocketPoints[0].y);
            for (let i = 1; i < rocketPoints.length; i++) ctx.lineTo(rocketPoints[i].x, rocketPoints[i].y);
            ctx.strokeStyle = '#ffc107';
            ctx.lineWidth = 4; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
            ctx.shadowColor = '#ffc107'; ctx.shadowBlur = 20;
            ctx.stroke();
            ctx.shadowBlur = 0;
        }
        if (rocketPoints.length > 0) {
            const last = rocketPoints[rocketPoints.length - 1];
            ctx.beginPath();
            ctx.arc(last.x, last.y, 8, 0, Math.PI * 2);
            ctx.fillStyle = '#ffc107';
            ctx.shadowColor = '#ffc107'; ctx.shadowBlur = 30;
            ctx.fill();
            ctx.shadowBlur = 0;
        }
        rocketAnimationId = requestAnimationFrame(draw);
    }
    draw();
}

function stopRocketCanvas() {
    if (rocketAnimationId) { cancelAnimationFrame(rocketAnimationId); rocketAnimationId = null; }
    rocketCanvasCtx = null;
}

function pollRocket() {
    if (rocketInterval) clearInterval(rocketInterval);
    rocketInterval = setInterval(async () => {
        try {
            const d = await api('/api/rocket/status');
            const mult = document.getElementById('rocketMult');
            const prize = document.getElementById('rocketPrize');

            if (d.crashed) {
                clearInterval(rocketInterval);
                rocketInterval = null;
                document.getElementById('rocketDisplay').classList.add('crashed');
                mult.textContent = `×${d.mult.toFixed(2)}`;
                mult.classList.add('crashed');
                prize.textContent = '💥 Взрыв!';

                if (rocketCanvasCtx) {
                    const canvas = document.getElementById('rocketCanvas');
                    const ctx = rocketCanvasCtx;
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    if (rocketPoints.length > 1) {
                        ctx.beginPath();
                        ctx.moveTo(rocketPoints[0].x, rocketPoints[0].y);
                        for (let i = 1; i < rocketPoints.length; i++) ctx.lineTo(rocketPoints[i].x, rocketPoints[i].y);
                        ctx.strokeStyle = 'rgba(255, 71, 87, 0.25)';
                        ctx.lineWidth = 28; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
                        ctx.stroke();
                        ctx.beginPath();
                        ctx.moveTo(rocketPoints[0].x, rocketPoints[0].y);
                        for (let i = 1; i < rocketPoints.length; i++) ctx.lineTo(rocketPoints[i].x, rocketPoints[i].y);
                        ctx.strokeStyle = '#ff4757';
                        ctx.lineWidth = 5; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
                        ctx.shadow/* ═══ РАКЕТКА ═══ */

function renderRocketHistory() {
    const el = document.getElementById('rocketHistory');
    if (!el) return;
    el.innerHTML = '';
    rocketHistoryArr.slice(0, 15).forEach(m => {
        const div = document.createElement('div');
        div.className = 'rocket-hist-item ' + (m >= 10 ? 'orange' : m >= 2 ? 'purple' : 'blue');
        div.textContent = '×' + m.toFixed(2);
        el.appendChild(div);
    });
}

async function rocketStart(bet) {
    haptic();
    try {
        const d = await api('/api/rocket/start', { bet });
        updateBalance(d.balance);
        lastBet = bet;
        document.getElementById('rocketBets').classList.add('hidden');
        document.getElementById('rocketDisplay').classList.remove('hidden');
        document.getElementById('rocketDisplay').classList.remove('crashed');
        document.getElementById('rocketMult').classList.remove('crashed');

        const emoji = document.getElementById('rocketEmoji');
        const flame = document.getElementById('rocketFlame');
        emoji.style.left = '30px';
        emoji.style.bottom = '30px';
        emoji.style.opacity = '1';
        flame.style.left = '30px';
        flame.style.bottom = '30px';
        flame.style.opacity = '0.95';

        startRocketCanvas();
        pollRocket();
        loadProfile();
    } catch (e) { toast(e.message, 'error'); }
}

function startRocketCanvas() {
    const canvas = document.getElementById('rocketCanvas');
    const field = document.getElementById('rocketField');
    if (!canvas || !field) return;
    canvas.width = field.clientWidth;
    canvas.height = field.clientHeight;
    rocketCanvasCtx = canvas.getContext('2d');
    rocketPoints = [{ x: 30, y: canvas.height - 30 }];

    function draw() {
        if (!rocketCanvasCtx) return;
        const ctx = rocketCanvasCtx;
        const w = canvas.width, h = canvas.height;
        ctx.clearRect(0, 0, w, h);
        if (rocketPoints.length > 1) {
            ctx.beginPath();
            ctx.moveTo(rocketPoints[0].x, rocketPoints[0].y);
            for (let i = 1; i < rocketPoints.length; i++) ctx.lineTo(rocketPoints[i].x, rocketPoints[i].y);
            ctx.strokeStyle = 'rgba(255, 193, 7, 0.15)';
            ctx.lineWidth = 24; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
            ctx.stroke();

            ctx.beginPath();
            ctx.moveTo(rocketPoints[0].x, rocketPoints[0].y);
            for (let i = 1; i < rocketPoints.length; i++) ctx.lineTo(rocketPoints[i].x, rocketPoints[i].y);
            ctx.strokeStyle = '#ffc107';
            ctx.lineWidth = 4; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
            ctx.shadowColor = '#ffc107'; ctx.shadowBlur = 20;
            ctx.stroke();
            ctx.shadowBlur = 0;
        }
        if (rocketPoints.length > 0) {
            const last = rocketPoints[rocketPoints.length - 1];
            ctx.beginPath();
            ctx.arc(last.x, last.y, 8, 0, Math.PI * 2);
            ctx.fillStyle = '#ffc107';
            ctx.shadowColor = '#ffc107'; ctx.shadowBlur = 30;
            ctx.fill();
            ctx.shadowBlur = 0;
        }
        rocketAnimationId = requestAnimationFrame(draw);
    }
    draw();
}

function stopRocketCanvas() {
    if (rocketAnimationId) { cancelAnimationFrame(rocketAnimationId); rocketAnimationId = null; }
    rocketCanvasCtx = null;
}

function pollRocket() {
    if (rocketInterval) clearInterval(rocketInterval);
    rocketInterval = setInterval(async () => {
        try {
            const d = await api('/api/rocket/status');
            const mult = document.getElementById('rocketMult');
            const prize = document.getElementById('rocketPrize');

            if (d.crashed) {
                clearInterval(rocketInterval);
                rocketInterval = null;
                document.getElementById('rocketDisplay').classList.add('crashed');
                mult.textContent = `×${d.mult.toFixed(2)}`;
                mult.classList.add('crashed');
                prize.textContent = '💥 Взрыв!';

                if (rocketCanvasCtx) {
                    const canvas = document.getElementById('rocketCanvas');
                    const ctx = rocketCanvasCtx;
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    if (rocketPoints.length > 1) {
                        ctx.beginPath();
                        ctx.moveTo(rocketPoints[0].x, rocketPoints[0].y);
                        for (let i = 1; i < rocketPoints.length; i++) ctx.lineTo(rocketPoints[i].x, rocketPoints[i].y);
                        ctx.strokeStyle = 'rgba(255, 71, 87, 0.25)';
                        ctx.lineWidth = 28; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
                        ctx.stroke();
                        ctx.beginPath();
                        ctx.moveTo(rocketPoints[0].x, rocketPoints[0].y);
                        for (let i = 1; i < rocketPoints.length; i++) ctx.lineTo(rocketPoints[i].x, rocketPoints[i].y);
                        ctx.strokeStyle = '#ff4757';
                        ctx.lineWidth = 5; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
                        ctx.shadowColor = '#ff4757'; ctx.shadowBlur = 30;
                        ctx.stroke();
                        ctx.shadowBlur = 0;
                    }
                }
                document.getElementById('rocketEmoji').style.opacity = '0';
                document.getElementById('rocketFlame').style.opacity = '0';
                loadProfile();
                setTimeout(() => {
                    showResult({ icon:'💥', title:'ВЗРЫВ!', titleClass:'lose',
                        amount:`−${fmt(lastBet)} 🪙`, details:`Ракета взорвалась на ×${d.mult.toFixed(2)}`,
                        game:'rocket', bet: lastBet });
                }, 1000);
                return;
            }

            mult.textContent = `×${d.mult.toFixed(2)}`;
            prize.textContent = fmt(Math.floor(lastBet * d.mult)) + ' 🪙';

            const emoji = document.getElementById('rocketEmoji');
            const flame = document.getElementById('rocketFlame');
            const canvas = document.getElementById('rocketCanvas');
            const progress = Math.min(d.mult / 10, 1);
            const x = 30 + progress * (canvas.width - 60);
            const y = (canvas.height - 30) - progress * (canvas.height - 60);
            emoji.style.left = x + 'px';
            emoji.style.bottom = (canvas.height - y) + 'px';
            flame.style.left = x + 'px';
            flame.style.bottom = (canvas.height - y) + 'px';
            rocketPoints.push({ x, y });
        } catch (e) { console.error(e); }
    }, 300);
}

async function rocketCashout() {
    haptic();
    if (!rocketInterval) return;
    clearInterval(rocketInterval);
    rocketInterval = null;
    try {
        const d = await api('/api/rocket/cashout');
        updateBalance(d.balance);
        stopRocketCanvas();
        loadProfile();
        showResult({ icon:'💰', title:'Забрано!', titleClass:'win',
            amount:`+${fmt(d.win)} 🪙`, details:`Множитель: ×${d.mult.toFixed(2)}`,
            game:'rocket', bet: lastBet });
    } catch (e) { toast(e.message, 'error'); }
}

/* ═══ ЗАГЛУШКИ (нужны, чтобы не было ошибок, если функций нет) ═══ */

function diceStart() { toast('Кости: в разработке'); }
function rrStart() { toast('Рулетка: в разработке'); }
function initPlinko() { toast('Plinko: в разработке'); }
function initPenalti() { toast('Penalti: в разработке'); }
function initCoin() { toast('Монетка: в разработке'); }
function loadTop() { /* загрузка топа */ }
function loadAch() { /* загрузка достижений */ }
function loadRef() { /* загрузка рефералов */ }
function loadWithdrawStatus() { /* статус вывода */ }
function renderPay() { /* отрисовка пополнения */ }
function switchAdminTab(tab) { /* переключение админ-таба */ }
function claimDaily() { toast('Бонус получен!'); }
function activatePromo() { toast('Промокод активирован!'); }
function copyRef() { toast('Ссылка скопирована'); }

/* ═══ ЗАПУСК ═══ */
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadProfile);
} else {
    loadProfile();
}
