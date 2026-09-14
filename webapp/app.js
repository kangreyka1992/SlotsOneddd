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
let withdrawAllowed = false;
let withdrawDays = 0;
let plinkoRisk = 'low';

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
    document.getElementById('resultIcon').textContent = icon;
    const titleEl = document.getElementById('resultTitle');
    titleEl.textContent = title;
    titleEl.className = 'result-title ' + (titleClass || '');

    const amountEl = document.getElementById('resultAmount');
    if (amount) {
        amountEl.textContent = amount;
        amountEl.style.display = 'block';
    } else {
        amountEl.style.display = 'none';
    }

    document.getElementById('resultDetails').innerHTML = details || '';
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

        const sg = document.getElementById('statGames');
        const sw = document.getElementById('statWagered');
        const so = document.getElementById('statWon');
        if (sg) sg.textContent = fmt(d.stats?.games || 0);
        if (sw) sw.textContent = fmt(d.stats?.wagered || 0);
        if (so) so.textContent = fmt(d.stats?.won || 0);

        const disc = document.getElementById('discountInfo');
        if (disc) disc.innerHTML = d.discount > 0 ? `🎁 <b>Скидка ${d.discount}%</b> на пополнение` : '';

        const adminBtn = document.getElementById('adminBtn');
        if (adminBtn && d.is_admin) adminBtn.classList.remove('hidden');
    } catch (e) {
        console.error('Profile load error:', e);
    }
}

/* ═══ ИГРЫ ═══ */

