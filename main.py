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
    has_deposited,
    add_user_item, get_user_items, get_user_item, sell_user_item,
    delete_user_item, get_user_items_stats,
    get_user_item_by_id, mark_items_sold,
    get_user_items_admin, transfer_item,
    get_free_case_info, claim_free_case,
    log_house_flow, get_house_stats,
)

WITHDRAW_RATE = 125
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
    await log_house_flow(wagered=bet, paid=win)
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
    await log_house_flow(wagered=total_bet, paid=total_win)
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
        await log_house_flow(wagered=bet, paid=0)
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
        await log_house_flow(wagered=game["bet"], paid=win)
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
    await log_house_flow(wagered=bet, paid=prize)
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

CRASH_EXP = 1.15
CRASH_MULT = 0.18


def crash_mult_from_elapsed(elapsed: float) -> float:
    return round(1.0 + (elapsed ** CRASH_EXP) * CRASH_MULT, 2)


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
    mult = crash_mult_from_elapsed(elapsed)

    if game["auto_cashout"] and mult >= game["auto_cashout"] and not game["cashed"]:
        game["cashed"] = True
        prize = int(game["bet"] * game["auto_cashout"])
        await add_balance(uid, prize)
        await log_game(uid, game["bet"], prize)
        await log_house_flow(wagered=game["bet"], paid=prize)
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
        await log_house_flow(wagered=bet, paid=0)
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
    mult = crash_mult_from_elapsed(elapsed)

    if mult >= game["crash_at"]:
        bet = game["bet"]
        del crash_games[uid]
        await log_game(uid, bet, 0)
        await log_house_flow(wagered=bet, paid=0)
        raise HTTPException(400, "crashed")

    prize = int(game["bet"] * mult)
    bet = game["bet"]
    del crash_games[uid]
    await add_balance(uid, prize)
    await log_game(uid, bet, prize)
    await log_house_flow(wagered=bet, paid=prize)
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

    if choice in ("low", "range_1_3"):
        if roll <= 3:
            mult = 1.95
            win = int(bet * mult)
    elif choice in ("high", "range_4_6"):
        if roll >= 4:
            mult = 1.95
            win = int(bet * mult)
    elif choice == "range_4_6_plus":
        if roll >= 4:
            mult = 2.9
            win = int(bet * mult)
    elif choice in ("exact", "range_6_6"):
        if roll == 6:
            mult = 5.7
            win = int(bet * mult)
    elif choice == "exact_number":
        if roll == exact:
            mult = 5.0
            win = int(bet * mult)

    if win > 0:
        await add_balance(uid, win)
    await log_game(uid, bet, win)
    await log_house_flow(wagered=bet, paid=win)
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
        await log_house_flow(wagered=bet, paid=0)
        return {"shot": True, "bet": bet, "balance": await get_balance(uid)}

    step += 1
    game["step"] = step

    if step >= 6:
        prize = int(game["bet"] * RR_MULTS[5])
        bet = game["bet"]
        del rr_games[uid]
        await add_balance(uid, prize)
        await log_game(uid, bet, prize)
        await log_house_flow(wagered=bet, paid=prize)
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
    await log_house_flow(wagered=bet, paid=prize)
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
    await log_house_flow(wagered=bet, paid=win)
    nb = await get_balance(uid)

    await unlock_achievement(uid, "first_bet")
    if win > bet:
        await unlock_achievement(uid, "first_win")
    if win >= 100000:
        await unlock_achievement(uid, "big_win")

    return {"slot": slot, "mult": mult, "win": win, "balance": nb}


# ═══════════ PENALTI ═══════════

penalti_games: dict = {}
PENALTI_TIMEOUT = 300
PENALTI_MULTS = [1.6, 2.2, 3.0, 4.5, 7.0]

PENALTI_KEEPER_WEIGHTS = [3, 5, 3, 5, 8, 5, 3, 5, 3]
PENALTI_SMARTNESS = [0.20, 0.30, 0.45, 0.60, 0.75]


def _keeper_pick_zone(step: int) -> int:
    smart = PENALTI_SMARTNESS[min(step, len(PENALTI_SMARTNESS) - 1)]
    weights = []
    for i, w in enumerate(PENALTI_KEEPER_WEIGHTS):
        if w >= 4:
            weights.append(w * (1 + smart * 2))
        elif w <= 3:
            weights.append(w * (1 - smart * 0.5))
        else:
            weights.append(w)
    total = sum(weights)
    r = random.random() * total
    cum = 0
    for i, w in enumerate(weights):
        cum += w
        if r <= cum:
            return i
    return 4


def cleanup_penalti():
    now = time.time()
    for uid in list(penalti_games.keys()):
        game = penalti_games.get(uid)
        if not game:
            continue
        if now - game.get("started", now) > PENALTI_TIMEOUT:
            del penalti_games[uid]


