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
let crashInterval = null;
let crashCanvasCtx = null;
let crashAnimationId = null;
let crashPoints = [];
let crashHistoryArr = [1.24, 3.5, 1.08, 8.2, 1.5, 2.1, 12.4, 1.02, 2.8, 1.7];
let rrState = null;
let diceBet = null;
let penaltiState = null;
let penaltiBusy = false;
let coinBet = null;
let coinHistory = [];
let lastGame = null;
let lastBet = 0;
let withdrawAllowed = false;
let withdrawDays = 0;
let plinkoRisk = 'low';
let soundEnabled = true;
let gameHistory = [];
let minesMinesCount = 5;
let slots2Lines = 5;
let duelPolling = null;
let gameLocked = false;
let freeCaseTimer = null;
let casesCache = [];
let caseRouletteBusy = false;
let currentCaseInfo = null;
let adminStatsTimer = null;

/* UPGRADER */
let upgraderItems = [];
let upgraderSelectedPks = new Set();
let upgraderTargetIdx = -1;
let upgraderTargets = [];
let upgraderBusy = false;

/* ═══ SOUND ═══ */
let audioCtx = null;

function initAudio() {
    if (!audioCtx) {
        try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) {}
    }
}

function playTone(freq, duration, type = 'sine', vol = 0.08) {
    if (!soundEnabled) return;
    initAudio();
    if (!audioCtx) return;
    try {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = type;
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(vol, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + duration);
    } catch (e) {}
}

const SFX = {
    click:   () => playTone(880, 0.06, 'square', 0.05),
    spin:    () => playTone(440, 0.1, 'sawtooth', 0.04),
    win:     () => { playTone(660, 0.12); setTimeout(() => playTone(880, 0.12), 100); setTimeout(() => playTone(1320, 0.2), 200); },
    lose:    () => { playTone(300, 0.15, 'sawtooth'); setTimeout(() => playTone(200, 0.25, 'sawtooth'), 100); },
    explode: () => { playTone(120, 0.4, 'sawtooth', 0.12); playTone(80, 0.5, 'square', 0.1); },
    cashout: () => { playTone(880, 0.1); setTimeout(() => playTone(1100, 0.15), 80); },
    jackpot: () => {
        [523, 659, 784, 1046, 1318].forEach((f, i) => setTimeout(() => playTone(f, 0.2, 'triangle', 0.1), i * 100));
    },
    flip:    () => { for (let i = 0; i < 6; i++) setTimeout(() => playTone(400 + i * 100, 0.05, 'square', 0.03), i * 80); },
    sword:   () => { playTone(1800, 0.08, 'square', 0.06); setTimeout(() => playTone(1200, 0.1, 'sawtooth', 0.05), 60); },
    clash:   () => { playTone(2200, 0.05, 'square', 0.08); playTone(1400, 0.12, 'sawtooth', 0.06); playTone(800, 0.15, 'square', 0.05); },
};

function toggleSound() {
    soundEnabled = !soundEnabled;
    document.getElementById('soundToggle').textContent = soundEnabled ? '🔊' : '🔇';
    toast(soundEnabled ? '🔊 Звук включён' : '🔇 Звук выключен');
}

/* ═══ UTILS ═══ */
function fmt(n) {
    return (n || 0).toLocaleString('ru-RU').replace(/,/g, '.');
}

function toast(text, type = '') {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = text;
    el.className = 'toast show ' + type;
    clearTimeout(el._t);
    el._t = setTimeout(() => el.className = 'toast', 2500);
}

function haptic(type = 'light') {
    try {
        if (type === 'success') tg.HapticFeedback.notificationOccurred('success');
        else if (type === 'error') tg.HapticFeedback.notificationOccurred('error');
        else if (type === 'medium') tg.HapticFeedback.impactOccurred('medium');
        else if (type === 'heavy') tg.HapticFeedback.impactOccurred('heavy');
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

async function gameApi(url, body = {}) {
    if (gameLocked) {
        throw new Error('⏳ Дождись окончания игры');
    }
    gameLocked = true;
    try {
        const res = await api(url, body);
        return res;
    } catch (e) {
        gameLocked = false;
        throw e;
    }
}

function addHistory(game, bet, win) {
    gameHistory.unshift({ game, bet, win, ts: Date.now() });
    gameHistory = gameHistory.slice(0, 20);
    renderHistory();
}

function renderHistory() {
    const el = document.getElementById('historyList');
    if (!el) return;
    if (!gameHistory.length) {
        el.innerHTML = '<div class="history-item"><span class="h-game">История пуста</span></div>';
        return;
    }
    const names = {
        slots: '🎰 Слоты', slots2: '🎰 Слоты 5×3', mines: '⛏ Mines', crash: '📈 Crash',
        dice: '🎲 Кости', rr: '🔫 Рулетка', plinko: '🎯 Plinko',
        penalti: '⚽ Penalti', coin: '🪙 Монетка', duel: '⚔️ Дуэль',
        case: '📦 Кейс', upgrader: '⚡ Апгрейд'
    };
    el.innerHTML = gameHistory.map(h => {
        const diff = h.win - h.bet;
        const cls = diff >= 0 ? 'h-win' : 'h-lose';
        const sign = diff >= 0 ? '+' : '−';
        return `<div class="history-item">
            <span class="h-game">${names[h.game] || h.game}</span>
            <span class="${cls}">${sign}${fmt(Math.abs(diff))} 🪙</span>
        </div>`;
    }).join('');
}

/* ═══ CONFETTI ═══ */
function confettiBurst(color = '#ffc107') {
    if (typeof confetti !== 'function') return;
    confetti({
        particleCount: 80, spread: 70, origin: { y: 0.6 },
        colors: [color, '#ffffff', '#ff8f00'], scalar: 0.9,
    });
}

function confettiJackpot() {
    if (typeof confetti !== 'function') return;
    const end = Date.now() + 1500;
    const colors = ['#ffc107', '#ff6b6b', '#7c5cff', '#00d68f'];
    (function frame() {
        confetti({ particleCount: 5, angle: 60, spread: 55, origin: { x: 0 }, colors });
        confetti({ particleCount: 5, angle: 120, spread: 55, origin: { x: 1 }, colors });
        if (Date.now() < end) requestAnimationFrame(frame);
    })();
}

/* ═══ RESULT ═══ */
function showResult({ icon, title, titleClass, amount, details, game, bet }) {
    gameLocked = false;
    document.getElementById('resultIcon').textContent = icon;
    const titleEl = document.getElementById('resultTitle');
    titleEl.textContent = title;
    titleEl.className = 'result-title ' + (titleClass || '');

    const amountEl = document.getElementById('resultAmount');
    if (amount) { amountEl.textContent = amount; amountEl.style.display = 'block'; }
    else { amountEl.style.display = 'none'; }

    document.getElementById('resultDetails').innerHTML = details || '';
    lastGame = game;
    lastBet = bet;

    if (titleClass === 'jackpot') { SFX.jackpot(); confettiJackpot(); haptic('success'); }
    else if (titleClass === 'win') { SFX.win(); confettiBurst('#00d68f'); haptic('success'); }
    else { SFX.lose(); haptic('error'); }

    showScreen('result');
}

function playAgain() {
    haptic();
    if (!lastGame) { showScreen('home'); return; }
    openGame(lastGame);
}

/* ═══ UI ═══ */
function showScreen(name) {
    if (gameLocked && name !== 'game' && name !== 'result') {
        toast('⏳ Дождись окончания игры', 'error');
        return;
    }

    const screen = document.getElementById('screen-' + name);
    if (!screen) return;
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    screen.classList.add('active');
    screen.scrollTop = 0;

    document.querySelectorAll('.nav-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.nav === name);
    });

    if (name !== 'admin' && adminStatsTimer) {
        clearInterval(adminStatsTimer);
        adminStatsTimer = null;
    }

    if (name === 'top') loadTop();
    if (name === 'ach') loadAch();
    if (name === 'withdraw') loadWithdrawStatus();
    if (name === 'pay') renderPay();
    if (name === 'profile') { loadProfile(); renderHistory(); }
    if (name === 'admin') switchAdminTab('stats');
    if (name === 'cases') { loadCases(); loadFreeCaseStatus(); }
    if (name === 'inventory') loadInventory();
    if (name === 'upgrader') loadUpgrader();
}

function updateBalance(b) {
    const prev = profile.balance;
    profile.balance = b;
    ['headerBalance', 'profileBalance', 'gameBalance', 'withdrawBalance'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = fmt(b);
            if (prev !== b && id === 'headerBalance') {
                el.classList.remove('balance-bump');
                void el.offsetWidth;
                el.classList.add('balance-bump');
            }
        }
    });
}

/* ═══ CAROUSEL + GRID ═══ */
const GAMES_META = {
    slots2:  { name: 'Слоты 5×3', desc: 'До ×50',   icon: '🎰', cls: 'slots',  sub: '20 линий, джекпот' },
    crash:   { name: 'Crash',     desc: 'До ×100',  icon: '📈', cls: 'rocket', sub: 'Успей забрать' },
    mines:   { name: 'Mines 7×7', desc: 'До ×25',   icon: '⛏', cls: 'mines',  sub: 'Настрой мины' },
    plinko:  { name: 'Plinko',    desc: 'До ×100',  icon: '🎯', cls: 'plinko', sub: 'Шарик удачи' },
    dice:    { name: 'Кости',     desc: 'До ×5.7',  icon: '🎲', cls: '',       sub: 'Угадай диапазон' },
    rr:      { name: 'Рулетка',   desc: 'До ×7',    icon: '🔫', cls: '',       sub: 'Русская рулетка' },
    penalti: { name: 'Penalti',   desc: 'До ×7',    icon: '⚽', cls: '',       sub: 'Забей и забери' },
    coin:    { name: 'Монетка',   desc: '×1.95',    icon: '🪙', cls: '',       sub: '50/50' },
    duel:    { name: 'PvP Дуэль', desc: '×1.96',    icon: '⚔️', cls: '',       sub: 'Против игрока' },
};

function renderCarousel() {
    const el = document.getElementById('gameCarousel');
    if (!el) return;
    const featured = ['slots2', 'crash', 'mines', 'plinko'];
    el.innerHTML = featured.map(g => {
        const m = GAMES_META[g];
        return `<div class="carousel-card ${m.cls}" onclick="openGame('${g}')">
            <div class="carousel-emoji">${m.icon}</div>
            <div class="carousel-title">${m.name}</div>
            <div class="carousel-sub">${m.sub}</div>
        </div>`;
    }).join('');
}

