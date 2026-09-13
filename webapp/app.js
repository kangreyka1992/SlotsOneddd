const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();
tg.setHeaderColor('#0f1721');
tg.setBackgroundColor('#0f1721');

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
let lastGame = null;
let lastBet = 0;
let withdrawAllowed = false;
let withdrawDays = 0;

/* ═══ UTILS ═══ */

function fmt(n) {
    return (n || 0).toLocaleString('ru-RU').replace(/,/g, '.');
}

function toast(text, type = '') {
    const el = document.getElementById('toast');
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
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    document.getElementById('screen-' + name).classList.add('active');
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
    document.getElementById('headerBalance').textContent = fmt(b);
    document.getElementById('homeBalance').textContent = fmt(b);
    document.getElementById('gameBalance').textContent = fmt(b);
    document.getElementById('withdrawBalance').textContent = fmt(b);
}

/* ═══ ПРОФИЛЬ ═══ */

async function loadProfile() {
    try {
        const d = await api('/api/profile');
        profile = d;
        document.getElementById('headerUsername').textContent = d.username;
        updateBalance(d.balance);
        document.getElementById('statGames').textContent = fmt(d.stats.games);
        document.getElementById('statWagered').textContent = fmt(d.stats.wagered);
        document.getElementById('statWon').textContent = fmt(d.stats.won);

        if (d.discount > 0) {
            document.getElementById('discountInfo').innerHTML =
                `🎁 <b>Скидка ${d.discount}%</b> на пополнение`;
        } else {
            document.getElementById('discountInfo').innerHTML = '';
        }

        if (d.is_admin) {
            document.getElementById('adminBtn').classList.remove('hidden');
        }
    } catch (e) {
        toast(e.message, 'error');
    }
}

/* ═══ ИГРЫ ═══ */

function openGame(game) {
    haptic();
    document.querySelectorAll('.game-content').forEach(c => c.classList.add('hidden'));
    document.getElementById('content-' + game).classList.remove('hidden');
    const titles = {
        slots: '🎰 Слоты', mines: '💣 Сапёр',
        rocket: '🚀 Ракетка', dice: '🎲 Кости', rr: '🔫 Русская рулетка',
    };
    document.getElementById('gameTitle').textContent = titles[game];
    showScreen('game');

    minesState = null;
    rrState = null;
    diceBet = null;

    if (game === 'slots') {
        document.getElementById('slotsBets').classList.remove('hidden');
        [0, 1, 2].forEach(i => document.getElementById('slot' + i).textContent = '❓');
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
}

function closeGame() {
    haptic();
    if (rocketInterval) clearInterval(rocketInterval);
    stopRocketCanvas();
    showScreen('home');
}

function renderBets(containerId, onPick) {
    const el = document.getElementById(containerId);
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
                showResult({
                    icon: '💥',
                    title: 'ДЖЕКПОТ!',
                    titleClass: 'jackpot',
                    amount: `+${fmt(d.win)} 🪙`,
                    details: `Ставка: ${fmt(bet)} 🪙<br>Множитель: ×10`,
                    game: 'slots',
                    bet: bet,
                });
            } else if (d.win > 0) {
                showResult({
                    icon: '🎉',
                    title: 'Выигрыш!',
                    titleClass: 'win',
                    amount: `+${fmt(d.win)} 🪙`,
                    details: `Ставка: ${fmt(bet)} 🪙<br>Баланс: ${fmt(d.balance)} 🪙`,
                    game: 'slots',
                    bet: bet,
                });
            } else {
                showResult({
                    icon: '😢',
                    title: 'Проигрыш',
                    titleClass: 'lose',
                    amount: `−${fmt(bet)} 🪙`,
                    details: `Баланс: ${fmt(d.balance)} 🪙`,
                    game: 'slots',
                    bet: bet,
                });
            }
        }, 300);
    } catch (e) {
        clearInterval(int);
        reels.forEach(el => el.classList.remove('spinning'));
        toast(e.message, 'error');
        renderBets('slotsBets', spinSlots);
    }
}

/* ═══ САПЁР ═══ */

function initMines() {
    if (minesState) return;
    renderBets('minesBets', minesStart);
}

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
    } catch (e) {
        toast(e.message, 'error');
    }
}

function renderMinesGrid(field) {
    const grid = document.getElementById('minesGrid');
    grid.innerHTML = '';
    grid.style.gridTemplateColumns = `repeat(${field}, 1fr)`;
    for (let i = 0; i < field * field; i++) {
        const cell = document.createElement('button');
        cell.className = 'mine-cell';
        cell.textContent = '⬜';
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
                showResult({
                    icon: '💥',
                    title: 'БУМ!',
                    titleClass: 'lose',
                    amount: `−${fmt(d.bet || lastBet)} 🪙`,
                    details: 'Вы попали на мину',
                    game: 'mines',
                    bet: d.bet || lastBet,
                });
            }, 800);
            return;
        }

        if (d.won) {
            cell.textContent = '✅';
            cell.classList.add('opened');
            minesState = null;
            loadProfile();
            setTimeout(() => {
                showResult({
                    icon: '🏆',
                    title: 'Победа!',
                    titleClass: 'win',
                    amount: `+${fmt(d.win)} 🪙`,
                    details: 'Все безопасные клетки открыты<br>Множитель: ×2.5',
                    game: 'mines',
                    bet: lastBet,
                });
            }, 800);
            return;
        }

        cell.textContent = d.around > 0 ? d.around : '·';
        cell.classList.add('opened');
        minesState.opened.add(idx);
        document.getElementById('minesOpened').textContent = d.opened.length;
        document.getElementById('minesPrize').textContent = fmt(d.current_prize);
        document.getElementById('minesCashout').classList.remove('hidden');
    } catch (e) {
        toast(e.message, 'error');
    }
}

