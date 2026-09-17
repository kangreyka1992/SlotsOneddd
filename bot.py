import asyncio
import hashlib
import hmac
import json
import math
import random
import time
import datetime
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl, quote
from fastapi.staticfiles import StaticFiles

import aiohttp
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
import uvicorn

from bot import bot, start_bot, RATE, STAR_PACKS
from database import (
    get_balance, add_balance, set_balance, create_withdrawal,
    get_top_players, get_user_full_stats,
    log_live_win,
    get_live_feed,
    get_daily_quests,
    update_quest_progress,
    claim_quest_reward,
    get_user_achievements, ACHIEVEMENTS,
    get_referral_stats, get_discount,
    log_game, unlock_achievement,
    get_promo, promo_already_used, use_promo,
    get_daily_info, claim_daily,
    ensure_user,
    get_battle_pass,
    add_battle_pass_xp,
    claim_battle_pass_reward,
    buy_premium_pass,
    BATTLE_PASS_REWARDS,
    XP_PER_LEVEL,
    MAX_LEVEL,
    get_stats, get_last_withdrawals, update_withdrawal,
    get_user_by_username, get_all_user_ids,
    create_promo, delete_promo, list_promos,
    log_admin_action, get_admin_logs,
    log_visit, can_withdraw,
    has_deposited,
    save_payment, payment_exists,
    add_user_item, get_user_items, get_user_item, sell_user_item,
    delete_user_item, get_user_items_stats,
    get_user_item_by_id, mark_items_sold,
    get_user_items_admin, transfer_item,
    get_free_case_info, claim_free_case,
    log_house_flow, get_house_stats,
    get_winrate, set_winrate, clear_winrate, list_winrates,
    get_referrer,
    get_jackpot, add_to_jackpot, win_jackpot,
    get_hourly_info, claim_hourly,
    add_to_cashback, get_cashback_info, claim_cashback,
    add_referral_commission, get_referral_earnings,
    get_profile, set_profile,
    get_active_tournament, add_tournament_score, get_tournament_leaderboard,
    add_to_hall_of_fame, get_hall_of_fame,
    get_wheel_info, add_wheel_spin, consume_wheel_spin,
    get_user_level, add_user_xp,
    initialize_tournament_if_needed,
)

WITHDRAW_RATE = 125
MIN_WITHDRAW = 15
BETS = [10, 50, 100, 500, 1000, 10000, 20000, 30000, 50000, 100000]
ADMIN_IDS = [7643224285]

WITHDRAW_RATES = {
    'stars': {'rate': 125,  'min': 15,  'unit': '⭐'},
    'sbp':   {'rate': 1000, 'min': 500, 'unit': '₽'},
    'usdc':  {'rate': 100,  'min': 5,   'unit': 'USDC'},
    'ton':   {'rate': 5000, 'min': 1,   'unit': 'TON'},
}


# ═══════════ ПОДКРУТКА ШАНСОВ ═══════════

async def _apply_winrate(uid: int, base_win: bool) -> bool:
    winrate, _ = await get_winrate(uid)

    if winrate >= 50:
        if not base_win:
            bias = (winrate - 50) / 50.0
            return random.random() < bias
        return True
    else:
        if base_win:
            bias = (50 - winrate) / 50.0
            return random.random() > bias
        return False


async def _apply_payout(uid: int, win_amount: int) -> int:
    _, payout_mult = await get_winrate(uid)
    if payout_mult == 1.0 or win_amount <= 0:
        return win_amount
    return max(0, int(win_amount * payout_mult))


# ═══════════ CRYPTO DIRECT (Polygon USDC) ═══════════
SELLER_WALLET = "0xFe06D515f0728567e34B94de549289791d9b1BA3"
POLYGONSCAN_API_KEY = "Y2CVHHPY54VYJUTKG2FW7YZAI49EMYVXHN"
USDC_POLYGON_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CRYPTO_PER_USD = 500

pending_payments: dict[str, dict] = {}


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


