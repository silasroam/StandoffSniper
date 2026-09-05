# ⚡ Быстрый старт (5 минут)

## 📋 Что скопировать в ваш проект

1. **Создать папку `api/`:**
   ```bash
   mkdir api
   ```

2. **Скопировать `api/webhook.py`** (из файла `api_webhook.py`)

3. **Скопировать `requirements.txt`** в корень проекта

4. **Скопировать `vercel.json`** в корень проекта

5. **Модифицировать `bot.py`** (конец файла, см. `bot_modifications.md`)

---

## 🚀 Команды для деплоя

### 1. Подготовка
```bash
# Инициализировать Git
git init

# Добавить файлы
git add .

# Коммитить
git commit -m "Add Vercel webhook support"

# Добавить удаленный репозиторий (GitHub)
git remote add origin https://github.com/YOUR_USERNAME/standoff-sniper.git
git push -u origin main
```

### 2. Установить Vercel CLI
```bash
npm i -g vercel
vercel login
```

### 3. Деплой на Vercel
```bash
vercel --prod
```

### 4. Добавить переменные окружения (Vercel Dashboard или CLI)
```bash
vercel env add BOT_TOKEN
vercel env add ADMIN_ID
vercel env add DB_PATH
vercel env add PRICE_JSON_PATH
```

### 5. Узнать URL проекта
```bash
vercel --prod
# Результат: https://standoff-sniper-XXXXX.vercel.app
```

### 6. Установить webhook в Telegram
```bash
# ЗАМЕНИТЕ: BOT_TOKEN и YOUR_DOMAIN!
curl -X POST https://api.telegram.org/bot[BOT_TOKEN]/setWebhook \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://[YOUR_DOMAIN].vercel.app/api/webhook",
    "allowed_updates": ["message", "callback_query", "pre_checkout_query", "successful_payment"]
  }'
```

### 7. Проверить webhook
```bash
# ЗАМЕНИТЕ: BOT_TOKEN!
curl https://api.telegram.org/bot[BOT_TOKEN]/getWebhookInfo
```

---

## 🔑 Значения для переменных окружения

| Переменная | Значение | Откуда |
|-----------|----------|--------|
| `BOT_TOKEN` | `8811143217:AAEPeOh0RwaOSlNJS4FOl8sY9S35aTzppX8` | Из `config.py` |
| `ADMIN_ID` | `7969090536` | Из `config.py` |
| `DB_PATH` | `/tmp/standoff_checker.db` | Vercel runtime |
| `PRICE_JSON_PATH` | `price.json` | По умолчанию |

---

## 📂 Финальная структура проекта

```
standoff-sniper/
├── api/
│   └── webhook.py              ✨ NEW
├── config.py                   ✓ как есть
├── bot.py                      ⚠️ модифицировать конец
├── init_db.py                  ✓ как есть
├── price.json                  ✓ как есть
├── standoff_checker.db         ✓ как есть
├── requirements.txt            ✨ NEW
├── vercel.json                 ✨ NEW
├── .gitignore                  ✓ обновить
├── .env.local                  ✓ локально (не коммитить!)
└── project.json                ✓ как есть
```

**✨ NEW** = новые файлы
**⚠️** = модифицировать
**✓** = сохранить как есть

---

## 🧪 Проверка после деплоя

### Способ 1: Проверить здоровье webhook'а
```bash
curl https://standoff-sniper-XXXXX.vercel.app/api/webhook
```

Результат: `{"ok":true,"status":"Bot webhook is running"}`

### Способ 2: Проверить статус в Telegram API
```bash
curl https://api.telegram.org/bot[BOT_TOKEN]/getWebhookInfo
```

Должно быть:
```json
{
  "ok": true,
  "result": {
    "url": "https://standoff-sniper-XXXXX.vercel.app/api/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0
  }
}
```

### Способ 3: Посмотреть логи на Vercel
```bash
vercel logs --prod
```

### Способ 4: Протестировать в Telegram
Отправьте боту `/start` и проверьте логи:
```bash
vercel logs --prod --follow
```

---

## ❓ Если что-то не работает

### Ошибка: "Build failed"
```bash
# Посмотреть логи сборки
vercel logs --prod

# Может быть неправильный Python версия в vercel.json
# Заменить на "python3.11" или "python3.12"
```

### Ошибка: "Webhook не получает обновления"
```bash
# 1. Проверить webhook установлен
curl https://api.telegram.org/bot[TOKEN]/getWebhookInfo

# 2. Если нет - переустановить
curl -X POST https://api.telegram.org/bot[TOKEN]/deleteWebhook
curl -X POST https://api.telegram.org/bot[TOKEN]/setWebhook \
  -H "Content-Type: application/json" \
  -d '{"url": "https://standoff-sniper-XXXXX.vercel.app/api/webhook"}'

# 3. Посмотреть логи
vercel logs --prod --follow
```

### Ошибка: "Database locked"
Это нормально на Vercel с SQLite. Решение:
- Использовать PostgreSQL на Supabase/Railway вместо SQLite
- Или увеличить timeout в БД

### Ошибка: "Function timeout"
Какая-то операция выполняется > 10 сек:
- Оптимизировать запросы к БД
- Добавить индексы
- Или использовать Vercel Pro (30 сек timeout)

---

## 📚 Структура webhook handler'а

```
Telegram API
    ↓
    └→ POST https://domain/api/webhook
         ↓
         └→ api/webhook.py (webhook handler)
              ↓
              ├→ dispatcher.feed_update()
              ├→ router (обработчики из bot.py)
              └→ БД (init_db, queries и т.д.)
                   ↓
                   └→ /tmp/standoff_checker.db
```

**Важно:** `router` и вся логика остаются в `bot.py`, а `api/webhook.py` просто передает обновления!

---

## 🎯 После деплоя

1. **Проверить работу:** Отправить `/start` боту
2. **Проверить админ-панель:** Отправить `/admin` как админ (ID из `config.py`)
3. **Проверить логи:** `vercel logs --prod`
4. **Настроить мониторинг:** Vercel Dashboard → Analytics
5. **Резервная копия:** Добавить PostgreSQL для постоянного хранилища

---

## 💾 Когда нужна база данных получше?

SQLite на Vercel используется только в `/tmp` (временное хранилище). Для **постоянного хранилища** нужна внешняя БД:

### Вариант 1: Supabase (PostgreSQL) - Бесплатно ✅
- Регистрация: https://supabase.com
- До 500 MB бесплатно
- Простая интеграция

### Вариант 2: Railway - Дешево ✅
- Регистрация: https://railway.app
- $5 в месяц бесплатно
- Отличный UX

### Вариант 3: MongoDB Atlas - Бесплатно ✅
- Регистрация: https://www.mongodb.com/cloud/atlas
- До 512 MB бесплатно
- NoSQL (если нужна гибкость)

**Добавить в `config.py`:**
```python
import os

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Использовать PostgreSQL
    DB_TYPE = "postgres"
else:
    # Использовать SQLite
    DB_TYPE = "sqlite"
    DB_PATH = "/tmp/standoff_checker.db"
```

---

## 🎉 Готово!

Ваш бот работает на Vercel с webhook'ом! 🚀

Вопросы? Смотрите:
- `WEBHOOK_SETUP.md` - полное объяснение
- `DEPLOYMENT_GUIDE.md` - подробный гайд
- `bot_modifications.md` - что менять в коде