function openGame(game) {
    haptic();
    const content = document.getElementById('content-' + game);
    if (!content) { console.error('Game not found: ' + game); return; }
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
        [0, 1, 2].forEach(i => document.getElementById('slot' + i).textContent = '❓');
        const sr = document.getElementById('slotsResult');
        sr.textContent = 'Выберите ставку';
        sr.className = 'game-result';
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
        document.getElementById('rocketDisplay').classList.remove('crashed');
        document.getElementById('rocketMult').classList.remove('crashed');
        renderBets('rocketBets', rocketStart);
    }
    if (game === 'dice') {
        document.getElementById('diceBets').classList.remove('hidden');
        document.getElementById('diceDisplay').classList.add('hidden');
        document.getElementById('diceChoices').classList.remove('disabled');
        renderBets('diceBets', diceStart);
    }
    if (game === 'rr') {
        document.getElementById('rrBets').classList.remove('hidden');
        document.getElementById('rrDisplay').classList.add('hidden');
        renderBets('rrBets', rrStart);
    }
    if (game === 'plinko') {
        document.getElementById('plinkoBets').classList.remove('hidden');
        document.getElementById('plinkoBall').style.display = 'none';
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
    const reels = [0, 1, 2].map(i => document.getElementById('slot' + i));
    reels.forEach(el => el.classList.add('spinning'));
    const res = document.getElementById('slotsResult');
    res.textContent = 'Крутим...';
    res.className = 'game-result';

    const fake = ['🍒', '🍋', '🍊', '💎', '🤑', '7️⃣'];
    const int = setInterval(() => {
        reels.forEach(el => el.textContent = fake[Math.floor(Math.random() * 6)]);
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
                showResult({ icon: '💥', title: 'ДЖЕКПОТ!', titleClass: 'jackpot',
                    amount: `+${fmt(d.win)} 🪙`, details: `Ставка: ${fmt(bet)} 🪙<br>Множитель: ×10`,
                    game: 'slots', bet });
            } else if (d.win > 0) {
                showResult({ icon: '🎉', title: 'Выигрыш!', titleClass: 'win',
                    amount: `+${fmt(d.win)} 🪙`, details: `Ставка: ${fmt(bet)} 🪙<br>Баланс: ${fmt(d.balance)} 🪙`,
                    game: 'slots', bet });
            } else {
                showResult({ icon: '😢', title: 'Проигрыш', titleClass: 'lose',
                    amount: `−${fmt(bet)} 🪙`, details: `Баланс: ${fmt(d.balance)} 🪙`,
                    game: 'slots', bet });
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
                showResult({ icon: '💥', title: 'ВЗРЫВ!', titleClass: 'lose',
                    amount: `−${fmt(d.bet || lastBet)} 🪙`, details: 'Вы наткнулись на бомбу',
                    game: 'mines', bet: d.bet || lastBet });
            }, 800);
            return;
        }
        if (d.won) {
            cell.textContent = '💎';
            cell.classList.add('opened');
            minesState = null;
            loadProfile();
            setTimeout(() => {
                showResult({ icon: '🏆', title: 'Всё золото собрано!', titleClass: 'win',
                    amount: `+${fmt(d.win)} 🪙`, details: 'Все безопасные клетки открыты<br>Множитель: ×2.5',
                    game: 'mines', bet: lastBet });
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
            showResult({ icon: '💎', title: 'Продано!', titleClass: 'win',
                amount: `+${fmt(d.prize)} 🪙`, details: 'Вы продали золото',
                game: 'mines', bet: d.bet || lastBet });
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
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        if (rocketPoints.length > 1) {
            ctx.beginPath();
            ctx.moveTo(rocketPoints[0].x, rocketPoints[0].y);
            for (let i = 1; i < rocketPoints.length; i++) {
                ctx.lineTo(rocketPoints[i].x, rocketPoints[i].y);
            }
            ctx.strokeStyle = 'rgba(255, 193, 7, 0.15)';
            ctx.lineWidth = 24;
            ctx.lineJoin = 'round';
            ctx.lineCap = 'round';
            ctx.stroke();

            ctx.beginPath();
            ctx.moveTo(rocketPoints[0].x, rocketPoints[0].y);
            for (let i = 1; i < rocketPoints.length; i++) {
                ctx.lineTo(rocketPoints[i].x, rocketPoints[i].y);
            }
            ctx.strokeStyle = '#ffc107';
            ctx.lineWidth = 4;
            ctx.lineJoin = 'round';
            ctx.lineCap = 'round';
            ctx.shadowColor = '#ffc107';
            ctx.shadowBlur = 20;
            ctx.stroke();
            ctx.shadowBlur = 0;
        }

        if (rocketPoints.length > 0) {
            const last = rocketPoints[rocketPoints.length - 1];
            ctx.beginPath();
            ctx.arc(last.x, last.y, 8, 0, Math.PI * 2);
            ctx.fillStyle = '#ffc107';
            ctx.shadowColor = '#ffc107';
            ctx.shadowBlur = 30;
            ctx.fill();
            ctx.shadowBlur = 0;
        }
        rocketAnimationId = requestAnimationFrame(draw);
    }
    draw();
}

function stopRocketCanvas() {
    if (rocketAnimationId) {
        cancelAnimationFrame(rocketAnimationId);
        rocketAnimationId = null;
    }
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
                        for (let i = 1; i < rocketPoints.length; i++) {
                            ctx.lineTo(rocketPoints[i].x, rocketPoints[i].y);
                        }
                        ctx.strokeStyle = 'rgba(255, 71, 87, 0.25)';
                        ctx.lineWidth = 28;
                        ctx.lineJoin = 'round';
                        ctx.lineCap = 'round';
                        ctx.stroke();

                        ctx.beginPath();
                        ctx.moveTo(rocketPoints[0].x, rocketPoints[0].y);
                        for (let i = 1; i < rocketPoints.length; i++) {
                            ctx.lineTo(rocketPoints[i].x, rocketPoints[i].y);
                        }
                        ctx.strokeStyle = '#ff4757';
                        ctx.lineWidth = 5;
                        ctx.lineJoin = 'round';
                        ctx.lineCap = 'round';
                        ctx.shadowColor = '#ff4757';
                        ctx.shadowBlur = 30;
                        ctx.stroke();
                        ctx.shadowBlur = 0;
                    }
                }
                stopRocketCanvas();

                updateBalance(d.balance);
                loadProfile();

                rocketHistoryArr.unshift(d.mult);
                rocketHistoryArr = rocketHistoryArr.slice(0, 15);
                renderRocketHistory();

                setTimeout(() => {
                    showResult({ icon: '💥', title: 'Взрыв!', titleClass: 'lose',
                        amount: `−${fmt(d.bet || lastBet)} 🪙`,
                        details: `Ракета взорвалась на ×${d.mult.toFixed(2)}`,
                        game: 'rocket', bet: d.bet || lastBet });
                }, 1200);
                return;
            }

            const field = document.getElementById('rocketField');
            const fieldW = field.clientWidth;
            const fieldH = field.clientHeight;
            const maxMult = 10;
            const progress = Math.min(d.mult / maxMult, 1);

            const startX = 30, startY = 30;
            const endX = fieldW - 70, endY = fieldH - 100;

            const newX = startX + (endX - startX) * progress;
            const newY = startY + (endY - startY) * progress;
            const canvasY = fieldH - newY;

            const emoji = document.getElementById('rocketEmoji');
            const flame = document.getElementById('rocketFlame');

            emoji.style.left = newX + 'px';
            emoji.style.bottom = newY + 'px';
            flame.style.left = newX + 'px';
            flame.style.bottom = newY + 'px';

            rocketPoints.push({ x: newX, y: canvasY });
            if (rocketPoints.length > 200) {
                rocketPoints = rocketPoints.slice(-200);
            }

            mult.textContent = `×${d.mult.toFixed(2)}`;
            mult.classList.add('growing');
            setTimeout(() => mult.classList.remove('growing'), 80);

            const fieldEl = document.getElementById('rocketField');
            if (d.mult < 2) fieldEl.setAttribute('data-heat', '1');
            else if (d.mult < 5) fieldEl.setAttribute('data-heat', '2');
            else if (d.mult < 10) fieldEl.setAttribute('data-heat', '3');
            else fieldEl.setAttribute('data-heat', '4');

            prize.textContent = `${fmt(d.prize)} 🪙`;
        } catch (e) {}
    }, 100);
}

