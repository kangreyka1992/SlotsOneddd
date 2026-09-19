import aiosqlite
import datetime
import os
import random
import time as _time

DB_PATH = os.getenv("DB_PATH", "casino.db")


# ═══════════ АВТОМИГРАЦИЯ ═══════════

async def _auto_migrate():
    print(f"🔍 Auto-migrate: DB_PATH = {DB_PATH}", flush=True)
    print(f"🔍 Auto-migrate: abs = {os.path.abspath(DB_PATH)}", flush=True)
    print(f"🔍 Auto-migrate: exists = {os.path.exists(DB_PATH)}", flush=True)

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            async with db.execute("PRAGMA table_info(profiles)") as cur:
                cols = [c[1] for c in await cur.fetchall()]
            if cols and "owned" not in cols:
                await db.execute("ALTER TABLE profiles ADD COLUMN owned TEXT DEFAULT '[]'")
                await db.commit()
                print("🔧 Migration: added profiles.owned", flush=True)
        except Exception as e:
            print(f"⚠️ profiles migration error: {e}", flush=True)

        try:
            async with db.execute("PRAGMA table_info(withdrawals)") as cur:
                cols = [c[1] for c in await cur.fetchall()]
            for col, definition in [
                ("method",  "TEXT NOT NULL DEFAULT 'stars'"),
                ("amount",  "REAL NOT NULL DEFAULT 0"),
                ("details", "TEXT"),
            ]:
                if cols and col not in cols:
                    await db.execute(f"ALTER TABLE withdrawals ADD COLUMN {col} {definition}")
                    await db.commit()
                    print(f"🔧 Migration: added withdrawals.{col}", flush=True)
            await db.execute("UPDATE withdrawals SET amount = stars WHERE amount = 0")
            await db.commit()
        except Exception as e:
            print(f"⚠️ withdrawals migration error: {e}", flush=True)

        try:
            async with db.execute("SELECT COUNT(*), SUM(balance) FROM users") as cur:
                cnt, total = await cur.fetchone()
            print(f"👥 Users: {cnt}, total balance: {total}", flush=True)
        except Exception as e:
            print(f"⚠️ users count error: {e}", flush=True)

    print("🎉 Auto-migrate: complete", flush=True)