async function minesCashout() {
    haptic();
    try {
        const d = await api('/api/mines/cashout');
        updateBalance(d.balance);
        minesState = null;
        loadProfile();
        setTimeout(() => {
            showResult({
                icon: '💰',
                title: 'Забрано!',
                titleClass: 'win',
                amount: `+${fmt(d.prize)} 🪙`,
                details: `Вы забрали выигрыш`,
                game: 'mines',
                bet: d.bet || lastBet,
            });
        }, 500);
    } catch (e) {
        toast(e.message, 'error');
    }
}

/* ═══ РАКЕТКА (стиль 1win Lucky Jet) ═══ */

function initRocket() {
    if (rocketInterval) return;
    renderRocketHistory();
    renderBets('rocketBets', rocketStart);
}

function renderRocketHistory() {
    const el = document.getElementById('rocketHistory');
    el.innerHTML = '';
    rocketHistoryArr.slice(0, 15).forEach(m => {
        const div = document.createElement('div');
        div.className = 'rocket-hist-item ' + (
            m >= 10 ? 'orange' : m >= 2 ? 'purple' : 'blue'
        );
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
    } catch (e) {
        toast(e.message, 'error');
    }
}

function startRocketCanvas() {
    const canvas = document.getElementById('rocketCanvas');
    const field = document.getElementById('rocketField');
    canvas.width = field.clientWidth;
    canvas.height = field.clientHeight;
    rocketCanvasCtx = canvas.getContext('2d');
    rocketPoints = [{ x: 30, y: canvas.height - 30 }];

    function draw() {
        if (!rocketCanvasCtx) return;
        const ctx = rocketCanvasCtx;
        const w = canvas.width;
        const h = canvas.height;
        ctx.clearRect(0, 0, w, h);

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

            if (d.crashed) {
                clearInterval(rocketInterval);
                rocketInterval = null;

                const display = document.getElementById('rocketDisplay');
                display.classList.add('crashed');
                document.getElementById('rocketMult').textContent = `×${d.mult.toFixed(2)}`;
                document.getElementById('rocketMult').classList.add('crashed');
                document.getElementById('rocketPrize').textContent = '💥 Взрыв!';

                if (rocketCanvasCtx) {
                    const canvas = document.getElementById('rocketCanvas');
                    const ctx = rocketCanvasCtx;
                    const w = canvas.width;
                    const h = canvas.height;
                    ctx.clearRect(0, 0, w, h);
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
                    showResult({
                        icon: '💥',
                        title: 'Взрыв!',
                        titleClass: 'lose',
                        amount: `−${fmt(d.bet || lastBet)} 🪙`,
                        details: `Ракета взорвалась на ×${d.mult.toFixed(2)}`,
                        game: 'rocket',
                        bet: d.bet || lastBet,
                    });
                }, 1200);
                return;
            }

            const field = document.getElementById('rocketField');
            const fieldW = field.clientWidth;
            const fieldH = field.clientHeight;
            const maxMult = 10;
            const progress = Math.min(d.mult / maxMult, 1);

            const startX = 30;
            const startY = 30;
            const endX = fieldW - 70;
            const endY = fieldH - 100;

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

            const multEl = document.getElementById('rocketMult');
            multEl.textContent = `×${d.mult.toFixed(2)}`;
            multEl.classList.add('growing');
            setTimeout(() => multEl.classList.remove('growing'), 80);

            document.getElementById('rocketPrize').textContent = `${fmt(d.prize)} 🪙`;
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
            showResult({
                icon: '💰',
                title: 'Забрано!',
                titleClass: 'win',
                amount: `+${fmt(d.prize)} 🪙`,
                details: `Множитель: ×${d.mult.toFixed(2)}`,
                game: 'rocket',
                bet: d.bet || lastBet,
            });
        }, 500);
    } catch (e) {
        toast(e.message, 'error');
        resetRocket();
    }
}

