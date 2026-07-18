import os
from dotenv import load_dotenv

load_dotenv()

# ========== ТОКЕНЫ И ID ==========
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Токен провайдера оплаты картой (ЮKassa / Robokassa / CloudPayments и т.п.).
# Выдаётся в @BotFather → /mybots → ваш бот → Payments → выбрать провайдера.
# Пока пусто — кнопка "Оплатить картой" сама скажет клиенту, что способ недоступен.
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "")

# ========== ПОДПИСЧИКИ: ЦЕНЫ И ЛИМИТЫ ==========
# Опт в PRmotion (услуга "Promo Subscribers", ID 611): rate = 0.5 руб. за 1000,
# т.е. ~0.0005 руб./подписчик — себестоимость почти нулевая.
# Старая розница 0.40 руб./шт (=400 руб./1000) была в разы дороже рынка
# (бюджетные сервисы дают 3–17 руб./1000). 0.18 руб./шт (=180 руб./1000) —
# по-прежнему заметно дешевле старой цены (-55%), но с более комфортным
# запасом по марже, чем первый вариант 0.12 ₽. Наценка к опту ~360x.
PRICE_PER_SUBSCRIBER_RUB = 0.18
# Оплата у нас ТОЛЬКО через Stars (карта отключена) — значит вся реальная
# выручка идёт через звёзды. При выводе Stars → TON → рубли обычно теряется
# 8–15% на спреде/комиссиях обменников (по независимым источникам, май 2026).
# STARS_MULTIPLIER = 1.4 значит, что клиент платит на 40% "звёзд", чем эквивалент
# в рублях — это с запасом покрывает потери на выводе (даже 20-25%) и оставляет
# честный доход сверху, а не просто отыгрывает конвертацию в ноль.
STARS_MULTIPLIER = 1.4
PRICE_PER_SUBSCRIBER_STARS = round(PRICE_PER_SUBSCRIBER_RUB * STARS_MULTIPLIER, 2)
MIN_ORDER = 10
MAX_ORDER = 50000

# Минимальное количество подписчиков на канале клиента, чтобы принять заказ
MIN_CHANNEL_SUBSCRIBERS = 5

# ========== РЕАКЦИИ НА ПОСТ: ЦЕНЫ И ЛИМИТЫ ==========
# Опт в PRmotion (услуги ID 962/963): rate = 0.25 руб. за 1000,
# т.е. ~0.00025 руб./реакцию — тоже практически бесплатно для нас.
# Рынок на реакции держит 0.10–1.00 руб./шт, старая цена 0.50 руб. была
# у верхней границы. 0.36 руб./шт — умеренная скидка (-28% от старой цены)
# с большим запасом маржи (~1440x к опту), чем первый вариант 0.30 ₽.
PRICE_PER_REACTION_RUB = 0.36
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
