import asyncio
import hashlib
import hmac
import json
import math
import random
import time
import datetime
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from bot import bot, start_bot, RATE, STAR_PACKS
from database import (
    get_balance, add_balance, set_balance, create_withdrawal,
    get_top_players, get_user_full_stats,
    get_user_achievements, ACHIEVEMENTS,
    get_referral_stats, get_discount,
    log_game, unlock_achievement,
    get_promo, promo_already_used, use_promo,
    get_daily_info, claim_daily,
    ensure_user,
    get_stats, get_last_withdrawals, update_withdrawal,
    get_user_by_username, get_all_user_ids,
    create_promo, delete_promo, list_promos,
    log_admin_action, get_admin_logs,
    log_visit, can_withdraw,
)

WITHDRAW_RATE = 100
MIN_WITHDRAW = 15
BETS = [10, 50, 100, 500, 1000, 10000, 20000, 30000, 50000, 100000]
ADMIN_IDS = [7643224285]


def validate_init_data(init_data: str) -> dict:
    if not init_data:
        raise HTTPException(401, "no_init_data")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "no_hash")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot.token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        raise HTTPException(401, "invalid_signature")
    return json.loads(pairs.get("user", "{}"))


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def admin_only(init_data: str) -> dict:
    user = validate_init_data(init_data)
    if not is_admin(user["id"]):
        raise HTTPException(403, "no_access")
    return user


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(start_bot())
    print("🚀 Бот и веб-сервер запущены")
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
app.mount("/webapp", StaticFiles(directory="webapp", html=True), name="webapp")