async def init_db():
    await _auto_migrate()

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
            CREATE TABLE IF NOT EXISTS daily_quests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                quest_id TEXT NOT NULL,
                progress INTEGER DEFAULT 0,
                target INTEGER NOT NULL,
                reward INTEGER NOT NULL,
                claimed INTEGER DEFAULT 0,
                quest_date TEXT NOT NULL,
                UNIQUE(user_id, quest_id, quest_date)
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
            CREATE TABLE IF NOT EXISTS battle_pass (
                user_id INTEGER PRIMARY KEY,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                season INTEGER NOT NULL,
                premium INTEGER DEFAULT 0,
                claimed_free TEXT DEFAULT '',
                claimed_premium TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS battle_pass_season (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season INTEGER NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ends_at TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                method TEXT NOT NULL DEFAULT 'stars',
                stars INTEGER NOT NULL DEFAULT 0,
                amount REAL NOT NULL DEFAULT 0,
                details TEXT,
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS winrate_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                winrate REAL NOT NULL DEFAULT 50.0,
                payout_mult REAL NOT NULL DEFAULT 1.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jackpot (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                amount INTEGER NOT NULL DEFAULT 10000000,
                last_winner INTEGER,
                last_won_at TIMESTAMP
            )
        """)
        await db.execute("INSERT OR IGNORE INTO jackpot (id, amount) VALUES (1, 10000000)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS hourly_bonus (
                user_id INTEGER PRIMARY KEY,
                last_claim TIMESTAMP,
                streak INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cashback (
                user_id INTEGER PRIMARY KEY,
                lost_total INTEGER DEFAULT 0,
                claimed_at TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referral_earnings (
                user_id INTEGER PRIMARY KEY,
                earned_total INTEGER DEFAULT 0,
                from_bets INTEGER DEFAULT 0,
                from_deposits INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY,
                avatar TEXT DEFAULT 'default',
                frame TEXT DEFAULT 'none',
                title TEXT DEFAULT 'Новичок',
                owned TEXT DEFAULT '[]',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game TEXT NOT NULL,
                prize_pool INTEGER NOT NULL,
                starts_at TIMESTAMP,
                ends_at TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tournament_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                score INTEGER DEFAULT 0,
                UNIQUE(tournament_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_levels (
                user_id INTEGER PRIMARY KEY,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS hall_of_fame (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                game TEXT NOT NULL,
                win INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wheel_spins (
                user_id INTEGER PRIMARY KEY,
                spins_available INTEGER DEFAULT 0,
                last_daily TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notification_settings (
                user_id INTEGER PRIMARY KEY,
                bonus_alerts INTEGER DEFAULT 1,
                cashback_alerts INTEGER DEFAULT 1,
                tournament_alerts INTEGER DEFAULT 1,
                daily_deal_alerts INTEGER DEFAULT 1,
                last_notified TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_case_deal (
                date TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                discount INTEGER NOT NULL DEFAULT 50
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                user_id INTEGER PRIMARY KEY,
                last_seen TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_states (
                user_id INTEGER PRIMARY KEY,
                state TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_tournaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game TEXT NOT NULL,
                prize_pool INTEGER NOT NULL DEFAULT 0,
                base_pool INTEGER NOT NULL DEFAULT 100000,
                started_at TIMESTAMP,
                ends_at TIMESTAMP,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_tournament_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                score INTEGER DEFAULT 0,
                UNIQUE(tournament_id, user_id)
            )
        """)
        # ═══════════ PVP ТАБЛИЦЫ ═══════════

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pvp_tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id INTEGER NOT NULL,
                game TEXT NOT NULL,
                bet INTEGER NOT NULL,
                format TEXT NOT NULL DEFAULT '1v1',
                max_players INTEGER NOT NULL DEFAULT 2,
                password TEXT,
                status TEXT DEFAULT 'waiting',
                prize_pool INTEGER DEFAULT 0,
                commission INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                winner_id INTEGER
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pvp_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                eliminated INTEGER DEFAULT 0,
                final_rank INTEGER,
                score INTEGER DEFAULT 0,
                UNIQUE(table_id, user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pvp_rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                round_num INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                score INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pvp_chat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pvp_stats (
                user_id INTEGER PRIMARY KEY,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_prize INTEGER DEFAULT 0,
                total_bet INTEGER DEFAULT 0
            )
        """)
        await db.commit()


# ═══════════ БАЗОВЫЕ ФУНКЦИИ ═══════════

async def has_deposited(user_id: int, min_stars: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT SUM(stars) FROM payments WHERE user_id = ? AND refunded = 0",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            total_stars = row[0] if row and row[0] else 0
            return total_stars >= min_stars


async def payment_exists(charge_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM payments WHERE charge_id = ?", (charge_id,)
        ) as cur:
            return await cur.fetchone() is not None


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


async def create_withdrawal(user_id: int, username: str, method: str,
                            amount: float, coins: int, details: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        stars_val = int(amount) if method == 'stars' else 0
        cursor = await db.execute(
            "INSERT INTO withdrawals "
            "(user_id, username, method, stars, amount, details, coins_spent) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, username, method, stars_val, amount, details, coins),
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


async def get_last_withdrawals(limit: int = 30):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, user_id, username, method, stars, amount, details, "
            "coins_spent, status, created_at "
            "FROM withdrawals ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            return await cur.fetchall()


# ═══════════ ПРОМОКОДЫ ═══════════

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


# ═══════════ СКИДКИ ═══════════

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


# ═══════════ РЕФЕРАЛЫ ═══════════

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


# ═══════════ ЕЖЕДНЕВНЫЙ БОНУС ═══════════

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


# ═══════════ ИГРЫ И СТАТИСТИКА ═══════════

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


# ═══════════ ДОСТИЖЕНИЯ ═══════════

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


# ═══════════ АДМИН-ЛОГИ ═══════════

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


# ═══════════ ВИЗИТЫ ═══════════

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


# ═══════════ ИНВЕНТАРЬ ═══════════

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


# ═══════════ БЕСПЛАТНЫЙ КЕЙС ═══════════

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


# ═══════════ ОБОРОТ КАЗИНО ═══════════

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


# ═══════════ ЛЕНТА ВЫИГРЫШЕЙ ═══════════

async def log_live_win(user_id: int, username: str, game: str, win: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO live_feed (user_id, username, game, win) VALUES (?, ?, ?, ?)",
            (user_id, username, game, win),
        )
        await db.execute(
            "DELETE FROM live_feed WHERE id NOT IN "
            "(SELECT id FROM live_feed ORDER BY id DESC LIMIT 100)"
        )
        await db.commit()


async def get_live_feed(limit: int = 15):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT username, game, win, created_at FROM live_feed "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            return await cur.fetchall()


# ═══════════ ЕЖЕДНЕВНЫЕ ЗАДАНИЯ ═══════════

DAILY_QUEST_POOL = [
    {"id": "bet_10",       "name": "🎯 Сделай 10 ставок",                "target": 10,     "reward": 500,   "type": "bets_count"},
    {"id": "bet_50",       "name": "🎯 Сделай 50 ставок",                "target": 50,     "reward": 2000,  "type": "bets_count"},
    {"id": "wagered_5000", "name": "💰 Поставь 5.000 монет",             "target": 5000,   "reward": 1000,  "type": "wagered"},
    {"id": "wagered_50000","name": "💰 Поставь 50.000 монет",            "target": 50000,  "reward": 8000,  "type": "wagered"},
    {"id": "win_3",        "name": "🎉 Выиграй 3 раза",                  "target": 3,      "reward": 800,   "type": "wins"},
    {"id": "win_10",       "name": "🏆 Выиграй 10 раз",                  "target": 10,     "reward": 3000,  "type": "wins"},
    {"id": "cases_2",      "name": "📦 Открой 2 кейса",                  "target": 2,      "reward": 1500,  "type": "cases_opened"},
    {"id": "cases_5",      "name": "📦 Открой 5 кейсов",                 "target": 5,      "reward": 4000,  "type": "cases_opened"},
    {"id": "slots_5",      "name": "🎰 Сыграй 5 раз в Слотах",           "target": 5,      "reward": 700,   "type": "game_slots2"},
    {"id": "mines_3",      "name": "⛏ Сыграй 3 раза в Mines",            "target": 3,      "reward": 700,   "type": "game_mines"},
    {"id": "crash_3",      "name": "📈 Сыграй 3 раза в Crash",           "target": 3,      "reward": 700,   "type": "game_crash"},
    {"id": "upgrade_1",    "name": "⚡ Сделай 1 апгрейд",                "target": 1,      "reward": 1000,  "type": "upgrades"},
]


async def get_daily_quests(user_id: int) -> list:
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT quest_id, progress, target, reward, claimed "
            "FROM daily_quests WHERE user_id = ? AND quest_date = ?",
            (user_id, today),
        ) as cur:
            rows = await cur.fetchall()

        if rows:
            quests = []
            for r in rows:
                quest_id = r[0]
                meta = next((q for q in DAILY_QUEST_POOL if q["id"] == quest_id), None)
                if not meta:
                    continue
                quests.append({
                    "id": quest_id,
                    "name": meta["name"],
                    "progress": r[1],
                    "target": r[2],
                    "reward": r[3],
                    "claimed": bool(r[4]),
                })
            return quests

        new_quests = random.sample(DAILY_QUEST_POOL, 3)
        for q in new_quests:
            await db.execute(
                "INSERT OR IGNORE INTO daily_quests "
                "(user_id, quest_id, progress, target, reward, quest_date) "
                "VALUES (?, ?, 0, ?, ?, ?)",
                (user_id, q["id"], q["target"], q["reward"], today),
            )
        await db.commit()

        return [
            {
                "id": q["id"],
                "name": q["name"],
                "progress": 0,
                "target": q["target"],
                "reward": q["reward"],
                "claimed": False,
            }
            for q in new_quests
        ]


async def update_quest_progress(user_id: int, quest_type: str, amount: int = 1):
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, quest_id, progress, target FROM daily_quests "
            "WHERE user_id = ? AND quest_date = ? AND claimed = 0",
            (user_id, today),
        ) as cur:
            rows = await cur.fetchall()

        for r in rows:
            q_id = r[1]
            meta = next((q for q in DAILY_QUEST_POOL if q["id"] == q_id), None)
            if not meta or meta["type"] != quest_type:
                continue

            new_progress = min(r[2] + amount, r[3])
            await db.execute(
                "UPDATE daily_quests SET progress = ? WHERE id = ?",
                (new_progress, r[0]),
            )

        await db.commit()


async def claim_quest_reward(user_id: int, quest_id: str) -> tuple:
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, progress, target, reward, claimed FROM daily_quests "
            "WHERE user_id = ? AND quest_id = ? AND quest_date = ?",
            (user_id, quest_id, today),
        ) as cur:
            row = await cur.fetchone()

        if not row:
            return False, 0, "Задание не найдено"

        q_db_id, progress, target, reward, claimed = row

        if claimed:
            return False, 0, "Награда уже получена"

        if progress < target:
            return False, 0, f"Не выполнено: {progress}/{target}"

        await db.execute(
            "UPDATE daily_quests SET claimed = 1 WHERE id = ?",
            (q_db_id,),
        )
        await db.commit()

        return True, reward, "Награда получена!"


# ═══════════ BATTLE PASS ═══════════

SEASON_DURATION_DAYS = 30
XP_PER_LEVEL = 1000
MAX_LEVEL = 50


def _current_season() -> int:
    now = int(_time.time())
    start = 1735689600
    days_passed = (now - start) // 86400
    return (days_passed // SEASON_DURATION_DAYS) + 1


BATTLE_PASS_REWARDS = [
    (1,   500,    1000,   None),
    (2,   500,    1000,   None),
    (3,   750,    1500,   None),
    (4,   750,    1500,   None),
    (5,   1000,   2000,   "case_starter"),
    (6,   1000,   2000,   None),
    (7,   1250,   2500,   None),
    (8,   1250,   2500,   None),
    (9,   1500,   3000,   None),
    (10,  1500,   3000,   "case_bronze"),
    (11,  1750,   3500,   None),
    (12,  1750,   3500,   None),
    (13,  2000,   4000,   None),
    (14,  2000,   4000,   None),
    (15,  2500,   5000,   "case_silver"),
    (16,  2500,   5000,   None),
    (17,  2750,   5500,   None),
    (18,  2750,   5500,   None),
    (19,  3000,   6000,   None),
    (20,  3000,   6000,   "case_gold"),
    (21,  3250,   6500,   None),
    (22,  3250,   6500,   None),
    (23,  3500,   7000,   None),
    (24,  3500,   7000,   None),
    (25,  4000,   8000,   "case_lucky"),
    (26,  4000,   8000,   None),
    (27,  4250,   8500,   None),
    (28,  4250,   8500,   None),
    (29,  4500,   9000,   None),
    (30,  4500,   9000,   "case_diamond_small"),
    (31,  4750,   9500,   None),
    (32,  4750,   9500,   None),
    (33,  5000,   10000,  None),
    (34,  5000,   10000,  None),
    (35,  5500,   11000,  "case_emerald"),
    (36,  5500,   11000,  None),
    (37,  5750,   11500,  None),
    (38,  5750,   11500,  None),
    (39,  6000,   12000,  None),
    (40,  6000,   12000,  "case_ruby"),
    (41,  6250,   12500,  None),
    (42,  6250,   12500,  None),
    (43,  6500,   13000,  None),
    (44,  6500,   13000,  None),
    (45,  7000,   14000,  "case_galaxy"),
    (46,  7000,   14000,  None),
    (47,  7500,   15000,  None),
    (48,  8000,   16000,  None),
    (49,  9000,   18000,  None),
    (50,  15000,  30000,  "case_titan"),
]


async def get_battle_pass(user_id: int) -> dict:
    season = _current_season()

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT xp, level, season, premium, claimed_free, claimed_premium "
            "FROM battle_pass WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()

        if row and row[2] != season:
            await db.execute(
                "UPDATE battle_pass SET xp = 0, level = 1, season = ?, "
                "claimed_free = '', claimed_premium = '' WHERE user_id = ?",
                (season, user_id),
            )
            await db.commit()
            row = (0, 1, season, row[3], "", "")

        if not row:
            await db.execute(
                "INSERT INTO battle_pass (user_id, xp, level, season, premium) "
                "VALUES (?, 0, 1, ?, 0)",
                (user_id, season),
            )
            await db.commit()
            row = (0, 1, season, 0, "", "")

        xp, level, season_db, premium, claimed_free, claimed_premium = row

        claimed_free_set = set(claimed_free.split(",")) if claimed_free else set()
        claimed_premium_set = set(claimed_premium.split(",")) if claimed_premium else set()

        return {
            "xp": xp,
            "level": level,
            "season": season_db,
            "premium": bool(premium),
            "claimed_free": list(claimed_free_set),
            "claimed_premium": list(claimed_premium_set),
            "xp_per_level": XP_PER_LEVEL,
            "max_level": MAX_LEVEL,
        }


async def add_battle_pass_xp(user_id: int, amount: int) -> dict:
    if amount <= 0:
        return await get_battle_pass(user_id)

    season = _current_season()

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT xp, level, season FROM battle_pass WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()

        if not row or row[2] != season:
            await db.execute(
                "INSERT INTO battle_pass (user_id, xp, level, season, premium) "
                "VALUES (?, ?, 1, ?, 0) "
                "ON CONFLICT(user_id) DO UPDATE SET xp = ?, level = 1, season = ?, "
                "claimed_free = '', claimed_premium = ''",
                (user_id, amount, season, amount, season),
            )
            await db.commit()
            return await get_battle_pass(user_id)

        new_xp = row[0] + amount
        new_level = min(MAX_LEVEL, (new_xp // XP_PER_LEVEL) + 1)

        await db.execute(
            "UPDATE battle_pass SET xp = ?, level = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE user_id = ?",
            (new_xp, new_level, user_id),
        )
        await db.commit()

    return await get_battle_pass(user_id)


async def claim_battle_pass_reward(user_id: int, level: int, premium: bool) -> tuple:
    season = _current_season()

    if level < 1 or level > MAX_LEVEL:
        return False, 0, None, "Неверный уровень"

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT xp, level, season, premium, claimed_free, claimed_premium "
            "FROM battle_pass WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()

        if not row:
            return False, 0, None, "Battle Pass не найден"

        xp, current_level, season_db, has_premium, claimed_free, claimed_premium = row

        if season_db != season:
            return False, 0, None, "Начался новый сезон — прогресс сброшен"

        if level > current_level:
            return False, 0, None, f"Уровень {level} ещё не достигнут"

        if premium and not has_premium:
            return False, 0, None, "Premium Pass не куплен"

        claimed_str = claimed_premium if premium else claimed_free
        claimed_set = set(claimed_str.split(",")) if claimed_str else set()
        key = str(level)

        if key in claimed_set:
            return False, 0, None, "Награда уже получена"

        reward_row = next((r for r in BATTLE_PASS_REWARDS if r[0] == level), None)
        if not reward_row:
            return False, 0, None, "Награда не найдена"

        _, free_coins, premium_coins, bonus_type = reward_row
        coins = premium_coins if premium else free_coins
        bonus = bonus_type

        claimed_set.add(key)
        new_claimed = ",".join(sorted(claimed_set))

        if premium:
            await db.execute(
                "UPDATE battle_pass SET claimed_premium = ? WHERE user_id = ?",
                (new_claimed, user_id),
            )
        else:
            await db.execute(
                "UPDATE battle_pass SET claimed_free = ? WHERE user_id = ?",
                (new_claimed, user_id),
            )
        await db.commit()

        return True, coins, bonus, "Награда получена!"


async def buy_premium_pass(user_id: int) -> bool:
    season = _current_season()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO battle_pass (user_id, xp, level, season, premium) "
            "VALUES (?, 0, 1, ?, 1) "
            "ON CONFLICT(user_id) DO UPDATE SET premium = 1, season = ?",
            (user_id, season, season),
        )
        await db.commit()
        return True


# ═══════════ ПОДКРУТКА ШАНСОВ ═══════════

async def set_winrate(user_id, winrate: float, payout_mult: float = 1.0):
    async with aiosqlite.connect(DB_PATH) as db:
        if user_id is None:
            await db.execute(
                "INSERT INTO winrate_settings (id, user_id, winrate, payout_mult) "
                "VALUES (1, NULL, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET winrate = ?, payout_mult = ?, "
                "updated_at = CURRENT_TIMESTAMP",
                (winrate, payout_mult, winrate, payout_mult),
            )
        else:
            await db.execute(
                "INSERT INTO winrate_settings (user_id, winrate, payout_mult) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET winrate = ?, payout_mult = ?, "
                "updated_at = CURRENT_TIMESTAMP",
                (user_id, winrate, payout_mult, winrate, payout_mult),
            )
        await db.commit()


async def get_winrate(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT winrate, payout_mult FROM winrate_settings WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if row:
                return row[0], row[1]

        async with db.execute(
            "SELECT winrate, payout_mult FROM winrate_settings WHERE id = 1 AND user_id IS NULL"
        ) as cur:
            row = await cur.fetchone()
            if row:
                return row[0], row[1]

    return 50.0, 1.0


async def clear_winrate(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        if user_id is None:
            await db.execute("DELETE FROM winrate_settings WHERE id = 1")
        else:
            await db.execute("DELETE FROM winrate_settings WHERE user_id = ?", (user_id,))
        await db.commit()


async def list_winrates():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, winrate, payout_mult, updated_at "
            "FROM winrate_settings ORDER BY updated_at DESC LIMIT 50"
        ) as cur:
            return await cur.fetchall()


# ═══════════ ДЖЕКПОТ ═══════════

async def get_jackpot() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT amount FROM jackpot WHERE id = 1") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def add_to_jackpot(amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jackpot SET amount = amount + ? WHERE id = 1",
            (amount,),
        )
        await db.commit()


async def win_jackpot(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT amount FROM jackpot WHERE id = 1") as cur:
            row = await cur.fetchone()
            amount = row[0] if row else 0
        await db.execute(
            "UPDATE jackpot SET amount = 10000000, last_winner = ?, "
            "last_won_at = CURRENT_TIMESTAMP WHERE id = 1",
            (user_id,),
        )
        await db.commit()
        return amount


# ═══════════ ЕЖЕЧАСНЫЙ БОНУС ═══════════

async def get_hourly_info(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT last_claim, streak FROM hourly_bonus WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return (row[0], row[1]) if row else (None, 0)


async def claim_hourly(user_id: int, streak: int):
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO hourly_bonus (user_id, last_claim, streak) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_claim = ?, streak = ?",
            (user_id, now, streak, now, streak),
        )
        await db.commit()


# ═══════════ КЭШБЭК ═══════════

async def add_to_cashback(user_id: int, lost: int):
    if lost <= 0:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO cashback (user_id, lost_total) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET lost_total = lost_total + ?",
            (user_id, lost, lost),
        )
        await db.commit()


async def get_cashback_info(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT lost_total FROM cashback WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            lost = row[0] if row else 0

    if lost >= 10_000_000:
        pct, tier = 12, "💎 Платина"
    elif lost >= 1_000_000:
        pct, tier = 8, "🥇 Золото"
    elif lost >= 50_000:
        pct, tier = 3, "🥈 Серебро"
    elif lost >= 5_000:
        pct, tier = 1, "🥉 Бронза"
    else:
        pct, tier = 0, "—"

    reward = int(lost * pct / 100)
    return {
        "lost": lost,
        "percent": pct,
        "tier": tier,
        "reward": reward,
        "can_claim": reward > 0,
    }


async def claim_cashback(user_id: int) -> int:
    info = await get_cashback_info(user_id)
    if info["reward"] <= 0:
        return 0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE cashback SET lost_total = 0, claimed_at = CURRENT_TIMESTAMP "
            "WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()
    await add_balance(user_id, info["reward"])
    return info["reward"]


# ═══════════ РЕФЕРАЛЬНЫЕ % ═══════════

async def add_referral_commission(referrer_id: int, bet_amount: int) -> int:
    commission = int(bet_amount * 0.05)
    if commission <= 0:
        return 0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO referral_earnings (user_id, earned_total, from_bets) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "earned_total = earned_total + ?, from_bets = from_bets + ?",
            (referrer_id, commission, commission, commission, commission),
        )
        await db.commit()
    await add_balance(referrer_id, commission)
    return commission


async def get_referral_earnings(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT earned_total, from_bets, from_deposits "
            "FROM referral_earnings WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if row:
                return {"earned": row[0] or 0, "from_bets": row[1] or 0, "from_deposits": row[2] or 0}
            return {"earned": 0, "from_bets": 0, "from_deposits": 0}


# ═══════════ ПРОФИЛЬ ═══════════

async def get_profile(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO profiles (user_id) VALUES (?)",
            (user_id,),
        )
        await db.commit()
        async with db.execute(
            "SELECT avatar, frame, title, owned FROM profiles WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return {
                "avatar": row[0] if row else "default",
                "frame": row[1] if row else "none",
                "title": row[2] if row else "Новичок",
                "owned": row[3] if row and row[3] else "[]",
            }


async def set_profile(user_id: int, avatar: str = None, frame: str = None,
                      title: str = None, owned: str = None):
    current = await get_profile(user_id)
    new_avatar = avatar if avatar is not None else current["avatar"]
    new_frame = frame if frame is not None else current["frame"]
    new_title = title if title is not None else current["title"]
    new_owned = owned if owned is not None else current.get("owned", "[]")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE profiles SET avatar = ?, frame = ?, title = ?, owned = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (new_avatar, new_frame, new_title, new_owned, user_id),
        )
        await db.commit()


# ═══════════ ТУРНИРЫ ═══════════

async def get_active_tournament():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, game, prize_pool, starts_at, ends_at, status "
            "FROM tournaments WHERE status = 'active' "
            "ORDER BY id DESC LIMIT 1",
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0], "game": row[1], "prize_pool": row[2],
                "starts_at": row[3], "ends_at": row[4], "status": row[5],
            }


async def add_tournament_score(tournament_id: int, user_id: int, score: int):
    if score <= 0:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO tournament_scores (tournament_id, user_id, score) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(tournament_id, user_id) DO UPDATE SET "
            "score = score + ?",
            (tournament_id, user_id, score, score),
        )
        await db.commit()


async def get_tournament_leaderboard(tournament_id: int, limit: int = 20):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT ts.user_id, u.username, ts.score "
            "FROM tournament_scores ts "
            "LEFT JOIN users u ON u.user_id = ts.user_id "
            "WHERE ts.tournament_id = ? "
            "ORDER BY ts.score DESC LIMIT ?",
            (tournament_id, limit),
        ) as cur:
            return await cur.fetchall()


async def initialize_tournament_if_needed():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM tournaments WHERE status = 'active'"
        ) as cur:
            cnt = (await cur.fetchone())[0]
        if cnt == 0:
            await db.execute(
                "INSERT INTO tournaments (game, prize_pool, starts_at, ends_at) "
                "VALUES ('crash', 1000000, CURRENT_TIMESTAMP, datetime('now', '+7 days'))"
            )
            await db.commit()
            print("🏆 Турнир создан", flush=True)


# ═══════════ HALL OF FAME ═══════════

async def add_to_hall_of_fame(user_id: int, username: str, game: str, win: int):
    if win < 100_000:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO hall_of_fame (user_id, username, game, win) "
            "VALUES (?, ?, ?, ?)",
            (user_id, username, game, win),
        )
        await db.commit()


async def get_hall_of_fame(limit: int = 30):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username, game, win, created_at "
            "FROM hall_of_fame ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            return await cur.fetchall()


# ═══════════ КОЛЕСО ФОРТУНЫ ═══════════

async def get_wheel_info(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO wheel_spins (user_id, spins_available) "
            "VALUES (?, 0)",
            (user_id,)
        )
        await db.commit()

        async with db.execute(
            "SELECT spins_available, last_daily FROM wheel_spins WHERE user_id = ?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()

        spins = row[0] if row else 0
        last_daily = row[1] if row else None

        now = datetime.datetime.utcnow()
        should_grant = False

        if not last_daily:
            should_grant = True
        else:
            try:
                last_dt = datetime.datetime.fromisoformat(last_daily)
                if (now - last_dt).total_seconds() >= 86400:
                    should_grant = True
            except (ValueError, TypeError):
                should_grant = True

        if should_grant:
            spins = 1
            await db.execute(
                "UPDATE wheel_spins SET spins_available = ?, last_daily = ? WHERE user_id = ?",
                (spins, now.isoformat(), user_id),
            )
            await db.commit()

        return {"spins": spins, "last_daily": last_daily}


async def add_wheel_spin(user_id: int, count: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO wheel_spins (user_id, spins_available) VALUES (?, 0)",
            (user_id,),
        )
        await db.execute(
            "UPDATE wheel_spins SET spins_available = spins_available + ? "
            "WHERE user_id = ?",
            (count, user_id),
        )
        await db.commit()


async def consume_wheel_spin(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT spins_available FROM wheel_spins WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row or row[0] <= 0:
                return False
        await db.execute(
            "UPDATE wheel_spins SET spins_available = spins_available - 1 "
            "WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()
        return True


# ═══════════ УРОВНИ ═══════════

async def get_user_level(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_levels (user_id) VALUES (?)",
            (user_id,),
        )
        await db.commit()
        async with db.execute(
            "SELECT xp, level FROM user_levels WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return {"xp": row[0] if row else 0, "level": row[1] if row else 1}


async def add_user_xp(user_id: int, xp: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT xp, level FROM user_levels WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT INTO user_levels (user_id, xp, level) VALUES (?, ?, 1)",
                (user_id, xp),
            )
        else:
            new_xp = row[0] + xp
            new_level = 1 + int((new_xp / 500) ** 0.5)
            await db.execute(
                "UPDATE user_levels SET xp = ?, level = ? WHERE user_id = ?",
                (new_xp, new_level, user_id),
            )
        await db.commit()


# ═══════════ УВЕДОМЛЕНИЯ ═══════════

async def get_notification_settings(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO notification_settings (user_id) VALUES (?)",
            (user_id,)
        )
        await db.commit()
        async with db.execute(
            "SELECT bonus_alerts, cashback_alerts, tournament_alerts, "
            "daily_deal_alerts FROM notification_settings WHERE user_id = ?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return {
                "bonus_alerts": bool(row[0]) if row else True,
                "cashback_alerts": bool(row[1]) if row else True,
                "tournament_alerts": bool(row[2]) if row else True,
                "daily_deal_alerts": bool(row[3]) if row else True,
            }


async def update_notification_settings(user_id: int, **kwargs):
    async with aiosqlite.connect(DB_PATH) as db:
        fields = []
        values = []
        for k, v in kwargs.items():
            if k in ("bonus_alerts", "cashback_alerts", "tournament_alerts", "daily_deal_alerts"):
                fields.append(f"{k} = ?")
                values.append(1 if v else 0)
        if not fields:
            return
        values.append(user_id)
        await db.execute(
            f"UPDATE notification_settings SET {', '.join(fields)} WHERE user_id = ?",
            values
        )
        await db.commit()


async def get_users_for_broadcast(alert_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT user_id FROM notification_settings WHERE {alert_type} = 1"
        ) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


# ═══════════ СКИДКА ДНЯ ═══════════

async def get_daily_case_deal():
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT case_id, discount FROM daily_case_deal WHERE date = ?",
            (today,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return {"case_id": row[0], "discount": row[1]}

            cases = ["gold", "lucky", "diamond_small", "emerald", "sapphire", "ruby"]
            chosen = random.choice(cases)
            discount = random.choice([30, 40, 50])

            await db.execute(
                "INSERT INTO daily_case_deal (date, case_id, discount) VALUES (?, ?, ?)",
                (today, chosen, discount)
            )
            await db.commit()
            return {"case_id": chosen, "discount": discount}


# ═══════════ ПУБЛИЧНАЯ СТАТИСТИКА ═══════════

async def get_public_stats():
    """Возвращает публичную статистику для лендинга /stats."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Общее количество юзеров
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = (await cur.fetchone())[0] or 0

        # Онлайн (юзеры, заходившие за последние 5 минут)
        # В таблице user_visits хранится только дата (без времени),
        # поэтому берём активных за сегодня
        today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        async with db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM user_visits WHERE visit_date = ?",
            (today,),
        ) as cur:
            online_today = (await cur.fetchone())[0] or 0

        # Всего сыграно игр
        async with db.execute(
            "SELECT COALESCE(SUM(games_played), 0) FROM users"
        ) as cur:
            total_games = (await cur.fetchone())[0] or 0

        # Всего поставлено монет
        async with db.execute(
            "SELECT COALESCE(SUM(total_wagered), 0) FROM users"
        ) as cur:
            total_wagered = (await cur.fetchone())[0] or 0

        # Всего выиграно монет
        async with db.execute(
            "SELECT COALESCE(SUM(total_won), 0) FROM users"
        ) as cur:
            total_won = (await cur.fetchone())[0] or 0

        # Общий джекпот
        async with db.execute("SELECT amount FROM jackpot WHERE id = 1") as cur:
            row = await cur.fetchone()
            jackpot = row[0] if row else 0

        # Оборот за 7 дней (по house_flow)
        seven_days_ago = (
            datetime.datetime.utcnow() - datetime.timedelta(days=7)
        ).isoformat()
        async with db.execute(
            "SELECT DATE(created_at), "
            "COALESCE(SUM(wagered), 0), COALESCE(SUM(paid), 0) "
            "FROM house_flow WHERE created_at >= ? "
            "GROUP BY DATE(created_at) ORDER BY DATE(created_at)",
            (seven_days_ago,),
        ) as cur:
            turnover_rows = await cur.fetchall()

        turnover_by_day = [
            {"date": r[0], "wagered": r[1] or 0, "paid": r[2] or 0}
            for r in turnover_rows
        ]

        # Live-лента (последние 20 крупных выигрышей > 1000)
        async with db.execute(
            "SELECT username, game, win, created_at FROM live_feed "
            "WHERE win >= 1000 ORDER BY id DESC LIMIT 20"
        ) as cur:
            feed_rows = await cur.fetchall()

        live_feed_data = [
            {
                "username": r[0] or "Игрок",
                "game": r[1],
                "win": r[2],
                "created_at": r[3],
            }
            for r in feed_rows
        ]

        return {
            "total_users": total_users,
            "online_today": online_today,
            "total_games": total_games,
            "total_wagered": total_wagered,
            "total_won": total_won,
            "jackpot": jackpot,
            "turnover_by_day": turnover_by_day,
            "live_feed": live_feed_data,
        }


async def get_online_count(minutes: int = 5) -> int:
    """
    Реальный онлайн за последние N минут.
    Требует таблицу user_sessions (создаётся в migrate).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        since = (
            datetime.datetime.utcnow() - datetime.timedelta(minutes=minutes)
        ).isoformat()
        async with db.execute(
            "SELECT COUNT(*) FROM user_sessions WHERE last_seen >= ?",
            (since,),
        ) as cur:
            return (await cur.fetchone())[0] or 0


async def touch_session(user_id: int):
    """Обновляет сессию юзера (для подсчёта онлайна)."""
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.datetime.utcnow().isoformat()
        await db.execute(
            "INSERT INTO user_sessions (user_id, last_seen) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_seen = ?",
            (user_id, now, now),
        )
        await db.commit()


# ═══════════ СОСТОЯНИЯ ЮЗЕРА (для поддержки) ═══════════

async def set_user_state(user_id: int, state: str):
    async with aiosqlite.connect(DB_PATH) as db:
        if state is None:
            await db.execute(
                "DELETE FROM user_states WHERE user_id = ?", (user_id,)
            )
        else:
            await db.execute(
                "INSERT INTO user_states (user_id, state) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET state = ?",
                (user_id, state, state),
            )
        await db.commit()


async def get_user_state(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT state FROM user_states WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

# ═══════════ ЕЖЕДНЕВНЫЙ ТУРНИР ═══════════

DAILY_TOURNAMENT_GAMES = ["crash", "mines", "slots2", "dice", "rr", "plinko", "coin"]
DAILY_TOURNAMENT_BASE_POOL = 100_000
DAILY_TOURNAMENT_PERCENT_FROM_BETS = 0.10  # 10% от ставок в фонд


def _current_tournament_game() -> str:
    """
    Игра турнира зависит от дня недели.
    Пн=crash, Вт=mines, Ср=slots2, Чт=dice, Пт=rr, Сб=plinko, Вс=coin.
    """
    weekday = datetime.datetime.utcnow().weekday()  # 0=Пн, 6=Вс
    return DAILY_TOURNAMENT_GAMES[weekday % len(DAILY_TOURNAMENT_GAMES)]


async def get_active_daily_tournament():
    """Возвращает активный турнир (status='active')."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, game, prize_pool, base_pool, started_at, ends_at, status "
            "FROM daily_tournaments WHERE status = 'active' "
            "ORDER BY id DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "game": row[1],
                "prize_pool": row[2],
                "base_pool": row[3],
                "started_at": row[4],
                "ends_at": row[5],
                "status": row[6],
            }