function renderGamesGrid() {
    const el = document.getElementById('gamesGrid');
    if (!el) return;
    el.innerHTML = Object.entries(GAMES_META).map(([key, m]) => `
        <div class="game-card" onclick="openGame('${key}')">
            <div class="game-card-icon">${m.icon}</div>
            <div class="game-card-name">${m.name}</div>
            <div class="game-card-desc">${m.desc}</div>
        </div>
    `).join('');
}

/* ═══ LIVE FEED ═══ */
const FEED_NAMES = ['Игрок', 'Lucky', 'Ace', 'King', 'Pro', 'Master', 'Winner', 'Star'];
const FEED_GAMES = ['Слоты', 'Plinko', 'Crash', 'Mines', 'Кости', 'Penalti', 'Кейсы'];

function pushFeed() {
    const el = document.getElementById('liveFeed');
    if (!el) return;
    const name = FEED_NAMES[Math.floor(Math.random() * FEED_NAMES.length)];
    const game = FEED_GAMES[Math.floor(Math.random() * FEED_GAMES.length)];
    const amount = [500, 1200, 5000, 15000, 50000, 120000][Math.floor(Math.random() * 6)];
    const item = document.createElement('div');
    item.className = 'feed-item';
    item.innerHTML = `🎉 <b>@${name}${Math.floor(Math.random()*99)}</b> выиграл <b>${fmt(amount)}</b> 🪙 в ${game}`;
    el.prepend(item);
    while (el.children.length > 8) el.lastChild.remove();
}

/* ═══ PROFILE ═══ */
async function loadProfile() {
    try {
        const d = await api('/api/profile');
        profile = d;
        updateBalance(d.balance);

        const nameEl = document.getElementById('headerName');
        const profileNameEl = document.getElementById('profileName');
        const avatarEl = document.getElementById('profileAvatar');
        const displayName = d.username ? '@' + d.username : 'Игрок';
        if (nameEl) nameEl.textContent = displayName;
        if (profileNameEl) profileNameEl.textContent = displayName;
        if (avatarEl) avatarEl.textContent = (d.username || 'И')[0].toUpperCase();

        const sg = document.getElementById('statGames');
        const sw = document.getElementById('statWagered');
        const so = document.getElementById('statWon');
        if (sg) sg.textContent = fmt(d.stats?.games || 0);
        if (sw) sw.textContent = fmt(d.stats?.wagered || 0);
        if (so) so.textContent = fmt(d.stats?.won || 0);

        const games = d.stats?.games || 0;
        const level = Math.floor(Math.sqrt(games / 10)) + 1;
        const nextLevelGames = Math.pow(level, 2) * 10;
        const prevLevelGames = Math.pow(level - 1, 2) * 10;
        const progress = Math.min(100, ((games - prevLevelGames) / (nextLevelGames - prevLevelGames)) * 100);
        const lf = document.getElementById('levelFill');
        const lt = document.getElementById('levelText');
        if (lf) lf.style.width = progress + '%';
        if (lt) lt.textContent = `Уровень ${level} · ${games} игр`;

        const adminBtn = document.getElementById('adminBtn');
        if (adminBtn && d.is_admin) adminBtn.classList.remove('hidden');
    } catch (e) {
        console.error('Profile load error:', e);
    }
}

/* ═══ GAMES ═══ */
function openGame(game) {
    if (gameLocked) {
        toast('⏳ Дождись окончания игры', 'error');
        return;
    }
    haptic();
    const content = document.getElementById('content-' + game);
    if (!content) { console.error('Game not found: ' + game); return; }
    document.querySelectorAll('.game-content').forEach(c => c.classList.add('hidden'));
    content.classList.remove('hidden');

    const titleEl = document.getElementById('gameTitle');
    if (titleEl) titleEl.textContent = GAMES_META[game]?.name || 'Игра';

    showScreen('game');
    updateBalance(profile.balance);

    minesState = null; rrState = null; diceBet = null; penaltiState = null; coinBet = null;
    penaltiBusy = false;

    if (game === 'slots2') {
        document.getElementById('slots2Bets').classList.remove('hidden');
        renderSlots2Field();
        renderSlots2Lines();
        document.getElementById('slots2Result').textContent = 'Выберите ставку';
        renderBets('slots2Bets', spinSlots2, slots2Lines);
    }
    if (game === 'crash') {
        if (crashInterval) { clearInterval(crashInterval); crashInterval = null; }
        stopCrashCanvas();
        renderCrashHistory();
        document.getElementById('crashBets').classList.remove('hidden');
        document.getElementById('crashAutoBlock').classList.remove('hidden');
        document.getElementById('crashAutoInline').classList.add('hidden');
        document.getElementById('crashDisplay').classList.add('hidden');
        document.getElementById('crashDisplay').classList.remove('crashed');
        document.getElementById('crashMult').classList.remove('crashed');
        renderBets('crashBets', crashStart);
    }
    if (game === 'mines') {
        document.getElementById('minesSettings').classList.remove('hidden');
        renderMinesOptions();
        document.getElementById('minesBets').classList.remove('hidden');
        document.getElementById('minesInfo').classList.add('hidden');
        document.getElementById('minesGrid').classList.add('hidden');
        document.getElementById('minesCashout').classList.add('hidden');
        renderBets('minesBets', minesStart);
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
        api('/api/penalti/reset').catch(() => {});
        document.getElementById('penaltiBets').classList.remove('hidden');
        document.getElementById('penaltiDisplay').classList.add('hidden');
        initPenalti();
    }
    if (game === 'coin') {
        document.getElementById('coinBets').classList.remove('hidden');
        document.getElementById('coinDisplay').classList.add('hidden');
        initCoin();
    }
    if (game === 'duel') {
        api('/api/duel/cancel').catch(() => {});
        document.getElementById('duelBets').classList.remove('hidden');
        document.getElementById('duelBattle').classList.add('hidden');
        document.getElementById('duelDisplay').classList.remove('hidden');
        document.getElementById('duelStatus').textContent = 'Выберите ставку';
        document.getElementById('duelStatus').className = 'duel-status';
        renderBets('duelBets', duelJoin);
    }
}

function closeGame() {
    if (gameLocked) {
        toast('⏳ Дождись окончания игры', 'error');
        return;
    }
    haptic();
    if (crashInterval) clearInterval(crashInterval);
    if (duelPolling) clearInterval(duelPolling);
    stopCrashCanvas();
    gameLocked = false;
    showScreen('home');
}

function renderBets(containerId, onPick, multiplier = 1) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = '';
    BETS.forEach(b => {
        const cost = b * multiplier;
        const btn = document.createElement('button');
        btn.className = 'bet-btn';
        btn.textContent = fmt(b) + ' 🪙' + (multiplier > 1 ? ` (${fmt(cost)})` : '');
        if (cost > profile.balance || gameLocked) btn.disabled = true;
        btn.onclick = () => {
            if (gameLocked) { toast('⏳ Дождись окончания игры', 'error'); return; }
            SFX.click(); haptic(); onPick(b);
        };
        el.appendChild(btn);
    });

    const all = document.createElement('button');
    all.className = 'bet-btn allin';
    const maxBet = Math.floor(profile.balance / multiplier);
    all.textContent = multiplier > 1
        ? `💯 Макс (${fmt(maxBet)} × ${multiplier})`
        : '💯 Весь баланс';
    if (maxBet <= 0 || gameLocked) all.disabled = true;
    all.onclick = () => {
        if (gameLocked) { toast('⏳ Дождись окончания игры', 'error'); return; }
        SFX.click(); haptic('medium'); onPick(maxBet);
    };
    el.appendChild(all);
}

/* ═══ СЛОТЫ 5×3 ═══ */
function renderSlots2Lines() {
    document.querySelectorAll('.lines-btn').forEach(b => {
        b.classList.toggle('active', parseInt(b.dataset.lines) === slots2Lines);
    });
}

function setSlotsLines(n) {
    if (gameLocked) { toast('⏳ Дождись окончания игры', 'error'); return; }
    slots2Lines = n;
    renderSlots2Lines();
    renderBets('slots2Bets', spinSlots2, slots2Lines);
    haptic();
}

function renderSlots2Field(field) {
    const el = document.getElementById('slots2Field');
    if (!el) return;
    el.innerHTML = '';
    const data = field || Array(5).fill(null).map(() => Array(3).fill('❓'));
    for (let r = 0; r < 3; r++) {
        for (let c = 0; c < 5; c++) {
            const cell = document.createElement('div');
            cell.className = 'slot2-cell';
            cell.dataset.col = c;
            cell.dataset.row = r;
            cell.textContent = data[c] ? data[c][r] : '❓';
            el.appendChild(cell);
        }
    }
}

async function spinSlots2(bet) {
    document.querySelectorAll('#slots2Bets button').forEach(b => b.disabled = true);
    const res = document.getElementById('slots2Result');
    res.textContent = 'Крутим...';
    res.className = 'game-result';

    const symbols = ['🍒', '🍋', '🍊', '🍇', '💎', '7️⃣', '🤑'];
    const spinInt = setInterval(() => {
        SFX.spin();
        document.querySelectorAll('#slots2Field .slot2-cell').forEach(cell => {
            cell.textContent = symbols[Math.floor(Math.random() * symbols.length)];
            cell.classList.add('spinning');
        });
    }, 80);

    try {
        const d = await gameApi('/api/slots2/spin', { bet, lines: slots2Lines });
        await new Promise(r => setTimeout(r, 800));
        clearInterval(spinInt);
        document.querySelectorAll('#slots2Field .slot2-cell').forEach(c => c.classList.remove('spinning'));

        renderSlots2Field(d.field);
        updateBalance(d.balance);
        loadProfile();
        addHistory('slots2', d.bet, d.win);

        setTimeout(() => {
            if (d.win > d.bet * 3) {
                showResult({ icon: '💥', title: 'БОЛЬШОЙ ВЫИГРЫШ!', titleClass: 'jackpot',
                    amount: `+${fmt(d.win)} 🪙`,
                    details: `Ставка: ${fmt(d.bet)} 🪙<br>Линий: ${d.lines}`,
                    game: 'slots2', bet });
            } else if (d.win > 0) {
                showResult({ icon: '🎉', title: 'Выигрыш!', titleClass: 'win',
                    amount: `+${fmt(d.win)} 🪙`,
                    details: `Ставка: ${fmt(d.bet)} 🪙<br>Линий: ${d.lines}`,
                    game: 'slots2', bet });
            } else {
                showResult({ icon: '😢', title: 'Проигрыш', titleClass: 'lose',
                    amount: `−${fmt(d.bet)} 🪙`,
                    details: `Баланс: ${fmt(d.balance)} 🪙`,
                    game: 'slots2', bet });
            }
        }, 300);
    } catch (e) {
        clearInterval(spinInt);
        document.querySelectorAll('#slots2Field .slot2-cell').forEach(c => c.classList.remove('spinning'));
        toast(e.message, 'error');
        gameLocked = false;
        renderBets('slots2Bets', spinSlots2, slots2Lines);
    }
}