@app.get("/")
async def root():
    return FileResponse("webapp/index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ═══════════ ПРОФИЛЬ ═══════════

@app.post("/api/profile")
async def api_profile(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    await ensure_user(uid, user.get("username"))
    await log_visit(uid)

    balance = await get_balance(uid)
    stats = await get_user_full_stats(uid)
    invited, bonuses = await get_referral_stats(uid)
    discount = await get_discount(uid)

    return {
        "balance": balance,
        "rate": RATE,
        "withdraw_rate": WITHDRAW_RATE,
        "min_withdraw": MIN_WITHDRAW,
        "username": user.get("username") or user.get("first_name") or "игрок",
        "user_id": uid,
        "is_admin": is_admin(uid),
        "stats": {
            "wagered": stats[1] if stats else 0,
            "won": stats[2] if stats else 0,
            "games": stats[3] if stats else 0,
            "daily_streak": stats[5] if stats else 0,
        },
        "referral": {"invited": invited, "bonuses": bonuses},
        "discount": discount,
    }


@app.post("/api/achievements")
async def api_ach(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    unlocked = {a[0] for a in await get_user_achievements(uid)}
    return {
        "achievements": [
            {"id": aid, "name": a["name"], "desc": a["desc"], "unlocked": aid in unlocked}
            for aid, a in ACHIEVEMENTS.items()
        ]
    }


@app.post("/api/top")
async def api_top(request: Request):
    data = await request.json()
    validate_init_data(data.get("initData", ""))
    top = await get_top_players(10)
    return {
        "top": [
            {"username": u[1] or f"user_{u[0]}", "balance": u[2], "games": u[4]}
            for u in top
        ]
    }


# ═══════════ СЛОТЫ 3×3 ═══════════

@app.post("/api/slots/spin")
async def api_slots(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))

    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)

    symbols = ["🍒", "🍋", "🍊", "💎", "🤑", "7️⃣"]
    result = [random.choice(symbols) for _ in range(3)]

    win = 0
    jackpot = False
    if result[0] == result[1] == result[2]:
        if result[0] == "🤑":
            win, jackpot = bet * 10, True
        elif result[0] == "💎":
            win = bet * 5
        elif result[0] == "7️⃣":
            win = bet * 4
        else:
            win = bet * 3
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        win = bet * 2

    if win > 0:
        await add_balance(uid, win)

    await log_game(uid, bet, win)
    nb = await get_balance(uid)

    await unlock_achievement(uid, "first_bet")
    if win > 0:
        await unlock_achievement(uid, "first_win")
    if jackpot:
        await unlock_achievement(uid, "jackpot")
    if win >= 100000:
        await unlock_achievement(uid, "big_win")
    if bet >= 100000:
        await unlock_achievement(uid, "high_roller")
    if nb >= 1000000:
        await unlock_achievement(uid, "millionaire")

    return {"result": result, "win": win, "jackpot": jackpot, "balance": nb}


# ═══════════ СЛОТЫ 5×3 ═══════════

SLOT_LINES = [
    [(0,0),(0,1),(0,2),(0,3),(0,4)],
    [(1,0),(1,1),(1,2),(1,3),(1,4)],
    [(2,0),(2,1),(2,2),(2,3),(2,4)],
    [(0,0),(1,1),(2,2),(1,3),(0,4)],
    [(2,0),(1,1),(0,2),(1,3),(2,4)],
    [(1,0),(0,1),(0,2),(0,3),(1,4)],
    [(1,0),(2,1),(2,2),(2,3),(1,4)],
    [(0,0),(1,1),(1,2),(1,3),(0,4)],
    [(2,0),(1,1),(1,2),(1,3),(2,4)],
    [(0,0),(0,1),(1,2),(2,3),(2,4)],
    [(2,0),(2,1),(1,2),(0,3),(0,4)],
    [(1,0),(1,1),(0,2),(1,3),(1,4)],
    [(1,0),(1,1),(2,2),(1,3),(1,4)],
    [(0,0),(1,1),(2,2),(2,3),(2,4)],
    [(2,0),(1,1),(0,2),(0,3),(0,4)],
    [(1,0),(0,1),(0,2),(1,3),(2,4)],
    [(1,0),(2,1),(2,2),(1,3),(0,4)],
    [(0,0),(1,1),(2,2),(1,3),(2,4)],
    [(0,0),(0,1),(0,2),(1,3),(2,4)],
    [(2,0),(2,1),(2,2),(1,3),(0,4)],
]

SLOT_SYMBOLS = [
    ("🍒", 30, 0.3, 1.2, 4),
    ("🍋", 25, 0.4, 1.5, 5),
    ("🍊", 20, 0.5, 2, 7),
    ("🍇", 15, 0.8, 3, 12),
    ("💎", 8, 2, 8, 25),
    ("7️⃣", 1.5, 5, 20, 100),
    ("🤑", 0.5, 10, 50, 500),
]

_SYM_EMOJI = [s[0] for s in SLOT_SYMBOLS]
_SYM_WEIGHTS = [s[1] for s in SLOT_SYMBOLS]


def _slot_spin(bet: int, lines_count: int):
    total_bet = bet * lines_count
    field = [[random.choices(_SYM_EMOJI, weights=_SYM_WEIGHTS, k=1)[0] for _ in range(3)] for _ in range(5)]

    total_win = 0
    line_wins = []

    for line_idx in range(lines_count):
        line = SLOT_LINES[line_idx]
        symbols = [field[c][r] for (r, c) in line]
        first = symbols[0]
        count = 1
        for s in symbols[1:]:
            if s == first:
                count += 1
            else:
                break

        if count >= 3:
            for emoji, _w, p3, p4, p5 in SLOT_SYMBOLS:
                if emoji == first:
                    if count == 3:
                        mult = p3
                    elif count == 4:
                        mult = p4
                    else:
                        mult = p5
                    win = int(total_bet * mult)
                    if win > 0:
                        total_win += win
                        line_wins.append({
                            "line": line_idx,
                            "count": count,
                            "symbol": first,
                            "win": win,
                        })
                    break

    return field, total_win, line_wins


@app.post("/api/slots2/spin")
async def api_slots2_spin(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))
    lines_count = int(data.get("lines", 5))

    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")
    if lines_count not in (1, 5, 10, 20):
        raise HTTPException(400, "invalid_lines")

    total_bet = bet * lines_count
    balance = await get_balance(uid)
    if balance < total_bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -total_bet)

    field, total_win, line_wins = _slot_spin(bet, lines_count)

    if total_win > 0:
        await add_balance(uid, total_win)

    await log_game(uid, total_bet, total_win)
    nb = await get_balance(uid)

    await unlock_achievement(uid, "first_bet")
    if total_win > 0:
        await unlock_achievement(uid, "first_win")
    if total_win >= total_bet * 10:
        await unlock_achievement(uid, "jackpot")
    if total_win >= 100000:
        await unlock_achievement(uid, "big_win")

    return {
        "field": field,
        "win": total_win,
        "bet": total_bet,
        "lines": lines_count,
        "line_wins": line_wins,
        "balance": nb,
    }


# ═══════════ MINES 2.0 (7×7) ═══════════

mines_games: dict[int, dict] = {}
MINES_FIELD = 7
MINES_MULT = {
    3:  0.10,
    5:  0.15,
    8:  0.22,
    12: 0.32,
    24: 0.55,
}