function resetRocket() {
    if (rocketInterval) { clearInterval(rocketInterval); rocketInterval = null; }
    stopRocketCanvas();
    document.getElementById('rocketBets').classList.remove('hidden');
    document.getElementById('rocketDisplay').classList.add('hidden');
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

    renderRocketHistory();
    renderBets('rocketBets', rocketStart);
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

async function rollDice(choice) {
    haptic();

    document.getElementById('diceChoices').classList.add('disabled');

    let exact = 0;
    if (choice === 'exact') {
        const num = prompt('Введите число (1-6):');
        if (!num) {
            document.getElementById('diceChoices').classList.remove('disabled');
            return;
        }
        exact = parseInt(num);
        if (exact < 1 || exact > 6) {
            toast('Нужно 1-6', 'error');
            document.getElementById('diceChoices').classList.remove('disabled');
            return;
        }
    }

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
        const d = await api('/api/dice/roll', { bet: diceBet, choice, exact });
        const resultEmoji = ['', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣'][d.roll];
        face.textContent = resultEmoji;
        updateBalance(d.balance);
        loadProfile();

        setTimeout(() => {
            if (d.win > 0) {
                showResult({
                    icon: '🎲',
                    title: 'Победа!',
                    titleClass: 'win',
                    amount: `+${fmt(d.win)} 🪙`,
                    details: `Выпало: ${d.roll}<br>Ставка: ${fmt(diceBet)} 🪙`,
                    game: 'dice',
                    bet: diceBet,
                });
            } else {
                showResult({
                    icon: '🎲',
                    title: 'Проигрыш',
                    titleClass: 'lose',
                    amount: `−${fmt(diceBet)} 🪙`,
                    details: `Выпало: ${d.roll}`,
                    game: 'dice',
                    bet: diceBet,
                });
            }
        }, 500);
    } catch (e) {
        face.classList.remove('spinning');
        document.getElementById('diceChoices').classList.remove('disabled');
        toast(e.message, 'error');
    }
}

/* ═══ РУССКАЯ РУЛЕТКА ═══ */

function initRR() {
    if (rrState) return;
    renderBets('rrBets', rrStart);
}

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
    } catch (e) {
        toast(e.message, 'error');
    }
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
                showResult({
                    icon: '💥',
                    title: 'ВЫСТРЕЛ!',
                    titleClass: 'lose',
                    amount: `−${fmt(d.bet || lastBet)} 🪙`,
                    details: 'Ставка сгорела',
                    game: 'rr',
                    bet: d.bet || lastBet,
                });
            }, 1200);
            return;
        }

        if (d.won) {
            rrState = null;
            loadProfile();
            setTimeout(() => {
                showResult({
                    icon: '🏆',
                    title: 'МАКСИМУМ!',
                    titleClass: 'win',
                    amount: `+${fmt(d.prize)} 🪙`,
                    details: `6 шагов · Множитель ×7.0`,
                    game: 'rr',
                    bet: d.bet || lastBet,
                });
            }, 800);
            return;
        }

        rrState.step = d.step;
        document.getElementById('rrMult').textContent = `×${d.mult}`;
        document.getElementById('rrPrize').textContent = `${fmt(d.prize)} 🪙`;
        haptic();
    } catch (e) {
        toast(e.message, 'error');
    }
}

async function rrCashout() {
    haptic();
    try {
        const d = await api('/api/rr/cashout');
        updateBalance(d.balance);
        rrState = null;
        loadProfile();
        setTimeout(() => {
            showResult({
                icon: '💰',
                title: 'Забрано!',
                titleClass: 'win',
                amount: `+${fmt(d.prize)} 🪙`,
                details: `Множитель: ×${d.mult}`,
                game: 'rr',
                bet: d.bet || lastBet,
            });
        }, 500);
    } catch (e) {
        toast(e.message, 'error');
    }
}

/* ═══ ПОПОЛНЕНИЕ ═══ */

function renderPay() {
    const el = document.getElementById('payGrid');
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
    } catch (e) {
        toast(e.message, 'error');
    }
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
    } catch (e) {
        toast(e.message, 'error');
    }
}

/* ═══ ТОП ═══ */

async function loadTop() {
    try {
        const d = await api('/api/top');
        const el = document.getElementById('topList');
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
        document.getElementById('refLink').textContent = link;
        document.getElementById('refInvited').textContent = d.referral.invited;
        document.getElementById('refBonuses').textContent = d.referral.bonuses;
    } catch (e) { toast(e.message, 'error'); }
}

function copyRef() {
    const text = document.getElementById('refLink').textContent;
    navigator.clipboard.writeText(text).then(() => {
        toast('📋 Скопировано', 'success');
        haptic();
    });
}

/* ═══ ПРОМОКОД ═══ */

async function activatePromo() {
    haptic();
    const code = document.getElementById('promoInput').value.trim();
    if (!code) { toast('Введите код', 'error'); return; }
    try {
        const d = await api('/api/promo/activate', { code });
        toast(`✅ ${d.message}`, 'success');
        document.getElementById('promoInput').value = '';
        loadProfile();
    } catch (e) {
        toast(e.message, 'error');
    }
}

/* ═══ ЕЖЕДНЕВНЫЙ БОНУС ═══ */

async function claimDaily() {
    haptic();
    try {
        const d = await api('/api/daily/claim');
        toast(`🎁 +${fmt(d.reward)} 🪙 (серия ${d.streak})`, 'success');
        updateBalance(d.balance);
        haptic('success');
    } catch (e) {
        toast(e.message, 'error');
    }
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