/* ═══ MINES ═══ */
const MINES_OPTIONS = [3, 5, 8, 12, 24];

function renderMinesOptions() {
    const el = document.getElementById('minesOptions');
    if (!el) return;
    el.innerHTML = '';
    MINES_OPTIONS.forEach(m => {
        const btn = document.createElement('button');
        btn.className = 'mines-setting-btn' + (m === minesMinesCount ? ' active' : '');
        btn.textContent = m;
        btn.onclick = () => {
            if (gameLocked) { toast('⏳ Дождись окончания игры', 'error'); return; }
            minesMinesCount = m;
            renderMinesOptions();
            haptic();
        };
        el.appendChild(btn);
    });
}

async function minesStart(bet) {
    try {
        const d = await gameApi('/api/mines/start', { bet, mines: minesMinesCount });
        minesState = { field: d.field, bet, opened: new Set(), minesCount: d.mines_count };
        lastBet = bet;
        document.getElementById('minesSettings').classList.add('hidden');
        document.getElementById('minesBets').classList.add('hidden');
        document.getElementById('minesInfo').classList.remove('hidden');
        document.getElementById('minesGrid').classList.remove('hidden');
        updateBalance(d.balance);
        renderMinesGrid(d.field);
        loadProfile();
        gameLocked = false;
    } catch (e) { toast(e.message, 'error'); gameLocked = false; }
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
            SFX.explode();
            haptic('heavy');
            const cells = document.querySelectorAll('#minesGrid .mine-cell');
            (d.mines || []).forEach(mi => {
                if (cells[mi] && !cells[mi].classList.contains('mine')) {
                    cells[mi].textContent = '💣';
                    cells[mi].style.background = 'rgba(255,71,87,0.15)';
                }
            });
            minesState = null;
            loadProfile();
            addHistory('mines', d.bet || lastBet, 0);
            setTimeout(() => {
                showResult({ icon: '💥', title: 'ВЗРЫВ!', titleClass: 'lose',
                    amount: `−${fmt(d.bet || lastBet)} 🪙`, details: 'Вы наткнулись на бомбу',
                    game: 'mines', bet: d.bet || lastBet });
            }, 1000);
            return;
        }
        if (d.won) {
            cell.textContent = '💎';
            cell.classList.add('opened');
            SFX.win();
            minesState = null;
            loadProfile();
            addHistory('mines', lastBet, d.win);
            setTimeout(() => {
                showResult({ icon: '🏆', title: 'Всё поле открыто!', titleClass: 'win',
                    amount: `+${fmt(d.win)} 🪙`, details: 'Максимальный множитель',
                    game: 'mines', bet: lastBet });
            }, 800);
            return;
        }
        cell.textContent = d.around > 0 ? d.around : '💰';
        cell.classList.add('opened');
        SFX.click();
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
        SFX.cashout();
        minesState = null;
        loadProfile();
        addHistory('mines', d.bet || lastBet, d.prize);
        setTimeout(() => {
            showResult({ icon: '💰', title: 'Продано!', titleClass: 'win',
                amount: `+${fmt(d.prize)} 🪙`, details: 'Вы забрали выигрыш',
                game: 'mines', bet: d.bet || lastBet });
        }, 500);
    } catch (e) { toast(e.message, 'error'); }
}

/* ═══ CRASH ═══ */
function renderCrashHistory() {
    const el = document.getElementById('crashHistory');
    if (!el) return;
    el.innerHTML = '';
    crashHistoryArr.slice(0, 15).forEach(m => {
        const div = document.createElement('div');
        let cls = 'blue';
        if (m >= 10) cls = 'orange';
        else if (m >= 2) cls = 'purple';
        if (m < 1.2) cls = 'red';
        div.className = 'crash-hist-item ' + cls;
        div.textContent = '×' + m.toFixed(2);
        el.appendChild(div);
    });
}

async function crashStart(bet) {
    try {
        const autoEl = document.getElementById('crashAuto');
        const auto = autoEl ? parseFloat(autoEl.value) || 0 : 0;
        const d = await gameApi('/api/crash/start', { bet, auto_cashout: auto });
        updateBalance(d.balance);
        lastBet = bet;
        document.getElementById('crashBets').classList.add('hidden');
        document.getElementById('crashAutoBlock').classList.add('hidden');
        document.getElementById('crashDisplay').classList.remove('hidden');
        document.getElementById('crashDisplay').classList.remove('crashed');
        document.getElementById('crashMult').classList.remove('crashed');
        const autoInline = document.getElementById('crashAutoInline');
        if (autoInline) {
            autoInline.classList.remove('hidden');
            autoInline.textContent = auto > 1 ? `Авто-кэшаут: ×${auto.toFixed(2)}` : '';
        }
        gameLocked = false;
        startCrashCanvas();
        pollCrash();
        loadProfile();
    } catch (e) { toast(e.message, 'error'); gameLocked = false; }
}

function startCrashCanvas() {
    const canvas = document.getElementById('crashCanvas');
    const field = document.getElementById('crashField');
    if (!canvas || !field) return;
    canvas.width = field.clientWidth;
    canvas.height = field.clientHeight;
    crashCanvasCtx = canvas.getContext('2d');
    crashPoints = [];

    function draw() {
        if (!crashCanvasCtx) return;
        const ctx = crashCanvasCtx;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (crashPoints.length > 1) {
            ctx.beginPath();
            ctx.moveTo(crashPoints[0].x, canvas.height);
            for (let i = 0; i < crashPoints.length; i++) ctx.lineTo(crashPoints[i].x, crashPoints[i].y);
            ctx.lineTo(crashPoints[crashPoints.length - 1].x, canvas.height);
            ctx.closePath();
            const grad = ctx.createLinearGradient(0, 0, 0, canvas.height);
            grad.addColorStop(0, 'rgba(255, 193, 7, 0.35)');
            grad.addColorStop(1, 'rgba(255, 193, 7, 0)');
            ctx.fillStyle = grad;
            ctx.fill();

            ctx.beginPath();
            ctx.moveTo(crashPoints[0].x, crashPoints[0].y);
            for (let i = 1; i < crashPoints.length; i++) ctx.lineTo(crashPoints[i].x, crashPoints[i].y);
            ctx.strokeStyle = '#ffc107';
            ctx.lineWidth = 4;
            ctx.lineJoin = 'round';
            ctx.lineCap = 'round';
            ctx.shadowColor = '#ffc107';
            ctx.shadowBlur = 20;
            ctx.stroke();
            ctx.shadowBlur = 0;

            const last = crashPoints[crashPoints.length - 1];
            ctx.beginPath();
            ctx.arc(last.x, last.y, 8, 0, Math.PI * 2);
            ctx.fillStyle = '#ffc107';
            ctx.shadowColor = '#ffc107';
            ctx.shadowBlur = 30;
            ctx.fill();
            ctx.shadowBlur = 0;
        }
        crashAnimationId = requestAnimationFrame(draw);
    }
    draw();
}

function stopCrashCanvas() {
    if (crashAnimationId) { cancelAnimationFrame(crashAnimationId); crashAnimationId = null; }
    crashCanvasCtx = null;
}