async def get_pending_daily_tournament():
    """Возвращает турнир, который ещё не стартовал (status='pending')."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, game, prize_pool, base_pool, started_at, ends_at, status "
            "FROM daily_tournaments WHERE status = 'pending' "
            "ORDER BY id ASC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "game": row[1],
                "prize_pool": row[2],
                "base_pool": row[3],
                "started_at": row[4],
                "ends_at": row[5],
                "status": row[6],
            }


async def get_latest_daily_tournament():
    """Последний турнир (активный или завершённый) — для отображения на UI."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, game, prize_pool, base_pool, started_at, ends_at, status "
            "FROM daily_tournaments "
            "WHERE status IN ('active', 'pending', 'finished') "
            "ORDER BY id DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "game": row[1],
                "prize_pool": row[2],
                "base_pool": row[3],
                "started_at": row[4],
                "ends_at": row[5],
                "status": row[6],
            }


async def create_daily_tournament(game: str, base_pool: int, duration_min: int = 30) -> int:
    """Создаёт турнир в статусе 'active' на duration_min минут."""
    now = datetime.datetime.utcnow()
    ends = now + datetime.timedelta(minutes=duration_min)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO daily_tournaments "
            "(game, prize_pool, base_pool, started_at, ends_at, status) "
            "VALUES (?, ?, ?, ?, ?, 'active')",
            (game, base_pool, base_pool, now.isoformat(), ends.isoformat()),
        )
        await db.commit()
        return cursor.lastrowid