async function rocketCashout() {
    haptic();
    if (rocketInterval) { clearInterval(rocketInterval); rocketInterval = null; }
    stopRocketCanvas();
    try {
        const d = await api('/api/rocket/cashout');
        updateBalance(d.balance);
        loadProfile();

        rocketHistoryArr.unshift(d.mult);
        rocketHistoryArr = rocketHistoryArr.slice(0, 15);
        renderRocketHistory();

        setTimeout(() => {
            showResult({ icon: '💰', title: 'Забрано!', titleClass: 'win',
                amount: `+${fmt(d.prize)} 🪙`, details: `Множитель: ×${d.mult.toFixed(2)}`,
                game: 'rocket', bet: d.bet || lastBet });
        }, 500);
    } catch (e) {
        toast(e.message, 'error');
    }
}

/* ═══ КОСТИ ═══ */

function diceStart(bet) {
    haptic();
    diceBet = bet;
    lastBet = bet;
    document.getElementById('diceBets').classList.add('hidden');
    document.getElementById('diceDisplay').classList.remove('hidden');
    document.getElementById('diceResult').textContent = '';
    document.getElementById('diceFace').textContent = '🎲';
    document.getElementById('diceChoices').classList.remove('disabled');
}

async function rollDice(mode) {
    haptic();
    document.getElementById('diceChoices').classList.add('disabled');

    const face = document.getElementById('diceFace');
    face.classList.add('spinning');

    const emojis = ['⚀', '⚁', '⚂', '⚃', '⚄', '⚅'];
    const spinInt = setInterval(() => {
        face.textContent = emojis[Math.floor(Math.random() * 6)];
    }, 100);

    await new Promise(r => setTimeout(r, 1500));
    clearInterval(spinInt);
    face.classList.remove('spinning');

    try {
        const d = await api('/api/dice/roll', { bet: diceBet, choice: mode });
        const resultEmoji = ['', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣'][d.roll];
        face.textContent = resultEmoji;
        updateBalance(d.balance);
        loadProfile();

        setTimeout(() => {
            if (d.win > 0) {
                showResult({ icon: '🎲', title: 'Победа!', titleClass: 'win',
                    amount: `+${fmt(d.win)} 🪙`, details: `Выпало: ${d.roll}<br>Множитель: ×${d.mult}`,
                    game: 'dice', bet: diceBet });
            } else {
                showResult({ icon: '🎲', title: 'Проигрыш', titleClass: 'lose',
                    amount: `−${fmt(diceBet)} 🪙`, details: `Выпало: ${d.roll}`,
                    game: 'dice', bet: diceBet });
            }
        }, 500);
    } catch (e) {
        face.classList.remove('spinning');
        document.getElementById('diceChoices').classList.remove('disabled');
        toast(e.message, 'error');
    }
}

/* ═══ РУССКАЯ РУЛЕТКА ═══ */

async function rrStart(bet) {
    haptic();
    try {
        const d = await api('/api/rr/start', { bet });
        rrState = { bet, step: 0 };
        lastBet = bet;
        updateBalance(d.balance);
        document.getElementById('rrBets').classList.add('hidden');
        document.getElementById('rrDisplay').classList.remove('hidden');
        document.getElementById('rrRevolver').textContent = '🔫';
        document.getElementById('rrMult').textContent = '×1.00';
        document.getElementById('rrPrize').textContent = '0 🪙';
        loadProfile();
    } catch (e) { toast(e.message, 'error'); }
}

async function rrSpin() {
    haptic();
    const rev = document.getElementById('rrRevolver');
    rev.classList.add('spinning');
    await new Promise(r => setTimeout(r, 300));
    rev.classList.remove('spinning');

    try {
        const d = await api('/api/rr/spin');
        updateBalance(d.balance);

        if (d.shot) {
            rev.textContent = '💥';
            rev.classList.add('shot');
            rrState = null;
            loadProfile();
            setTimeout(() => {
                showResult({ icon: '💥', title: 'ВЫСТРЕЛ!', titleClass: 'lose',
                    amount: `−${fmt(d.bet || lastBet)} 🪙`, details: 'Ставка сгорела',
                    game: 'rr', bet: d.bet || lastBet });
            }, 1200);
            return;
        }
        if (d.won) {
            rrState = null;
            loadProfile();
            setTimeout(() => {
                showResult({ icon: '🏆', title: 'МАКСИМУМ!', titleClass: 'win',
                    amount: `+${fmt(d.prize)} 🪙`, details: '6 шагов · Множитель ×7.0',
                    game: 'rr', bet: d.bet || lastBet });
            }, 800);
            return;
        }
        rrState.step = d.step;
        document.getElementById('rrMult').textContent = `×${d.mult}`;
        document.getElementById('rrPrize').textContent = `${fmt(d.prize)} 🪙`;
        haptic();
    } catch (e) { toast(e.message, 'error'); }
}

async function rrCashout() {
    haptic();
    try {
        const d = await api('/api/rr/cashout');
        updateBalance(d.balance);
        rrState = null;
        loadProfile();
        setTimeout(() => {
            showResult({ icon: '💰', title: 'Забрано!', titleClass: 'win',
                amount: `+${fmt(d.prize)} 🪙`, details: `Множитель: ×${d.mult}`,
                game: 'rr', bet: d.bet || lastBet });
        }, 500);
    } catch (e) { toast(e.message, 'error'); }
}

/* ═══ PLINKO ═══ */

const PLINKO_MULTIPLIERS = {
    low:    [10, 3, 1.6, 1.4, 1.1, 1, 0.5, 1, 1.1, 1.4, 1.6, 3, 10],
    medium: [25, 8, 3, 2, 1.4, 0.5, 0.2, 0.5, 1.4, 2, 3, 8, 25],
    high:   [100, 25, 8, 4, 2, 0.2, 0, 0.2, 2, 4, 8, 25, 100],
};

function setPlinkoRisk(risk) {
    haptic();
    plinkoRisk = risk;
    document.querySelectorAll('.plinko-risk-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.risk === risk);
    });
    renderPlinkoSlots();
}