function pollCrash() {
    if (crashInterval) clearInterval(crashInterval);

    crashInterval = setInterval(async () => {
        try {
            const d = await api('/api/crash/status');
            const mult = document.getElementById('crashMult');
            const prize = document.getElementById('crashPrize');

            if (d.crashed) {
                clearInterval(crashInterval);
                crashInterval = null;
                document.getElementById('crashDisplay').classList.add('crashed');
                mult.textContent = `×${d.mult.toFixed(2)}`;
                mult.classList.add('crashed');
                prize.textContent = '💥 Crash!';
                SFX.explode();
                haptic('heavy');

                if (crashCanvasCtx) {
                    const canvas = document.getElementById('crashCanvas');
                    const ctx = crashCanvasCtx;
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    if (crashPoints.length > 1) {
                        ctx.beginPath();
                        ctx.moveTo(crashPoints[0].x, crashPoints[0].y);
                        for (let i = 1; i < crashPoints.length; i++) ctx.lineTo(crashPoints[i].x, crashPoints[i].y);
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
                stopCrashCanvas();

                updateBalance(d.balance);
                loadProfile();
                addHistory('crash', d.bet || lastBet, 0);

                crashHistoryArr.unshift(d.mult);
                crashHistoryArr = crashHistoryArr.slice(0, 15);
                renderCrashHistory();

                setTimeout(() => {
                    showResult({ icon: '💥', title: 'CRASH!', titleClass: 'lose',
                        amount: `−${fmt(d.bet || lastBet)} 🪙`,
                        details: `Множитель упал на ×${d.mult.toFixed(2)}`,
                        game: 'crash', bet: d.bet || lastBet });
                }, 1200);
                return;
            }

            if (d.cashed) {
                clearInterval(crashInterval);
                crashInterval = null;
                stopCrashCanvas();
                updateBalance(d.balance);
                loadProfile();
                addHistory('crash', d.bet || lastBet, d.prize);
                crashHistoryArr.unshift(d.mult);
                crashHistoryArr = crashHistoryArr.slice(0, 15);
                renderCrashHistory();
                SFX.cashout();
                setTimeout(() => {
                    showResult({ icon: '💰', title: 'Авто-кэшаут!', titleClass: 'win',
                        amount: `+${fmt(d.prize)} 🪙`,
                        details: `Множитель: ×${d.mult.toFixed(2)}`,
                        game: 'crash', bet: d.bet || lastBet });
                }, 500);
                return;
            }

            const field = document.getElementById('crashField');
            const fieldW = field.clientWidth;
            const fieldH = field.clientHeight;
            const progress = Math.min(d.mult / 20, 1);

            const padX = 30, padY = 30;
            const startX = padX;
            const startY = fieldH - padY;
            const endX = fieldW - padX;
            const endY = padY;

            const newX = startX + (endX - startX) * progress;
            const newY = startY - (startY - endY) * progress;

            crashPoints.push({ x: newX, y: newY });
            if (crashPoints.length > 300) crashPoints = crashPoints.slice(-300);

            mult.textContent = `×${d.mult.toFixed(2)}`;
            mult.classList.add('growing');
            setTimeout(() => mult.classList.remove('growing'), 80);

            const fieldEl = document.getElementById('crashField');
            if (d.mult < 2) fieldEl.setAttribute('data-heat', '1');
            else if (d.mult < 5) fieldEl.setAttribute('data-heat', '2');
            else if (d.mult < 10) fieldEl.setAttribute('data-heat', '3');
            else fieldEl.setAttribute('data-heat', '4');

            prize.textContent = `${fmt(d.prize)} 🪙`;
        } catch (e) {}
    }, 100);
}

async function crashCashout() {
    haptic();
    if (crashInterval) { clearInterval(crashInterval); crashInterval = null; }
    stopCrashCanvas();
    try {
        const d = await api('/api/crash/cashout');
        updateBalance(d.balance);
        SFX.cashout();
        loadProfile();
        addHistory('crash', d.bet || lastBet, d.prize);
        crashHistoryArr.unshift(d.mult);
        crashHistoryArr = crashHistoryArr.slice(0, 15);
        renderCrashHistory();
        setTimeout(() => {
            showResult({ icon: '💰', title: 'Забрано!', titleClass: 'win',
                amount: `+${fmt(d.prize)} 🪙`, details: `Множитель: ×${d.mult.toFixed(2)}`,
                game: 'crash', bet: d.bet || lastBet });
        }, 500);
    } catch (e) {
        toast(e.message, 'error');
        gameLocked = false;
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
        const d = await gameApi('/api/dice/roll', { bet: diceBet, choice: mode });
        const resultEmoji = ['', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣'][d.roll];
        face.textContent = resultEmoji;
        updateBalance(d.balance);
        loadProfile();
        addHistory('dice', diceBet, d.win);

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
        gameLocked = false;
    }
}

/* ═══ РУССКАЯ РУЛЕТКА ═══ */
async function rrStart(bet) {
    try {
        const d = await gameApi('/api/rr/start', { bet });
        rrState = { bet, step: 0 };
        lastBet = bet;
        updateBalance(d.balance);
        document.getElementById('rrBets').classList.add('hidden');
        document.getElementById('rrDisplay').classList.remove('hidden');
        document.getElementById('rrRevolver').textContent = '🔫';
        document.getElementById('rrMult').textContent = '×1.00';
        document.getElementById('rrPrize').textContent = '0 🪙';
        loadProfile();
        gameLocked = false;
    } catch (e) { toast(e.message, 'error'); gameLocked = false; }
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
            SFX.explode();
            haptic('heavy');
            rrState = null;
            loadProfile();
            addHistory('rr', d.bet || lastBet, 0);
            setTimeout(() => {
                showResult({ icon: '💥', title: 'ВЫСТРЕЛ!', titleClass: 'lose',
                    amount: `−${fmt(d.bet || lastBet)} 🪙`, details: 'Ставка сгорела',
                    game: 'rr', bet: d.bet || lastBet });
            }, 1200);
            return;
        }
        if (d.won) {
            SFX.win();
            rrState = null;
            loadProfile();
            addHistory('rr', d.bet || lastBet, d.prize);
            setTimeout(() => {
                showResult({ icon: '🏆', title: 'МАКСИМУМ!', titleClass: 'win',
                    amount: `+${fmt(d.prize)} 🪙`, details: '6 шагов · Множитель ×7.0',
                    game: 'rr', bet: d.bet || lastBet });
            }, 800);
            return;
        }
        SFX.click();
        rrState.step = d.step;
        document.getElementById('rrMult').textContent = `×${d.mult}`;
        document.getElementById('rrPrize').textContent = `${fmt(d.prize)} 🪙`;
    } catch (e) { toast(e.message, 'error'); }
}

async function rrCashout() {
    haptic();
    try {
        const d = await api('/api/rr/cashout');
        updateBalance(d.balance);
        SFX.cashout();
        rrState = null;
        loadProfile();
        addHistory('rr', d.bet || lastBet, d.prize);
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
    if (gameLocked) { toast('⏳ Дождись окончания игры', 'error'); return; }
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
    lastBet = bet;
    const d = await gameApi('/api/plinko/play', { bet, risk: plinkoRisk });
    if (!d) return;

    updateBalance(d.balance);
    loadProfile();
    addHistory('plinko', bet, d.win);

    const ball = document.getElementById('plinkoBall');
    const field = document.getElementById('plinkoField');
    ball.style.display = 'block';
    ball.style.top = '12px';
    ball.style.left = '50%';
    ball.style.transform = 'translateX(-50%)';

    const fieldHeight = field.clientHeight - 40;
    const slotIdx = d.slot;
    const slots = PLINKO_MULTIPLIERS[plinkoRisk].length;
    const finalXPercent = (slotIdx + 0.5) / slots * 100;

    const steps = 12;
    for (let i = 1; i <= steps; i++) {
        await new Promise(r => setTimeout(r, 80));
        playTone(600 + i * 60, 0.05, 'square', 0.03);
        const top = (fieldHeight / steps) * i;
        const noise = i < steps - 2 ? (Math.random() - 0.5) * 20 : 0;
        const randX = 50 + noise + (finalXPercent - 50) * (i / steps);
        ball.style.top = top + 'px';
        ball.style.left = randX + '%';
    }

    ball.style.left = finalXPercent + '%';
    await new Promise(r => setTimeout(r, 200));

    const slotEl = document.querySelector(`.plinko-slot[data-idx="${slotIdx}"]`);
    if (slotEl) {
        slotEl.classList.add('hit');
        setTimeout(() => slotEl.classList.remove('hit'), 2000);
    }

    const shownMult = PLINKO_MULTIPLIERS[plinkoRisk][slotIdx];

    setTimeout(() => {
        ball.style.display = 'none';
        if (d.win > bet) {
            showResult({ icon: '🎯', title: 'Победа!', titleClass: 'win',
                amount: `+${fmt(d.win)} 🪙`, details: `Множитель: ×${shownMult}`,
                game: 'plinko', bet });
        } else {
            showResult({ icon: '🎯', title: d.win === bet ? 'Возврат' : 'Проигрыш',
                titleClass: d.win === bet ? 'win' : 'lose',
                amount: d.win === bet ? `±0 🪙` : `−${fmt(bet - d.win)} 🪙`,
                details: `Множитель: ×${shownMult}`,
                game: 'plinko', bet });
        }
    }, 800);
}

/* ═══ PENALTI (переделано) ═══ */
function initPenalti() {
    renderBets('penaltiBets', penaltiStart);
}

const PENALTI_ZONE_POS = [
    { left: 16.6, top: 16.6 },
    { left: 50.0, top: 16.6 },
    { left: 83.3, top: 16.6 },
    { left: 16.6, top: 50.0 },
    { left: 50.0, top: 50.0 },
    { left: 83.3, top: 50.0 },
    { left: 16.6, top: 83.3 },
    { left: 50.0, top: 83.3 },
    { left: 83.3, top: 83.3 },
];

function zonePercent(zone) {
    return PENALTI_ZONE_POS[zone] || PENALTI_ZONE_POS[4];
}

function zoneToScene(zone) {
    const goal = document.getElementById('goalFrame');
    const scene = document.getElementById('penaltiScene');
    const z = zonePercent(zone);
    const gRect = goal.getBoundingClientRect();
    const sRect = scene.getBoundingClientRect();
    const leftPx = (gRect.left - sRect.left) + (gRect.width * z.left / 100);
    const topPx  = (gRect.top  - sRect.top)  + (gRect.height * z.top  / 100);
    return {
        left: (leftPx / sRect.width) * 100,
        top:  (topPx  / sRect.height) * 100,
    };
}

async function penaltiStart(bet) {
    } catch (e) {
        penaltiBusy = false;
        gameLocked = false;
        toast(e.message, 'error');
    }
}

        document.getElementById('penaltiBets').classList.add('hidden');
        document.getElementById('penaltiDisplay').classList.remove('hidden');
        document.getElementById('penaltiMult').textContent = '×1.00';
        document.getElementById('penaltiPrize').textContent = '0 🪙';
        document.getElementById('penaltiGoals').textContent = '0';
        document.getElementById('penaltiCashoutBtn').style.display = 'none';
        document.getElementById('penaltiHint').textContent = '👇 Выбери, куда бить';
        document.getElementById('penaltiHint').className = 'penalti-hint';

        resetPenaltiField();
        loadProfile();
        penaltiBusy = false;
        gameLocked = false;
    } catch (e) {
        penaltiBusy = false;
        gameLocked = false;
        toast(e.message, 'error');
    }
}

function resetPenaltiField() {
    document.querySelectorAll('.goal-zone').forEach(z => {
        const zn = parseInt(z.dataset.zone);
        const used = penaltiState && penaltiState.usedZones && penaltiState.usedZones.has(zn);
        z.disabled = !!used;
        z.classList.remove('scored', 'missed');
        if (used) z.classList.add('used');
        else z.classList.remove('used');
    });

    const keeper = document.getElementById('keeper');
    const center = zoneToScene(4);
    keeper.style.left = center.left + '%';
    keeper.style.top  = center.top  + '%';
    keeper.classList.remove('diving');
    keeper.classList.add('idle');

    const ball = document.getElementById('ballAnim');
    ball.style.opacity = '0';
    ball.style.left = '50%';
    ball.style.bottom = '6%';
    ball.style.top = 'auto';
    ball.style.transition = 'none';
    void ball.offsetWidth;
    ball.style.transition = 'left 0.5s cubic-bezier(0.3, 0, 0.7, 1), top 0.5s cubic-bezier(0.3, 0, 0.7, 1), bottom 0.5s cubic-bezier(0.3, 0, 0.7, 1), opacity 0.2s';
}