@app.post("/api/mines/start")
async def api_mines_start(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))
    mines_count = int(data.get("mines", 5))

    if uid in mines_games:
        raise HTTPException(400, "already_playing")
    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")
    if mines_count not in MINES_MULT:
        raise HTTPException(400, "invalid_mines")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)

    total = MINES_FIELD * MINES_FIELD
    mines_games[uid] = {
        "bet": bet,
        "mines_count": mines_count,
        "mines": set(random.sample(list(range(total)), mines_count)),
        "opened": set(),
    }

    return {
        "field": MINES_FIELD,
        "mines_count": mines_count,
        "bet": bet,
        "balance": await get_balance(uid),
    }


@app.post("/api/mines/open")
async def api_mines_open(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    idx = int(data.get("idx", -1))

    game = mines_games.get(uid)
    if not game or idx in game["opened"]:
        raise HTTPException(400, "invalid")

    field = MINES_FIELD
    total = field * field

    def around(i):
        r, c = divmod(i, field)
        n = 0
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < field and 0 <= nc < field and (nr * field + nc) in game["mines"]:
                    n += 1
        return n

    if idx in game["mines"]:
        game["opened"].add(idx)
        bet = game["bet"]
        del mines_games[uid]
        await log_game(uid, bet, 0)
        return {
            "hit_mine": True,
            "idx": idx,
            "bet": bet,
            "mines": list(game["mines"]),
            "balance": await get_balance(uid),
        }

    game["opened"].add(idx)
    safe = total - game["mines_count"]

    if len(game["opened"]) >= safe:
        step_mult = MINES_MULT[game["mines_count"]]
        win = int(game["bet"] * (1 + step_mult * safe))
        await add_balance(uid, win)
        await log_game(uid, game["bet"], win)
        del mines_games[uid]
        await unlock_achievement(uid, "first_bet")
        await unlock_achievement(uid, "first_win")
        return {
            "hit_mine": False,
            "won": True,
            "win": win,
            "balance": await get_balance(uid),
        }

    step_mult = MINES_MULT[game["mines_count"]]
    current_prize = int(game["bet"] * (1 + step_mult * len(game["opened"])))

    return {
        "hit_mine": False,
        "won": False,
        "idx": idx,
        "around": around(idx),
        "opened": list(game["opened"]),
        "current_prize": current_prize,
        "balance": await get_balance(uid),
    }


@app.post("/api/mines/cashout")
async def api_mines_cashout(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    game = mines_games.get(uid)
    if not game or not game["opened"]:
        raise HTTPException(400, "nothing_to_cashout")

    step_mult = MINES_MULT[game["mines_count"]]
    prize = int(game["bet"] * (1 + step_mult * len(game["opened"])))
    bet = game["bet"]
    await add_balance(uid, prize)
    await log_game(uid, bet, prize)
    del mines_games[uid]
    await unlock_achievement(uid, "first_bet")
    return {"prize": prize, "bet": bet, "balance": await get_balance(uid)}


@app.post("/api/mines/cancel")
async def api_mines_cancel(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    game = mines_games.pop(uid, None)
    if game:
        await add_balance(uid, game["bet"])
    return {"balance": await get_balance(uid)}


# ═══════════ CRASH ═══════════

crash_games: dict[int, dict] = {}


@app.post("/api/crash/start")
async def api_crash_start(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))
    auto_cashout = float(data.get("auto_cashout", 0))

    if uid in crash_games:
        raise HTTPException(400, "already_playing")
    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)

    r = random.random()
    if r < 0.05:
        crash_at = 1.00
    else:
        crash_at = min(100.0, max(1.01, 0.95 / (1 - r)))

    crash_games[uid] = {
        "bet": bet,
        "crash_at": crash_at,
        "started": time.time(),
        "auto_cashout": auto_cashout if auto_cashout > 1.0 else 0,
        "cashed": False,
    }

    return {
        "balance": await get_balance(uid),
        "bet": bet,
        "started_at": crash_games[uid]["started"],
    }


@app.post("/api/crash/status")
async def api_crash_status(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    game = crash_games.get(uid)
    if not game:
        raise HTTPException(400, "no_game")

    elapsed = time.time() - game["started"]
    mult = 1.0 + (elapsed ** 1.4) * 0.35
    mult = round(mult, 2)

    if game["auto_cashout"] and mult >= game["auto_cashout"] and not game["cashed"]:
        game["cashed"] = True
        prize = int(game["bet"] * game["auto_cashout"])
        await add_balance(uid, prize)
        await log_game(uid, game["bet"], prize)
        await unlock_achievement(uid, "first_bet")
        if prize > game["bet"]:
            await unlock_achievement(uid, "first_win")
        del crash_games[uid]
        return {
            "crashed": False,
            "cashed": True,
            "mult": game["auto_cashout"],
            "prize": prize,
            "bet": game["bet"],
            "balance": await get_balance(uid),
        }

    if mult >= game["crash_at"]:
        bet = game["bet"]
        del crash_games[uid]
        await log_game(uid, bet, 0)
        return {
            "crashed": True,
            "mult": game["crash_at"],
            "bet": bet,
            "balance": await get_balance(uid),
        }

    return {
        "crashed": False,
        "cashed": False,
        "mult": mult,
        "prize": int(game["bet"] * mult),
        "bet": game["bet"],
        "balance": await get_balance(uid),
    }


@app.post("/api/crash/cashout")
async def api_crash_cashout(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    game = crash_games.get(uid)
    if not game:
        raise HTTPException(400, "no_game")

    elapsed = time.time() - game["started"]
    mult = round(1.0 + (elapsed ** 1.4) * 0.35, 2)

    if mult >= game["crash_at"]:
        bet = game["bet"]
        del crash_games[uid]
        await log_game(uid, bet, 0)
        raise HTTPException(400, "crashed")

    prize = int(game["bet"] * mult)
    bet = game["bet"]
    del crash_games[uid]
    await add_balance(uid, prize)
    await log_game(uid, bet, prize)
    await unlock_achievement(uid, "first_bet")
    if prize > bet:
        await unlock_achievement(uid, "first_win")
    return {"prize": prize, "mult": mult, "bet": bet, "balance": await get_balance(uid)}


# ═══════════ КОСТИ ═══════════

@app.post("/api/dice/roll")
async def api_dice(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))
    choice = data.get("choice")
    exact = int(data.get("exact", 0))

    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)
    roll = random.randint(1, 6)
    win = 0
    mult = 0

    if choice in ("low", "range_3_6") and roll >= 3:
        mult = 1.95
        win = int(bet * mult)
    elif choice in ("high", "range_4_6") and roll >= 4:
        mult = 2.9
        win = int(bet * mult)
    elif choice in ("exact", "range_6_6") and roll == 6:
        mult = 5.7
        win = int(bet * mult)
    elif choice == "exact_number" and roll == exact:
        mult = 5.0
        win = int(bet * mult)

    if win > 0:
        await add_balance(uid, win)
    await log_game(uid, bet, win)
    nb = await get_balance(uid)
    await unlock_achievement(uid, "first_bet")
    if win > 0:
        await unlock_achievement(uid, "first_win")
    if win >= 100000:
        await unlock_achievement(uid, "big_win")

    return {"roll": roll, "win": win, "mult": mult, "balance": nb}


# ═══════════ РУССКАЯ РУЛЕТКА ═══════════

rr_games: dict[int, dict] = {}
RR_MULTS = [1.1, 1.3, 1.7, 2.3, 3.5, 7.0]


@app.post("/api/rr/start")
async def api_rr_start(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))

    if uid in rr_games:
        raise HTTPException(400, "already_playing")
    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)
    rr_games[uid] = {"bet": bet, "step": 0}
    return {"balance": await get_balance(uid)}