function initPlinko() {
    renderPlinkoBoard();
    renderPlinkoSlots();
    renderBets('plinkoBets', plinkoPlay);
}

function renderPlinkoBoard() {
    const board = document.getElementById('plinkoBoard');
    if (!board) return;
    board.innerHTML = '';
    const rows = [3, 4, 5, 6, 7, 8];
    rows.forEach((count) => {
        const row = document.createElement('div');
        row.className = 'plinko-row';
        for (let i = 0; i < count; i++) {
            const peg = document.createElement('div');
            peg.className = 'plinko-peg';
            row.appendChild(peg);
        }
        board.appendChild(row);
    });
}

function renderPlinkoSlots() {
    const el = document.getElementById('plinkoSlots');
    if (!el) return;
    el.innerHTML = '';
    PLINKO_MULTIPLIERS[plinkoRisk].forEach((m, i) => {
        const slot = document.createElement('div');
        slot.className = 'plinko-slot';
        slot.dataset.idx = i;
        slot.textContent = `×${m}`;
        el.appendChild(slot);
    });
}

async function plinkoPlay(bet) {
    haptic();
    lastBet = bet;

    const d = await api('/api/plinko/play', { bet, risk: plinkoRisk });
    if (!d) return;

    updateBalance(d.balance);
    loadProfile();

    const ball = document.getElementById('plinkoBall');
    const field = document.getElementById('plinkoField');
    ball.style.display = 'block';
    ball.style.top = '0px';
    ball.style.left = '50%';
    ball.style.transform = 'translateX(-50%)';

    const fieldHeight = field.clientHeight - 40;
    const slotIdx = d.slot;
    const slots = PLINKO_MULTIPLIERS[plinkoRisk].length;
    const finalXPercent = (slotIdx + 0.5) / slots * 100;

    const steps = 8;
    for (let i = 1; i <= steps; i++) {
        await new Promise(r => setTimeout(r, 100));
        const top = (fieldHeight / steps) * i;
        const randX = 50 + (Math.random() - 0.5) * 30 + (finalXPercent - 50) * (i / steps);
        ball.style.top = top + 'px';
        ball.style.left = randX + '%';
    }

    await new Promise(r => setTimeout(r, 200));

    const slotEl = document.querySelector(`.plinko-slot[data-idx="${slotIdx}"]`);
    if (slotEl) {
        slotEl.classList.add('hit');
        setTimeout(() => slotEl.classList.remove('hit'), 2000);
    }

    setTimeout(() => {
        ball.style.display = 'none';
        if (d.win > bet) {
            showResult({ icon: '🎯', title: 'Победа!', titleClass: 'win',
                amount: `+${fmt(d.win)} 🪙`, details: `Множитель: ×${d.mult}`,
                game: 'plinko', bet });
        } else {
            showResult({ icon: '🎯', title: d.win === bet ? 'Возврат' : 'Проигрыш',
                titleClass: d.win === bet ? 'win' : 'lose',
                amount: d.win === bet ? `±0 🪙` : `−${fmt(bet - d.win)} 🪙`,
                details: `Множитель: ×${d.mult}`,
                game: 'plinko', bet });
        }
    }, 800);
}