async function penaltiKick(zone) {
    if (penaltiBusy) return;
    if (!penaltiState) return;
    if (gameLocked) return;

    if (penaltiState.usedZones && penaltiState.usedZones.has(zone)) {
        toast('Эта зона уже использована', 'error');
        return;
    }

    penaltiBusy = true;
    haptic();

    document.querySelectorAll('.goal-zone').forEach(z => z.disabled = true);
    document.getElementById('penaltiHint').textContent = '⚽ Удар...';
    document.getElementById('penaltiHint').className = 'penalti-hint';

    const ball = document.getElementById('ballAnim');
    const target = zoneToScene(zone);
    ball.style.opacity = '1';
    ball.style.left = '50%';
    ball.style.bottom = '6%';
    ball.style.top = 'auto';

    await new Promise(r => setTimeout(r, 30));
    ball.style.top = target.top + '%';
    ball.style.bottom = 'auto';
    ball.style.left = target.left + '%';

    await new Promise(r => setTimeout(r, 500));

    try {
        const d = await gameApi('/api/penalti/kick', { zone });

        const keeper = document.getElementById('keeper');
        keeper.classList.remove('idle');
        keeper.classList.add('diving');

        const diveZone = (d.keeper_dive_zone !== undefined && d.keeper_dive_zone !== null)
            ? d.keeper_dive_zone
            : d.keeper_zone;

        const keeperPos = zoneToScene(diveZone);
        keeper.style.left = keeperPos.left + '%';
        keeper.style.top  = keeperPos.top  + '%';

        await new Promise(r => setTimeout(r, 400));

        updateBalance(d.balance);

        const zoneEl = document.querySelector(`.goal-zone[data-zone="${zone}"]`);

        if (d.save) {
            if (zoneEl) zoneEl.classList.add('missed');
            document.getElementById('penaltiHint').textContent = '🧤 Вратарь отбил!';
            document.getElementById('penaltiHint').className = 'penalti-hint fail';
            document.getElementById('penaltiScene').classList.add('save-flash');
            SFX.lose();
            haptic('heavy');
            penaltiState = null;
            loadProfile();
            addHistory('penalti', lastBet, 0);

            setTimeout(() => {
                document.getElementById('penaltiScene').classList.remove('save-flash');
                penaltiBusy = false;
                showResult({
                    icon: '🧤',
                    title: 'ВРАТАРЬ ОТБИЛ!',
                    titleClass: 'lose',
                    amount: `−${fmt(lastBet)} 🪙`,
                    details: `Голов забито: ${d.step}`,
                    game: 'penalti',
                    bet: lastBet,
                });
            }, 1400);
            return;
        }

        if (zoneEl) zoneEl.classList.add('scored');
        document.getElementById('penaltiScene').classList.add('goal-flash');
        SFX.win();
        haptic('success');

        document.getElementById('penaltiGoals').textContent = d.step;
        document.getElementById('penaltiMult').textContent = `×${d.mult}`;
        document.getElementById('penaltiPrize').textContent = `${fmt(d.prize)} 🪙`;

        if (penaltiState) {
            penaltiState.step = d.step;
            penaltiState.usedZones = new Set(d.history || []);
        }

        if (d.maxed) {
            penaltiState = null;
            loadProfile();
            addHistory('penalti', lastBet, d.prize);

            setTimeout(() => {
                document.getElementById('penaltiScene').classList.remove('goal-flash');
                penaltiBusy = false;
                showResult({
                    icon: '🏆',
                    title: 'МАКСИМУМ!',
                    titleClass: 'win',
                    amount: `+${fmt(d.prize)} 🪙`,
                    details: `5 голов · Множитель ×${d.mult}`,
                    game: 'penalti',
                    bet: lastBet,
                });
            }, 1200);
            return;
        }

        document.getElementById('penaltiHint').textContent = '⚽ Гол! Бей ещё или забери';
        document.getElementById('penaltiHint').className = 'penalti-hint success';
        document.getElementById('penaltiCashoutBtn').style.display = 'block';

        setTimeout(() => {
            document.getElementById('penaltiScene').classList.remove('goal-flash');
            resetPenaltiField();
            penaltiBusy = false;
            gameLocked = false;
        }, 1200);
    } catch (e) {
        toast(e.message, 'error');
        document.querySelectorAll('.goal-zone').forEach(z => {
            const zn = parseInt(z.dataset.zone);
            const used = penaltiState && penaltiState.usedZones && penaltiState.usedZones.has(zn);
            z.disabled = !!used;
        });
        penaltiBusy = false;
        gameLocked = false;
    }
}

async function penaltiCashout() {
    if (penaltiBusy) return;
    if (!penaltiState || penaltiState.step <= 0) {
        toast('Сначала забей гол', 'error');
        return;
    }
    penaltiBusy = true;
    haptic();
    try {
        const d = await api('/api/penalti/cashout');
        updateBalance(d.balance);
        SFX.cashout();
        penaltiState = null;
        loadProfile();
        addHistory('penalti', lastBet, d.prize);
        setTimeout(() => {
            penaltiBusy = false;
            showResult({
                icon: '💰',
                title: 'Забрано!',
                titleClass: 'win',
                amount: `+${fmt(d.prize)} 🪙`,
                details: `Множитель: ×${d.mult}`,
                game: 'penalti',
                bet: lastBet,
            });
        }, 500);
    } catch (e) {
        penaltiBusy = false;
        toast(e.message, 'error');
    }
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

    const choices = document.querySelector('.coin-choices');
    if (choices) choices.classList.remove('disabled');
}

async function flipCoin(side) {
    haptic();

    const choices = document.querySelector('.coin-choices');
    if (choices) choices.classList.add('disabled');

    const face = document.getElementById('coinFace');
    face.classList.remove('coin-heads', 'coin-tails');
    face.classList.add('flipping');
    face.textContent = '🪙';
    SFX.flip();

    await new Promise(r => setTimeout(r, 600));

    try {
        const d = await api('/api/coin/flip', { bet: coinBet, side });
        face.classList.remove('flipping');

        if (d.result === 'heads') {
            face.textContent = '👑';
            face.classList.add('coin-heads');
        } else {
            face.textContent = '🔢';
            face.classList.add('coin-tails');
        }
        SFX.win();

        setTimeout(() => {
            face.classList.remove('coin-heads', 'coin-tails');
        }, 1200);

        updateBalance(d.balance);
        loadProfile();
        addHistory('coin', coinBet, d.win);

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
        face.classList.remove('flipping', 'coin-heads', 'coin-tails');
        if (choices) choices.classList.remove('disabled');
        toast(e.message, 'error');
        gameLocked = false;
    }
}

/* ═══ PVP ДУЭЛЬ ═══ */
async function duelJoin(bet) {
    haptic();
    try {
        const d = await gameApi('/api/duel/join', { bet });
        const status = document.getElementById('duelStatus');
        if (d.status === 'waiting') {
            status.textContent = '⏳ Ищем соперника...';
            status.className = 'duel-status waiting';
            document.querySelectorAll('#duelBets button').forEach(b => b.disabled = true);
            startDuelPolling();
            gameLocked = false;
        } else if (d.status === 'matched') {
            updateBalance(d.balance);
            loadProfile();
            addHistory('duel', bet, d.you_win ? d.prize : 0);
            status.textContent = d.you_win ? '🏆 Победа!' : '😢 Поражение';
            status.className = 'duel-status';
            gameLocked = false;
            playDuelBattle(d.you_win, d.prize, bet);
        }
    } catch (e) { toast(e.message, 'error'); gameLocked = false; }
}

function playDuelBattle(youWin, prize, bet) {
    const battleEl = document.getElementById('duelBattle');
    const displayEl = document.getElementById('duelDisplay');
    const fighterLeft = document.getElementById('fighterLeft');
    const fighterRight = document.getElementById('fighterRight');
    const spark = document.getElementById('battleSpark');
    const battleStatus = document.getElementById('battleStatus');

    displayEl.classList.add('hidden');
    battleEl.classList.remove('hidden');

    fighterLeft.className = 'fighter fighter-left';
    fighterRight.className = 'fighter fighter-right';
    spark.classList.remove('burst');
    battleStatus.textContent = '⚔️ Битва начинается...';
    battleStatus.className = 'battle-status';

    const you = fighterLeft;
    const enemy = fighterRight;

    setTimeout(() => {
        SFX.sword();
        you.classList.add('attacking');
        battleStatus.textContent = '🗡️ Удар!';
        haptic('medium');

        setTimeout(() => {
            you.classList.remove('attacking');
            SFX.sword();
            enemy.classList.add('attacking');
            battleStatus.textContent = '🛡️ Ответный удар!';
            haptic('medium');

            setTimeout(() => {
                enemy.classList.remove('attacking');
                SFX.clash();
                spark.classList.add('burst');
                haptic('heavy');

                if (youWin) {
                    enemy.classList.add('defeated');
                    you.classList.add('victorious');
                    battleStatus.textContent = '🏆 ПОБЕДА!';
                    battleStatus.className = 'battle-status win';
                    confettiBurst('#ffc107');
                } else {
                    you.classList.add('defeated');
                    enemy.classList.add('victorious');
                    battleStatus.textContent = '💀 Поражение';
                    battleStatus.className = 'battle-status lose';
                }

                setTimeout(() => {
                    showResult({
                        icon: youWin ? '🏆' : '💀',
                        title: youWin ? 'ПОБЕДА В ДУЭЛИ!' : 'Поражение',
                        titleClass: youWin ? 'win' : 'lose',
                        amount: youWin ? `+${fmt(prize)} 🪙` : `−${fmt(bet)} 🪙`,
                        details: youWin
                            ? `Вы победили соперника!<br>Ставка: ${fmt(bet)} 🪙<br>Выигрыш: ${fmt(prize)} 🪙`
                            : `Соперник оказался сильнее<br>Ставка: ${fmt(bet)} 🪙 сгорела`,
                        game: 'duel', bet
                    });
                }, 2200);
            }, 500);
        }, 500);
    }, 300);
}