async def add_daily_tournament_score(tournament_id: int, user_id: int, score: int):
    """Добавляет очки игроку в турнире. Также 10% от очков идёт в призовой фонд."""
    if score <= 0:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        # Очки
        await db.execute(
            "INSERT INTO daily_tournament_scores (tournament_id, user_id, score) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(tournament_id, user_id) DO UPDATE SET score = score + ?",
            (tournament_id, user_id, score, score),
        )
        # Фонд
        pool_add = int(score * DAILY_TOURNAMENT_PERCENT_FROM_BETS)
        if pool_add > 0:
            await db.execute(
                "UPDATE daily_tournaments SET prize_pool = prize_pool + ? WHERE id = ?",
                (pool_add, tournament_id),
            )
        await db.commit()


async def get_daily_tournament_leaderboard(tournament_id: int, limit: int = 20):
    """Возвращает топ игроков турнира: [(user_id, username, score), ...]."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT ts.user_id, u.username, ts.score "
            "FROM daily_tournament_scores ts "
            "LEFT JOIN users u ON u.user_id = ts.user_id "
            "WHERE ts.tournament_id = ? "
            "ORDER BY ts.score DESC LIMIT ?",
            (tournament_id, limit),
        ) as cur:
            return await cur.fetchall()


async def get_daily_tournament_participants_count(tournament_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM daily_tournament_scores WHERE tournament_id = ?",
            (tournament_id,),
        ) as cur:
            return (await cur.fetchone())[0] or 0


async def close_daily_tournament(tournament_id: int) -> dict:
    """
    Закрывает турнир, выплачивает призы топ-3.
    Возвращает результат: {status, prize_pool, winners: [{user_id, username, prize, place}]}.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Получаем данные турнира
        async with db.execute(
            "SELECT prize_pool FROM daily_tournaments WHERE id = ?",
            (tournament_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return {"status": "not_found", "prize_pool": 0, "winners": []}

            prize_pool = row[0] or 0

        # Топ-3
        async with db.execute(
            "SELECT ts.user_id, u.username, ts.score "
            "FROM daily_tournament_scores ts "
            "LEFT JOIN users u ON u.user_id = ts.user_id "
            "WHERE ts.tournament_id = ? "
            "ORDER BY ts.score DESC LIMIT 3",
            (tournament_id,),
        ) as cur:
            top = await cur.fetchall()

    # Если нет участников — отменяем
    if not top:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE daily_tournaments SET status = 'cancelled' WHERE id = ?",
                (tournament_id,),
            )
            await db.commit()
        return {"status": "cancelled", "prize_pool": prize_pool, "winners": []}

    # Распределение призов 50/30/20 (топ-3), если меньше — то по факту
    shares = [0.50, 0.30, 0.20]
    winners = []

    for i, (uid, uname, score) in enumerate(top):
        prize = int(prize_pool * shares[i]) if i < len(shares) else 0
        if prize > 0:
            await add_balance(uid, prize, None)
        winners.append({
            "user_id": uid,
            "username": uname or f"user_{uid}",
            "score": score,
            "prize": prize,
            "place": i + 1,
        })

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE daily_tournaments SET status = 'finished' WHERE id = ?",
            (tournament_id,),
        )
        await db.commit()

    return {"status": "finished", "prize_pool": prize_pool, "winners": winners}