/* ═══ PENALTI ═══ */

function initPenalti() {
    renderBets('penaltiBets', penaltiStart);
}

async function penaltiStart(bet) {
    haptic();
    try {
        const d = await api('/api/penalti/start', { bet });
        penaltiState = { bet, step: 0 };
        lastBet = bet;
        updateBalance(d.balance);
        document.getElementById('penaltiBets').classList.add('hidden');
        document.getElementById('penaltiDisplay').classList.remove('hidden');
        document.getElementById('penaltiMult').textContent = '×1.00';
        document.getElementById('penaltiPrize').textContent = '0 🪙';

        for (let i = 0; i < 5; i++) {
            const g = document.getElementById('goal' + i);
            g.textContent = '⚪';
            g.className = 'goal-dot';
        }
        loadProfile();
    } catch (e) { toast(e.message, 'error'); }
}

async function penaltiKick() {
    haptic();
    try {
        const d = await api('/api/penalti/kick');
        updateBalance(d.balance);

        const goalEl = document.getElementById('goal' + d.step);
        if (d.goal) {
            goalEl.textContent = '⚽';
            goalEl.classList.add('hit');
        } else {
            goalEl.textContent = '❌';
            goalEl.classList.add('miss');
        }

        if (!d.goal) {
            penaltiState = null;
            loadProfile();
            setTimeout(() => {
                showResult({ icon: '❌', title: 'Вратарь поймал!', titleClass: 'lose',
                    amount: `−${fmt(lastBet)} 🪙`, details: `Голов забито: ${d.step}`,
                    game: 'penalti', bet: lastBet });
            }, 1000);
            return;
        }
        if (d.maxed) {
            penaltiState = null;
            loadProfile();
            setTimeout(() => {
                showResult({ icon: '🏆', title: 'Максимум!', titleClass: 'win',
                    amount: `+${fmt(d.prize)} 🪙`, details: `5 голов · Множитель ×${d.mult}`,
                    game: 'penalti', bet: lastBet });
            }, 800);
            return;
        }
        penaltiState.step = d.step;
        document.getElementById('penaltiMult').textContent = `×${d.mult}`;
        document.getElementById('penaltiPrize').textContent = `${fmt(d.prize)} 🪙`;
    } catch (e) { toast(e.message, 'error'); }
}

async function penaltiCashout() {
    haptic();
    try {
        const d = await api('/api/penalti/cashout');
        updateBalance(d.balance);
        penaltiState = null;
        loadProfile();
        setTimeout(() => {
            showResult({ icon: '💰', title: 'Забрано!', titleClass: 'win',
                amount: `+${fmt(d.prize)} 🪙`, details: `Множитель: ×${d.mult}`,
                game: 'penalti', bet: lastBet });
        }, 500);
    } catch (e) { toast(e.message, 'error'); }
}

/* ═══ МОНЕТКА ═══ */

function initCoin() {
    renderCoinHistory();
    renderBets('coinBets', coinStart);
}

function renderCoinHistory() {
    const el = document.getElementById('coinHistory');
    if (!el) return;
    el.innerHTML = '';
    coinHistory.slice(0, 15).forEach(h => {
        const div = document.createElement('div');
        div.className = 'coin-hist-item';
        div.textContent = h === 'heads' ? '👑' : '🔢';
        el.appendChild(div);
    });
}

function coinStart(bet) {
    haptic();
    coinBet = bet;
    lastBet = bet;
    document.getElementById('coinBets').classList.add('hidden');
    document.getElementById('coinDisplay').classList.remove('hidden');
    document.getElementById('coinResult').textContent = 'Выберите сторону';
    document.getElementById('coinFace').textContent = '🪙';
}