function startDuelPolling() {
    if (duelPolling) clearInterval(duelPolling);
    duelPolling = setInterval(async () => {
        try {
            const d = await api('/api/duel/status');
            if (d.status === 'matched') {
                clearInterval(duelPolling);
                duelPolling = null;
                updateBalance(d.balance);
                loadProfile();
                addHistory('duel', d.bet, d.you_win ? d.prize : 0);

                const status = document.getElementById('duelStatus');
                status.textContent = d.you_win ? '🏆 Победа!' : '😢 Поражение';
                status.className = 'duel-status';

                playDuelBattle(d.you_win, d.prize, d.bet);
            }
        } catch (e) {}
    }, 1500);
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
                SFX.cashout();
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

    const max = Math.floor(profile.balance / 125);
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

/* ═══ ПРОМОКОД ═══ */
async function activatePromo() {
    haptic();
    const el = document.getElementById('promoInput');
    const code = el.value.trim();
    if (!code) { toast('Введите код', 'error'); return; }
    try {
        const d = await api('/api/promo/activate', { code });
        toast(`✅ ${d.message}`, 'success');
        SFX.cashout();
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
        confettiBurst('#ffc107');
        SFX.win();
        haptic('success');
    } catch (e) {
        if (e.message.includes('пополнения')) {
            toast('💳 Бонус доступен после пополнения на 10+ ⭐', 'error');
        } else {
            toast(e.message, 'error');
        }
    }
}

/* ═══ CASES ═══ */
async function loadCases() {
    try {
        const d = await api('/api/cases/list');
        casesCache = d.cases;

        const el = document.getElementById('casesGrid');
        const homeEl = document.getElementById('homeCasesGrid');

        const cardHtml = (c) => `
            <div class="case-card" onclick="openCaseInfo('${c.id}')">
                <div class="case-emoji">${c.emoji}</div>
                <div class="case-name">${c.name}</div>
                <div class="case-price">${c.price_stars} ⭐ · ${fmt(c.price_coins)} 🪙</div>
                <div class="case-desc">${c.desc}</div>
            </div>
        `;

        if (el) el.innerHTML = d.cases.map(cardHtml).join('');
        if (homeEl) homeEl.innerHTML = d.cases.slice(0, 6).map(cardHtml).join('');
    } catch (e) { toast(e.message, 'error'); }
}

async function openCaseInfo(id) {
    haptic();
    try {
        const d = await api('/api/cases/info', { case_id: id });
        currentCaseInfo = d;

        document.getElementById('ciTitle').textContent = `${d.emoji} ${d.name}`;

        const rarityColors = {
            common: '#8b95a5', uncommon: '#00d68f', rare: '#4a9eff',
            epic: '#7c5cff', legendary: '#ffc107', mythic: '#ff4757',
        };

        const el = document.getElementById('ciContents');
        el.innerHTML = d.items.map(i => `
            <div class="ci-item" data-rarity="${i.rarity}">
                <div class="ci-emoji">${i.emoji}</div>
                <div>
                    <div class="ci-name">${i.name}</div>
                    <div class="ci-rarity" style="color:${rarityColors[i.rarity]}">${i.rarity_emoji} ${i.rarity_name}</div>
                </div>
                <div style="text-align:right">
                    <div class="ci-price">${fmt(i.value)} 🪙</div>
                    <div class="ci-chance">${i.chance}%</div>
                </div>
            </div>
        `).join('');

        document.getElementById('caseInfo').classList.remove('hidden');
    } catch (e) { toast(e.message, 'error'); }
}

function closeCaseInfo() {
    document.getElementById('caseInfo').classList.add('hidden');
}

function ciOpen(count) {
    if (!currentCaseInfo) return;
    closeCaseInfo();
    const c = casesCache.find(x => x.id === currentCaseInfo.case_id);
    if (!c) { toast('Кейс не найден', 'error'); return; }
    openCase(c, count);
}

/* ═══ CASE ROULETTE ═══ */
async function openCase(c, count = 1) {
    if (caseRouletteBusy) return;
    haptic('medium');

    const totalCost = c.price_coins * count;
    if (profile.balance < totalCost) {
        toast(`Нужно ${fmt(totalCost)} 🪙`, 'error');
        return;
    }

    caseRouletteBusy = true;
    const overlay = document.getElementById('caseRoulette');
    const track = document.getElementById('crTrack');
    const title = document.getElementById('crTitle');
    const status = document.getElementById('crStatus');
    const multi = document.getElementById('crMulti');

    overlay.classList.add('csgo');
    overlay.classList.remove('zoom');

    title.textContent = `${c.emoji} ${c.name}` + (count > 1 ? ` · ×${count}` : '');
    status.textContent = 'Открываем...';
    status.className = 'cr-status';
    multi.classList.add('hidden');
    multi.innerHTML = '';
    track.style.transition = 'none';
    track.style.transform = 'translateX(0)';
    track.innerHTML = '';
    overlay.classList.remove('hidden');

    let data;
    try {
        const url = count > 1 ? '/api/cases/spin_multi' : '/api/cases/spin';
        const body = count > 1
            ? { case_id: c.id, count }
            : { case_id: c.id };
        data = await api(url, body);
    } catch (e) {
        overlay.classList.add('hidden');
        overlay.classList.remove('csgo');
        caseRouletteBusy = false;
        toast(e.message, 'error');
        return;
    }

    track.innerHTML = data.track.map(item => `
        <div class="cr-item" data-rarity="${item.rarity}">
            <div class="cr-emoji">${item.emoji}</div>
            <div class="cr-name">${item.name}</div>
            <div class="cr-price">${fmt(item.value)}</div>
        </div>
    `).join('');

    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

    const firstItem = track.querySelector('.cr-item');
    const ITEM_W = firstItem ? firstItem.offsetWidth : 100;
    const ITEM_GAP = parseFloat(getComputedStyle(track).gap) || 8;
    const ITEM_TOTAL = ITEM_W + ITEM_GAP;
    const viewportW = overlay.querySelector('.cr-viewport').clientWidth;

    const viewportCenter = viewportW / 2;
    const winCenterInTrack = data.win_pos * ITEM_TOTAL + ITEM_W / 2;
    const finalX = viewportCenter - winCenterInTrack;

    const jitter = (Math.random() - 0.5) * (ITEM_W * 0.4);
    const targetX = finalX + jitter;

    const DURATION = 6000;
    const start = performance.now();
    let lastTick = 0;

    function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }
    function easeOutQuint(t) { return 1 - Math.pow(1 - t, 5); }

    function animate(now) {
        const elapsed = now - start;
        const t = Math.min(elapsed / DURATION, 1);
        const eased = t < 0.85
            ? easeOutCubic(t / 0.85) * 0.9
            : 0.9 + easeOutQuint((t - 0.85) / 0.15) * 0.1;
        const x = targetX * eased;

        track.style.transform = `translateX(${x}px)`;

        const passedItems = Math.floor(Math.abs(x) / ITEM_TOTAL);
        if (passedItems > lastTick) {
            lastTick = passedItems;
            if (elapsed < DURATION - 1000) {
                playTone(1200 + Math.random() * 200, 0.02, 'square', 0.02);
            }
        }

        if (t < 1) {
            requestAnimationFrame(animate);
            return;
        }

        const items = track.querySelectorAll('.cr-item');
        const winnerEl = items[data.win_pos];
        if (winnerEl) winnerEl.classList.add('winner');

        setTimeout(() => {
            overlay.classList.add('zoom');
        }, 400);

        const r = count === 1 ? data.result : data.best;
        const totalWin = count === 1
            ? r.value
            : data.results.reduce((s, x) => s + x.value, 0);

        if (r.rarity === 'mythic' || r.rarity === 'legendary') {
            SFX.jackpot(); confettiJackpot();
        } else if (r.rarity === 'epic') {
            SFX.win(); confettiBurst('#7c5cff');
        } else {
            SFX.cashout();
        }
        haptic('success');

        status.textContent = count === 1
            ? `${r.emoji} ${r.name} · ${fmt(r.value)} 🪙`
            : `🏆 ${r.name} · ${fmt(r.value)} 🪙`;
        status.className = 'cr-status win';

        if (count > 1) {
            multi.innerHTML = data.results.map(x => `
                <div class="cr-multi-item" data-rarity="${x.rarity}">
                    <span class="cr-multi-emoji">${x.emoji}</span>
                    <span>${x.name}</span>
                    <span class="cr-multi-val">+${fmt(x.value)}</span>
                </div>
            `).join('');
            multi.classList.remove('hidden');
        }

        updateBalance(data.balance);
        loadProfile();
        addHistory('case', count === 1 ? c.price_coins : totalCost, totalWin);

        setTimeout(() => {
            overlay.classList.add('hidden');
            overlay.classList.remove('csgo');
            overlay.classList.remove('zoom');
            caseRouletteBusy = false;
        }, 3000);
    }

    requestAnimationFrame(animate);
}

function closeCaseRoulette() {
    if (caseRouletteBusy) return;
    const overlay = document.getElementById('caseRoulette');
    overlay.classList.add('hidden');
    overlay.classList.remove('csgo');
    overlay.classList.remove('zoom');
}

/* ═══ INVENTORY ═══ */
async function loadInventory() {
    try {
        const d = await api('/api/cases/inventory');
        const statsEl = document.getElementById('inventoryStats');
        const listEl = document.getElementById('inventoryList');

        if (statsEl) {
            statsEl.innerHTML = `
                <div class="inv-stat">
                    <div class="inv-stat-val">${d.stats.count}</div>
                    <div class="inv-stat-lbl">Предметов</div>
                </div>
                <div class="inv-stat">
                    <div class="inv-stat-val">${fmt(d.stats.total_value)}</div>
                    <div class="inv-stat-lbl">Общая ценность 🪙</div>
                </div>
            `;
        }

        if (!listEl) return;
        if (!d.items.length) {
            listEl.innerHTML = '<div class="history-item"><span class="h-game">Инвентарь пуст</span></div>';
            return;
        }

        const rarityColors = {
            common: '#8b95a5', uncommon: '#00d68f', rare: '#4a9eff',
            epic: '#7c5cff', legendary: '#ffc107', mythic: '#ff4757',
        };

        listEl.innerHTML = d.items.map(i => `
            <div class="inventory-item" data-rarity="${i.rarity}">
                <div class="inv-emoji">${i.emoji}</div>
                <div class="inv-info">
                    <div class="inv-name">${i.name} ${i.kind === 'nft' ? '🎨' : ''}</div>
                    <div class="inv-rarity" style="color:${rarityColors[i.rarity]}">${i.rarity}</div>
                </div>
                <button class="inv-sell-btn" onclick="sellItem(${i.id})">+${fmt(i.value)}</button>
            </div>
        `).join('');
    } catch (e) { toast(e.message, 'error'); }
}

