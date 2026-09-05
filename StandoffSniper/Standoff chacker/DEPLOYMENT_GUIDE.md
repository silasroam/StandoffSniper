# 🚀 Пошаговый гайд деплоя на Vercel

## Шаг 1️⃣: Подготовка локального проекта

### 1.1 Структура файлов

Убедиться, что ваш проект имеет эту структуру:

```
standoff-sniper/
├── api/
│   └── webhook.py          ← NEW: скопировать из api_webhook.py
├── config.py               ← сохранить как есть
├── bot.py                  ← модифицировать конец файла (см. bot_modifications.md)
├── init_db.py              ← сохранить как есть
├── price.json              ← сохранить как есть
├── requirements.txt        ← NEW: скопировать из предоставленного файла
├── vercel.json             ← NEW: скопировать из предоставленного файла
├── .gitignore              ← обновить (см. ниже)
└── .env.local              ← локально (не коммитить!)
```

### 1.2 Обновить `.gitignore`

Если в `.gitignore` еще нет этого, добавить:

```
# Окружение
.env
.env.local
.env.*.local

# Vercel
.vercel/

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/

# БД
*.db
*.sqlite

# IDE
.vscode/
.idea/
*.swp
```

---

## Шаг 2️⃣: Инициализировать Git репозиторий

```bash
# Если еще не инициализирован
git init

# Добавить все файлы
git add .

# Закоммитить
git commit -m "Initial commit: Add Telegram bot with Vercel webhook support"

# Добавить удаленный репозиторий (GitHub, GitLab и т.д.)
git remote add origin https://github.com/YOUR_USERNAME/standoff-sniper.git

# Залить в репозиторий
git branch -M main
git push -u origin main
```

---

## Шаг 3️⃣: Установить Vercel CLI

```bash
# Через npm
npm i -g vercel

# Или через homebrew (macOS)
brew install vercel

# Проверить установку
vercel --version
```

---

## Шаг 4️⃣: Залогиниться в Vercel

```bash
vercel login
```

Следовать подсказкам в браузере.

---

## Шаг 5️⃣: Залить проект на Vercel

### Вариант A: Автоматически (рекомендуется)

```bash
vercel --prod
```

Vercel автоматически:
- Определит, что это Python проект
- Прочитает `vercel.json`
- Установит зависимости из `requirements.txt`
- Деплойнет функции

### Вариант B: Через Vercel Dashboard

1. Перейти на https://vercel.com/dashboard
2. Нажать "Add New" → "Project"
3. Выбрать свой GitHub репозиторий
4. Нажать "Import"
5. В настройках **Build & Development Settings** убедиться, что использует Python
6. Нажать "Deploy"

---

## Шаг 6️⃣: Добавить переменные окружения

### Вариант A: Через Vercel Dashboard

1. Перейти в **Settings** проекта
2. Выбрать **Environment Variables**
3. Добавить переменные:

| Key | Value |
|-----|-------|
| `BOT_TOKEN` | Ваш токен бота (из `config.py`) |
| `ADMIN_ID` | ID админа (из `config.py`) |
| `DB_PATH` | `/tmp/standoff_checker.db` |
| `PRICE_JSON_PATH` | `price.json` |

### Вариант B: Через CLI

```bash
vercel env add BOT_TOKEN
vercel env add ADMIN_ID
vercel env add DB_PATH
vercel env add PRICE_JSON_PATH
```

---

## Шаг 7️⃣: Установить Webhook в Telegram

После успешного деплоя получить URL вашего проекта:

```bash
# Узнать URL проекта
vercel --prod

# Вывод будет типа:
# Deployment complete! https://standoff-sniper-abc123.vercel.app
```

Установить webhook в Telegram:

```bash
# Замените BOT_TOKEN и DOMAIN!
curl -X POST https://api.telegram.org/bot8811143217:AAEPeOh0RwaOSlNJS4FOl8sY9S35aTzppX8/setWebhook \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://standoff-sniper-abc123.vercel.app/api/webhook",
    "allowed_updates": ["message", "callback_query", "pre_checkout_query", "successful_payment"]
  }'
```

### Проверить статус webhook:

```bash
curl https://api.telegram.org/bot8811143217:AAEPeOh0RwaOSlNJS4FOl8sY9S35aTzppX8/getWebhookInfo
```

Ожидаемый результат:
```json
{
  "ok": true,
  "result": {
    "url": "https://standoff-sniper-abc123.vercel.app/api/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0,
    "ip_address": "...",
    "last_error_date": 0,
    "max_connections": 40
  }
}
```