async function flipCoin(side) {
    haptic();
    const face = document.getElementById('coinFace');
    face.classList.add('flipping');

    await new Promise(r => setTimeout(r, 600));

    try {
        const d = await api('/api/coin/flip', { bet: coinBet, side });
        face.classList.remove('flipping');

        face.textContent = d.result === 'heads' ? '👑' : '🔢';
        updateBalance(d.balance);
        loadProfile();

        coinHistory.unshift(d.result);
        coinHistory = coinHistory.slice(0, 15);
        renderCoinHistory();

        setTimeout(() => {
            if (d.win > 0) {
                showResult({ icon: d.result === 'heads' ? '👑' : '🔢',
                    title: 'Победа!', titleClass: 'win',
                    amount: `+${fmt(d.win)} 🪙`,
                    details: `Выпало: ${d.result === 'heads' ? 'Орёл' : 'Решка'}`,
                    game: 'coin', bet: coinBet });
            } else {
                showResult({ icon: d.result === 'heads' ? '👑' : '🔢',
                    title: 'Проигрыш', titleClass: 'lose',
                    amount: `−${fmt(coinBet)} 🪙`,
                    details: `Выпало: ${d.result === 'heads' ? 'Орёл' : 'Решка'}`,
                    game: 'coin', bet: coinBet });
            }
        }, 800);
    } catch (e) {
        face.classList.remove('flipping');
        toast(e.message, 'error');
    }
}

/* ═══ ПОПОЛНЕНИЕ ═══ */

function renderPay() {
    const el = document.getElementById('payGrid');
    if (!el) return;
    el.innerHTML = '';
    PAY_PACKS.forEach(s => {
        const btn = document.createElement('button');
        btn.className = 'withdraw-btn';
        btn.textContent = `${s} ⭐ → ${fmt(s * 100)} 🪙`;
        btn.onclick = () => buyStars(s);
        el.appendChild(btn);
    });
}

async function buyStars(stars) {
    haptic();
    try {
        const d = await api('/api/invoice', { stars });
        tg.openInvoice(d.link, (status) => {
            if (status === 'paid') {
                toast('✅ Оплата успешна', 'success');
                setTimeout(loadProfile, 1500);
            }
        });
    } catch (e) { toast(e.message, 'error'); }
}

/* ═══ ВЫВОД ═══ */

async function loadWithdrawStatus() {
    try {
        const d = await api('/api/withdraw/status');
        withdrawAllowed = d.allowed;
        withdrawDays = d.days;

        const info = document.querySelector('#screen-withdraw .withdraw-info');
        let warn = document.getElementById('withdrawWarn');
        if (!withdrawAllowed) {
            if (!warn) {
                warn = document.createElement('div');
                warn.id = 'withdrawWarn';
                warn.className = 'withdraw-warn';
                info.appendChild(warn);
            }
            warn.innerHTML = `⏳ <b>Вывод заблокирован</b><br>Активность: <b>${d.days}</b> из <b>${d.required}</b> дней<br>Осталось: <b>${d.days_left}</b> дн.`;
        } else if (warn) {
            warn.remove();
        }
        renderWithdraw();
    } catch (e) {
        toast(e.message, 'error');
        renderWithdraw();
    }
}

function renderWithdraw() {
    const el = document.getElementById('withdrawGrid');
    if (!el) return;
    el.innerHTML = '';

    WITHDRAW_PACKS.forEach(s => {
        const btn = document.createElement('button');
        btn.className = 'withdraw-btn';
        btn.textContent = `${s} ⭐`;
        btn.onclick = () => withdrawStars(s);
        if (!withdrawAllowed) btn.disabled = true;
        el.appendChild(btn);
    });

    const max = Math.floor(profile.balance / 100);
    if (max >= 15) {
        const all = document.createElement('button');
        all.className = 'withdraw-btn';
        all.style.gridColumn = 'span 2';
        all.textContent = `💯 Все звёзды (${max} ⭐)`;
        all.onclick = () => withdrawStars(max);
        if (!withdrawAllowed) all.disabled = true;
        el.appendChild(all);
    }
}

async function withdrawStars(stars) {
    haptic();
    try {
        const d = await api('/api/withdraw', { stars });
        updateBalance(d.balance);
        toast(d.message, 'success');
        loadProfile();
    } catch (e) { toast(e.message, 'error'); }
}

/* ═══ ТОП ═══ */

async function loadTop() {
    try {
        const d = await api('/api/top');
        const el = document.getElementById('topList');
        if (!el) return;
        el.innerHTML = '';
        d.top.forEach((u, i) => {
            const item = document.createElement('div');
            item.className = 'top-item';
            if (i === 0) item.classList.add('gold');
            if (i === 1) item.classList.add('silver');
            if (i === 2) item.classList.add('bronze');
            const medal = ['🥇', '🥈', '🥉'][i] || `${i + 1}`;
            item.innerHTML = `
                <div class="top-place">${medal}</div>
                <div class="top-name">@${u.username}</div>
                <div class="top-bal">${fmt(u.balance)} 🪙</div>
            `;
            el.appendChild(item);
        });
    } catch (e) { toast(e.message, 'error'); }
}

/* ═══ ДОСТИЖЕНИЯ ═══ */