async function sellItem(pk) {
    haptic();
    try {
        const d = await api('/api/cases/sell', { item_pk: pk });
        toast(`✅ Продано за ${fmt(d.sold_value)} 🪙`, 'success');
        SFX.cashout();
        updateBalance(d.balance);
        loadInventory();
        loadProfile();
    } catch (e) { toast(e.message, 'error'); }
}

async function sellAllItems() {
    haptic('medium');
    try {
        const d = await api('/api/cases/sell_all');
        if (d.count === 0) {
            toast('Нечего продавать', 'error');
            return;
        }
        toast(`✅ Продано ${d.count} предметов за ${fmt(d.total)} 🪙`, 'success');
        SFX.cashout();
        confettiBurst('#00d68f');
        updateBalance(d.balance);
        loadInventory();
        loadProfile();
    } catch (e) { toast(e.message, 'error'); }
}

/* ═══ UPGRADER ═══ */
async function loadUpgrader() {
    try {
        const [inv, tg] = await Promise.all([
            api('/api/cases/inventory'),
            api('/api/upgrader/targets'),
        ]);
        upgraderItems = inv.items || [];
        upgraderTargets = tg.targets || [];
        upgraderSelectedPks.clear();
        upgraderTargetIdx = upgraderTargets.length > 1 ? 1 : 0;
        renderUpgraderInv();
        renderUpgraderMyItem();
        renderUpgraderTarget();
        updateUpgraderChance();
    } catch (e) { toast(e.message, 'error'); }
}

function renderUpgraderInv() {
    const el = document.getElementById('upgInvList');
    if (!el) return;
    if (!upgraderItems.length) {
        el.innerHTML = '<div class="upg-inv-empty">Инвентарь пуст</div>';
        const cnt = document.getElementById('upgSelectedCount');
        if (cnt) cnt.textContent = '';
        return;
    }
    el.innerHTML = upgraderItems.map(i => `
        <div class="upg-inv-item ${upgraderSelectedPks.has(i.id) ? 'selected' : ''}" onclick="selectUpgraderItem(${i.id})">
            <div class="upg-inv-item-emoji">${i.emoji}</div>
            <div class="upg-inv-item-name">${i.name}</div>
            <div class="upg-inv-item-price">${fmt(i.value)}</div>
        </div>
    `).join('');
    const cntEl = document.getElementById('upgSelectedCount');
    if (cntEl) {
        cntEl.textContent = upgraderSelectedPks.size > 0 ? `(выбрано: ${upgraderSelectedPks.size})` : '';
    }
}

function selectUpgraderItem(pk) {
    haptic();
    if (upgraderSelectedPks.has(pk)) {
        upgraderSelectedPks.delete(pk);
    } else {
        upgraderSelectedPks.add(pk);
    }
    renderUpgraderInv();
    renderUpgraderMyItem();
    updateUpgraderChance();
}

function getSelectedItems() {
    return upgraderItems.filter(i => upgraderSelectedPks.has(i.id));
}

function getSelectedTotal() {
    return getSelectedItems().reduce((s, i) => s + i.value, 0);
}

function renderUpgraderMyItem() {
    const el = document.getElementById('upgMyItem');
    if (!el) return;
    const items = getSelectedItems();
    if (!items.length) {
        el.innerHTML = '<div class="upg-side-empty">Выбери предметы<br>снизу ↓</div>';
        return;
    }
    el.innerHTML = `
        <div class="upg-side-list">
            ${items.map(i => `
                <div class="upg-side-list-item">
                    <span class="upg-side-list-emoji">${i.emoji}</span>
                    <span class="upg-side-list-name">${i.name}</span>
                    <span class="upg-side-list-price">${fmt(i.value)}</span>
                </div>
            `).join('')}
        </div>
        <div class="upg-total-inline">${fmt(getSelectedTotal())} 🪙</div>
    `;
}

function renderUpgraderTarget() {
    const el = document.getElementById('upgTargetCard');
    if (!el) return;
    if (upgraderTargetIdx < 0 || !upgraderTargets.length) {
        el.innerHTML = `
            <button class="upg-nav upg-nav-prev" onclick="upgraderNav(-1)">‹</button>
            <div class="upg-side-empty">Нет целей</div>
            <button class="upg-nav upg-nav-next" onclick="upgraderNav(1)">›</button>
        `;
        return;
    }
    const t = upgraderTargets[upgraderTargetIdx];
    el.innerHTML = `
        <button class="upg-nav upg-nav-prev" onclick="upgraderNav(-1)">‹</button>
        <div class="upg-side-emoji">${t.emoji}</div>
        <div class="upg-side-name">${t.name}</div>
        <div class="upg-side-price">${fmt(t.price_coins)}</div>
        <button class="upg-nav upg-nav-next" onclick="upgraderNav(1)">›</button>
    `;
}

function upgraderNav(dir) {
    if (!upgraderTargets.length) return;
    haptic();
    upgraderTargetIdx = (upgraderTargetIdx + dir + upgraderTargets.length) % upgraderTargets.length;
    renderUpgraderTarget();
    updateUpgraderChance();
}

function upgraderRandomTarget() {
    if (!upgraderTargets.length) return;
    haptic();
    let newIdx = upgraderTargetIdx;
    while (newIdx === upgraderTargetIdx && upgraderTargets.length > 1) {
        newIdx = Math.floor(Math.random() * upgraderTargets.length);
    }
    upgraderTargetIdx = newIdx;
    renderUpgraderTarget();
    updateUpgraderChance();
}

function updateUpgraderChance() {
    const successEl = document.getElementById('upgCircleSuccess');
    const failEl = document.getElementById('upgCircleFail');
    const percentEl = document.getElementById('upgPercent');
    if (!successEl || !failEl || !percentEl) return;

    const CIRC = 534;

    if (upgraderSelectedPks.size === 0 || upgraderTargetIdx < 0) {
        percentEl.textContent = '0%';
        percentEl.className = 'upg-percent';
        successEl.style.strokeDashoffset = CIRC;
        failEl.style.strokeDashoffset = 0;
        return;
    }

    const total = getSelectedTotal();
    const target = upgraderTargets[upgraderTargetIdx];
    if (!target) {
        percentEl.textContent = '0%';
        percentEl.className = 'upg-percent';
        successEl.style.strokeDashoffset = CIRC;
        failEl.style.strokeDashoffset = 0;
        return;
    }

    if (target.price_coins <= total) {
        percentEl.textContent = '—';
        percentEl.className = 'upg-percent red';
        successEl.style.strokeDashoffset = 0;
        failEl.style.strokeDashoffset = 0;
        return;
    }

    const chance = Math.min(0.95, Math.max(0.01, total / target.price_coins));
    const percent = chance * 100;

    percentEl.textContent = percent.toFixed(2) + '%';

    percentEl.classList.remove('green', 'yellow', 'red');
    if (percent < 30) percentEl.classList.add('red');
    else if (percent < 65) percentEl.classList.add('yellow');
    else percentEl.classList.add('green');

    successEl.style.strokeDashoffset = CIRC - CIRC * chance;
    failEl.style.strokeDashoffset = -(CIRC * chance);
}

function upgraderQuickMult(mult) {
    haptic();
    if (upgraderSelectedPks.size === 0) {
        toast('Выбери предметы', 'error');
        return;
    }
    const total = getSelectedTotal();
    const desiredValue = total * mult;
    let bestIdx = -1;
    let bestDiff = Infinity;
    upgraderTargets.forEach((t, i) => {
        if (t.price_coins <= total) return;
        const diff = Math.abs(t.price_coins - desiredValue);
        if (diff < bestDiff) { bestDiff = diff; bestIdx = i; }
    });
    if (bestIdx < 0) {
        toast('Нет подходящей цели', 'error');
        return;
    }
    upgraderTargetIdx = bestIdx;
    renderUpgraderTarget();
    updateUpgraderChance();
}

function upgraderQuickChance(percent) {
    haptic();
    if (upgraderSelectedPks.size === 0) {
        toast('Выбери предметы', 'error');
        return;
    }
    const total = getSelectedTotal();
    const desiredValue = total / (percent / 100);
    let bestIdx = -1;
    let bestDiff = Infinity;
    upgraderTargets.forEach((t, i) => {
        if (t.price_coins <= total) return;
        const diff = Math.abs(t.price_coins - desiredValue);
        if (diff < bestDiff) { bestDiff = diff; bestIdx = i; }
    });
    if (bestIdx < 0) {
        toast('Нет подходящей цели', 'error');
        return;
    }
    upgraderTargetIdx = bestIdx;
    renderUpgraderTarget();
    updateUpgraderChance();
}