@app.post("/api/rr/spin")
async def api_rr_spin(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    game = rr_games.get(uid)
    if not game:
        raise HTTPException(400, "no_game")

    step = game["step"]
    bullets = step + 1

    if random.random() < (bullets / 7):
        bet = game["bet"]
        del rr_games[uid]
        await log_game(uid, bet, 0)
        return {"shot": True, "bet": bet, "balance": await get_balance(uid)}

    step += 1
    game["step"] = step

    if step >= 6:
        prize = int(game["bet"] * RR_MULTS[5])
        bet = game["bet"]
        del rr_games[uid]
        await add_balance(uid, prize)
        await log_game(uid, bet, prize)
        await unlock_achievement(uid, "first_bet")
        await unlock_achievement(uid, "first_win")
        await unlock_achievement(uid, "rr_max")
        return {"shot": False, "won": True, "step": step, "mult": RR_MULTS[5],
                "prize": prize, "bet": bet, "balance": await get_balance(uid)}

    mult = RR_MULTS[step - 1]
    return {"shot": False, "won": False, "step": step, "mult": mult,
            "prize": int(game["bet"] * mult), "next_bullets": step + 1,
            "balance": await get_balance(uid)}


@app.post("/api/rr/cashout")
async def api_rr_cashout(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    game = rr_games.get(uid)
    if not game or game["step"] <= 0:
        raise HTTPException(400, "nothing_to_cashout")

    mult = RR_MULTS[game["step"] - 1]
    prize = int(game["bet"] * mult)
    bet = game["bet"]
    del rr_games[uid]
    await add_balance(uid, prize)
    await log_game(uid, bet, prize)
    await unlock_achievement(uid, "first_bet")
    return {"prize": prize, "mult": mult, "bet": bet, "balance": await get_balance(uid)}


# ═══════════ PLINKO ═══════════

PLINKO_MULTS = {
    "low":    [10, 3, 1.6, 1.4, 1.1, 1, 0.5, 1, 1.1, 1.4, 1.6, 3, 10],
    "medium": [25, 8, 3, 2, 1.4, 0.5, 0.2, 0.5, 1.4, 2, 3, 8, 25],
    "high":   [100, 25, 8, 4, 2, 0.2, 0, 0.2, 2, 4, 8, 25, 100],
}


@app.post("/api/plinko/play")
async def api_plinko(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))
    risk = data.get("risk", "low")

    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")
    if risk not in PLINKO_MULTS:
        raise HTTPException(400, "invalid_risk")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)

    mults = PLINKO_MULTS[risk]
    n = len(mults) - 1
    probs = [math.comb(n, k) * (0.5 ** n) for k in range(n + 1)]

    r = random.random()
    cum = 0
    slot = 0
    for i, p in enumerate(probs):
        cum += p
        if r <= cum:
            slot = i
            break

    mult = mults[slot]
    win = int(bet * mult)

    if win > 0:
        await add_balance(uid, win)

    await log_game(uid, bet, win)
    nb = await get_balance(uid)

    await unlock_achievement(uid, "first_bet")
    if win > bet:
        await unlock_achievement(uid, "first_win")
    if win >= 100000:
        await unlock_achievement(uid, "big_win")

    return {"slot": slot, "mult": mult, "win": win, "balance": nb}