---

## Шаг 8️⃣: Тестирование

### Способ 1: Проверка webhook'а в Telegram

Отправить любую команду боту в Telegram и проверить логи:

```bash
vercel logs --prod
```

### Способ 2: Прямой запрос

```bash
# GET запрос (health check)
curl https://standoff-sniper-abc123.vercel.app/api/webhook

# Ожидаемый результат:
# {"ok":true,"status":"Bot webhook is running","bot_initialized":false}
```

### Способ 3: Симуляция обновления Telegram

```bash
curl -X POST https://standoff-sniper-abc123.vercel.app/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "update_id": 123456789,
    "message": {
      "message_id": 1,
      "date": 1234567890,
      "chat": {
        "id": 7969090536,
        "type": "private"
      },
      "from": {
        "id": 7969090536,
        "is_bot": false,
        "first_name": "Test"
      },
      "text": "/start"
    }
  }'
```

---

## 🔧 Устранение проблем

### Ошибка: "Function timeout after 10 seconds"

**Причина:** Функция выполняется дольше 10 секунд

**Решение:**
- Оптимизировать запросы к БД
- Использовать индексы в БД
- Разделить сложные операции на несколько функций

### Ошибка: "Database locked"

**Причина:** Несколько процессов пытаются писать в SQLite одновременно

**Решение:**
- Перейти на PostgreSQL (рекомендуется для Vercel)
- Использовать SQLite с WAL режимом
- Добавить timeout'ы в подключение

### Webhook не получает обновления

**Проверить:**
```bash
# 1. Статус webhook
curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo

# 2. Логи Vercel
vercel logs --prod

# 3. Переустановить webhook (если нужно)
curl -X POST https://api.telegram.org/bot<TOKEN>/deleteWebhook
curl -X POST https://api.telegram.org/bot<TOKEN>/setWebhook \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-domain.vercel.app/api/webhook"}'
```

---

## 📚 Локальное тестирование (после деплоя)

Можно все еще тестировать локально с polling режимом:

```bash
# Удалить webhook из Telegram
curl -X POST https://api.telegram.org/bot<TOKEN>/deleteWebhook

# Запустить локально
python bot.py

# Когда закончили тестирование, переустановить webhook
curl -X POST https://api.telegram.org/bot<TOKEN>/setWebhook \
  -d '{"url": "https://your-domain.vercel.app/api/webhook"}'
```

---

## 🎉 Готово!

Ваш бот должен работать на Vercel! 

Теперь:
- ✅ Бот запускается с помощью webhook
- ✅ Нет холодных стартов из-за polling
- ✅ Структура проекта сохранена
- ✅ Можно тестировать локально и на продакшене
- ✅ Все переменные окружения защищены

---

## 📋 Финальный чек-лист

- [ ] Git репозиторий инициализирован
- [ ] Все файлы залиты на GitHub (или другой сервис)
- [ ] Vercel CLI установлен
- [ ] Залогинены в Vercel
- [ ] Проект деплойнен (`vercel --prod`)
- [ ] Переменные окружения добавлены в Vercel Dashboard
- [ ] Webhook установлен в Telegram API (`setWebhook`)
- [ ] Webhook статус проверен (`getWebhookInfo`)
- [ ] Логи проверены (`vercel logs --prod`)
- [ ] Бот протестирован в Telegram

---

## 💡 Советы

1. **Для дополнительной безопасности webhook'а** добавить проверку токена:
   
   ```python
   # В api/webhook.py
   TELEGRAM_SECRET = os.getenv("TELEGRAM_SECRET", "default-secret")
   
   if request.headers.get("X-Telegram-Bot-API-Secret-Token") != TELEGRAM_SECRET:
       return {"ok": False, "error": "Unauthorized"}
   ```

2. **Для мониторинга** использовать Vercel Analytics:
   ```
   https://vercel.com/dashboard/project-name/analytics
   ```

3. **Для отладки** добавить логирование:
   ```python
   # В api/webhook.py
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

4. **Для продакшена** перейти на PostgreSQL:
   - Supabase (бесплатно до 500 MB)
   - Railway.app
   - Heroku PostgreSQL

---

## 🆘 Нужна помощь?

- Документация aiogram: https://docs.aiogram.dev/
- Документация Vercel: https://vercel.com/docs
- API Telegram: https://core.telegram.org/bots/api