async def get_daily_tournament_history(limit: int = 10):
    """Возвращает последние завершённые турниры с топ-3."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, game, prize_pool, started_at, ends_at, status "
            "FROM daily_tournaments "
            "WHERE status IN ('finished', 'cancelled') "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            tournaments = await cur.fetchall()

        result = []
        for t in tournaments:
            tid = t[0]
            async with db.execute(
                "SELECT ts.user_id, u.username, ts.score "
                "FROM daily_tournament_scores ts "
                "LEFT JOIN users u ON u.user_id = ts.user_id "
                "WHERE ts.tournament_id = ? "
                "ORDER BY ts.score DESC LIMIT 3",
                (tid,),
            ) as cur:
                top = await cur.fetchall()

            result.append({
                "id": tid,
                "game": t[1],
                "prize_pool": t[2],
                "started_at": t[3],
                "ends_at": t[4],
                "status": t[5],
                "top": [
                    {"user_id": r[0], "username": r[1] or f"user_{r[0]}", "score": r[2]}
                    for r in top
                ],
            })

        return result


async def get_user_daily_tournament_score(tournament_id: int, user_id: int) -> int:
    """Очки конкретного игрока в турнире."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT score FROM daily_tournament_scores "
            "WHERE tournament_id = ? AND user_id = ?",
            (tournament_id, user_id),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def reset_stale_tournaments():
    """
    Закрывает все 'active' турниры, у которых ends_at в прошлом.
    Нужно для случая, если сервер был выключен.
    """
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM daily_tournaments "
            "WHERE status = 'active' AND ends_at < ?",
            (now,),
        ) as cur:
            stale = [r[0] for r in await cur.fetchall()]

    for tid in stale:
        try:
            await close_daily_tournament(tid)
        except Exception as e:
            print(f"⚠️ reset stale tournament {tid} error: {e}", flush=True)

