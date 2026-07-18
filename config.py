import os
from dotenv import load_dotenv

load_dotenv()

# ========== ТОКЕНЫ И ID ==========
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# ========== ПОДПИСЧИКИ: ЦЕНЫ И ЛИМИТЫ ==========
PRICE_PER_SUBSCRIBER_RUB = 0.40
STARS_MULTIPLIER = 1.35
PRICE_PER_SUBSCRIBER_STARS = round(PRICE_PER_SUBSCRIBER_RUB * STARS_MULTIPLIER, 2)
MIN_ORDER = 10
MAX_ORDER = 50000

# Минимальное количество подписчиков на канале клиента, чтобы принять заказ
MIN_CHANNEL_SUBSCRIBERS = 5

# ========== РЕАКЦИИ НА ПОСТ: ЦЕНЫ И ЛИМИТЫ ==========
# ВАЖНО: подставь свою реальную цену — сейчас это заглушка-плейсхолдер.
PRICE_PER_REACTION_RUB = 0.50
PRICE_PER_REACTION_STARS = round(PRICE_PER_REACTION_RUB * STARS_MULTIPLIER, 2)
MIN_REACTIONS_ORDER = 10
MAX_REACTIONS_ORDER = 5000

# ID двух услуг в PRmotion — найди их через `python get_services.py реакции`
# (или другое ключевое слово, подходящее под твою панель) и подставь в .env.
PRMOTION_SERVICE_ID_REACTIONS_GOOD = int(os.getenv("PRMOTION_SERVICE_ID_REACTIONS_GOOD", 0))
PRMOTION_SERVICE_ID_REACTIONS_BAD = int(os.getenv("PRMOTION_SERVICE_ID_REACTIONS_BAD", 0))

# Запасной курс USD -> RUB, если сервис конвертации недоступен.
# ВАЖНО: обновляй время от времени вручную — это грубая подстраховка, не рыночный курс.
USD_TO_RUB_FALLBACK_RATE = 95.0

# ========== PRMOTION API ==========
PRMOTION_API_KEY = os.getenv("PRMOTION_API_KEY")
PRMOTION_SERVICE_ID = int(os.getenv("PRMOTION_SERVICE_ID", 0))
PRMOTION_API_URL = os.getenv("PRMOTION_API_URL", "https://api.prmotion.me/v1")

# ========== КАНАЛ НОВОСТЕЙ ==========
# Публичный канал с @username, например "@my_news_channel".
# Админ-бот должен быть добавлен в канал администратором с правом публикации постов.
NEWS_CHANNEL = os.getenv("NEWS_CHANNEL")

# ========== ПРОВЕРКА ПРИ СТАРТЕ ==========
print(f"✅ BOT_TOKEN: {TOKEN[:10]}..." if TOKEN else "❌ BOT_TOKEN не найден!")
print(f"✅ ADMIN_BOT_TOKEN: {ADMIN_BOT_TOKEN[:10]}..." if ADMIN_BOT_TOKEN else "❌ ADMIN_BOT_TOKEN не найден!")
print(f"✅ ADMIN_ID: {ADMIN_ID}")

if not all([TOKEN, ADMIN_BOT_TOKEN, PRMOTION_API_KEY]):
    print("❌ ОШИБКА: Проверь .env файл!")
    exit()
