#!/usr/bin/env python3
"""
Скрипт очистки личных данных перед продажей проекта.
Заменяет токены, ID админов, ключи API и БД на заглушки.

Запуск:
    python cleanup.py
"""

import re
import os
import shutil
from pathlib import Path

# ═══════════ НАСТРОЙКИ ЗАМЕН ═══════════

REPLACEMENTS = {
    # В main.py и bot.py
    r'BOT_TOKEN\s*=\s*["\'][^"\']+["\']': 'BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token_here")',
    r'ADMIN_IDS\s*=\s*\[[^\]]+\]': 'ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "123456789").split(",")]',
    r'POLYGONSCAN_API_KEY\s*=\s*["\'][^"\']+["\']': 'POLYGONSCAN_API_KEY = os.getenv("POLYGONSCAN_API_KEY", "your_api_key_here")',
    r'SELLER_WALLET\s*=\s*["\'][^"\']+["\']': 'SELLER_WALLET = os.getenv("SELLER_WALLET", "0x0000000000000000000000000000000000000000")',
    r'WEBAPP_URL\s*=\s*["\'][^"\']+["\']': 'WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-domain.com")',
    r'BOT_USERNAME\s*=\s*["\'][^"\']+["\']': 'BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBotUsername")',
    r'bot_username\s*=\s*["\'][^"\']+["\']': 'bot_username = os.getenv("BOT_USERNAME", "YourBotUsername")',
    r'https://bot-[\w\-]+\.bothost\.tech[^\s"\']*': 'https://your-domain.com',
}

# Файлы для обработки
FILES_TO_CLEAN = [
    "main.py",
    "bot.py",
    "database.py",
    "webapp/app.js",
    "webapp/index.html",
]

# Файлы/папки для удаления
FILES_TO_DELETE = [
    "casino.db",
    "casino.db-shm",
    "casino.db-wal",
    "__pycache__",
    ".env",
    "*.pyc",
    ".DS_Store",
    "Thumbs.db",
    "logs/",
]

# ═══════════ ЛОГИКА ═══════════


def clean_file(filepath: str) -> int:
    """Очищает файл, заменяя все паттерны. Возвращает кол-во замен."""
    path = Path(filepath)
    if not path.exists():
        return 0
    
    content = path.read_text(encoding="utf-8")
    original = content
    replacements_count = 0
    
    for pattern, replacement in REPLACEMENTS.items():
        new_content, count = re.subn(pattern, replacement, content)
        if count > 0:
            content = new_content
            replacements_count += count
            print(f"  ✓ {filepath}: {count} замен по паттерну {pattern[:40]}...")
    
    if content != original:
        path.write_text(content, encoding="utf-8")
    
    return replacements_count


def delete_personal_files():
    """Удаляет БД, кэш и другие личные файлы."""
    for pattern in FILES_TO_DELETE:
        if "*" in pattern:
            for file in Path(".").rglob(pattern):
                try:
                    if file.is_dir():
                        shutil.rmtree(file)
                    else:
                        file.unlink()
                    print(f"  🗑 Удалено: {file}")
                except Exception as e:
                    print(f"  ⚠️ Не удалось удалить {file}: {e}")
        else:
            path = Path(pattern)
            if path.exists():
                try:
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    print(f"  🗑 Удалено: {path}")
                except Exception as e:
                    print(f"  ⚠️ Не удалось удалить {path}: {e}")


def create_env_example():
    """Создаёт .env.example с заглушками."""
    env_content = """# ═══════════ TELEGRAM BOT ═══════════
BOT_TOKEN=your_bot_token_here
WEBAPP_URL=https://your-domain.com
ADMIN_IDS=123456789
BOT_USERNAME=YourBotUsername

# ═══════════ DATABASE ═══════════
DB_PATH=casino.db

# ═══════════ GAME ECONOMY ═══════════
RATE=100

# ═══════════ CRYPTO PAYMENTS ═══════════
SELLER_WALLET=0x0000000000000000000000000000000000000000
POLYGONSCAN_API_KEY=your_polygonscan_api_key_here

# ═══════════ SERVER ═══════════
PORT=8000
"""
    Path(".env.example").write_text(env_content, encoding="utf-8")
    print("  ✓ Создан .env.example")


def main():
    print("🧹 Очистка личных данных...\n")
    
    print("📝 Обработка файлов:")
    total_replacements = 0
    for filepath in FILES_TO_CLEAN:
        count = clean_file(filepath)
        total_replacements += count
    
    print(f"\n✅ Всего заменено: {total_replacements}\n")
    
    print("🗑 Удаление личных файлов:")
    delete_personal_files()
    
    print("\n📄 Создание .env.example:")
    create_env_example()
    
    print("\n🎉 Готово! Проект очищен.")
    print("\n⚠️ Проверь вручную:")
    print("   • main.py — не осталось ли хардкод-значений")
    print("   • bot.py — токен заменён на переменную окружения")
    print("   • webapp/app.js — BOT_USERNAME заменён")
    print("   • casino.db — удалена (новая создастся при первом запуске)")


if __name__ == "__main__":
    main()
