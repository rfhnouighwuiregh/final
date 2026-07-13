import asyncio
import aiohttp

import config
import database
from bots import admin_bot

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


def channel_to_link(channel: str) -> str:
    """
    Мы храним и показываем канал как @username, но PRmotion в параметре
    'link' ожидает полную ссылку вида https://t.me/username — иначе
    возвращает ошибку "Enter the correct link".
    """
    channel = channel.strip()
    if channel.startswith('@'):
        return f"https://t.me/{channel[1:]}"
    return channel


async def check_connection() -> tuple[bool, str]:
    """
    Быстрая проверка, что PRmotion вообще принимает запросы (сайт жив,
    ключ рабочий). Используется при старте бота — чтобы проблему было видно
    сразу, а не когда до сайта дойдёт первый реальный заказ.
    Возвращает (ok, сообщение).
    """
    if not config.PRMOTION_API_KEY:
        return False, "PRMOTION_API_KEY не задан в .env"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                config.PRMOTION_API_URL,
                params={'key': config.PRMOTION_API_KEY, 'action': 'balance', 'currency': 'RUB'},
                timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status != 200:
                    return False, f"Сайт ответил HTTP {resp.status}"
                data = await resp.json(content_type=None)
                print(f"🔎 PRmotion check_connection raw response: {data}")
                if isinstance(data, dict) and 'error' in data:
                    return False, f"API вернул ошибку: {data['error']}"
                if not isinstance(data, dict) or 'balance' not in data:
                    return False, f"Неожиданный формат ответа: {data}"
                return True, f"Баланс: {data.get('balance')} {data.get('currency', '')}".strip()
    except aiohttp.ClientConnectorError as e:
        return False, f"Не удалось подключиться к сайту: {e}"
    except asyncio.TimeoutError:
        return False, f"Сайт не ответил за {REQUEST_TIMEOUT.total:.0f} секунд"
    except Exception as e:
        return False, f"Ошибка подключения: {e}"


async def get_usd_to_rub_rate() -> float:
    """
    Получает текущий курс USD -> RUB через открытый сервис конвертации.
    При ошибке использует запасной курс из config.USD_TO_RUB_FALLBACK_RATE.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.exchangerate-api.com/v4/latest/USD",
                timeout=REQUEST_TIMEOUT
            ) as resp:
                data = await resp.json()
                return float(data["rates"]["RUB"])
    except Exception as e:
        print(f"⚠️ Не удалось получить курс USD/RUB: {e}. Использую запасной курс {config.USD_TO_RUB_FALLBACK_RATE}")
        return config.USD_TO_RUB_FALLBACK_RATE


async def check_prmotion_balance():
    """
    Возвращает (balance_rub, raw_balance, raw_currency).
    balance_rub — баланс, приведённый к рублям (для сравнения с ценой заказа).
    raw_balance / raw_currency — как есть, для логов и уведомлений.
    В случае ошибки — (None, None, None).

    ВАЖНО: у PRmotion, судя по всему, пополнения в рублях и в долларах — это
    два РАЗНЫХ кошелька в одном аккаунте (не просто отображение одной и той
    же суммы в разных валютах). Обычный action=balance возвращал 0 USD, хотя
    на сайте в личном кабинете видно 1000 (в рублях) — то есть это другой
    кошелёк, который дефолтный запрос не показывает.

    Ниже — попытка явно запросить рублёвый баланс параметром currency=RUB
    (частый паттерн у SMM-панелей). Если это не сработает и API всё равно
    вернёт доллары/0 — нужно свериться с документацией на prmotion.me/en/api
    в личном кабинете, там должен быть точный параметр для второго кошелька.
    """
    async with aiohttp.ClientSession() as session:
        params = {'key': config.PRMOTION_API_KEY, 'action': 'balance', 'currency': 'RUB'}
        try:
            async with session.get(config.PRMOTION_API_URL, params=params, timeout=REQUEST_TIMEOUT) as resp:
                data = await resp.json()
                print(f"🔎 PRmotion balance raw response: {data}")
        except Exception as e:
            print(f"❌ Ошибка запроса баланса PRmotion: {e}")
            return None, None, None

    try:
        raw_balance = float(data.get('balance', 0))
    except (TypeError, ValueError):
        print(f"❌ PRmotion вернул баланс в неожиданном формате: {data}")
        return None, None, None

    raw_currency = str(data.get('currency') or 'RUB').upper()

    if raw_currency == 'RUB':
        balance_rub = raw_balance
    elif raw_currency == 'USD':
        rate = await get_usd_to_rub_rate()
        balance_rub = raw_balance * rate
        print(f"💱 PRmotion баланс: {raw_balance} USD ≈ {balance_rub:.2f} ₽ (курс {rate:.2f})")
    else:
        print(f"⚠️ PRmotion вернул баланс в незнакомой валюте '{raw_currency}' — сравниваю как есть, проверь вручную!")
        balance_rub = raw_balance

    return balance_rub, raw_balance, raw_currency


async def get_services():
    """Возвращает список услуг PRmotion (action=services) или None при ошибке."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                config.PRMOTION_API_URL,
                params={'key': config.PRMOTION_API_KEY, 'action': 'services'},
                timeout=REQUEST_TIMEOUT
            ) as resp:
                data = await resp.json(content_type=None)
                if isinstance(data, list):
                    return data
                print(f"❌ PRmotion вернул неожиданный формат списка услуг: {data}")
                return None
        except Exception as e:
            print(f"❌ Ошибка получения списка услуг PRmotion: {e}")
            return None