# ═══════════ PVP РЕЖИМ ═══════════

PVP_GAMES = ("slots2", "crash", "mines", "dice")
PVP_FORMATS = {
    "1v1":   {"max_players": 2, "min_players": 2, "label": "1×1 Дуэль"},
    "tour4": {"max_players": 4, "min_players": 4, "label": "Турнир на 4"},
    "tour8": {"max_players": 8, "min_players": 8, "label": "Турнир на 8"},
}
PVP_COMMISSION_PERCENT = 0.02  # 2% с банка
PVP_TABLE_TIMEOUT = 300       # 5 минут — если не собрались, отмена


async def pvp_create_table(
    creator_id: int,
    game: str,
    bet: int,
    format: str = "1v1",
    password: str = None,
) -> int:
    """
    Создать PvP-стол. Возвращает table_id.
    
    ⚠️ ВАЖНО: функция САМА списывает ставку с баланса создателя
    и добавляет её в prize_pool. НЕ списывайте баланс повторно в эндпоинте!
    """
    fmt = PVP_FORMATS.get(format)
    if not fmt:
        raise ValueError("Неизвестный формат")

    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Проверяем баланс создателя
        async with db.execute(
            "SELECT balance FROM users WHERE user_id = ?",
            (creator_id,),
        ) as cur:
            row = await cur.fetchone()
            balance = row[0] if row else 0

        if balance < bet:
            raise ValueError(f"Нужно {bet} 🪙 (у тебя {balance})")

        # 2. Проверяем, что создатель ещё не в другом столе
        async with db.execute(
            "SELECT t.id FROM pvp_tables t "
            "JOIN pvp_participants p ON p.table_id = t.id "
            "WHERE p.user_id = ? AND t.status IN ('waiting', 'active')",
            (creator_id,),
        ) as cur:
            existing = await cur.fetchone()
            if existing:
                raise ValueError(f"Вы уже в столе #{existing[0]}")

        # 3. Списываем ставку
        await db.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ?",
            (bet, creator_id),
        )

        # 4. Создаём стол с сразу заполненным prize_pool
        cursor = await db.execute(
            "INSERT INTO pvp_tables "
            "(creator_id, game, bet, format, max_players, password, status, prize_pool) "
            "VALUES (?, ?, ?, ?, ?, ?, 'waiting', ?)",
            (creator_id, game, bet, format, fmt["max_players"], password, bet),
        )
        table_id = cursor.lastrowid

        # 5. Добавляем создателя как участника
        await db.execute(
            "INSERT INTO pvp_participants (table_id, user_id) VALUES (?, ?)",
            (table_id, creator_id),
        )

        await db.commit()
        return table_id


