# 🚀 SlotsGaming — Инструкция по развёртыванию

## 1. Что нужно

- **VPS** с Ubuntu 22.04+ (мин. 2 GB RAM, 20 GB SSD)
- **Домен** (например, `slotsgaming.tech`)
- **Telegram-бот** (токен от @BotFather)
- **10–15 минут** времени

---

## 2. Быстрый старт (Docker)

### Шаг 1. Подключись к VPS

```bash
ssh root@ТВОЙ_IP

Шаг 2. Установи Docker
bash
apt update && apt install -y docker.io docker-compose git
Шаг 3. Клонируй проект
bash
git clone https://github.com/твой-репозиторий/slotsgaming.git
cd slotsgaming
Шаг 4. Настрой переменные
Создай .env файл:

bash
cp .env.example .env
nano .env
Заполни:

text
BOT_TOKEN=8602932446:AAH...  # токен от @BotFather
WEBAPP_URL=https://slotsgaming.tech
ADMIN_IDS=7643224285         # твой Telegram ID
DB_PATH=data/casino.db
PORT=8000
Шаг 5. Запусти
bash
docker-compose up -d
Проверь:

bash
docker-compose logs -f
curl http://localhost:8000/health
# → {"status":"ok"}
Шаг 6. Настрой домен + SSL
Установи Nginx и Certbot:

bash
apt install -y nginx certbot python3-certbot-nginx
Создай /etc/nginx/sites-available/slotsgaming:

nginx
server {
    listen 80;
    server_name slotsgaming.tech;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
Активируй:

bash
ln -s /etc/nginx/sites-available/slotsgaming /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d slotsgaming.tech
Шаг 7. Подключи Mini App
Открой @BotFather → /mybots → свой бот

Bot Settings → Menu Button → Configure menu button

Укажи URL: https://slotsgaming.tech/webapp

Название: 🎰 Играть

Шаг 8. Проверка
Открой бота → нажми 🎰 ИГРАТЬ 🎰 → должна открыться игра.

3. Резервное копирование
Создай скрипт /root/backup.sh:

bash
#!/bin/bash
mkdir -p /backup
cp /root/slotsgaming/data/casino.db /backup/casino_$(date +%Y%m%d_%H).db
find /backup -name "casino_*.db" -mtime +7 -delete
Сделай исполняемым:

bash
chmod +x /root/backup.sh
Добавь в cron (каждый час):

bash
crontab -e
# добавь строку:
0 * * * * /root/backup.sh
4. Обновление
bash
cd /root/slotsgaming
git pull
docker-compose down
docker-compose up -d --build
5. Частые проблемы
Бот не отвечает
bash
docker-compose logs bot
Проверь токен в .env.

Mini App не открывается
Проверь WEBAPP_URL в .env — должен быть https://...

Проверь SSL: curl https://твой-домен/health

Открой в Telegram Desktop → Console → ищи ошибки

«Сессия истекла» в Mini App
Обнови ?v= в index.html (app.js?v=417 → 418).

База повреждена
Восстанови из бэкапа:

bash
cp /backup/casino_20260919_12.db data/casino.db
docker-compose restart
6. Полезные команды
bash
# Логи
docker-compose logs -f

# Перезапуск
docker-compose restart

# Остановка
docker-compose down

# Полная очистка (осторожно — удалит БД!)
docker-compose down -v
7. Безопасность
Никогда не коммить .env в git

Регулярно обновляй сервер: apt update && apt upgrade

Используй SSH-ключи, а не пароль

Настрой firewall: ufw allow 22,80,443/tcp && ufw enable

text


Также обнови `README.md` в корне — короткое описание проекта (если ещё нет).

---

## 💬 Пункт 5: Поддержка + `/help`

### 5.1. Добавь в `bot.py`

После команды `/webapp` вставь:

```python
@router.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "📚 <b>Справка SlotsGaming</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎰 <b>Как играть</b>\n"
        "1. Нажми «🎰 ИГРАТЬ 🎰»\n"
        "2. Пополни баланс через ⭐ Stars\n"
        "3. Выбирай игру и делай ставку\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎁 <b>Бонусы</b>\n"
        "• Ежедневный бонус (раз в 24ч)\n"
        "• Ежечасный бонус (раз в час)\n"
        "• Бесплатный кейс\n"
        "• Кэшбэк до 12%\n"
        "• Колесо фортуны\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💸 <b>Вывод</b>\n"
        "• Минимум: 1000 ⭐\n"
        "• Срок: до 24 часов\n"
        "• Нужно 3 дня активности\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👥 <b>Рефералы</b>\n"
        "• 5% с каждой ставки друга\n"
        "• +5000 🪙 за депозит друга\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "❓ <b>Вопросы?</b> → /support"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎰  ИГРАТЬ  🎰",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/webapp"),
        )],
    ])

    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(Command("support"))
async def cmd_support(message: types.Message):
    await message.answer(
        "💬 <b>Поддержка SlotsGaming</b>\n\n"
        "Опиши свою проблему одним сообщением.\n"
        "Отвечаем в течение 1–2 часов.\n\n"
        "⚠️ Не отправляй пароли и личные данные.",
        parse_mode="HTML",
    )
    # Помечаем юзера как ожидающего ответа
    from database import set_user_state
    try:
        await set_user_state(message.from_user.id, "awaiting_support")
    except Exception:
        pass


@router.message(F.text & ~F.text.startswith("/"))
async def handle_support_message(message: types.Message):
    from database import get_user_state, set_user_state

    # Проверяем, ждёт ли юзер ответа поддержки
    try:
        state = await get_user_state(message.from_user.id)
    except Exception:
        state = None

    if state != "awaiting_support":
        return

    # Пересылаем сообщение админам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💬 <b>Сообщение в поддержку</b>\n\n"
                f"От: @{message.from_user.username or message.from_user.id}\n"
                f"ID: <code>{message.from_user.id}</code>\n\n"
                f"Текст:\n<i>{message.text}</i>",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await set_user_state(message.from_user.id, None)
    await message.answer(
        "✅ Сообщение отправлено. Ответим в течение 1–2 часов.",
        parse_mode="HTML",
    )

Не забудь добавить ADMIN_IDS в bot.py (если его нет):

python
ADMIN_IDS = [7643224285]
