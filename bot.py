import asyncio
import logging
import os

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

# ⚠️ ЗАМЕНИ НА СВОЙ URL от cloudflared/ngrok
WEBAPP_URL = "https://immunity-overcrowd-props.ngrok-free.dev"

RATE = 100
STAR_PACKS = {s: s * RATE for s in [10, 30, 50, 100, 250, 500]}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    await log_visit(message.from_user.id)

    # Реферальная ссылка
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

    # Данные для меню
    uid = message.from_user.id
    balance = await get_balance(uid)
    stats = await get_user_full_stats(uid)

    games = stats[3] if stats else 0
    wagered = stats[1] if stats else 0
    won = stats[2] if stats else 0

    # Проверка на вывод
    allowed, days = await can_withdraw(uid)
    if allowed:
        withdraw_status = "✅ Доступен"
    else:
        left = 3 - days
        withdraw_status = f"🔒 Ещё {left} дн. (активность {days}/3)"

    # Кнопка Mini App
    if WEBAPP_URL and WEBAPP_URL.startswith("http"):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🎰 ОТКРЫТЬ КАЗИНО",
                web_app=WebAppInfo(url=f"{WEBAPP_URL}/webapp"),
            )],
        ])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Mini App не настроен", callback_data="noop")],
        ])

    text = (
        "╔══════════════════════════╗\n"
        "      🎰 <b>CASINO</b> 🎰\n"
        "╚══════════════════════════╝\n\n"

        f"👤 <b>{message.from_user.first_name or 'Игрок'}</b>, добро пожаловать!\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💼 <b>ВАШ ПРОФИЛЬ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 Баланс: <b>{fmt(balance)}</b>\n"
        f"🎮 Игр сыграно: <b>{fmt(games)}</b>\n"
        f"💸 Поставлено: <b>{fmt(wagered)}</b>\n"
        f"🏆 Выиграно: <b>{fmt(won)}</b>\n"
        f"💳 Вывод: <b>{withdraw_status}</b>\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎮 <b>ДОСТУПНЫЕ ИГРЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎰 Слоты — выигрыш до ×10\n"
        "💣 Сапёр — ×2.5 за поле\n"
        "🚀 Ракетка — растущий множитель\n"
        "🎲 Кости — ×5 на точное число\n"
        "🔫 Русская рулетка — до ×7\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💎 <b>ВОЗМОЖНОСТИ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⭐ Пополнение от 10 звёзд\n"
        "💸 Вывод от 15 звёзд\n"
        "🎁 Ежедневный бонус\n"
        "🎟 Промокоды\n"
        "👥 Реферальная программа −10%\n"
        "🏅 Достижения и награды\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💱 Курс: <b>1 ⭐ = {RATE} 🪙</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "👇 <b>Нажми кнопку ниже, чтобы играть</b>"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()


@router.message(Command("webapp"))
async def cmd_webapp(message: types.Message):
    await log_visit(message.from_user.id)

    if not WEBAPP_URL or not WEBAPP_URL.startswith("http"):
        await message.answer(
            "❌ <b>Mini App не настроен</b>\n\n"
            "<i>Администратор должен указать WEBAPP_URL в настройках бота.</i>",
            parse_mode="HTML",
        )
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎰 ОТКРЫТЬ КАЗИНО",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/webapp"),
        )],
    ])
    await message.answer(
        "🎰 <b>Казино ждёт тебя!</b>\n\n"
        "Нажми кнопку ниже 👇",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "📖 <b>ИНСТРУКЦИЯ</b>\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎮 <b>ИГРЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "🎰 <b>Слоты</b>\n"
        "Крути 3 барабана. 2 совпадения → ×2, "
        "3 одинаковых → ×3–×10. 🤑 джекпот — ×10.\n\n"

        "💣 <b>Сапёр</b>\n"
        "Поле 5×5, 5 мин. Все безопасные клетки → ×2.5.\n"
        "Можно забрать выигрыш досрочно.\n\n"

        "🚀 <b>Ракетка</b>\n"
        "Множитель растёт каждую секунду. "
        "Успей забрать до взрыва.\n\n"

        "🎲 <b>Кости</b>\n"
        "1-3 или 4-6 → ×2. Точное число → ×5.\n\n"

        "🔫 <b>Русская рулетка</b>\n"
        "7 патронов, каждый шаг +1. Максимум ×7.\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💱 <b>ФИНАНСЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"⭐ <b>Пополнение</b> — 1 ⭐ = {RATE} 🪙\n"
        f"💸 <b>Вывод</b> — 1 ⭐ = {RATE} 🪙, минимум 15 ⭐\n"
        "🔒 <b>Условие вывода</b> — заходить 3 дня из последних 7\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎁 <b>БОНУСЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "🎁 <b>Ежедневный бонус</b> — 500 🪙 + 100 🪙 за каждый день серии\n\n"

        "🎟 <b>Промокоды</b> — дают монеты или скидку\n\n"

        "👥 <b>Рефералы</b> — пригласи друга, "
        "получи скидку 10% когда он пополнит на 100+ ⭐\n\n"

        "🏅 <b>Достижения</b> — за активность и рекорды"
    )
    await message.answer(text, parse_mode="HTML")


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)


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
                "🎁 Вам начислена скидка <b>10%</b> на следующее пополнение.",
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


async def start_bot():
    await init_db()
    await dp.start_polling(bot)