# ═══════════ PENALTI (интерактивный) ═══════════

penalti_games: dict = {}

# Зоны:
#   0 1 2
#   3 4 5
#   6 7 8

PENALTI_MULTS = [1.6, 2.2, 3.0, 4.5, 7.0]
PENALTI_SAVE_CHANCE = [0.11, 0.15, 0.20, 0.25, 0.33]


@app.post("/api/penalti/start")
async def api_penalti_start(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))

    if uid in penalti_games:
        raise HTTPException(400, "already_playing")
    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)
    penalti_games[uid] = {"bet": bet, "step": 0, "history": []}
    return {"balance": await get_balance(uid), "bet": bet}


@app.post("/api/penalti/kick")
async def api_penalti_kick(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    zone = int(data.get("zone", -1))

    if zone < 0 or zone > 8:
        raise HTTPException(400, "invalid_zone")

    game = penalti_games.get(uid)
    if not game:
        raise HTTPException(400, "no_game")

    step = game["step"]
    if step >= 5:
        raise HTTPException(400, "already_max")

    keeper_zone = random.randint(0, 8)

    save_chance = PENALTI_SAVE_CHANCE[step]
    is_save = (zone == keeper_zone) and (random.random() < save_chance * 9)

    if not is_save and random.random() < max(0, save_chance - 1/9):
        is_save = True
        keeper_zone = zone

    if is_save:
        bet = game["bet"]
        del penalti_games[uid]
        await log_game(uid, bet, 0)
        return {
            "goal": False,
            "save": True,
            "zone": zone,
            "keeper_zone": keeper_zone,
            "step": step,
            "bet": bet,
            "balance": await get_balance(uid),
        }

    step += 1
    game["step"] = step
    game["history"].append(zone)
    mult = PENALTI_MULTS[step - 1]
    prize = int(game["bet"] * mult)

    if step >= 5:
        bet = game["bet"]
        del penalti_games[uid]
        await add_balance(uid, prize)
        await log_game(uid, bet, prize)
        await unlock_achievement(uid, "first_bet")
        await unlock_achievement(uid, "first_win")
        if prize >= 100000:
            await unlock_achievement(uid, "big_win")
        return {
            "goal": True, "save": False, "zone": zone, "keeper_zone": keeper_zone,
            "step": step, "maxed": True, "mult": mult, "prize": prize,
            "balance": await get_balance(uid),
        }

    return {
        "goal": True, "save": False, "zone": zone, "keeper_zone": keeper_zone,
        "step": step, "maxed": False, "mult": mult, "prize": prize,
        "balance": await get_balance(uid),
    }


@app.post("/api/penalti/cashout")
async def api_penalti_cashout(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    game = penalti_games.get(uid)
    if not game or game["step"] <= 0:
        raise HTTPException(400, "nothing_to_cashout")

    mult = PENALTI_MULTS[game["step"] - 1]
    prize = int(game["bet"] * mult)
    bet = game["bet"]
    del penalti_games[uid]
    await add_balance(uid, prize)
    await log_game(uid, bet, prize)
    await unlock_achievement(uid, "first_bet")
    return {"prize": prize, "mult": mult, "balance": await get_balance(uid)}


# ═══════════ МОНЕТКА ═══════════

@app.post("/api/coin/flip")
async def api_coin_flip(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))
    side = data.get("side")

    if side not in ("heads", "tails"):
        raise HTTPException(400, "invalid_side")
    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)

    result = random.choice(["heads", "tails"])
    win = 0
    mult = 0
    if result == side:
        mult = 1.95
        win = int(bet * mult)
        await add_balance(uid, win)

    await log_game(uid, bet, win)
    nb = await get_balance(uid)
    await unlock_achievement(uid, "first_bet")
    if win > 0:
        await unlock_achievement(uid, "first_win")

    return {"result": result, "win": win, "mult": mult, "balance": nb}


