import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.types import (
    LabeledPrice, PreCheckoutQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo,
)

from database import (
    init_db, get_balance, add_balance, save_payment, payment_exists,
    ensure_user, get_referrer, set_referrer,
    add_referral_bonus, set_discount, clear_discount,
    get_users_for_broadcast,
    unlock_achievement, log_visit,
    get_user_full_stats, can_withdraw,
    buy_premium_pass, get_battle_pass,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8602932446:AAG_aVvoLz6CjhwfTP8sL9JKAoRK0tcGk_Q"
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://bot-1789335277-8932-slotbots.bothost.tech")

RATE = 100
STAR_PACKS = {s: s * RATE for s in [10, 15, 25, 30, 50, 100, 250, 500]}

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
        "🎯 Plinko  ·  🎲 Кости  ·  🪙 Монетка  ·  🔫 Рулетка\n"
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
    payload = p.invoice_payload
    uid = message.from_user.id

    if payload.startswith("battlepass_"):
        bp = await get_battle_pass(uid)
        if bp["premium"]:
            await message.answer(
                "⚠️ <b>Premium Battle Pass уже активирован!</b>\n\n"
                "Повторная оплата невозможна. Если это ошибка — обратитесь в поддержку.",
                parse_mode="HTML",
            )
            return
        await buy_premium_pass(uid)
        await message.answer(
            "✅ <b>Premium Battle Pass активирован!</b>\n\n"
            "Теперь вам доступны удвоенные награды на каждом уровне.",
            parse_mode="HTML",
        )
        return

    if await payment_exists(p.telegram_payment_charge_id):
        await message.answer(
            "ℹ️ Этот платёж уже был обработан. Баланс не изменился.",
            parse_mode="HTML",
        )
        return

    parts = payload.split("_")
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


# ═══════════ ФОНОВЫЕ УВЕДОМЛЕНИЯ ═══════════

async def _notify_worker():
    await asyncio.sleep(60)

    while True:
        try:
            await _send_bonus_reminders()
        except Exception as e:
            print(f"⚠️ notif worker error: {e}", flush=True)

        await asyncio.sleep(30 * 60)


async def _send_bonus_reminders():
    from database import get_notification_settings
    users = await get_users_for_broadcast("bonus_alerts")
    sent = 0
    for uid in users:
        try:
            await bot.send_message(
                uid,
                "🎁 <b>Не забудь про бонусы!</b>\n\n"
                "Загляни в приложение — тебя ждут ежедневный бонус, кэшбэк и колесо.",
                parse_mode="HTML",
            )
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    if sent:
        print(f"📨 Reminders sent: {sent}", flush=True)


async def start_bot():
    asyncio.create_task(_notify_worker())
    await dp.start_polling(bot)