async function loadAch() {
    try {
        const d = await api('/api/achievements');
        const el = document.getElementById('achList');
        if (!el) return;
        el.innerHTML = '';
        d.achievements.forEach(a => {
            const item = document.createElement('div');
            item.className = 'ach-item' + (a.unlocked ? ' unlocked' : '');
            item.innerHTML = `
                <div class="ach-icon">${a.unlocked ? '✅' : '🔒'}</div>
                <div class="ach-info">
                    <div class="ach-name">${a.name}</div>
                    <div class="ach-desc">${a.desc}</div>
                </div>
            `;
            el.appendChild(item);
        });
    } catch (e) { toast(e.message, 'error'); }
}

/* ═══ РЕФЕРАЛЫ ═══ */

async function loadRef() {
    try {
        const d = await api('/api/profile');
        const link = `https://t.me/${BOT_USERNAME}?start=ref_${d.user_id}`;
        const refEl = document.getElementById('refLink');
        const invEl = document.getElementById('refInvited');
        const bonEl = document.getElementById('refBonuses');
        if (refEl) refEl.textContent = link;
        if (invEl) invEl.textContent = d.referral.invited;
        if (bonEl) bonEl.textContent = d.referral.bonuses;
    } catch (e) { toast(e.message, 'error'); }
}

function copyRef() {
    const el = document.getElementById('refLink');
    if (!el) return;
    navigator.clipboard.writeText(el.textContent).then(() => {
        toast('📋 Скопировано', 'success');
        haptic();
    });
}

/* ═══ ПРОМОКОД ═══ */

async function activatePromo() {
    haptic();
    const el = document.getElementById('promoInput');
    const code = el.value.trim();
    if (!code) { toast('Введите код', 'error'); return; }
    try {
        const d = await api('/api/promo/activate', { code });
        toast(`✅ ${d.message}`, 'success');
        el.value = '';
        loadProfile();
    } catch (e) { toast(e.message, 'error'); }
}

/* ═══ ЕЖЕДНЕВНЫЙ БОНУС ═══ */

async function claimDaily() {
    haptic();
    try {
        const d = await api('/api/daily/claim');
        toast(`🎁 +${fmt(d.reward)} 🪙 (серия ${d.streak})`, 'success');
        updateBalance(d.balance);
        haptic('success');
    } catch (e) { toast(e.message, 'error'); }
}

/* ═══ АДМИНКА ═══ */

function switchAdminTab(tab) {
    document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`.admin-tab[data-tab="${tab}"]`).classList.add('active');
    document.querySelectorAll('.admin-content').forEach(c => c.classList.add('hidden'));
    document.getElementById('admin-' + tab).classList.remove('hidden');
    haptic();

    if (tab === 'stats') loadAdminStats();
    if (tab === 'wd') loadAdminWd();
    if (tab === 'promo') loadAdminPromos();
    if (tab === 'logs') loadAdminLogs();
}

async function loadAdminStats() {
    try {
        const d = await api('/api/admin/stats');
        document.getElementById('admUsers').textContent = fmt(d.users);
        document.getElementById('admCoins').textContent = fmt(d.coins);
        document.getElementById('admWd').textContent = fmt(d.withdrawals);
        document.getElementById('admStars').textContent = fmt(d.withdraw_stars);

        const top = document.getElementById('admTop');
        top.innerHTML = '';
        d.top.forEach((u, i) => {
            const row = document.createElement('div');
            row.className = 'admin-row';
            row.innerHTML = `<span>${i+1}. @${u.username}</span><b>${fmt(u.balance)} 🪙</b>`;
            top.appendChild(row);
        });
    } catch (e) { toast(e.message, 'error'); }
}

async function loadAdminWd() {
    try {
        const d = await api('/api/admin/withdrawals');
        const el = document.getElementById('admWdList');
        el.innerHTML = '';
        if (!d.withdrawals.length) {
            el.innerHTML = '<div class="admin-card">Заявок нет</div>';
            return;
        }
        d.withdrawals.forEach(w => {
            const item = document.createElement('div');
            item.className = 'wd-item ' + w.status;
            const icon = { done: '✅', pending: '⏳', failed: '❌' }[w.status] || '❔';
            item.innerHTML = `
                <div class="wd-header">
                    <span>${icon} #${w.id} @${w.username}</span>
                    <b>${w.stars} ⭐</b>
                </div>
                <div class="wd-info">
                    Списано: ${fmt(w.coins)} 🪙 · ${w.created_at ? w.created_at.slice(0, 16) : ''}
                </div>
                ${w.status === 'pending' ? `
                    <div class="wd-actions">
                        <button class="wd-btn done" onclick="setWdStatus(${w.id}, 'done')">✅ Выплачено</button>
                        <button class="wd-btn fail" onclick="setWdStatus(${w.id}, 'failed')">❌ Отклонить</button>
                    </div>
                ` : ''}
            `;
            el.appendChild(item);
        });
    } catch (e) { toast(e.message, 'error'); }
}