# ═══════════ PVP ДУЭЛЬ ═══════════

duel_queue: list[dict] = []
duel_active: dict[str, dict] = {}


@app.post("/api/duel/join")
async def api_duel_join(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))

    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")

    for q in duel_queue:
        if q["uid"] == uid:
            raise HTTPException(400, "already_in_queue")

    for did, g in duel_active.items():
        if uid in (g["p1"], g["p2"]):
            raise HTTPException(400, "already_in_duel")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    opponent = None
    for i, q in enumerate(duel_queue):
        if q["bet"] == bet and q["uid"] != uid:
            opponent = duel_queue.pop(i)
            break

    if not opponent:
        duel_queue.append({"uid": uid, "bet": bet, "joined": time.time()})
        return {"status": "waiting", "queue_size": len(duel_queue)}

    await add_balance(uid, -bet)
    await add_balance(opponent["uid"], -bet)

    winner = random.choice([uid, opponent["uid"]])
    prize = int(bet * 2 * 0.98)

    duel_id = f"duel_{int(time.time())}_{random.randint(1000,9999)}"
    duel_active[duel_id] = {
        "p1": uid,
        "p2": opponent["uid"],
        "bet": bet,
        "winner": winner,
        "prize": prize,
        "created": time.time(),
        "claimed": set(),
    }

    await add_balance(winner, prize)
    await log_game(uid, bet, prize if winner == uid else 0)
    await log_game(opponent["uid"], bet, prize if winner == opponent["uid"] else 0)
    await unlock_achievement(uid, "first_bet")
    await unlock_achievement(opponent["uid"], "first_bet")
    if winner == uid:
        await unlock_achievement(uid, "first_win")
    else:
        await unlock_achievement(opponent["uid"], "first_win")

    for player_uid, is_winner in [(uid, winner == uid), (opponent["uid"], winner == opponent["uid"])]:
        try:
            if is_winner:
                await bot.send_message(
                    player_uid,
                    f"🏆 <b>Победа в дуэли!</b>\n\nСтавка: <b>{bet}</b> 🪙\nВыигрыш: <b>+{prize}</b> 🪙",
                    parse_mode="HTML",
                )
            else:
                await bot.send_message(
                    player_uid,
                    f"😢 <b>Поражение в дуэли</b>\n\nСтавка: <b>{bet}</b> 🪙 сгорела",
                    parse_mode="HTML",
                )
        except Exception:
            pass

    return {
        "status": "matched",
        "duel_id": duel_id,
        "winner": winner,
        "you_win": winner == uid,
        "prize": prize,
        "opponent_id": opponent["uid"],
        "balance": await get_balance(uid),
    }


@app.post("/api/duel/status")
async def api_duel_status(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]

    for did, g in list(duel_active.items()):
        if uid in (g["p1"], g["p2"]) and uid not in g["claimed"]:
            g["claimed"].add(uid)
            return {
                "status": "matched",
                "duel_id": did,
                "you_win": g["winner"] == uid,
                "prize": g["prize"] if g["winner"] == uid else 0,
                "bet": g["bet"],
                "opponent_id": g["p2"] if g["p1"] == uid else g["p1"],
                "balance": await get_balance(uid),
            }

    for q in duel_queue:
        if q["uid"] == uid:
            return {"status": "waiting", "queue_size": len(duel_queue)}

    return {"status": "idle"}


