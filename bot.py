import asyncio
import logging
import os
from urllib.parse import quote

import aiohttp
from aiohttp import web

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.types import (
    LabeledPrice, PreCheckoutQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo,
)

from database import (
    init_db, get_balance, add_balance, save_payment,
    ensure_user, get_referrer, set_referrer,
    add_referral_bonus, set_discount, clear_discount,
    unlock_achievement, log_visit,
    get_user_full_stats, can_withdraw,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8602932446:AAEtYr2rsT8jFSVjYErG9Q84duJ3dVfSyCo"

# ⚠️ ЗАМЕНИ НА СВОЙ URL
WEBAPP_URL = "https://bot-1789335277-8932-slotbots.bothost.tech"

# ← НОВОЕ: настройки Paygate
SELLER_WALLET = "0x67C0Bb050B459f843c2821402D122c62D2F92eB5"
PAYGATE_CALLBACK_URL = f"{WEBAPP_URL}/paygate/callback"
CRYPTO_PER_USD = 100  # 1 USDC = 100 монет в боте (можешь поменять)

RATE = 100
STAR_PACKS = {s: s * RATE for s in [10, 30, 50, 100, 250, 500]}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


# ═══════════════════════════════════════════════
# ← НОВОЕ: PAYGATE — создание платёжной ссылки
# ═══════════════════════════════════════════════
async def create_paygate_link(user_id: int, amount_usd: float) -> str:
    """Создаёт ссылку на оплату через Paygate.to"""
    # Уникальный callback для каждого заказа
    callback = f"{PAYGATE_CALLBACK_URL}?number={user_id}"

    url1 = (
        f"https://api.paygate.to/control/wallet.php"
        f"?address={SELLER_WALLET}"
        f"&callback={quote(callback, safe='')}"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url1) as resp:
            data = await resp.json()
            address_in = data.get("address_in")
            if not address_in:
                raise Exception("Paygate не вернул address_in")

        # Формируем ссылку на оплату
        pay_url = (
            f"https://checkout.paygate.to/process-payment.php"
            f"?address={quote(address_in, safe='')}"
            f"&amount={amount_usd}"
            f"&provider=moonpay"
            f"&email=player{user_id}%40example.com"
            f"&currency=USD"
        )
        return pay_url


# ═══════════════════════════════════════════════
# ← НОВОЕ: AIOHTTP-СЕРВЕР для приёма callback
# ═══════════════════════════════════════════════
web_app = web.Application()


async def paygate_callback(request: web.Request):
    """Принимает уведомление от Paygate после оплаты"""
    params = dict(request.query_params)
    logging.info(f"PAYGATE CALLBACK: {params}")

    try:
        user_id = int(params.get("number", 0))
        amount_usdc = float(params.get("value_coin", 0))
    except (ValueError, TypeError):
        return web.Response(text="BAD PARAMS", status=400)

    if user_id <= 0 or amount_usdc <= 0:
        return web.Response(text="INVALID", status=400)

    # Начисляем баланс
    coins = int(amount_usdc * CRYPTO_PER_USD)
    bal = await add_balance(user_id, coins, None)
    await save_payment(
        user_id,
        params.get("txid_in", ""),
        int(amount_usdc),
        coins,
    )
    await unlock_achievement(user_id, "paid_user")

    # Уведомляем игрока в Telegram
    try:
        await bot.send_message(
            user_id,
            "✅ <b>Оплата получена!</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💳 Оплачено: <b>{amount_usdc} USDC</b>\n"
            f"🪙 Зачислено: <b>{fmt(coins)}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Баланс: <b>{fmt(bal)}</b> 🪙",
            parse_mode="HTML",
        )
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение: {e}")

    return web.Response(text="OK")


async def paygate_test(request: web.Request):
    """Тестовый эндпоинт — проверка что сервер работает"""
    return web.Response(text="Paygate webhook is alive")


web_app.router.add_get("/paygate/callback", paygate_callback)
web_app.router.add_get("/paygate/test", paygate_test)


# ═══════════════════════════════════════════════
# ← НОВОЕ: команда /topup для теста
# ═══════════════════════════════════════════════
@router.message(Command("topup"))
async def cmd_topup(message: types.Message):
    """Тестовая команда для создания платёжной ссылки"""
    try:
        link = await create_paygate_link(message.from_user.id, 25.0)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить $25", url=link)],
        ])
        await message.answer(
            "💳 <b>Пополнение баланса</b>\n\n"
            "Нажми кнопку ниже, чтобы оплатить картой или криптой.\n"
            "После оплаты баланс зачислится автоматически.",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ═══════════════════════════════════════════════
# Существующие хэндлеры
# ═══════════════════════════════════════════════

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    await log_visit(message.from_user.id)

    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1].split("_")[1])
            if ref_id != message.from_user.id:
                ok = await set_referrer(message.from_user.id, ref_id)
                if ok:
                    await unlock_achievement(ref_id, "referrer")
                    try:
                        await bot.send_message(
                            ref_id,
                            "👥 <b>Новый реферал!</b>\n\n"
                            "🎁 Когда он пополнит баланс на <b>100+ ⭐</b>,\n"
                            "вы получите <b>скидку 10%</b> на следующее пополнение.",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
        except (ValueError, IndexError):
            pass
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎰  ИГРАТЬ  🎰",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/webapp"),
        )],
    ])
    text = (
        "🎰 <b>ДОБРО ПОЖАЛОВАТЬ В SlotsGame</b> 🎰\n"
        "\n"
        "✨ <b>Мир азарта ждёт тебя!</b>\n"
        "\n"
        "🪙 <b>Доступные игры:</b>\n"
        "🎰 Слоты  ·  📈 Crash  ·  ⛏ Mines\n"
        "🎯 Plinko  ·  🎲 Кости  ·  ⚔️ Дуэли\n"
        "🪙 Монетка  ·  ⚽ Penalti  ·  🔫 Рулетка\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎁 <b>Бонус новичка</b> — забери прямо сейчас\n"
        "👥 <b>Рефералы</b> — получай 10% скидку\n"
        "💸 <b>Вывод</b> — от 15 ⭐ на кошелёк\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "👇 <b>Нажми кнопку ниже, чтобы играть</b>\n"
        "\n"
        "🔥 <i>Удачи и крупных выигрышей!</i> 🔥"
    )

    BANNER = "AgACAgIAAxkBAAIBVWqn3lOgAAEeJ77pG0LSOCrbNexvKwAC2yRrGxk3QEkvmpH1MmpOGAEAAwIAA3kAAz0E"

    try:
        await message.answer_photo(
            photo=BANNER,
            caption=text,
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()


@router.message(Command("webapp"))
async def cmd_webapp(message: types.Message):
    await log_visit(message.from_user.id)

    if not WEBAPP_URL or not WEBAPP_URL.startswith("http"):
        await message.answer("❌ <b>Mini App не настроен</b>", parse_mode="HTML")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎰  ИГРАТЬ  🎰",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/webapp"),
        )],
    ])
    await message.answer(
        "🎰 <b>Казино ждёт тебя!</b>\n\nНажми кнопку ниже 👇",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)