async def precheck_order(order: dict) -> tuple[bool, str]:
    """
    Проверяет, что заказ реально можно оформить в PRmotion, ДО того как
    Telegram спишет деньги с клиента (вызывается из pre_checkout_query_handler).
    Ничего не создаёт и не списывает — только читает (action=services, action=balance).

    ЧЕСТНО: 100%-й гарантии, что реальный action=add потом пройдёт, это не
    даёт — у PRmotion нет отдельного метода "проверить без создания". Но
    отсекает главные типовые причины провала (нет денег, не тот SERVICE_ID,
    количество вне допустимых границ услуги) ДО оплаты — если что-то из
    этого не так, платёж просто не проведётся, и клиент не потеряет деньги.

    Возвращает (ok, текст_ошибки_для_клиента).
    """
    services = await get_services()
    if services is None:
        return False, "Сервис временно недоступен. Попробуйте, пожалуйста, через несколько минут."

    service = next(
        (s for s in services if str(s.get('service')) == str(config.PRMOTION_SERVICE_ID)),
        None
    )
    if service is None:
        return False, "Сервис временно недоступен (ошибка конфигурации). Напишите в поддержку."

    try:
        service_min = int(float(service.get('min', 0)))
        service_max = int(float(service.get('max', 0)))
    except (TypeError, ValueError):
        service_min, service_max = 0, 0

    if service_min and order['count'] < service_min:
        return False, f"Минимальное количество для этой услуги — {service_min}. Отмените заказ и создайте новый с большим количеством."
    if service_max and order['count'] > service_max:
        return False, f"Максимальное количество для этой услуги — {service_max}. Отмените заказ и создайте новый с меньшим количеством."

    balance_rub, raw_balance, raw_currency = await check_prmotion_balance()
    if balance_rub is None:
        return False, "Сервис временно недоступен. Попробуйте, пожалуйста, через несколько минут."
    if balance_rub < order['price']:
        return False, "Сервис временно не может принять новые заказы (технические работы). Попробуйте позже или напишите в поддержку."

    return True, ""


async def create_prmotion_order(channel, quantity):
    async with aiohttp.ClientSession() as session:
        params = {
            'key': config.PRMOTION_API_KEY,
            'action': 'add',
            'service': config.PRMOTION_SERVICE_ID,
            'currency': 'RUB',  # по докам PRmotion это дефолт, но фиксируем явно
            'link': channel,
            'quantity': quantity
        }
        try:
            # ВАЖНО: action=add принимает только POST (в отличие от action=balance,
            # который допускает и GET, и POST) — раньше здесь был session.get(),
            # из-за чего PRmotion отвечал "Method Not Allowed".
            async with session.post(config.PRMOTION_API_URL, data=params, timeout=REQUEST_TIMEOUT) as resp:
                data = await resp.json(content_type=None)
                print(f"📤 PRmotion ответ: {data}")
                if isinstance(data, dict) and 'error' in data:
                    print(f"❌ PRmotion вернул ошибку: {data['error']}")
                    return None
                return data.get('order')
        except Exception as e:
            print(f"❌ Ошибка PRmotion: {e}")
            return None


async def send_to_prmotion(order_id):
    order = database.get_order(order_id)
    if not order:
        return False

    try:
        balance_rub, raw_balance, raw_currency = await check_prmotion_balance()
        if balance_rub is None:
            await admin_bot.send_message(config.ADMIN_ID, f"⚠️ Ошибка PRmotion! Заказ #{order_id}")
            return False

        if balance_rub < order['price']:
            currency_note = f" ({raw_balance} {raw_currency})" if raw_currency != 'RUB' else ""
            await admin_bot.send_message(
                config.ADMIN_ID,
                f"⚠️ Недостаточно средств в PRmotion!\n"
                f"Заказ #{order_id}\n"
                f"Нужно: {order['price']:.2f} ₽\n"
                f"Доступно: {balance_rub:.2f} ₽{currency_note}",
                parse_mode="HTML"
            )
            return False

        prmotion_order_id = await create_prmotion_order(channel_to_link(order['channel']), order['count'])

        if prmotion_order_id:
            database.update_prmotion_order_id(order_id, prmotion_order_id)
            database.update_order_status(order_id, "в_работе")

            await admin_bot.send_message(
                config.ADMIN_ID,
                f"🚀 Заказ #{order_id} отправлен в PRmotion!\n"
                f"👤 Клиент: @{order['username']}\n"
                f"📢 Канал: {order['channel']}\n"
                f"👥 Подписчиков: {order['count']}\n"
                f"💰 Сумма: {order['price']:.2f} ₽\n"
                f"🆔 PRmotion ID: {prmotion_order_id}",
                parse_mode="HTML"
            )
            return True
        else:
            await admin_bot.send_message(config.ADMIN_ID, f"❌ Ошибка создания заказа в PRmotion!\nЗаказ #{order_id}", parse_mode="HTML")
            return False
    except Exception as e:
        await admin_bot.send_message(config.ADMIN_ID, f"❌ Ошибка: {str(e)}")
        return False