@app.post("/api/duel/leave")
async def api_duel_leave(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    for i, q in enumerate(duel_queue):
        if q["uid"] == uid:
            duel_queue.pop(i)
            return {"status": "left"}
    return {"status": "not_in_queue"}


# ═══════════ ВЫВОД ═══════════

@app.post("/api/withdraw")
async def api_withdraw(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    username = user.get("username")

    if not username:
        raise HTTPException(400, "Установите @username в Telegram")

    allowed, days = await can_withdraw(uid)
    if not allowed:
        left = 3 - days
        raise HTTPException(
            400,
            f"Вывод доступен только после 3 дней активности. "
            f"Заходили: {days} из 3. Осталось ещё {left} дн."
        )

    stars = int(data.get("stars", 0))
    if stars < MIN_WITHDRAW:
        raise HTTPException(400, f"Минимум {MIN_WITHDRAW} ⭐")

    need = stars * WITHDRAW_RATE
    balance = await get_balance(uid)
    if balance < need:
        raise HTTPException(400, f"Нужно {need}")

    await add_balance(uid, -need)
    wid = await create_withdrawal(uid, username, stars, need)

    return {"status": "pending", "id": wid,
            "message": f"Заявка №{wid} создана",
            "balance": await get_balance(uid)}


@app.post("/api/withdraw/status")
async def api_withdraw_status(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]

    allowed, days = await can_withdraw(uid)
    return {
        "allowed": allowed,
        "days": days,
        "required": 3,
        "days_left": max(0, 3 - days),
    }


# ═══════════ ПРОМОКОД ═══════════

@app.post("/api/promo/activate")
async def api_promo(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    code = data.get("code", "").strip().upper()

    if not code:
        raise HTTPException(400, "Введите код")

    promo = await get_promo(code)
    if not promo:
        raise HTTPException(400, "Промокод не найден")

    if await promo_already_used(uid, code):
        raise HTTPException(400, "Уже использован")

    _, kind, value, max_uses, used = promo
    if max_uses > 0 and used >= max_uses:
        raise HTTPException(400, "Промокод исчерпан")

    await use_promo(uid, code)

    if kind == "coins":
        nb = await add_balance(uid, value)
        return {"kind": "coins", "value": value, "balance": nb,
                "message": f"+{value} монет"}

    if kind == "discount":
        return {"kind": "discount", "value": value,
                "message": f"Скидка {value}% на следующее пополнение"}

    raise HTTPException(400, "Неизвестный тип")


# ═══════════ ЕЖЕДНЕВНЫЙ БОНУС ═══════════

@app.post("/api/daily/claim")
async def api_daily(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]

    last, streak = await get_daily_info(uid)
    now = datetime.datetime.utcnow()

    if last:
        try:
            last_dt = datetime.datetime.fromisoformat(last)
            if (now - last_dt).total_seconds() < 86400:
                raise HTTPException(400, "Уже получен сегодня")
        except (ValueError, TypeError):
            pass

    reward = 500 + min(streak, 7) * 100
    new_streak = streak + 1
    await claim_daily(uid, new_streak)
    nb = await add_balance(uid, reward)

    if new_streak >= 7:
        await unlock_achievement(uid, "daily_7")

    return {"reward": reward, "streak": new_streak, "balance": nb}


# ═══════════ ИНВОЙС ═══════════

@app.post("/api/invoice")
async def api_invoice(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    stars = int(data.get("stars", 0))

    if stars not in STAR_PACKS:
        raise HTTPException(400, "invalid_pack")

    coins = STAR_PACKS[stars]
    d = await get_discount(uid)
    final = max(1, stars - (stars * d // 100)) if d > 0 else stars

    from aiogram.types import LabeledPrice

    link = await bot.create_invoice_link(
        title="Пополнение баланса",
        description=f"{coins} монет за {final} ⭐",
        payload=f"deposit_{uid}_{coins}_{d}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"{coins} монет", amount=final)],
    )

    return {"link": link, "coins": coins, "stars": final, "discount": d}


# ═══════════ АДМИНКА ═══════════

@app.post("/api/admin/check")
async def api_admin_check(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    return {"is_admin": is_admin(user["id"])}


@app.post("/api/admin/stats")
async def api_admin_stats(request: Request):
    data = await request.json()
    admin_only(data.get("initData", ""))
    s = await get_stats()
    return {
        "users": s["users"],
        "coins": s["coins"],
        "withdrawals": s["withdrawals"],
        "withdraw_stars": s["withdraw_stars"],
        "top": [
            {"user_id": u[0], "username": u[1] or f"user_{u[0]}", "balance": u[2]}
            for u in s["top"]
        ],
    }


@app.post("/api/admin/withdrawals")
async def api_admin_wd(request: Request):
    data = await request.json()
    admin_only(data.get("initData", ""))
    rows = await get_last_withdrawals(30)
    return {
        "withdrawals": [
            {
                "id": w[0], "user_id": w[1], "username": w[2],
                "stars": w[3], "coins": w[4], "status": w[5], "created_at": w[6],
            }
            for w in rows
        ]
    }


@app.post("/api/admin/withdraw/status")
async def api_admin_wd_status(request: Request):
    data = await request.json()
    admin = admin_only(data.get("initData", ""))
    wid = int(data.get("id", 0))
    status = data.get("status", "done")
    if status not in ("done", "failed", "pending"):
        raise HTTPException(400, "invalid_status")

    await update_withdrawal(wid, status)
    await log_admin_action(admin["id"], f"withdraw_{status}", None, f"#{wid}")
    return {"ok": True}


@app.post("/api/admin/give")
async def api_admin_give(request: Request):
    data = await request.json()
    admin = admin_only(data.get("initData", ""))
    target = str(data.get("target", "")).strip()
    amount = int(data.get("amount", 0))

    if not target:
        raise HTTPException(400, "Укажите ID или @username")

    target_id = None
    if target.startswith("@"):
        row = await get_user_by_username(target)
        if not row:
            raise HTTPException(404, "Пользователь не найден")
        target_id = row[0]
    else:
        try:
            target_id = int(target)
        except ValueError:
            raise HTTPException(400, "Некорректный ID")

    new_bal = await add_balance(target_id, amount)
    await log_admin_action(admin["id"], "give", target_id, str(amount))

    try:
        sign = "+" if amount >= 0 else ""
        await bot.send_message(
            target_id,
            f"🎁 Вам начислено <b>{sign}{amount:,}</b> 🪙\nБаланс: <b>{new_bal:,}</b> 🪙".replace(",", "."),
            parse_mode="HTML",
        )
    except Exception:
        pass

    return {"ok": True, "balance": new_bal}


@app.post("/api/admin/setbal")
async def api_admin_setbal(request: Request):
    data = await request.json()
    admin = admin_only(data.get("initData", ""))
    target = str(data.get("target", "")).strip()
    amount = int(data.get("amount", 0))

    target_id = None
    if target.startswith("@"):
        row = await get_user_by_username(target)
        if not row:
            raise HTTPException(404, "Пользователь не найден")
        target_id = row[0]
    else:
        try:
            target_id = int(target)
        except ValueError:
            raise HTTPException(400, "Некорректный ID")

    await set_balance(target_id, amount)
    await log_admin_action(admin["id"], "setbal", target_id, str(amount))
    return {"ok": True, "balance": amount}


@app.post("/api/admin/promos")
async def api_admin_promos(request: Request):
    data = await request.json()
    admin_only(data.get("initData", ""))
    rows = await list_promos()
    return {
        "promos": [
            {"code": p[0], "kind": p[1], "value": p[2], "max_uses": p[3], "used": p[4]}
            for p in rows
        ]
    }


@app.post("/api/admin/promo/create")
async def api_admin_promo_create(request: Request):
    data = await request.json()
    admin = admin_only(data.get("initData", ""))
    code = data.get("code", "").strip().upper()
    kind = data.get("kind", "coins")
    value = int(data.get("value", 0))
    max_uses = int(data.get("max_uses", 0))

    if not code or len(code) < 3:
        raise HTTPException(400, "Код от 3 символов")
    if kind not in ("coins", "discount"):
        raise HTTPException(400, "kind: coins или discount")
    if value <= 0:
        raise HTTPException(400, "value > 0")
    if kind == "discount" and value > 100:
        raise HTTPException(400, "Скидка ≤ 100")

    ok = await create_promo(code, kind, value, max_uses)
    if not ok:
        raise HTTPException(400, "Такой промокод уже есть")

    await log_admin_action(admin["id"], "create_promo", None, f"{code} {kind}={value}")
    return {"ok": True}


@app.post("/api/admin/promo/delete")
async def api_admin_promo_delete(request: Request):
    data = await request.json()
    admin = admin_only(data.get("initData", ""))
    code = data.get("code", "").strip().upper()
    ok = await delete_promo(code)
    if not ok:
        raise HTTPException(404, "Не найден")
    await log_admin_action(admin["id"], "delete_promo", None, code)
    return {"ok": True}


@app.post("/api/admin/logs")
async def api_admin_logs(request: Request):
    data = await request.json()
    admin_only(data.get("initData", ""))
    rows = await get_admin_logs(50)
    return {
        "logs": [
            {"admin_id": l[0], "action": l[1], "target_id": l[2],
             "details": l[3], "created_at": l[4]}
            for l in rows
        ]
    }


@app.post("/api/admin/broadcast")
async def api_admin_broadcast(request: Request):
    data = await request.json()
    admin = admin_only(data.get("initData", ""))
    text = data.get("text", "").strip()
    if not text:
        raise HTTPException(400, "Пустой текст")

    ids = await get_all_user_ids()
    sent, failed = 0, 0
    for uid in ids:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await log_admin_action(admin["id"], "broadcast", None, f"sent={sent} failed={failed}")
    return {"ok": True, "sent": sent, "failed": failed}


if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Запуск на порту {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