@router.message(F.photo)
async def debug_photo(message: types.Message):
    file_id = message.photo[-1].file_id
    await message.answer(f"<code>{file_id}</code>", parse_mode="HTML")


@router.message(F.successful_payment)
async def on_payment(message: types.Message):
    p = message.successful_payment
    parts = p.invoice_payload.split("_")
    uid = message.from_user.id
    coins = int(parts[2]) if len(parts) >= 3 else RATE
    disc = int(parts[3]) if len(parts) >= 4 else 0

    if disc > 0:
        await clear_discount(uid)

    await save_payment(uid, p.telegram_payment_charge_id, p.total_amount, coins)
    bal = await add_balance(uid, coins, message.from_user.username)
    await unlock_achievement(uid, "paid_user")

    ref = await get_referrer(uid)
    if ref and p.total_amount >= 100:
        await add_referral_bonus(ref)
        await set_discount(ref, 10)
        try:
            await bot.send_message(
                ref,
                "👥 <b>Реферальный бонус!</b>\n\n"
                f"Ваш реферал пополнил на <b>{p.total_amount} ⭐</b>.\n"
                "🎁 Вам начислена скидка <b>10%</b>.",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await message.answer(
        "✅ <b>Оплата получена!</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 Оплачено: <b>{p.total_amount} ⭐</b>\n"
        f"🪙 Зачислено: <b>{fmt(coins)}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Баланс: <b>{fmt(bal)}</b> 🪙",
        parse_mode="HTML",
    )


# ═══════════════════════════════════════════════
# ← НОВОЕ: запуск бота + веб-сервера параллельно
# ═══════════════════════════════════════════════
async def start_bot():
    await init_db()

    # Запускаем веб-сервер на порту 3000 (Bothost обычно слушает 3000)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8000)
    await site.start()
    logging.info("Web-сервер запущен на порту 8000")

    # Запускаем polling бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(start_bot())