async def pvp_get_table(table_id: int):
    """Получить информацию о столе."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, creator_id, game, bet, format, max_players, password, "
            "status, prize_pool, commission, created_at, started_at, finished_at, winner_id "
            "FROM pvp_tables WHERE id = ?",
            (table_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0], "creator_id": row[1], "game": row[2], "bet": row[3],
                "format": row[4], "max_players": row[5], "password": row[6],
                "status": row[7], "prize_pool": row[8], "commission": row[9],
                "created_at": row[10], "started_at": row[11],
                "finished_at": row[12], "winner_id": row[13],
            }


async def pvp_list_open_tables(limit: int = 30):
    """Список открытых столов (status = waiting)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT t.id, t.creator_id, u.username, t.game, t.bet, t.format, "
            "t.max_players, t.password, t.created_at, "
            "(SELECT COUNT(*) FROM pvp_participants WHERE table_id = t.id) as players "
            "FROM pvp_tables t "
            "LEFT JOIN users u ON u.user_id = t.creator_id "
            "WHERE t.status = 'waiting' "
            "ORDER BY t.id DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            return [
                {
                    "id": r[0], "creator_id": r[1], "creator_username": r[2] or f"user_{r[1]}",
                    "game": r[3], "bet": r[4], "format": r[5],
                    "max_players": r[6], "is_private": bool(r[7]),
                    "created_at": r[8], "players": r[9],
                }
                for r in rows
            ]


async def pvp_get_participants(table_id: int):
    """Список участников стола."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT p.user_id, u.username, p.joined_at, p.eliminated, "
            "p.final_rank, p.score "
            "FROM pvp_participants p "
            "LEFT JOIN users u ON u.user_id = p.user_id "
            "WHERE p.table_id = ? "
            "ORDER BY p.id ASC",
            (table_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [
                {
                    "user_id": r[0], "username": r[1] or f"user_{r[0]}",
                    "joined_at": r[2], "eliminated": bool(r[3]),
                    "final_rank": r[4], "score": r[5],
                }
                for r in rows
            ]


async def pvp_join_table(table_id: int, user_id: int, password: str = None) -> dict:
    """Присоединиться к столу. Возвращает {ok, error?, status?}."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Проверяем стол
        async with db.execute(
            "SELECT game, bet, format, max_players, password, status "
            "FROM pvp_tables WHERE id = ?",
            (table_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return {"ok": False, "error": "Стол не найден"}

            game, bet, format, max_players, pwd, status = row

        if status != "waiting":
            return {"ok": False, "error": "Стол уже не принимает игроков"}

        if pwd and pwd != password:
            return {"ok": False, "error": "Неверный пароль"}

        # Проверяем, не в столе ли уже
        async with db.execute(
            "SELECT 1 FROM pvp_participants WHERE table_id = ? AND user_id = ?",
            (table_id, user_id),
        ) as cur:
            if await cur.fetchone():
                return {"ok": False, "error": "Вы уже в этом столе"}

        # Проверяем, не в другом ли столе
        async with db.execute(
            "SELECT t.id FROM pvp_tables t "
            "JOIN pvp_participants p ON p.table_id = t.id "
            "WHERE p.user_id = ? AND t.status IN ('waiting', 'active')",
            (user_id,),
        ) as cur:
            existing = await cur.fetchone()
            if existing:
                return {"ok": False, "error": f"Вы уже в столе #{existing[0]}"}

        # Проверяем баланс
        async with db.execute(
            "SELECT balance FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            bal_row = await cur.fetchone()
            balance = bal_row[0] if bal_row else 0

        if balance < bet:
            return {"ok": False, "error": f"Нужно {bet} 🪙 (у тебя {balance})"}

        # Проверяем количество игроков
        async with db.execute(
            "SELECT COUNT(*) FROM pvp_participants WHERE table_id = ?",
            (table_id,),
        ) as cur:
            players = (await cur.fetchone())[0]

        if players >= max_players:
            return {"ok": False, "error": "Стол заполнен"}

        # Списываем ставку
        await db.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ?",
            (bet, user_id),
        )

        # Добавляем участника
        await db.execute(
            "INSERT INTO pvp_participants (table_id, user_id) VALUES (?, ?)",
            (table_id, user_id),
        )

        # Обновляем prize_pool
        await db.execute(
            "UPDATE pvp_tables SET prize_pool = prize_pool + ? WHERE id = ?",
            (bet, table_id),
        )

        await db.commit()

    # Проверяем, собрались ли все
    new_players = players + 1
    if new_players >= max_players:
        # Стартуем автоматически
        await pvp_start_table(table_id)
        return {"ok": True, "status": "started"}
    else:
        return {"ok": True, "status": "waiting"}


async def pvp_leave_table(table_id: int, user_id: int) -> dict:
    """Покинуть стол (только если status = waiting)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT bet, status FROM pvp_tables WHERE id = ?", (table_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return {"ok": False, "error": "Стол не найден"}

            bet, status = row

        if status != "waiting":
            return {"ok": False, "error": "Нельзя покинуть начавшийся стол"}

        # Возвращаем ставку
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (bet, user_id),
        )

        # Удаляем из участников
        await db.execute(
            "DELETE FROM pvp_participants WHERE table_id = ? AND user_id = ?",
            (table_id, user_id),
        )

        # Уменьшаем prize_pool
        await db.execute(
            "UPDATE pvp_tables SET prize_pool = MAX(0, prize_pool - ?) WHERE id = ?",
            (bet, table_id),
        )

        # Если это был создатель — удаляем стол
        async with db.execute(
            "SELECT creator_id FROM pvp_tables WHERE id = ?", (table_id,)
        ) as cur:
            creator_row = await cur.fetchone()

        if creator_row and creator_row[0] == user_id:
            # Возвращаем всем участникам ставки
            async with db.execute(
                "SELECT user_id FROM pvp_participants WHERE table_id = ?",
                (table_id,),
            ) as cur:
                others = await cur.fetchall()

            for o in others:
                await db.execute(
                    "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                    (bet, o[0]),
                )

            await db.execute("DELETE FROM pvp_participants WHERE table_id = ?", (table_id,))
            await db.execute("DELETE FROM pvp_tables WHERE id = ?", (table_id,))

        await db.commit()
        return {"ok": True}


async def pvp_start_table(table_id: int) -> bool:
    """Стартует стол (status → active, started_at = now)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pvp_tables SET status = 'active', started_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = 'waiting'",
            (table_id,),
        )
        await db.commit()
        return True


async def pvp_submit_round_score(table_id: int, user_id: int, round_num: int, score: int):
    """Сохранить результат раунда игрока."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO pvp_rounds (table_id, round_num, user_id, score) "
            "VALUES (?, ?, ?, ?)",
            (table_id, round_num, user_id, score),
        )
        # Обновляем общий счёт
        await db.execute(
            "UPDATE pvp_participants SET score = score + ? "
            "WHERE table_id = ? AND user_id = ?",
            (score, table_id, user_id),
        )
        await db.commit()


async def pvp_get_round_scores(table_id: int, round_num: int):
    """Результаты конкретного раунда."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT r.user_id, u.username, r.score "
            "FROM pvp_rounds r "
            "LEFT JOIN users u ON u.user_id = r.user_id "
            "WHERE r.table_id = ? AND r.round_num = ? "
            "ORDER BY r.score DESC",
            (table_id, round_num),
        ) as cur:
            rows = await cur.fetchall()
            return [
                {"user_id": r[0], "username": r[1] or f"user_{r[0]}", "score": r[2]}
                for r in rows
            ]


