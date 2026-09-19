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
    pvp_get_table,
    pvp_get_participants,
    pvp_join_table,
    pvp_get_active_table_for_user,
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

    # Обработка реферальной ссылки
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

    # Обработка PvP-приглашения (ОТДЕЛЬНЫЙ блок, СНАРУЖИ первого)
    if len(args) > 1 and args[1].startswith("pvp_"):
        try:
            pvp_table_id = int(args[1].split("_")[1])
            await handle_pvp_invite(message, pvp_table_id)
            return
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
@router.message(Command("pvp"))
async def cmd_pvp(message: types.Message):
    """Главное меню PvP: создать стол или присоединиться."""
    await ensure_user(message.from_user.id, message.from_user.username)

    args = message.text.split(maxsplit=1)
    # Если есть аргумент — приглашение на стол
    if len(args) > 1 and args[1].startswith("join_"):
        try:
            table_id = int(args[1].split("_")[1])
            await handle_pvp_invite(message, table_id)
            return
        except (ValueError, IndexError):
            pass

    text = (
        "⚔️ <b>PvP Арена SlotsGaming</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎮 <b>Как играть</b>\n"
        "1. Создай стол или присоединись к чужому\n"
        "2. Дождись соперников\n"
        "3. Играйте раунд — кто больше очков, тот победил\n"
        "4. Победитель забирает банк\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💰 <b>Форматы</b>\n"
        "• 1×1 Дуэль (2 игрока)\n"
        "• Турнир на 4 (4 игрока)\n"
        "• Турнир на 8 (8 игроков)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>Игры</b>\n"
        "🎰 Слоты · 📈 Crash · ⛏ Mines · 🎲 Кости\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💸 Комиссия казино: <b>2%</b> с банка\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⚔️  ОТКРЫТЬ PVP-АРЕНУ  ⚔️",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/webapp"),
        )],
    ])

    await message.answer(text, parse_mode="HTML", reply_markup=kb)


async def handle_pvp_invite(message: types.Message, table_id: int):
    """Обработка перехода по ссылке-приглашению."""
    uid = message.from_user.id

    table = await pvp_get_table(table_id)
    if not table:
        await message.answer(
            "❌ <b>Стол не найден</b>\n\nВозможно, он уже закрыт.",
            parse_mode="HTML",
        )
        return

    if table["status"] != "waiting":
        await message.answer(
            "⚠️ <b>Стол уже начался или закрыт</b>\n\n"
            "Попробуй найти другой стол.",
            parse_mode="HTML",
        )
        return

    # Проверяем, есть ли пароль
    if table["password"]:
        await message.answer(
            f"🔒 <b>Стол #{table_id} защищён паролем</b>\n\n"
            f"🎮 Игра: <b>{table['game']}</b>\n"
            f"💰 Ставка: <b>{table['bet']}</b> 🪙\n\n"
            f"Открой Mini App и введи пароль:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⚔️  ОТКРЫТЬ PVP  ⚔️",
                    web_app=WebAppInfo(url=f"{WEBAPP_URL}/webapp"),
                )],
            ]),
        )
        return

    # Присоединяем
    result = await pvp_join_table(table_id, uid, None)

    if not result["ok"]:
        await message.answer(
            f"❌ <b>Не удалось присоединиться</b>\n\n{result['error']}",
            parse_mode="HTML",
        )
        return

    if result["status"] == "waiting":
        participants = await pvp_get_participants(table_id)
        await message.answer(
            f"✅ <b>Ты в столе #{table_id}!</b>\n\n"
            f"🎮 Игра: <b>{table['game']}</b>\n"
            f"💰 Ставка: <b>{table['bet']}</b> 🪙\n"
            f"👥 Игроков: <b>{len(participants)}/{table['max_players']}</b>\n\n"
            f"Ждём остальных...",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⚔️  ОТКРЫТЬ СТОЛ  ⚔️",
                    web_app=WebAppInfo(url=f"{WEBAPP_URL}/webapp"),
                )],
            ]),
        )
    else:
        await message.answer(
            f"🚀 <b>Игра начинается!</b>\n\n"
            f"🎮 Игра: <b>{table['game']}</b>\n"
            f"💰 Ставка: <b>{table['bet']}</b> 🪙\n\n"
            f"Открывай Mini App и играй!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⚔️  ИГРАТЬ  ⚔️",
                    web_app=WebAppInfo(url=f"{WEBAPP_URL}/webapp"),
                )],
            ]),
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
