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


# ═══════════ СЛОТЫ ═══════════

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


# ═══════════ GOLD MINE (сапёр) ═══════════

mines_games: dict[int, dict] = {}


@app.post("/api/mines/start")
async def api_mines_start(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))

    if uid in mines_games:
        raise HTTPException(400, "already_playing")
    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)

    mines_games[uid] = {
        "bet": bet,
        "mines": set(random.sample(list(range(25)), 5)),
        "opened": set(),
    }

    return {"field": 5, "mines_count": 5, "bet": bet, "balance": await get_balance(uid)}


@app.post("/api/mines/open")
async def api_mines_open(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    idx = int(data.get("idx", -1))

    game = mines_games.get(uid)
    if not game or idx in game["opened"]:
        raise HTTPException(400, "invalid")

    field = 5

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
        return {"hit_mine": True, "idx": idx, "bet": bet, "balance": await get_balance(uid)}

    game["opened"].add(idx)
    safe = 25 - 5

    if len(game["opened"]) >= safe:
        win = int(game["bet"] * 2.5)
        await add_balance(uid, win)
        await log_game(uid, game["bet"], win)
        del mines_games[uid]
        await unlock_achievement(uid, "first_bet")
        await unlock_achievement(uid, "first_win")
        return {"hit_mine": False, "won": True, "win": win, "balance": await get_balance(uid)}

    return {
        "hit_mine": False, "won": False, "idx": idx, "around": around(idx),
        "opened": list(game["opened"]),
        "current_prize": int(game["bet"] * (1 + 0.3 * len(game["opened"]))),
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

    prize = int(game["bet"] * (1 + 0.3 * len(game["opened"])))
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


# ═══════════ РАКЕТКА ═══════════

rockets: dict[int, dict] = {}


@app.post("/api/rocket/start")
async def api_rocket_start(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))

    if uid in rockets:
        raise HTTPException(400, "already_playing")
    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)
    r = random.random() * 98
    rockets[uid] = {
        "bet": bet,
        "crash_at": max(1.0, 99 / (100 - r)),
        "started": time.time(),
    }
    return {"balance": await get_balance(uid)}


@app.post("/api/rocket/status")
async def api_rocket_status(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    game = rockets.get(uid)
    if not game:
        raise HTTPException(400, "no_game")

    elapsed = time.time() - game["started"]
    mult = max(1.0, 1.0 + elapsed * 0.4)

    if mult >= game["crash_at"]:
        del rockets[uid]
        await log_game(uid, game["bet"], 0)
        return {"crashed": True, "mult": game["crash_at"], "bet": game["bet"], "balance": await get_balance(uid)}

    return {"crashed": False, "mult": mult, "prize": int(game["bet"] * mult),
            "bet": game["bet"], "balance": await get_balance(uid)}


@app.post("/api/rocket/cashout")
async def api_rocket_cashout(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    game = rockets.get(uid)
    if not game:
        raise HTTPException(400, "no_game")

    elapsed = time.time() - game["started"]
    mult = max(1.01, 1.0 + elapsed * 0.4)

    if mult >= game["crash_at"]:
        del rockets[uid]
        await log_game(uid, game["bet"], 0)
        raise HTTPException(400, "crashed")

    prize = int(game["bet"] * mult)
    bet = game["bet"]
    del rockets[uid]
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

    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)
    roll = random.randint(1, 6)
    win = 0
    mult = 0

    if choice == "range_3_6" and roll >= 3:
        mult = 1.95
        win = int(bet * mult)
    elif choice == "range_4_6" and roll >= 4:
        mult = 2.9
        win = int(bet * mult)
    elif choice == "range_6_6" and roll == 6:
        mult = 5.7
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

    # Биномиальное распределение
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


# ═══════════ PENALTI ═══════════

penalti_games: dict = {}
PENALTI_MULTS = [1.6, 2.2, 3.0, 4.5, 7.0]


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
    penalti_games[uid] = {"bet": bet, "step": 0}
    return {"balance": await get_balance(uid)}


@app.post("/api/penalti/kick")
async def api_penalti_kick(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    game = penalti_games.get(uid)
    if not game:
        raise HTTPException(400, "no_game")

    step = game["step"]
    chance = 0.9 - step * 0.1
    goal = random.random() < chance

    if not goal:
        bet = game["bet"]
        del penalti_games[uid]
        await log_game(uid, bet, 0)
        return {"goal": False, "step": step, "balance": await get_balance(uid)}

    step += 1
    game["step"] = step
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
        return {"goal": True, "step": step, "maxed": True, "mult": mult, "prize": prize, "balance": await get_balance(uid)}

    return {"goal": True, "step": step, "maxed": False, "mult": mult, "prize": prize, "balance": await get_balance(uid)}


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


# ═══════════ СЛОТЫ ═══════════

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


# ═══════════ САПЁР ═══════════

mines_games: dict[int, dict] = {}


@app.post("/api/mines/start")
async def api_mines_start(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))

    if uid in mines_games:
        raise HTTPException(400, "already_playing")

    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)

    mines_games[uid] = {
        "bet": bet,
        "mines": set(random.sample(list(range(25)), 5)),
        "opened": set(),
    }

    return {"field": 5, "mines_count": 5, "bet": bet, "balance": await get_balance(uid)}


