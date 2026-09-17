docker exec -it <имя_контейнера> bash
cd /app
cat > migrate.py << 'EOF'
import asyncio
import aiosqlite
import os

DB_PATH = os.getenv("DB_PATH", "casino.db")
print(f"📁 DB_PATH = {DB_PATH}")
print(f"📁 Абсолютный путь: {os.path.abspath(DB_PATH)}")
print(f"📁 Файл существует: {os.path.exists(DB_PATH)}")


async def migrate():
    async with aiosqlite.connect(DB_PATH) as db:
        # profiles
        async with db.execute("PRAGMA table_info(profiles)") as cur:
            cols = [c[1] for c in await cur.fetchall()]
        print(f"📋 profiles колонки: {cols}")

        if "owned" not in cols:
            print("🔧 Добавляю profiles.owned...")
            await db.execute("ALTER TABLE profiles ADD COLUMN owned TEXT DEFAULT '[]'")
            await db.commit()
            print("✅ profiles.owned добавлена")
        else:
            print("✅ profiles.owned уже есть")

        # withdrawals
        async with db.execute("PRAGMA table_info(withdrawals)") as cur:
            cols = [c[1] for c in await cur.fetchall()]
        print(f"📋 withdrawals колонки: {cols}")

        for col, definition in [
            ("method",  "TEXT NOT NULL DEFAULT 'stars'"),
            ("amount",  "REAL NOT NULL DEFAULT 0"),
            ("details", "TEXT"),
        ]:
            if col not in cols:
                print(f"🔧 Добавляю withdrawals.{col}...")
                await db.execute(f"ALTER TABLE withdrawals ADD COLUMN {col} {definition}")
                await db.commit()
                print(f"✅ withdrawals.{col} добавлена")

        await db.execute("UPDATE withdrawals SET amount = stars WHERE amount = 0")
        await db.commit()

        # Финальная проверка
        async with db.execute("PRAGMA table_info(profiles)") as cur:
            cols = [c[1] for c in await cur.fetchall()]
        print(f"🎉 Финальная схема profiles: {cols}")

        # Покажи пользователей для проверки
        async with db.execute("SELECT user_id, balance FROM users LIMIT 5") as cur:
            rows = await cur.fetchall()
        print(f"👥 Первые 5 юзеров: {rows}")


asyncio.run(migrate())
EOF

python migrate.py