async function upgraderPlay() {
    if (upgraderBusy) return;
    if (upgraderSelectedPks.size === 0) { toast('Выбери предметы', 'error'); return; }
    if (upgraderTargetIdx < 0) { toast('Выбери цель', 'error'); return; }

    const target = upgraderTargets[upgraderTargetIdx];
    const total = getSelectedTotal();

    if (target.price_coins <= total) {
        toast('⚠️ Цель дешевле ставки — так нельзя', 'error');
        return;
    }

    upgraderBusy = true;
    haptic('medium');

    const arrowEl = document.getElementById('upgArrowSpin');
    const percentEl = document.getElementById('upgPercent');
    const goBtn = document.getElementById('upgGoBtn');

    if (goBtn) goBtn.disabled = true;

    let d;
    try {
        d = await api('/api/upgrader/play', {
            item_pks: Array.from(upgraderSelectedPks),
            target_idx: upgraderTargetIdx,
        });
    } catch (e) {
        toast(e.message, 'error');
        upgraderBusy = false;
        if (goBtn) goBtn.disabled = false;
        return;
    }

    const chance = Math.min(0.95, Math.max(0.01, d.total_value / d.target.price_coins));
    const chancePercent = chance * 100;

    let finalPercent;
    if (d.win) {
        finalPercent = Math.random() * chancePercent * 0.95;
    } else {
        finalPercent = chancePercent + Math.random() * (100 - chancePercent) * 0.95;
    }

    const baseTurns = 6 + Math.floor(Math.random() * 2);
    const finalAngle = baseTurns * 360 + (finalPercent / 100) * 360;

    if (arrowEl) {
        arrowEl.classList.remove('animate');
        arrowEl.style.transform = 'rotate(0deg)';
        void arrowEl.offsetWidth;
        arrowEl.classList.add('animate');
        arrowEl.style.transform = `rotate(${finalAngle}deg)`;
    }

    const startTime = performance.now();
    const duration = 6000;
    let rafId = null;

    function updatePercentWhileSpinning() {
        const t = (performance.now() - startTime) / duration;
        if (t >= 1) return;
        const randomPercent = Math.random() * 100;
        percentEl.textContent = randomPercent.toFixed(2) + '%';
        percentEl.classList.remove('green', 'yellow', 'red');
        if (randomPercent < 30) percentEl.classList.add('red');
        else if (randomPercent < 65) percentEl.classList.add('yellow');
        else percentEl.classList.add('green');
        rafId = requestAnimationFrame(updatePercentWhileSpinning);
    }
    rafId = requestAnimationFrame(updatePercentWhileSpinning);

    const tickInt = setInterval(() => {
        playTone(800 + Math.random() * 400, 0.02, 'square', 0.02);
    }, 70);

    await new Promise(r => setTimeout(r, duration + 100));

    if (rafId) cancelAnimationFrame(rafId);
    clearInterval(tickInt);

    percentEl.textContent = finalPercent.toFixed(2) + '%';
    percentEl.classList.remove('green', 'yellow', 'red');
    if (d.win) percentEl.classList.add('green');
    else percentEl.classList.add('red');

    const overlay = document.createElement('div');
    overlay.className = 'upg-overlay';
    document.body.appendChild(overlay);

    if (d.win) {
        SFX.jackpot();
        confettiJackpot();
        overlay.innerHTML = `
            <div class="upg-result-icon">${d.target.emoji}</div>
            <div class="upg-result-text win">УСПЕХ!</div>
            <div class="upg-result-name">${d.target.name}</div>
            <div class="upg-result-price">+${fmt(d.target.price_coins)} 🪙</div>
        `;
    } else {
        SFX.lose();
        overlay.innerHTML = `
            <div class="upg-result-icon">💀</div>
            <div class="upg-result-text lose">НЕ ПОВЕЗЛО</div>
            <div class="upg-result-name">Предметы потеряны</div>
            <div class="upg-result-price">−${fmt(d.total_value)} 🪙</div>
        `;
    }

    haptic(d.win ? 'success' : 'error');
    updateBalance(d.balance);
    loadProfile();
    addHistory('upgrader', d.total_value, d.win ? d.target.price_coins : 0);

    setTimeout(() => {
        overlay.remove();
        upgraderBusy = false;
        if (goBtn) goBtn.disabled = false;
        loadUpgrader();
    }, 2500);
}

/* ═══ БЕСПЛАТНЫЙ КЕЙС ═══ */
async function loadFreeCaseStatus() {
    try {
        const d = await api('/api/cases/free/status');
        const buttons = [
            { btn: 'freeCaseBtn', sub: 'freeCaseSub', streak: 'freeCaseStreak' },
            { btn: 'freeCaseBtn2', sub: 'freeCaseSub2', streak: 'freeCaseStreak2' },
        ];
        buttons.forEach(({ btn, sub, streak }) => {
            const b = document.getElementById(btn);
            const s = document.getElementById(sub);
            const st = document.getElementById(streak);
            if (!b || !s) return;
            if (d.can_claim) {
                b.disabled = false;
                s.textContent = 'Доступен сейчас — забери!';
            } else {
                b.disabled = true;
                s.textContent = 'Доступен через ' + formatCooldown(d.seconds_left);
            }
            if (st) {
                if (d.streak > 0) {
                    st.classList.remove('hidden');
                    st.textContent = '🔥 ' + d.streak;
                } else {
                    st.classList.add('hidden');
                }
            }
        });

        if (freeCaseTimer) clearInterval(freeCaseTimer);
        if (!d.can_claim) {
            freeCaseTimer = setInterval(loadFreeCaseStatus, 1000);
        }
    } catch (e) {
        console.error('free case status error', e);
    }
}

function formatCooldown(sec) {
    sec = Math.max(0, Math.floor(sec));
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

async function openFreeCase() {
    haptic('medium');

    const overlay = document.createElement('div');
    overlay.className = 'case-opening';
    overlay.innerHTML = `<div class="spin">🎁</div><div style="color:#8b95a5;font-size:13px;">Открываем...</div>`;
    document.body.appendChild(overlay);

    await new Promise(r => setTimeout(r, 900));

    try {
        const d = await api('/api/cases/free/open');
        SFX.cashout();
        haptic('success');

        const rarityColors = {
            common: '#8b95a5', uncommon: '#00d68f', rare: '#4a9eff',
            epic: '#7c5cff', legendary: '#ffc107', mythic: '#ff4757',
        };
        const color = rarityColors[d.rarity] || '#fff';
        const kindLabel = d.kind === 'nft' ? '🎨 NFT-подарок' : '🎁 Подарок';

        overlay.innerHTML = `
            <div class="case-result">
                <div class="case-result-emoji" style="color:${color}">${d.emoji}</div>
                <div class="case-result-rarity" style="color:${color}">${d.rarity_emoji} ${d.rarity_name}</div>
                <div class="case-result-name">${d.name}</div>
                <div class="case-result-kind">${kindLabel}</div>
                <div class="case-result-value">💰 ${fmt(d.value)} 🪙</div>
                ${d.streak_mult > 1 ? `<div class="case-result-kind" style="background:rgba(255,193,7,0.2);color:#ffc107;">🔥 Серия ×${d.streak_mult}</div>` : ''}
            </div>
        `;

        if (d.rarity === 'epic') confettiBurst(color);

        setTimeout(() => {
            overlay.remove();
            loadFreeCaseStatus();
            loadInventory();
        }, 2600);
    } catch (e) {
        overlay.remove();
        toast(e.message, 'error');
        loadFreeCaseStatus();
    }
}

/* ═══ АДМИНКА ═══ */
function switchAdminTab(tab) {
    document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.admin-content').forEach(c => c.classList.add('hidden'));
    const activeTab = document.querySelector(`.admin-tab[data-tab="${tab}"]`);
    if (activeTab) activeTab.classList.add('active');
    const content = document.getElementById('admin-' + tab);
    if (content) content.classList.remove('hidden');
    haptic();

    if (adminStatsTimer) { clearInterval(adminStatsTimer); adminStatsTimer = null; }

    if (tab === 'stats') {
        loadAdminStats();
        adminStatsTimer = setInterval(loadAdminStats, 5000);
    }
    if (tab === 'wd') loadAdminWd();
    if (tab === 'promo') loadAdminPromos();
    if (tab === 'inv') {}
    if (tab === 'logs') loadAdminLogs();
}

async function loadAdminStats() {
    try {
        const d = await api('/api/admin/stats');
        document.getElementById('admUsers').textContent = fmt(d.users);
        document.getElementById('admCoins').textContent = fmt(d.coins);
        document.getElementById('admWd').textContent = fmt(d.withdrawals);
        document.getElementById('admStars').textContent = fmt(d.withdraw_stars);

        const h = d.house || {};
        const setText = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        setText('admWagered', fmt(h.wagered || 0));
        setText('admPaid', fmt(h.paid || 0));
        setText('admProfit', fmt(h.profit || 0));
        setText('admRtp', (h.rtp || 0) + '%');

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
            el.innerHTML = '<div class="admin-row">Заявок нет</div>';
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
        loadAdminStats();
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
        loadAdminStats();
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
        loadAdminStats();
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
            el.innerHTML = '<div class="admin-row">Логов нет</div>';
            return;
        }
        d.logs.forEach(l => {
            const item = document.createElement('div');
            item.className = 'log-item';
            item.innerHTML = `[${(l.created_at || '').slice(0, 16)}] <b>${l.action}</b> → ${l.target_id || '—'} ${l.details || ''}`;
            el.appendChild(item);
        });
    } catch (e) { toast(e.message, 'error'); }
}

/* ═══ ADMIN INVENTORY ═══ */
async function loadUserInventory() {
    const target = document.getElementById('invTarget').value.trim();
    if (!target) { toast('Введи ID или @username', 'error'); return; }
    try {
        const d = await api('/api/admin/user_inventory', { target });
        const el = document.getElementById('admInvList');
        if (!d.items.length) {
            el.innerHTML = '<div class="admin-row">Инвентарь пуст</div>';
            return;
        }
        el.innerHTML = d.items.map(i => `
            <div class="adm-inv-item" data-rarity="${i.rarity}">
                <div class="adm-inv-emoji">${i.emoji}</div>
                <div class="adm-inv-info">
                    <div class="adm-inv-name">${i.name} ${i.kind === 'nft' ? '🎨' : ''}</div>
                    <div class="adm-inv-rarity">${i.rarity}</div>
                </div>
                <div class="adm-inv-value">${fmt(i.value)} 🪙</div>
                <button class="adm-inv-steal" onclick="stealItem(${i.id}, ${d.user_id})">Забрать</button>
            </div>
        `).join('');
    } catch (e) { toast(e.message, 'error'); }
}

async function stealItem(itemPk, fromUserId) {
    haptic('medium');
    if (!confirm('Забрать этот предмет себе?')) return;
    try {
        await api('/api/admin/steal_item', { item_pk: itemPk, from_user_id: fromUserId });
        toast('✅ Предмет у тебя в инвентаре', 'success');
        loadUserInventory();
        loadAdminStats();
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
function bootstrap() {
    renderCarousel();
    renderGamesGrid();
    renderHistory();
    loadProfile();
    loadCases();
    loadFreeCaseStatus();
    pushFeed();
    setInterval(pushFeed, 5000);

    api('/api/penalti/reset').catch(() => {});
    api('/api/duel/cancel').catch(() => {});

    let touchStart = 0;
    document.querySelector('.screens').addEventListener('touchstart', e => {
        touchStart = e.touches[0].clientY;
    }, { passive: true });
    document.querySelector('.screens').addEventListener('touchend', e => {
        const diff = e.changedTouches[0].clientY - touchStart;
        const screen = document.querySelector('.screen.active');
        if (diff > 120 && screen && screen.scrollTop === 0 && !gameLocked) {
            loadProfile();
            loadFreeCaseStatus();
            toast('🔄 Обновлено');
        }
    }, { passive: true });
}

bootstrap();