@app.post("/api/mines/open")
async def api_mines_open(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    idx = int(data.get("idx", -1))

    game = mines_games.get(uid)
    if not game or idx in game["opened"]:
        raise HTTPException(400, "invalid")

    field = 5

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
        return {"hit_mine": True, "idx": idx, "bet": bet, "balance": await get_balance(uid)}

    game["opened"].add(idx)
    safe = 25 - 5

    if len(game["opened"]) >= safe:
        win = int(game["bet"] * 2.5)
        await add_balance(uid, win)
        await log_game(uid, game["bet"], win)
        del mines_games[uid]
        await unlock_achievement(uid, "first_bet")
        await unlock_achievement(uid, "first_win")
        return {"hit_mine": False, "won": True, "win": win, "balance": await get_balance(uid)}

    return {
        "hit_mine": False, "won": False, "idx": idx, "around": around(idx),
        "opened": list(game["opened"]),
        "current_prize": int(game["bet"] * (1 + 0.3 * len(game["opened"]))),
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

    prize = int(game["bet"] * (1 + 0.3 * len(game["opened"])))
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


# ═══════════ РАКЕТКА ═══════════

rockets: dict[int, dict] = {}


@app.post("/api/rocket/start")
async def api_rocket_start(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    bet = int(data.get("bet", 0))

    if uid in rockets:
        raise HTTPException(400, "already_playing")

    if bet <= 0 or bet > 10000000:
        raise HTTPException(400, "invalid_bet")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)
    r = random.random() * 98
    rockets[uid] = {
        "bet": bet,
        "crash_at": max(1.0, 99 / (100 - r)),
        "started": time.time(),
    }
    return {"balance": await get_balance(uid)}


@app.post("/api/rocket/status")
async def api_rocket_status(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    game = rockets.get(uid)
    if not game:
        raise HTTPException(400, "no_game")

    elapsed = time.time() - game["started"]
    mult = max(1.0, 1.0 + elapsed * 0.4)

    if mult >= game["crash_at"]:
        del rockets[uid]
        await log_game(uid, game["bet"], 0)
        return {"crashed": True, "mult": game["crash_at"], "bet": game["bet"], "balance": await get_balance(uid)}

    return {"crashed": False, "mult": mult, "prize": int(game["bet"] * mult),
            "bet": game["bet"], "balance": await get_balance(uid)}


@app.post("/api/rocket/cashout")
async def api_rocket_cashout(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    game = rockets.get(uid)
    if not game:
        raise HTTPException(400, "no_game")

    elapsed = time.time() - game["started"]
    mult = max(1.01, 1.0 + elapsed * 0.4)

    if mult >= game["crash_at"]:
        del rockets[uid]
        await log_game(uid, game["bet"], 0)
        raise HTTPException(400, "crashed")

    prize = int(game["bet"] * mult)
    bet = game["bet"]
    del rockets[uid]
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
    if choice == "low" and roll in (1, 2, 3):
        win = bet * 2
    elif choice == "high" and roll in (4, 5, 6):
        win = bet * 2
    elif choice == "exact" and roll == exact:
        win = bet * 5

    if win > 0:
        await add_balance(uid, win)
    await log_game(uid, bet, win)
    nb = await get_balance(uid)
    await unlock_achievement(uid, "first_bet")
    if win > 0:
        await unlock_achievement(uid, "first_win")
    return {"roll": roll, "win": win, "balance": nb}


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