async def _notify_admin_withdraw(wid: int, method: str, amount: float,
                                 unit: str, need: int, uid: int,
                                 extra: str = ""):
    """Отправляет всем админам уведомление о новой заявке на вывод."""
    text = (
        f"💸 <b>Новая заявка №{wid}</b>\n"
        f"Метод: <b>{method}</b>\n"
        f"Сумма: <b>{amount} {unit}</b>\n"
        f"Монет: <b>{need}</b> 🪙\n"
        f"Юзер: <code>{uid}</code>"
    )
    if extra:
        text += f"\n{extra}"
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception as e:
            print(f"notify admin {admin_id} error: {e}")


def _calc_withdraw_need(method: str, amount: float) -> int:
    cfg = WITHDRAW_RATES.get(method)
    if not cfg:
        raise HTTPException(400, "Неизвестный метод вывода")
    return int(amount * cfg['rate'])


def _validate_withdraw_amount(method: str, amount: float) -> None:
    cfg = WITHDRAW_RATES.get(method)
    if not cfg:
        raise HTTPException(400, "Неизвестный метод вывода")
    if amount < cfg['min']:
        raise HTTPException(400, f"Минимум {cfg['min']} {cfg['unit']}")


async def _process_game_rewards(uid: int, bet: int, win: int, game: str,
                                username: str = None):
    if win < bet:
        try:
            await add_to_cashback(uid, bet - win)
        except Exception as e:
            print(f"cashback error: {e}")

    try:
        referrer = await get_referrer(uid)
        if referrer:
            await add_referral_commission(referrer, bet)
    except Exception as e:
        print(f"referral error: {e}")

    try:
        await add_to_jackpot(max(1, int(bet * 0.01)))
    except Exception as e:
        print(f"jackpot error: {e}")

    try:
        tour = await get_active_tournament()
        if tour and tour["game"] == game and win > 0:
            await add_tournament_score(tour["id"], uid, win)
    except Exception as e:
        print(f"tournament error: {e}")

    try:
        if win >= 100_000:
            await add_to_hall_of_fame(uid, username or f"user_{uid}", game, win)
    except Exception as e:
        print(f"hall error: {e}")

    try:
        await add_user_xp(uid, max(1, bet // 1000))
    except Exception as e:
        print(f"xp error: {e}")

    try:
        if random.random() < 0.05:
            await add_wheel_spin(uid, 1)
    except Exception as e:
        print(f"wheel error: {e}")


async def periodic_cleanup():
    """Фоновый таск — чистит зависшие игры и очередь дуэлей."""
    while True:
        await asyncio.sleep(60)
        try:
            cleanup_penalti()
        except Exception as e:
            print(f"cleanup_penalti error: {e}")
        try:
            cleanup_duel()
        except Exception as e:
            print(f"cleanup_duel error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(start_bot())
    cleanup_task = asyncio.create_task(periodic_cleanup())
    print("🚀 Бот и веб-сервер запущены", flush=True)

    try:
        await initialize_tournament_if_needed()
    except Exception as e:
        print(f"⚠️ tournament init skipped: {e}", flush=True)

    yield
    task.cancel()
    cleanup_task.cancel()


app = FastAPI(lifespan=lifespan)


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


app.mount("/webapp", NoCacheStaticFiles(directory="webapp", html=True), name="webapp")


@app.get("/")
async def root():
    return FileResponse("webapp/index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ═══════════ CRYPTO DIRECT ═══════════

@app.post("/api/crypto/create")
async def api_crypto_create(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    amount_usd = float(data.get("amount_usd", 10))

    if amount_usd < 1:
        raise HTTPException(400, "Минимум $1")

    order_id = f"{uid}_{int(time.time())}"
    unique_amount = round(amount_usd + random.randint(1, 999) / 10000, 4)

    pending_payments[order_id] = {
        "user_id": uid,
        "amount": unique_amount,
        "base_amount": amount_usd,
        "created": time.time(),
        "status": "pending",
    }

    amount_micro = int(unique_amount * 10 ** 6)
    deeplink = (
        f"ethereum:{SELLER_WALLET}@137/transfer"
        f"?address={USDC_POLYGON_CONTRACT}"
        f"&uint256={amount_micro}"
    )

    qr_url = (
        f"https://api.qrserver.com/v1/create-qr-code/"
        f"?size=300x300&data={quote(deeplink, safe='')}"
    )

    return {
        "order_id": order_id,
        "wallet": SELLER_WALLET,
        "network": "Polygon (MATIC)",
        "token": "USDC",
        "amount": unique_amount,
        "base_amount": amount_usd,
        "coins": int(amount_usd * CRYPTO_PER_USD),
        "qr_url": qr_url,
        "deeplink": deeplink,
        "expires_in": 3600,
    }


@app.post("/api/crypto/check")
async def api_crypto_check(request: Request):
    data = await request.json()
    user = validate_init_data(data.get("initData", ""))
    uid = user["id"]
    order_id = data.get("order_id", "")

    order = pending_payments.get(order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    if order["user_id"] != uid:
        raise HTTPException(403, "Это не ваш заказ")

    if order["status"] == "paid":
        return {
            "status": "paid",
            "coins": order.get("coins", 0),
            "balance": await get_balance(uid),
        }

    try:
        url = (
            f"https://api.polygonscan.com/api"
            f"?module=account"
            f"&action=tokentx"
            f"&contractaddress={USDC_POLYGON_CONTRACT}"
            f"&address={SELLER_WALLET}"
            f"&page=1&offset=20&sort=desc"
            f"&apikey={POLYGONSCAN_API_KEY}"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                result = await resp.json()

        txs = result.get("result", [])
        if not isinstance(txs, list):
            txs = []

        target_amount = order["amount"]
        order_created = order["created"]

        for tx in txs:
            if tx["to"].lower() != SELLER_WALLET.lower():
                continue
            if int(tx["timeStamp"]) < order_created - 60:
                continue

            value_usdc = int(tx["value"]) / (10 ** int(tx["tokenDecimal"]))

            if abs(value_usdc - target_amount) < 0.001:
                order["status"] = "paid"
                coins = int(order["base_amount"] * CRYPTO_PER_USD)
                order["coins"] = coins

                bal = await add_balance(uid, coins, None)
                await save_payment(
                    uid,
                    f"crypto_{order_id}",
                    int(order["base_amount"]),
                    coins,
                )
                await unlock_achievement(uid, "paid_user")

                try:
                    await bot.send_message(
                        uid,
                        "✅ <b>Оплата получена!</b>\n\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💳 Оплачено: <b>{value_usdc} USDC</b>\n"
                        f"🪙 Зачислено: <b>{coins}</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💰 Баланс: <b>{bal}</b> 🪙",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    print(f"notify error: {e}")

                return {
                    "status": "paid",
                    "coins": coins,
                    "balance": bal,
                    "txid": tx["hash"],
                }

        return {"status": "pending"}

    except Exception as e:
        print(f"crypto check error: {e}")
        return {"status": "pending", "error": str(e)}


@app.get("/crypto/pending")
async def crypto_pending():
    return {
        "count": len(pending_payments),
        "orders": [
            {"id": k, "user": v["user_id"], "amount": v["amount"], "status": v["status"]}
            for k, v in list(pending_payments.items())[-20:]
        ],
    }


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
    profile_custom = await get_profile(uid)

    return {
        "balance": balance,
        "rate": RATE,
        "withdraw_rate": WITHDRAW_RATE,
        "min_withdraw": MIN_WITHDRAW,
        "username": user.get("username") or user.get("first_name") or "игрок",
        "user_id": uid,
        "is_admin": is_admin(uid),
        "profile": profile_custom,
        "stats": {
            "wagered": stats[1] if stats else 0,
            "won": stats[2] if stats else 0,
            "games": stats[3] if stats else 0,
            "daily_streak": stats[5] if stats else 0,
        },
        "referral": {"invited": invited, "bonuses": bonuses},
        "discount": discount,
    }


@app.post("/api/feed/live")
async def api_feed_live(request: Request):
    data = await request.json()
    validate_init_data(data.get("initData", ""))
    feed = await get_live_feed(15)
    return {
        "feed": [
            {"username": f[0] or "Игрок", "game": f[1], "win": f[2], "time": f[3]}
            for f in feed
        ]
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

    if bet <= 0 or bet > 10000000000:
        raise HTTPException(400, "invalid_bet")

    balance = await get_balance(uid)
    if balance < bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -bet)

    symbols = ["🍒", "🍋", "🍊", "💎", "🤑", "7️⃣"]
    result = [random.choice(symbols) for _ in range(3)]

    base_win = 0
    jackpot = False
    if result[0] == result[1] == result[2]:
        if result[0] == "🤑":
            base_win, jackpot = bet * 10, True
        elif result[0] == "💎":
            base_win = bet * 5
        elif result[0] == "7️⃣":
            base_win = bet * 4
        else:
            base_win = bet * 3
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        base_win = bet * 2

    base_win_bool = base_win > 0
    final_win_bool = await _apply_winrate(uid, base_win_bool)

    if final_win_bool and not base_win_bool:
        win = int(bet * random.choice([1.5, 2.0, 2.5, 3.0]))
        jackpot = False
    elif not final_win_bool and base_win_bool:
        win = 0
        jackpot = False
    else:
        win = base_win

    win = await _apply_payout(uid, win)

    if win > 0:
        await add_balance(uid, win)

    await log_game(uid, bet, win)
    await add_battle_pass_xp(uid, bet // 10)
    await log_house_flow(wagered=bet, paid=win)
    await _process_game_rewards(uid, bet, win, "slots", user.get("username"))
    nb = await get_balance(uid)

    await update_quest_progress(uid, "bets_count", 1)
    await update_quest_progress(uid, "wagered", bet)
    await update_quest_progress(uid, "game_slots", 1)
    if win > 0:
        await update_quest_progress(uid, "wins", 1)

    await unlock_achievement(uid, "first_bet")
    if win > 0:
        await unlock_achievement(uid, "first_win")
    if jackpot and win > 0:
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

    if bet <= 0 or bet > 10000000000:
        raise HTTPException(400, "invalid_bet")
    if lines_count not in (1, 5, 10, 20):
        raise HTTPException(400, "invalid_lines")

    total_bet = bet * lines_count
    balance = await get_balance(uid)
    if balance < total_bet:
        raise HTTPException(400, "not_enough_coins")

    await add_balance(uid, -total_bet)

    field, total_win, line_wins = _slot_spin(bet, lines_count)

    base_win_bool = total_win > 0
    final_win_bool = await _apply_winrate(uid, base_win_bool)
    if final_win_bool and not base_win_bool:
        total_win = int(total_bet * random.choice([0.5, 1.0, 1.5, 2.0]))
    elif not final_win_bool and base_win_bool:
        total_win = 0
        line_wins = []
    # ФИКС: раскомментировано — подкрутка выплат
    total_win = await _apply_payout(uid, total_win)

    if total_win > 0:
        await add_balance(uid, total_win)
    await log_game(uid, total_bet, total_win)
    await add_battle_pass_xp(uid, total_bet // 10)
    await log_house_flow(wagered=total_bet, paid=total_win)
    await _process_game_rewards(uid, total_bet, total_win, "slots2", user.get("username"))
    nb = await get_balance(uid)
    await update_quest_progress(uid, "bets_count", 1)
    await update_quest_progress(uid, "wagered", total_bet)
    await update_quest_progress(uid, "game_slots2", 1)
    if total_win > 0:
        await update_quest_progress(uid, "wins", 1)

    if total_win >= 1000:
        username = user.get("username") or user.get("first_name") or "Игрок"
        await log_live_win(uid, username, "Слоты 5×3", total_win)

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