async def pvp_eliminate_player(table_id: int, user_id: int, rank: int):
    """Пометить игрока выбывшим с его финальным местом."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pvp_participants SET eliminated = 1, final_rank = ? "
            "WHERE table_id = ? AND user_id = ?",
            (rank, table_id, user_id),
        )
        await db.commit()


async def pvp_finish_table(table_id: int, winner_id: int) -> dict:
    """Завершить стол, выплатить призы."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Получаем prize_pool
        async with db.execute(
            "SELECT prize_pool FROM pvp_tables WHERE id = ?", (table_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return {"ok": False, "error": "Стол не найден"}
            prize_pool = row[0] or 0

        commission = int(prize_pool * PVP_COMMISSION_PERCENT)
        prize = prize_pool - commission

        # Выплачиваем победителю
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (prize, winner_id),
        )

        # Обновляем стол
        await db.execute(
            "UPDATE pvp_tables SET status = 'finished', finished_at = CURRENT_TIMESTAMP, "
            "winner_id = ?, commission = ? WHERE id = ?",
            (winner_id, commission, table_id),
        )

        # Обновляем статистику всех участников
        async with db.execute(
            "SELECT user_id FROM pvp_participants WHERE table_id = ?",
            (table_id,),
        ) as cur:
            participants = [r[0] for r in await cur.fetchall()]

        bet_row = None
        async with db.execute(
            "SELECT bet FROM pvp_tables WHERE id = ?", (table_id,)
        ) as cur:
            bet_row = await cur.fetchone()
        bet = bet_row[0] if bet_row else 0

        for uid in participants:
            if uid == winner_id:
                await db.execute(
                    "INSERT INTO pvp_stats (user_id, wins, total_prize, total_bet) "
                    "VALUES (?, 1, ?, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET "
                    "wins = wins + 1, total_prize = total_prize + ?, total_bet = total_bet + ?",
                    (uid, prize, bet, prize, bet),
                )
            else:
                await db.execute(
                    "INSERT INTO pvp_stats (user_id, losses, total_bet) "
                    "VALUES (?, 1, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET "
                    "losses = losses + 1, total_bet = total_bet + ?",
                    (uid, bet, bet),
                )

        await db.commit()

        return {
            "ok": True,
            "prize": prize,
            "commission": commission,
            "prize_pool": prize_pool,
        }


async def pvp_get_active_table_for_user(user_id: int):
    """Возвращает активный или ожидающий стол, в котором юзер сейчас."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT t.id, t.creator_id, t.game, t.bet, t.format, t.max_players, "
            "t.status, t.prize_pool, t.started_at "
            "FROM pvp_tables t "
            "JOIN pvp_participants p ON p.table_id = t.id "
            "WHERE p.user_id = ? AND t.status IN ('waiting', 'active') "
            "ORDER BY t.id DESC LIMIT 1",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0], "creator_id": row[1], "game": row[2], "bet": row[3],
                "format": row[4], "max_players": row[5], "status": row[6],
                "prize_pool": row[7], "started_at": row[8],
            }


async def pvp_get_stats(user_id: int):
    """Статистика PvP игрока."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT wins, losses, total_prize, total_bet FROM pvp_stats WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return {"wins": 0, "losses": 0, "total_prize": 0, "total_bet": 0, "winrate": 0}

            wins, losses, prize, bet = row
            total = wins + losses
            winrate = round(wins / total * 100, 1) if total > 0 else 0
            return {
                "wins": wins, "losses": losses,
                "total_prize": prize or 0, "total_bet": bet or 0,
                "winrate": winrate,
            }


async def pvp_leaderboard(limit: int = 20):
    """Топ PvP игроков."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT s.user_id, u.username, s.wins, s.losses, s.total_prize "
            "FROM pvp_stats s "
            "LEFT JOIN users u ON u.user_id = s.user_id "
            "WHERE s.wins > 0 OR s.losses > 0 "
            "ORDER BY s.wins DESC, s.total_prize DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            result = []
            for i, r in enumerate(rows, 1):
                total = (r[2] or 0) + (r[3] or 0)
                winrate = round(r[2] / total * 100, 1) if total > 0 else 0
                result.append({
                    "rank": i, "user_id": r[0], "username": r[1] or f"user_{r[0]}",
                    "wins": r[2], "losses": r[3], "total_prize": r[4] or 0,
                    "winrate": winrate,
                })
            return result


async def pvp_chat_send(table_id: int, user_id: int, username: str, text: str):
    """Отправить сообщение в чат стола."""
    if not text or len(text) > 200:
        return False

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO pvp_chat (table_id, user_id, username, text) "
            "VALUES (?, ?, ?, ?)",
            (table_id, user_id, username, text),
        )
        # Чистим старые (оставляем только последние 100 на стол)
        await db.execute(
            "DELETE FROM pvp_chat WHERE table_id = ? AND id NOT IN "
            "(SELECT id FROM pvp_chat WHERE table_id = ? ORDER BY id DESC LIMIT 100)",
            (table_id, table_id),
        )
        await db.commit()
        return True


async def pvp_chat_get(table_id: int, limit: int = 50):
    """Получить последние сообщения чата."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username, text, created_at FROM pvp_chat "
            "WHERE table_id = ? ORDER BY id DESC LIMIT ?",
            (table_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [
                {"user_id": r[0], "username": r[1] or f"user_{r[0]}",
                 "text": r[2], "created_at": r[3]}
                for r in reversed(rows)
            ]


async def pvp_cleanup_stale_tables():
    """Удаляет зависшие столы (waiting > 5 минут)."""
    cutoff = (
        datetime.datetime.utcnow() - datetime.timedelta(seconds=PVP_TABLE_TIMEOUT)
    ).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, bet FROM pvp_tables WHERE status = 'waiting' AND created_at < ?",
            (cutoff,),
        ) as cur:
            stale = await cur.fetchall()

    for table_id, bet in stale:
        async with aiosqlite.connect(DB_PATH) as db:
            # Возвращаем ставки всем
            async with db.execute(
                "SELECT user_id FROM pvp_participants WHERE table_id = ?",
                (table_id,),
            ) as cur:
                players = await cur.fetchall()

            for p in players:
                await db.execute(
                    "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                    (bet, p[0]),
                )

            await db.execute("DELETE FROM pvp_participants WHERE table_id = ?", (table_id,))
            await db.execute("DELETE FROM pvp_tables WHERE id = ?", (table_id,))
            await db.commit()

        print(f"🧹 PvP стол #{table_id} удалён (таймаут)", flush=True)