async function setWdStatus(id, status) {
    haptic();
    try {
        await api('/api/admin/withdraw/status', { id, status });
        toast('✅ Обновлено', 'success');
        loadAdminWd();
    } catch (e) { toast(e.message, 'error'); }
}

async function adminGive() {
    haptic();
    const target = document.getElementById('giveTarget').value.trim();
    const amount = parseInt(document.getElementById('giveAmount').value);
    if (!target || !amount) { toast('Заполните поля', 'error'); return; }
    try {
        const d = await api('/api/admin/give', { target, amount });
        toast(`✅ +${fmt(amount)} 🪙 → баланс ${fmt(d.balance)}`, 'success');
        document.getElementById('giveTarget').value = '';
        document.getElementById('giveAmount').value = '';
    } catch (e) { toast(e.message, 'error'); }
}

async function adminSetbal() {
    haptic();
    const target = document.getElementById('setbalTarget').value.trim();
    const amount = parseInt(document.getElementById('setbalAmount').value);
    if (!target || isNaN(amount)) { toast('Заполните поля', 'error'); return; }
    try {
        await api('/api/admin/setbal', { target, amount });
        toast(`✅ Баланс установлен: ${fmt(amount)} 🪙`, 'success');
        document.getElementById('setbalTarget').value = '';
        document.getElementById('setbalAmount').value = '';
    } catch (e) { toast(e.message, 'error'); }
}

async function loadAdminPromos() {
    try {
        const d = await api('/api/admin/promos');
        const el = document.getElementById('admPromoList');
        el.innerHTML = '';
        if (!d.promos.length) {
            el.innerHTML = '<div class="admin-row">Промокодов нет</div>';
            return;
        }
        d.promos.forEach(p => {
            const item = document.createElement('div');
            item.className = 'promo-item';
            const icon = p.kind === 'coins' ? '🪙' : '💸';
            const limit = p.max_uses === 0 ? '∞' : p.max_uses;
            item.innerHTML = `
                <div>${icon} <b>${p.code}</b><br>${p.value} (${p.used}/${limit})</div>
                <button class="del" onclick="adminDeletePromo('${p.code}')">🗑</button>
            `;
            el.appendChild(item);
        });
    } catch (e) { toast(e.message, 'error'); }
}

async function adminCreatePromo() {
    haptic();
    const code = document.getElementById('promoCode').value.trim();
    const kind = document.getElementById('promoKind').value;
    const value = parseInt(document.getElementById('promoValue').value);
    const max_uses = parseInt(document.getElementById('promoMaxUses').value) || 0;
    if (!code || !value) { toast('Заполните поля', 'error'); return; }
    try {
        await api('/api/admin/promo/create', { code, kind, value, max_uses });
        toast('✅ Промокод создан', 'success');
        document.getElementById('promoCode').value = '';
        document.getElementById('promoValue').value = '';
        loadAdminPromos();
    } catch (e) { toast(e.message, 'error'); }
}

async function adminDeletePromo(code) {
    haptic();
    if (!confirm(`Удалить промокод ${code}?`)) return;
    try {
        await api('/api/admin/promo/delete', { code });
        toast('🗑 Удалён', 'success');
        loadAdminPromos();
    } catch (e) { toast(e.message, 'error'); }
}

async function loadAdminLogs() {
    try {
        const d = await api('/api/admin/logs');
        const el = document.getElementById('admLogs');
        el.innerHTML = '';
        if (!d.logs.length) {
            el.innerHTML = '<div class="admin-card">Логов нет</div>';
            return;
        }
        d.logs.forEach(l => {
            const item = document.createElement('div');
            item.className = 'log-item';
            item.innerHTML = `
                [${(l.created_at || '').slice(0, 16)}] <b>${l.action}</b>
                → ${l.target_id || '—'} ${l.details || ''}
            `;
            el.appendChild(item);
        });
    } catch (e) { toast(e.message, 'error'); }
}

async function adminBroadcast() {
    haptic();
    const text = document.getElementById('broadcastText').value.trim();
    if (!text) { toast('Введите текст', 'error'); return; }
    if (!confirm('Отправить всем пользователям?')) return;
    try {
        const d = await api('/api/admin/broadcast', { text });
        toast(`✅ Отправлено: ${d.sent}, ошибок: ${d.failed}`, 'success');
        document.getElementById('broadcastText').value = '';
    } catch (e) { toast(e.message, 'error'); }
}

/* ═══ СТАРТ ═══ */

loadProfile();
