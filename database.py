import aiosqlite
import datetime
import os

DB_PATH = os.getenv("DB_PATH", "casino.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                username TEXT,
                daily_last TIMESTAMP,
                daily_streak INTEGER DEFAULT 0,
                total_wagered INTEGER DEFAULT 0,
                total_won INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                referrals INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS live_feed (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                game TEXT NOT NULL,
                win INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                charge_id TEXT NOT NULL UNIQUE,
                stars INTEGER NOT NULL,
                coins INTEGER NOT NULL,
                refunded INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                stars INTEGER NOT NULL,
                coins_spent INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                tx_hash TEXT,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                value INTEGER NOT NULL,
                max_uses INTEGER DEFAULT 0,
                used_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_used (
                user_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, code)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_discounts (
                user_id INTEGER PRIMARY KEY,
                percent INTEGER NOT NULL,
                expires_at TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                user_id INTEGER PRIMARY KEY,
                referrer_id INTEGER NOT NULL,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referral_stats (
                user_id INTEGER PRIMARY KEY,
                invited_count INTEGER DEFAULT 0,
                bonus_discounts INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                user_id INTEGER NOT NULL,
                ach_id TEXT NOT NULL,
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, ach_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_id INTEGER,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_visits (
                user_id INTEGER NOT NULL,
                visit_date TEXT NOT NULL,
                PRIMARY KEY (user_id, visit_date)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                rarity TEXT NOT NULL,
                emoji TEXT NOT NULL,
                name TEXT NOT NULL,
                value INTEGER NOT NULL,
                kind TEXT NOT NULL DEFAULT 'gift',
                sold INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS free_case (
                user_id INTEGER PRIMARY KEY,
                last_claim TIMESTAMP,
                streak INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS house_flow (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wagered INTEGER NOT NULL DEFAULT 0,
                paid INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def has_deposited(user_id: int, min_stars: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT SUM(stars) FROM payments WHERE user_id = ?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            total_stars = row[0] if row and row[0] else 0
            return total_stars >= min_stars


async def ensure_user(user_id: int, username: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (user_id, balance, username) VALUES (?, 0, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET username = COALESCE(?, username)",
            (user_id, username, username),
        )
        await db.commit()


async def get_balance(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT balance FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def add_balance(user_id: int, amount: int, username: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (user_id, balance, username) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?, "
            "username = COALESCE(?, username)",
            (user_id, amount, username, amount, username),
        )
        await db.commit()
        async with db.execute(
            "SELECT balance FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def set_balance(user_id: int, amount: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (user_id, balance) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET balance = ?",
            (user_id, amount, amount),
        )
        await db.commit()
        return amount


async def save_payment(user_id: int, charge_id: str, stars: int, coins: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO payments (user_id, charge_id, stars, coins) "
            "VALUES (?, ?, ?, ?)",
            (user_id, charge_id, stars, coins),
        )
        await db.commit()


async def create_withdrawal(user_id: int, username: str, stars: int, coins: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO withdrawals (user_id, username, stars, coins_spent) "
            "VALUES (?, ?, ?, ?)",
            (user_id, username, stars, coins),
        )
        await db.commit()
        return cursor.lastrowid


async def update_withdrawal(wid: int, status: str, tx_hash: str = None, error: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE withdrawals SET status = ?, tx_hash = ?, error = ? WHERE id = ?",
            (status, tx_hash, error, wid),
        )
        await db.commit()


async def get_user_by_username(username: str):
    if username.startswith("@"):
        username = username[1:]
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM users WHERE LOWER(username) = LOWER(?)",
            (username,),
        ) as cur:
            return await cur.fetchone()


async def get_all_user_ids():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*), COALESCE(SUM(balance), 0) FROM users"
        ) as cur:
            users_count, total_coins = await cur.fetchone()
        async with db.execute(
            "SELECT COUNT(*), COALESCE(SUM(stars), 0) FROM withdrawals "
            "WHERE status = 'done'"
        ) as cur:
            withdraw_count, withdraw_stars = await cur.fetchone()
        async with db.execute(
            "SELECT user_id, username, balance FROM users "
            "ORDER BY balance DESC LIMIT 10"
        ) as cur:
            top = await cur.fetchall()
        return {
            "users": users_count,
            "coins": total_coins,
            "withdrawals": withdraw_count,
            "withdraw_stars": withdraw_stars,
            "top": top,
        }


async def get_last_withdrawals(limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, user_id, username, stars, coins_spent, status, created_at "
            "FROM withdrawals ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            return await cur.fetchall()


async def create_promo(code: str, kind: str, value: int, max_uses: int = 0) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO promocodes (code, kind, value, max_uses) "
                "VALUES (?, ?, ?, ?)",
                (code.upper(), kind, value, max_uses),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def delete_promo(code: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM promocodes WHERE code = ?", (code.upper(),)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_promo(code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT code, kind, value, max_uses, used_count "
            "FROM promocodes WHERE code = ?",
            (code.upper(),),
        ) as cur:
            return await cur.fetchone()


async def promo_already_used(user_id: int, code: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM promo_used WHERE user_id = ? AND code = ?",
            (user_id, code.upper()),
        ) as cur:
            return await cur.fetchone() is not None


async def use_promo(user_id: int, code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO promo_used (user_id, code) VALUES (?, ?)",
            (user_id, code.upper()),
        )
        await db.execute(
            "UPDATE promocodes SET used_count = used_count + 1 WHERE code = ?",
            (code.upper(),),
        )
        await db.commit()


async def list_promos():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT code, kind, value, max_uses, used_count FROM promocodes "
            "ORDER BY created_at DESC LIMIT 30"
        ) as cur:
            return await cur.fetchall()


async def set_discount(user_id: int, percent: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO user_discounts (user_id, percent) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET percent = MAX(percent, ?)",
            (user_id, percent, percent),
        )
        await db.commit()


async def get_discount(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT percent FROM user_discounts WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def clear_discount(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM user_discounts WHERE user_id = ?", (user_id,)
        )
        await db.commit()


async def set_referrer(user_id: int, referrer_id: int) -> bool:
    if user_id == referrer_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO referrals (user_id, referrer_id) VALUES (?, ?)",
                (user_id, referrer_id),
            )
            await db.execute(
                "UPDATE users SET referrals = referrals + 1 WHERE user_id = ?",
                (referrer_id,),
            )
            await db.execute(
                "INSERT INTO referral_stats (user_id, invited_count) VALUES (?, 1) "
                "ON CONFLICT(user_id) DO UPDATE SET invited_count = invited_count + 1",
                (referrer_id,),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_referrer(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT referrer_id FROM referrals WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def get_referral_stats(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT invited_count, bonus_discounts FROM referral_stats "
            "WHERE user_id = ?",
            (user_id,),
        ) as cur:
            return await cur.fetchone() or (0, 0)


async def add_referral_bonus(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO referral_stats (user_id, bonus_discounts) VALUES (?, 1) "
            "ON CONFLICT(user_id) DO UPDATE SET bonus_discounts = bonus_discounts + 1",
            (user_id,),
        )
        await db.commit()


async def get_daily_info(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT daily_last, daily_streak FROM users WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None, 0
            return row[0], row[1]


async def claim_daily(user_id: int, streak: int):
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET daily_last = ?, daily_streak = ? WHERE user_id = ?",
            (now, streak, user_id),
        )
        await db.commit()


async def log_game(user_id: int, wagered: int, won: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET "
            "total_wagered = total_wagered + ?, "
            "total_won = total_won + ?, "
            "games_played = games_played + 1 "
            "WHERE user_id = ?",
            (wagered, won, user_id),
        )
        await db.commit()


async def get_user_full_stats(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT balance, total_wagered, total_won, games_played, "
            "referrals, daily_streak FROM users WHERE user_id = ?",
            (user_id,),
        ) as cur:
            return await cur.fetchone()


async def get_top_players(limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username, balance, total_won, games_played "
            "FROM users ORDER BY balance DESC LIMIT ?",
            (limit,),
        ) as cur:
            return await cur.fetchall()


ACHIEVEMENTS = {
    "first_bet":    {"name": "🎯 Первая ставка",   "desc": "Сделать первую ставку"},
    "first_win":    {"name": "🎉 Первый выигрыш",  "desc": "Выиграть впервые"},
    "jackpot":      {"name": "🤑 Джекпот",         "desc": "Собрать 3 символа 🤑"},
    "big_win":      {"name": "💰 Крупный выигрыш", "desc": "Выиграть 100.000+ за раз"},
    "high_roller":  {"name": "🎩 Хайроллер",       "desc": "Поставить 100.000+ за раз"},
    "referrer":     {"name": "👥 Реферер",         "desc": "Пригласить друга"},
    "daily_7":      {"name": "📅 Неделя подряд",   "desc": "Заходить 7 дней подряд"},
    "millionaire":  {"name": "💎 Миллионер",       "desc": "Накопить 1.000.000 🪙"},
    "rr_max":       {"name": "🔫 Счастливчик",     "desc": "Пройти рулетку до 6-го шага"},
    "paid_user":    {"name": "⭐ Плательщик",      "desc": "Пополнить баланс"},
}


async def unlock_achievement(user_id: int, ach_id: str) -> bool:
    if ach_id not in ACHIEVEMENTS:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO achievements (user_id, ach_id) VALUES (?, ?)",
                (user_id, ach_id),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_user_achievements(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT ach_id, unlocked_at FROM achievements WHERE user_id = ? "
            "ORDER BY unlocked_at",
            (user_id,),
        ) as cur:
            return await cur.fetchall()


async def log_admin_action(admin_id: int, action: str, target_id: int = None, details: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO admin_logs (admin_id, action, target_id, details) "
            "VALUES (?, ?, ?, ?)",
            (admin_id, action, target_id, details),
        )
        await db.commit()


async def get_admin_logs(limit: int = 30):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT admin_id, action, target_id, details, created_at "
            "FROM admin_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            return await cur.fetchall()


async def log_visit(user_id: int):
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_visits (user_id, visit_date) VALUES (?, ?)",
            (user_id, today),
        )
        await db.commit()


async def count_recent_visits(user_id: int, days: int = 7) -> int:
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(DISTINCT visit_date) FROM user_visits "
            "WHERE user_id = ? AND visit_date >= ?",
            (user_id, since),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def can_withdraw(user_id: int) -> tuple:
    days = await count_recent_visits(user_id, days=7)
    return days >= 3, days


async def add_user_item(user_id: int, item_id: str, case_id: str,
                        rarity: str, emoji: str, name: str, value: int,
                        kind: str = "gift"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO user_items (user_id, item_id, case_id, rarity, emoji, name, value, kind) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, item_id, case_id, rarity, emoji, name, value, kind),
        )
        await db.commit()


async def get_user_items(user_id: int, limit: int = 100, only_unsold: bool = True):
    async with aiosqlite.connect(DB_PATH) as db:
        query = (
            "SELECT id, item_id, case_id, rarity, emoji, name, value, kind, created_at "
            "FROM user_items WHERE user_id = ?"
        )
        params = [user_id]
        if only_unsold:
            query += " AND sold = 0"
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        async with db.execute(query, params) as cur:
            return await cur.fetchall()


async def get_user_item(item_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, item_id, case_id, rarity, emoji, name, value, kind, sold "
            "FROM user_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        ) as cur:
            return await cur.fetchone()


async def get_user_item_by_id(item_pk: int, user_id: int):
    return await get_user_item(item_pk, user_id)


async def mark_items_sold(item_pks: list, user_id: int):
    if not item_pks:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        placeholders = ",".join("?" for _ in item_pks)
        await db.execute(
            f"UPDATE user_items SET sold = 1 WHERE user_id = ? AND id IN ({placeholders}) AND sold = 0",
            [user_id, *item_pks],
        )
        await db.commit()


async def sell_user_item(item_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE user_items SET sold = 1 WHERE id = ? AND user_id = ? AND sold = 0",
            (item_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_user_item(item_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM user_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        )
        await db.commit()


async def get_user_items_stats(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*), COALESCE(SUM(value), 0) FROM user_items "
            "WHERE user_id = ? AND sold = 0",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return {"count": row[0] or 0, "total_value": row[1] or 0}


async def get_user_items_admin(user_id: int, limit: int = 100):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, item_id, case_id, rarity, emoji, name, value, kind, created_at "
            "FROM user_items WHERE user_id = ? AND sold = 0 ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ) as cur:
            return await cur.fetchall()


async def transfer_item(item_pk: int, from_user_id: int, to_user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE user_items SET user_id = ? WHERE id = ? AND user_id = ? AND sold = 0",
            (to_user_id, item_pk, from_user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_free_case_info(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT last_claim, streak FROM free_case WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None, 0
            return row[0], row[1]


async def claim_free_case(user_id: int, streak: int):
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO free_case (user_id, last_claim, streak) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_claim = ?, streak = ?",
            (user_id, now, streak, now, streak),
        )
        await db.commit()


async def log_house_flow(wagered: int, paid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO house_flow (wagered, paid) VALUES (?, ?)",
            (wagered, paid),
        )
        await db.commit()


async def get_house_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COALESCE(SUM(wagered), 0), COALESCE(SUM(paid), 0) FROM house_flow"
        ) as cur:
            row = await cur.fetchone()
            wagered = row[0] or 0
            paid = row[1] or 0
            profit = wagered - paid
            rtp = (paid / wagered * 100) if wagered > 0 else 0
            return {
                "wagered": wagered,
                "paid": paid,
                "profit": profit,
                "rtp": round(rtp, 2),
            }
async def log_live_win(user_id: int, username: str, game: str, win: int):
    """Записывает крупный выигрыш в ленту"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO live_feed (user_id, username, game, win) VALUES (?, ?, ?, ?)",
            (user_id, username, game, win),
        )
        await db.commit()
        # Оставляем только последние 100 записей
        await db.execute(
            "DELETE FROM live_feed WHERE id NOT IN "
            "(SELECT id FROM live_feed ORDER BY id DESC LIMIT 100)"
        )
        await db.commit()


async def get_live_feed(limit: int = 15):
    """Возвращает последние крупные выигрыши"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT username, game, win, created_at FROM live_feed "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            return await cur.fetchall()