@app.post("/api/penalti/start")
async def api_penalti_start(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))

    cleanup_penalti()

    existing = penalti_games.get(uid)
    if existing and existing.get("step", 0) == 0:
        await add_balance(uid, existing["bet"])
        del penalti_games[uid]

    if uid in penalti_games:
        raise HTTPException(400, "already_playing")
    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)
    penalti_games[uid] = {
        "bet": bet,
        "step": 0,
        "history": [],
        "started": time.time(),
    }
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

    keeper_zone = _keeper_pick_zone(step)
    is_save = (keeper_zone == zone)

    if is_save:
        bet = game["bet"]
        del penalti_games[uid]
        await log_game(uid, bet, 0)
        await log_house_flow(wagered=bet, paid=0)
        return {
            "goal": False, "save": True,
            "zone": zone, "keeper_zone": keeper_zone,
            "step": step, "bet": bet,
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
        await log_house_flow(wagered=bet, paid=prize)
        await unlock_achievement(uid, "first_bet")
        await unlock_achievement(uid, "first_win")
        if prize >= 100000:
            await unlock_achievement(uid, "big_win")
        return {
            "goal": True, "save": False,
            "zone": zone, "keeper_zone": keeper_zone,
            "step": step, "maxed": True,
            "mult": mult, "prize": prize,
            "balance": await get_balance(uid),
        }

    return {
        "goal": True, "save": False,
        "zone": zone, "keeper_zone": keeper_zone,
        "step": step, "maxed": False,
        "mult": mult, "prize": prize,
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
    await log_house_flow(wagered=bet, paid=prize)
    await unlock_achievement(uid, "first_bet")
    return {"prize": prize, "mult": mult, "balance": await get_balance(uid)}


@app.post("/api/penalti/reset")
async def api_penalti_reset(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    game = penalti_games.pop(uid, None)
    if game:
        await add_balance(uid, game["bet"])
    return {"balance": await get_balance(uid)}



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
    await log_house_flow(wagered=bet, paid=win)
    nb = await get_balance(uid)
    await unlock_achievement(uid, "first_bet")
    if win > 0:
        await unlock_achievement(uid, "first_win")

    return {"result": result, "win": win, "mult": mult, "balance": nb}


# ═══════════ PVP ДУЭЛЬ ═══════════

duel_queue: list[dict] = []
duel_active: dict[str, dict] = {}
DUEL_QUEUE_TIMEOUT = 120
DUEL_ACTIVE_TIMEOUT = 300


def cleanup_duel():
    now = time.time()
    for i in range(len(duel_queue) - 1, -1, -1):
        q = duel_queue[i]
        if now - q.get("joined", now) > DUEL_QUEUE_TIMEOUT:
            duel_queue.pop(i)
    for did in list(duel_active.keys()):
        g = duel_active.get(did)
        if not g:
            continue
        if now - g.get("created", now) > DUEL_ACTIVE_TIMEOUT:
            del duel_active[did]


@app.post("/api/duel/join")
async def api_duel_join(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))

    cleanup_duel()

    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")

    for i in range(len(duel_queue) - 1, -1, -1):
        if duel_queue[i]["uid"] == uid:
            duel_queue.pop(i)

    for did, g in list(duel_active.items()):
        if uid in (g["p1"], g["p2"]):
            if uid in g.get("claimed", set()):
                del duel_active[did]
            else:
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
        "p1": uid, "p2": opponent["uid"], "bet": bet,
        "winner": winner, "prize": prize,
        "created": time.time(), "claimed": set(),
    }

    await add_balance(winner, prize)
    await log_game(uid, bet, prize if winner == uid else 0)
    await log_game(opponent["uid"], bet, prize if winner == opponent["uid"] else 0)
    await log_house_flow(wagered=bet * 2, paid=prize)
    await unlock_achievement(uid, "first_bet")
    await unlock_achievement(opponent["uid"], "first_bet")
    if winner == uid:
        await unlock_achievement(uid, "first_win")
    else:
        await unlock_achievement(opponent["uid"], "first_win")

    for player_uid, is_winner in [(uid, winner == uid), (opponent["uid"], winner == opponent["uid"])]:
        try:
            if is_winner:
                await bot.send_message(player_uid,
                    f"🏆 <b>Победа в дуэли!</b>\n\nСтавка: <b>{bet}</b> 🪙\nВыигрыш: <b>+{prize}</b> 🪙",
                    parse_mode="HTML")
            else:
                await bot.send_message(player_uid,
                    f"😢 <b>Поражение в дуэли</b>\n\nСтавка: <b>{bet}</b> 🪙 сгорела",
                    parse_mode="HTML")
        except Exception:
            pass

    return {
        "status": "matched", "duel_id": duel_id, "winner": winner,
        "you_win": winner == uid, "prize": prize,
        "opponent_id": opponent["uid"], "balance": await get_balance(uid),
    }


@app.post("/api/duel/status")
async def api_duel_status(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]

    cleanup_duel()

    for did, g in list(duel_active.items()):
        if uid in (g["p1"], g["p2"]) and uid not in g["claimed"]:
            g["claimed"].add(uid)
            return {
                "status": "matched", "duel_id": did,
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
    for i in range(len(duel_queue) - 1, -1, -1):
        if duel_queue[i]["uid"] == uid:
            duel_queue.pop(i)
            return {"status": "left"}
    return {"status": "not_in_queue"}


@app.post("/api/duel/cancel")
async def api_duel_cancel(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    cleanup_duel()
    for i in range(len(duel_queue) - 1, -1, -1):
        if duel_queue[i]["uid"] == uid:
            duel_queue.pop(i)
    return {"status": "ok"}


# ═══════════ CASE SYSTEM ═══════════

RARITY_TABLE = [
    ("common",    "⬜", "Обычный",     6500, 0.40),
    ("uncommon",  "🟩", "Необычный",   2300, 0.75),
    ("rare",      "🟦", "Редкий",       800, 1.60),
    ("epic",      "🟪", "Эпический",    300, 3.80),
    ("legendary", "🟨", "Легендарный",   85, 11.00),
    ("mythic",    "🟥", "Мифический",    15, 35.00),
]

ITEMS_BY_RARITY = {
    "common": [
        ("cherry",   "🍒", "Вишня"),
        ("lemon",    "🍋", "Лимон"),
        ("orange",   "🍊", "Апельсин"),
        ("grape",    "🍇", "Виноград"),
        ("coin",     "🪙", "Монетка"),
    ],
    "uncommon": [
        ("gem",      "💎", "Самоцвет"),
        ("star",     "⭐", "Звезда"),
        ("clover",   "🍀", "Клевер"),
        ("bell",     "🔔", "Колокольчик"),
        ("horseshoe","🧲", "Подкова"),
    ],
    "rare": [
        ("seven",    "7️⃣", "Семёрка"),
        ("money",    "🤑", "Денежный"),
        ("crown",    "👑", "Корона"),
        ("trophy",   "🏆", "Кубок"),
        ("ring",     "💍", "Кольцо"),
    ],
    "epic": [
        ("rocket",   "🚀", "Ракета"),
        ("diamond",  "💠", "Алмаз"),
        ("skull",    "💀", "Череп"),
        ("alien",    "👽", "Пришелец"),
        ("robot",    "🤖", "Робот"),
    ],
    "legendary": [
        ("dragon",   "🐉", "Дракон"),
        ("phoenix",  "🦅", "Феникс"),
        ("unicorn",  "🦄", "Единорог"),
        ("galaxy",   "🌌", "Галактика"),
        ("fire",     "🔥", "Пламя"),
    ],
    "mythic": [
        ("blackhole","🕳️", "Чёрная дыра"),
        ("cosmos",   "🌠", "Космос"),
        ("infinite", "♾️", "Бесконечность"),
        ("god",      "⚡", "Молния Бога"),
        ("void",     "🔮", "Пустота"),
    ],
}

CASES = [
    # ═══ БАЗОВЫЕ (1-31) ═══
    ("starter",       "Стартовый",        "📦",  10, "Первый шаг в мир кейсов"),
    ("bronze",        "Бронзовый",        "🥉",  20, "Для начинающих игроков"),
    ("silver",        "Серебряный",       "🥈",  30, "Немного серьёзнее"),
    ("gold",          "Золотой",          "🥇",  50, "Классика жанра"),
    ("lucky",         "Счастливый",       "🍀",  75, "Клевер на удачу"),
    ("diamond_small", "Малый Алмаз",      "💎", 100, "Блеск и шик"),
    ("emerald",       "Изумрудный",       "💚", 150, "Зелёная волна"),
    ("sapphire",      "Сапфировый",       "💙", 200, "Синяя бездна"),
    ("ruby",          "Рубиновый",        "❤️", 250, "Огненный рубин"),
    ("amethyst",      "Аметистовый",      "💜", 300, "Фиолетовый туман"),
    ("topaz",         "Топазовый",        "🧡", 350, "Тёплый топаз"),
    ("opal",          "Опаловый",         "🤍", 400, "Лунный камень"),
    ("onyx",          "Ониксовый",        "🖤", 450, "Чёрный оникс"),
    ("pearl",         "Жемчужный",        "🦪", 500, "Глубины океана"),
    ("dragon_egg",    "Яйцо Дракона",     "🥚", 750, "Что внутри?"),
    ("phoenix_fire",  "Пламя Феникса",    "🔥", 900, "Возрождение"),
    ("ice_crystal",   "Ледяной Кристалл", "❄️",1000, "Вечный холод"),
    ("storm",         "Штормовой",        "🌩️",1200, "Гроза морей"),
    ("volcano",       "Вулканический",    "🌋",1500, "Раскалённая лава"),
    ("abyss",         "Бездна",           "🕳️",1800, "Тёмная сторона"),
    ("galaxy",        "Галактический",    "🌌",2500, "Звёздная пыль"),
    ("nebula",        "Туманность",       "🌠",3000, "Космический туман"),
    ("supernova",     "Сверхновая",       "💥",3500, "Взрыв звезды"),
    ("black_hole",    "Чёрная Дыра",      "⚫",4000, "Гравитация вне закона"),
    ("quantum",       "Квантовый",        "🔬",4500, "Микро и макро"),
    ("infinity",      "Бесконечность",    "♾️",5000, "Предела нет"),
    ("chronos",       "Хронос",           "⏳",5500, "Власть над временем"),
    ("poseidon",      "Посейдон",         "🔱",6000, "Гнев морей"),
    ("zeus",          "Зевс",             "⚡",7000, "Повелитель молний"),
    ("olympus",       "Олимп",            "🏔️",8000, "Обитель богов"),
    ("titan",         "Титан",            "🗿",10000, "Древняя сила"),

    # ═══ ДОПОЛНИТЕЛЬНЫЕ 70 (32-101) ═══
    ("k_mecha",       "Механический",     "⚙️", 12000, "Железо и сталь"),
    ("k_neon",        "Неоновый",         "💡", 13000, "Свет большого города"),
    ("k_cyber",       "Киберпанк",        "🤖", 14000, "Будущее уже здесь"),
    ("k_matrix",      "Матрица",          "🟢", 15000, "Зелёная таблетка"),
    ("k_phantom",     "Фантом",           "👻", 16000, "Призрак в машине"),
    ("k_wraith",      "Призрак",          "💨", 17000, "Невидимый враг"),
    ("k_hydra",       "Гидра",            "🐍", 18000, "Многоголовая"),
    ("k_griffin",     "Грифон",           "🦁", 19000, "Царь зверей и птиц"),
    ("k_wyvern",      "Виверна",          "🐲", 20000, "Огненное дыхание"),
    ("k_kraken",      "Кракен",           "🦑", 22000, "Морское чудовище"),
    ("k_leviathan",   "Левиафан",         "🐋", 25000, "Властелин глубин"),
    ("k_behemoth",    "Бегемот",          "🐘", 28000, "Древний титан"),
    ("k_cerberus",    "Цербер",           "🐕", 30000, "Страж врат"),
    ("k_hades",       "Аид",              "💀", 35000, "Царство мёртвых"),
    ("k_anubis",      "Анубис",           "🐺", 40000, "Египетский бог"),
    ("k_ra",          "Ра",               "☀️", 45000, "Солнечный бог"),
    ("k_isis",        "Изида",            "🌙", 50000, "Лунная богиня"),
    ("k_osiris",      "Осирис",           "🌿", 55000, "Бог возрождения"),
    ("k_thor",        "Тор",              "🔨", 60000, "Бог грома"),
    ("k_odin",        "Один",             "👁️", 65000, "Отец богов"),
    ("k_loki",        "Локи",             "🎭", 70000, "Бог обмана"),
    ("k_freya",       "Фрейя",            "🌸", 75000, "Богиня любви"),
    ("k_tyr",         "Тюр",              "⚔️", 80000, "Бог войны"),
    ("k_balder",      "Бальдр",           "✨", 85000, "Светлый бог"),
    ("k_hel",         "Хель",             "🌑", 90000, "Владычица теней"),
    ("k_ymir",        "Имир",             "🧊", 95000, "Ледяной великан"),
    ("k_surt",        "Сурт",             "🔥", 100000, "Огненный великан"),
    ("k_fenrir",      "Фенрир",           "🐺", 110000, "Волк апокалипсиса"),
    ("k_jormung",     "Йормунганд",       "🐍", 120000, "Мировой змей"),
    ("k_nidhogg",     "Нидхёгг",          "🐉", 130000, "Пожиратель корней"),
    ("k_valkyrie",    "Валькирия",        "🦅", 140000, "Дева-воительница"),
    ("k_einherjar",   "Эйнхерии",         "🛡️", 150000, "Воины Вальгаллы"),
    ("k_berserk",     "Берсерк",          "🪓", 160000, "Ярость без границ"),
    ("k_viking",      "Викинг",           "⛵", 170000, "Сын севера"),
    ("k_rune",        "Руны",             "ᚱ", 180000, "Древние знаки"),
    ("k_seidr",       "Сейдр",            "🔮", 200000, "Магия судьбы"),
    ("k_yggdrasil",   "Иггдрасиль",       "🌳", 220000, "Древо жизни"),
    ("k_asgard",      "Асгард",           "🏰", 250000, "Город богов"),
    ("k_bifrost",     "Биврёст",          "🌈", 280000, "Радужный мост"),
    ("k_ragnarok",    "Рагнарёк",         "💥", 300000, "Конец света"),
    ("k_apocalypse",  "Апокалипсис",      "☄️", 350000, "Последний день"),
    ("k_armageddon",  "Армагеддон",       "🌋", 400000, "Великая битва"),
    ("k_extinction",  "Вымирание",        "🦖", 450000, "Древние ящеры"),
    ("k_evolution",   "Эволюция",         "🧬", 500000, "Скачок развития"),
    ("k_singularity", "Сингулярность",    "🕳️", 600000, "Точка невозврата"),
    ("k_multiverse",  "Мультивселенная",  "🌀", 700000, "Мир во всех мирах"),
    ("k_omniverse",   "Омниверс",         "♾️", 800000, "Всё сущее"),
    ("k_creator",     "Создатель",        "🌟", 1000000, "Творец миров"),
    ("k_architect",   "Архитектор",       "🏛️", 1100000, "Строитель реальности"),
    ("k_eternity",    "Вечность",         "⏳", 1200000, "Бесконечное время"),
    ("k_oblivion",    "Забвение",         "⚫", 1300000, "Пустота и ничто"),
    ("k_chaos",       "Хаос",             "🌪️", 1400000, "Первозданный хаос"),
    ("k_order",       "Порядок",          "⚖️", 1500000, "Закон вселенной"),
    ("k_light",       "Свет",             "🔆", 1600000, "Начало всего"),
    ("k_darkness",    "Тьма",             "🌑", 1700000, "Изначальная тьма"),
    ("k_life",        "Жизнь",            "🌱", 1800000, "Искра бытия"),
    ("k_death",       "Смерть",           "💀", 1900000, "Конец пути"),
    ("k_rebirth",     "Перерождение",     "🦋", 2000000, "Новый цикл"),
    ("k_ascension",   "Вознесение",       "⛰️", 2200000, "Путь наверх"),
    ("k_enlighten",   "Просветление",     "🧘", 2400000, "Истина внутри"),
    ("k_nirvana",     "Нирвана",          "🕉️", 2600000, "Освобождение"),
    ("k_zenith",      "Зенит",            "🎯", 2800000, "Высшая точка"),
    ("k_apex",        "Апекс",            "🏔️", 3000000, "Вершина мира"),
    ("k_alpha",       "Альфа",            "🅰️", 3500000, "Начало"),
    ("k_omega",       "Омега",            "🅾️", 4000000, "Конец"),
    ("k_legend",      "Легенда",          "📜", 4500000, "История веков"),
    ("k_myth",        "Миф",              "🐲", 5000000, "Древнее сказание"),
    ("k_epic",        "Эпос",             "🎭", 5500000, "Героическая песнь"),
    ("k_saga",        "Сага",             "📖", 6000000, "Хроники героев"),
    ("k_universe",    "Вселенная",        "🌌", 7000000, "Всё и вся"),
]


def _pick_random_rarity():
    total_w = sum(r[3] for r in RARITY_TABLE)
    r = random.randint(1, total_w)
    cum = 0
    for rar in RARITY_TABLE:
        cum += rar[3]
        if r <= cum:
            return rar
    return RARITY_TABLE[0]


def _roll_case(case_id: str):
    rarity = _pick_random_rarity()
    rarity_id, rarity_emoji, rarity_name, _, value_mult = rarity
    items = ITEMS_BY_RARITY[rarity_id]
    item_id, emoji, name = random.choice(items)
    return item_id, rarity_id, rarity_emoji, rarity_name, emoji, name, value_mult


def _build_track(case_id: str, price_coins: int, win_item: dict):
    TRACK_LEN = 60
    WIN_POS = 55
    track = []
    for i in range(TRACK_LEN):
        if i == WIN_POS:
            track.append({**win_item, "is_win": True})
            continue
        rar = _pick_random_rarity()
        rar_id, rar_emoji, rar_name, _, rar_mult = rar
        items = ITEMS_BY_RARITY[rar_id]
        _iid, iemoji, iname = random.choice(items)
        fake_price = int(price_coins * rar_mult)
        track.append({
            "emoji": iemoji,
            "name": iname,
            "rarity": rar_id,
            "rarity_name": rar_name,
            "rarity_emoji": rar_emoji,
            "value": fake_price,
            "is_win": False,
        })
    return track, WIN_POS


@app.post("/api/cases/list")
async def api_cases_list(request: Request):
    data = await request.json()
    validate_init_data(data.get("initData", ""))
    return {
        "cases": [
            {
                "id": c[0],
                "name": c[1],
                "emoji": c[2],
                "price_stars": c[3],
                "price_coins": c[3] * RATE,
                "desc": c[4],
            }
            for c in CASES
        ]
    }


@app.post("/api/cases/info")
async def api_cases_info(request: Request):
    data = await request.json()
    validate_init_data(data.get("initData", ""))
    case_id = data.get("case_id", "")

    case = next((c for c in CASES if c[0] == case_id), None)
    if not case:
        raise HTTPException(400, "Кейс не найден")

    price_coins = case[3] * RATE

    total_w = sum(r[3] for r in RARITY_TABLE)
    items = []
    for rar_id, rar_emoji, rar_name, weight, value_mult in RARITY_TABLE:
        rarity_chance = weight / total_w
        for item_id, emoji, name in ITEMS_BY_RARITY[rar_id]:
            item_chance = rarity_chance / len(ITEMS_BY_RARITY[rar_id])
            value = int(price_coins * value_mult)
            items.append({
                "item_id": item_id,
                "emoji": emoji,
                "name": name,
                "rarity": rar_id,
                "rarity_name": rar_name,
                "rarity_emoji": rar_emoji,
                "value": value,
                "chance": round(item_chance * 100, 3),
            })

    items.sort(key=lambda x: -x["value"])

    return {
        "case_id": case_id,
        "name": case[1],
        "emoji": case[2],
        "price_stars": case[3],
        "price_coins": price_coins,
        "desc": case[4],
        "items": items,
    }


@app.post("/api/cases/spin")
async def api_cases_spin(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    case_id = data.get("case_id", "")

    case = next((c for c in CASES if c[0] == case_id), None)
    if not case:
        raise HTTPException(400, "Кейс не найден")

    price_coins = case[3] * RATE
    balance = await get_balance(uid)
    if balance < price_coins:
        raise HTTPException(400, f"Нужно {price_coins} 🪙")

    await add_balance(uid, -price_coins)

    item_id, rarity_id, rarity_emoji, rarity_name, emoji, name, value_mult = _roll_case(case_id)
    value = int(price_coins * value_mult)
    kind = "nft" if rarity_id in ("epic", "legendary", "mythic") else "gift"

    await add_user_item(uid, item_id, case_id, rarity_id, emoji, name, value, kind=kind)
    await log_game(uid, price_coins, 0)
    await log_house_flow(wagered=price_coins, paid=0)
    await unlock_achievement(uid, "first_bet")
    if rarity_id in ("epic", "legendary", "mythic"):
        await unlock_achievement(uid, "big_win")
    if rarity_id == "mythic":
        await unlock_achievement(uid, "jackpot")

    win_item = {
        "emoji": emoji,
        "name": name,
        "rarity": rarity_id,
        "rarity_name": rarity_name,
        "rarity_emoji": rarity_emoji,
        "value": value,
    }
    track, win_pos = _build_track(case_id, price_coins, win_item)

    return {
        "track": track,
        "win_pos": win_pos,
        "result": {
            "case_id": case_id,
            "item_id": item_id,
            "rarity": rarity_id,
            "rarity_name": rarity_name,
            "rarity_emoji": rarity_emoji,
            "emoji": emoji,
            "name": name,
            "value": value,
            "kind": kind,
        },
        "balance": await get_balance(uid),
    }


@app.post("/api/cases/spin_multi")
async def api_cases_spin_multi(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    case_id = data.get("case_id", "")
    count = int(data.get("count", 1))

    if count not in (2, 3, 5, 10):
        raise HTTPException(400, "count: 2/3/5/10")

    case = next((c for c in CASES if c[0] == case_id), None)
    if not case:
        raise HTTPException(400, "Кейс не найден")

    price_coins = case[3] * RATE
    total_cost = price_coins * count
    balance = await get_balance(uid)
    if balance < total_cost:
        raise HTTPException(400, f"Нужно {total_cost} 🪙")

    await add_balance(uid, -total_cost)

    results = []
    for _ in range(count):
        item_id, rarity_id, rarity_emoji, rarity_name, emoji, name, value_mult = _roll_case(case_id)
        value = int(price_coins * value_mult)
        kind = "nft" if rarity_id in ("epic", "legendary", "mythic") else "gift"

        await add_user_item(uid, item_id, case_id, rarity_id, emoji, name, value, kind=kind)

        results.append({
            "item_id": item_id,
            "rarity": rarity_id,
            "rarity_name": rarity_name,
            "rarity_emoji": rarity_emoji,
            "emoji": emoji,
            "name": name,
            "value": value,
            "kind": kind,
        })

    await log_game(uid, total_cost, 0)
    await log_house_flow(wagered=total_cost, paid=0)
    await unlock_achievement(uid, "first_bet")

    best = max(results, key=lambda r: r["value"])
    win_item = {
        "emoji": best["emoji"],
        "name": best["name"],
        "rarity": best["rarity"],
        "rarity_name": best["rarity_name"],
        "rarity_emoji": best["rarity_emoji"],
        "value": best["value"],
    }
    track, win_pos = _build_track(case_id, price_coins, win_item)

    return {
        "track": track,
        "win_pos": win_pos,
        "results": results,
        "best": best,
        "count": count,
        "total_cost": total_cost,
        "balance": await get_balance(uid),
    }


@app.post("/api/cases/open")
async def api_cases_open(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    case_id = data.get("case_id", "")

    case = next((c for c in CASES if c[0] == case_id), None)
    if not case:
        raise HTTPException(400, "Кейс не найден")

    price_coins = case[3] * RATE
    balance = await get_balance(uid)
    if balance < price_coins:
        raise HTTPException(400, f"Нужно {price_coins} 🪙")

    await add_balance(uid, -price_coins)

    item_id, rarity_id, rarity_emoji, rarity_name, emoji, name, value_mult = _roll_case(case_id)
    value = int(price_coins * value_mult)
    kind = "nft" if rarity_id in ("epic", "legendary", "mythic") else "gift"

    await add_user_item(uid, item_id, case_id, rarity_id, emoji, name, value, kind=kind)
    await log_game(uid, price_coins, 0)
    await log_house_flow(wagered=price_coins, paid=0)
    await unlock_achievement(uid, "first_bet")

    return {
        "case_id": case_id,
        "item_id": item_id,
        "rarity": rarity_id,
        "rarity_name": rarity_name,
        "rarity_emoji": rarity_emoji,
        "emoji": emoji,
        "name": name,
        "value": value,
        "kind": kind,
        "balance": await get_balance(uid),
    }


@app.post("/api/cases/inventory")
async def api_cases_inventory(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    items = await get_user_items(uid, 200, only_unsold=True)
    stats = await get_user_items_stats(uid)
    return {
        "items": [
            {
                "id": i[0], "item_id": i[1], "case_id": i[2],
                "rarity": i[3], "emoji": i[4], "name": i[5],
                "value": i[6], "kind": i[7], "created_at": i[8],
            }
            for i in items
        ],
        "stats": stats,
    }


@app.post("/api/cases/sell")
async def api_cases_sell(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    item_pk = int(data.get("item_pk", 0))

    item = await get_user_item(item_pk, uid)
    if not item or item[8] == 1:
        raise HTTPException(400, "Предмет не найден или уже продан")

    sold = await sell_user_item(item_pk, uid)
    if not sold:
        raise HTTPException(400, "Не удалось продать")

    value = item[6]
    new_balance = await add_balance(uid, value)
    return {"ok": True, "sold_value": value, "balance": new_balance}


@app.post("/api/cases/sell_all")
async def api_cases_sell_all(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]

    items = await get_user_items(uid, 500, only_unsold=True)
    total = 0
    count = 0
    for it in items:
        pk = it[0]
        value = it[6]
        sold = await sell_user_item(pk, uid)
        if sold:
            total += value
            count += 1

    new_balance = await add_balance(uid, total) if total > 0 else await get_balance(uid)
    return {"ok": True, "count": count, "total": total, "balance": new_balance}


# ═══════════ UPGRADER ═══════════

UPGRADER_TARGETS = [
    ("🍒", "Вишня",       "common",    50),
    ("🍋", "Лимон",       "common",    100),
    ("🍊", "Апельсин",    "common",    200),
    ("🍇", "Виноград",    "common",    400),
    ("💎", "Самоцвет",    "uncommon",  800),
    ("⭐", "Звезда",      "uncommon", 1500),
    ("🍀", "Клевер",      "uncommon", 2500),
    ("🔔", "Колокольчик", "uncommon", 4000),
    ("7️⃣", "Семёрка",     "rare",     6000),
    ("🤑", "Денежный",    "rare",     8000),
    ("👑", "Корона",      "rare",    12000),
    ("🏆", "Кубок",       "rare",    18000),
    ("🚀", "Ракета",      "epic",    25000),
    ("💠", "Алмаз",       "epic",    35000),
    ("💀", "Череп",       "epic",    50000),
    ("🐉", "Дракон",      "legendary", 100000),
    ("🦅", "Феникс",      "legendary", 150000),
    ("🦄", "Единорог",    "legendary", 250000),
    ("🌌", "Галактика",   "legendary", 500000),
    ("🌠", "Космос",      "mythic",   1000000),
    ("♾️", "Бесконечность","mythic",  2000000),
]


@app.post("/api/upgrader/targets")
async def api_upgrader_targets(request: Request):
    data = await request.json()
    validate_init_data(data.get("initData", ""))
    return {
        "targets": [
            {
                "emoji": t[0],
                "name": t[1],
                "rarity": t[2],
                "price_stars": t[3],
                "price_coins": t[3] * RATE,
            }
            for t in UPGRADER_TARGETS
        ]
    }


@app.post("/api/upgrader/play")
async def api_upgrader_play(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]

    item_pks = data.get("item_pks", [])
    target_idx = int(data.get("target_idx", -1))

    if not item_pks:
        raise HTTPException(400, "Выбери хотя бы один предмет")
    if target_idx < 0 or target_idx >= len(UPGRADER_TARGETS):
        raise HTTPException(400, "Неверная цель")

    total_value = 0
    for pk in item_pks:
        it = await get_user_item(pk, uid)
        if not it or it[8] == 1:
            raise HTTPException(400, "Предмет не найден или уже продан")
        total_value += it[6]

    target = UPGRADER_TARGETS[target_idx]
    target_price_coins = target[3] * RATE

    if total_value <= 0:
        raise HTTPException(400, "Некорректная ставка")

    # ⚠️ Защита: цель должна быть дороже ставки
    if target_price_coins <= total_value:
        raise HTTPException(
            400,
            "Цель дешевле твоей ставки — так нельзя"
        )

    chance = total_value / target_price_coins
    chance = max(0.01, min(0.95, chance))

    roll = random.random()
    win = roll < chance

    await mark_items_sold(item_pks, uid)

    if win:
        await add_user_item(
            uid,
            f"upgrade_{target_idx}",
            "upgrader",
            target[2],
            target[0],
            target[1],
            target_price_coins,
            kind="nft" if target[2] in ("epic", "legendary", "mythic") else "gift",
        )
        result_item = {
            "emoji": target[0],
            "name": target[1],
            "rarity": target[2],
            "value": target_price_coins,
        }
    else:
        result_item = None

    await log_game(uid, total_value, target_price_coins if win else 0)
    await log_house_flow(wagered=total_value, paid=target_price_coins if win else 0)

    return {
        "win": win,
        "chance": round(chance * 100, 2),
        "total_value": total_value,
        "target": {
            "emoji": target[0],
            "name": target[1],
            "rarity": target[2],
            "price_coins": target_price_coins,
        },
        "result_item": result_item,
        "balance": await get_balance(uid),
    }


# ═══════════ БЕСПЛАТНЫЙ КЕЙС ═══════════

FREE_CASE_COOLDOWN = 24 * 60 * 60
FREE_CASE_BASE_PRICE = 50 * RATE
FREE_CASE_ALLOWED_RARITIES = ("common", "uncommon", "rare", "epic")


def _roll_free_case():
    table = [r for r in RARITY_TABLE if r[0] in FREE_CASE_ALLOWED_RARITIES]
    total_w = sum(r[3] for r in table)
    r = random.randint(1, total_w)
    cum = 0
    chosen = table[0]
    for rar in table:
        cum += rar[3]
        if r <= cum:
            chosen = rar
            break
    rarity_id, rarity_emoji, rarity_name, _, value_mult = chosen
    items = ITEMS_BY_RARITY[rarity_id]
    item_id, emoji, name = random.choice(items)
    return item_id, rarity_id, rarity_emoji, rarity_name, emoji, name, value_mult


@app.post("/api/cases/free/status")
async def api_cases_free_status(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]

    last, streak = await get_free_case_info(uid)
    now = datetime.datetime.utcnow()

    can_claim = True
    seconds_left = 0
    if last:
        try:
            last_dt = datetime.datetime.fromisoformat(last)
            delta = (now - last_dt).total_seconds()
            if delta < FREE_CASE_COOLDOWN:
                can_claim = False
                seconds_left = int(FREE_CASE_COOLDOWN - delta)
        except (ValueError, TypeError):
            pass

    return {"can_claim": can_claim, "seconds_left": seconds_left, "streak": streak}


@app.post("/api/cases/free/open")
async def api_cases_free_open(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]

    if not await has_deposited(uid, min_stars=10):
        raise HTTPException(400, "Бесплатный кейс доступен после пополнения на 10+ ⭐")

    last, streak = await get_free_case_info(uid)
    now = datetime.datetime.utcnow()

    if last:
        try:
            last_dt = datetime.datetime.fromisoformat(last)
            if (now - last_dt).total_seconds() < FREE_CASE_COOLDOWN:
                raise HTTPException(400, "Бесплатный кейс пока недоступен")
        except (ValueError, TypeError):
            pass

    new_streak = streak + 1
    if last:
        try:
            last_dt = datetime.datetime.fromisoformat(last)
            if (now - last_dt).total_seconds() > FREE_CASE_COOLDOWN * 2:
                new_streak = 1
        except (ValueError, TypeError):
            new_streak = 1

    streak_mult = 1.0 + min(new_streak - 1, 6) * (1.0 / 6.0)

    item_id, rarity_id, rarity_emoji, rarity_name, emoji, name, value_mult = _roll_free_case()
    base_value = int(FREE_CASE_BASE_PRICE * value_mult * streak_mult)
    kind = "nft" if rarity_id == "epic" else "gift"

    await add_user_item(uid, item_id, "free_daily", rarity_id, emoji, name, base_value, kind=kind)
    await claim_free_case(uid, new_streak)

    if rarity_id == "epic":
        await unlock_achievement(uid, "big_win")

    return {
        "case_id": "free_daily",
        "item_id": item_id,
        "rarity": rarity_id,
        "rarity_name": rarity_name,
        "rarity_emoji": rarity_emoji,
        "emoji": emoji,
        "name": name,
        "value": base_value,
        "kind": kind,
        "streak": new_streak,
        "streak_mult": round(streak_mult, 2),
        "balance": await get_balance(uid),
    }


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

    if not await has_deposited(uid, min_stars=10):
        raise HTTPException(
            400,
            "Ежедневный бонус доступен только после пополнения на 10+ ⭐"
        )

    last, streak = await get_daily_info(uid)
    now = datetime.datetime.utcnow()

    if last:
        try:
            last_dt = datetime.datetime.fromisoformat(last)
            if (now - last_dt).total_seconds() < 86400:
                raise HTTPException(400, "Уже получен сегодня")
        except (ValueError, TypeError):
            pass

    reward = 200 + min(streak, 7) * 50
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
    h = await get_house_stats()
    return {
        "users": s["users"],
        "coins": s["coins"],
        "withdrawals": s["withdrawals"],
        "withdraw_stars": s["withdraw_stars"],
        "top": [
            {"user_id": u[0], "username": u[1] or f"user_{u[0]}", "balance": u[2]}
            for u in s["top"]
        ],
        "house": h,
    }


@app.post("/api/admin/house")
async def api_admin_house(request: Request):
    data = await request.json()
    admin_only(data.get("initData", ""))
    return await get_house_stats()


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


@app.post("/api/admin/user_inventory")
async def api_admin_user_inventory(request: Request):
    data = await request.json()
    admin = admin_only(data.get("initData", ""))
    target = str(data.get("target", "")).strip()

    if not target:
        raise HTTPException(400, "Укажи ID или @username")

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

    items = await get_user_items_admin(target_id, 200)
    return {
        "user_id": target_id,
        "items": [
            {
                "id": i[0], "item_id": i[1], "case_id": i[2],
                "rarity": i[3], "emoji": i[4], "name": i[5],
                "value": i[6], "kind": i[7], "created_at": i[8],
            }
            for i in items
        ],
    }


@app.post("/api/admin/steal_item")
async def api_admin_steal_item(request: Request):
    data = await request.json()
    admin = admin_only(data.get("initData", ""))
    item_pk = int(data.get("item_pk", 0))
    from_user_id = int(data.get("from_user_id", 0))

    if not item_pk or not from_user_id:
        raise HTTPException(400, "Неверные параметры")

    ok = await transfer_item(item_pk, from_user_id, admin["id"])
    if not ok:
        raise HTTPException(400, "Не удалось передать предмет")

    await log_admin_action(admin["id"], "steal_item", from_user_id, f"#{item_pk}")
    return {"ok": True}


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
