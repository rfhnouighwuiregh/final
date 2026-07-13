import asyncio

import config
from bots import bot, admin_bot, dp, admin_dp
from prmotion import check_connection

import daily_report  # noqa: F401 — регистрирует /addchange и /sendnow на admin_dp

# Импорт регистрирует все хэндлеры на dp / admin_dp
import client_bot  # noqa: F401
import payments  # noqa: F401
import admin_bot as admin_handlers  # noqa: F401


async def startup_checks():
    """
    Общая логика старта. Вынесена в отдельную функцию, потому что раньше она
    жила только внутри main() и вызывалась лишь при `python main.py` напрямую
    — а на Render точка входа app.py, который main() никогда не вызывал.
    Из-за этого планировщик ежедневного отчёта на реальном деплое не запускался.
    Теперь app.py тоже явно вызывает эту функцию.
    """
    print("🚀 Бот запущен!")
    print(f"💰 Цена: {config.PRICE_PER_SUBSCRIBER_RUB} ₽/подписчик")
    print(f"⭐ В Stars: ~{config.PRICE_PER_SUBSCRIBER_STARS:.2f} Stars/подписчик")
    print(f"📊 Лимиты: {config.MIN_ORDER} - {config.MAX_ORDER}")
    print("📨 Заказы автоматически отправляются в PRmotion после оплаты")

    print("🔍 Проверяю подключение к PRmotion...")
    ok, info = await check_connection()
    if ok:
        print(f"✅ PRmotion доступен. {info}")
    else:
        print(f"❌ PRmotion недоступен: {info}")
        try:
            await admin_bot.send_message(
                config.ADMIN_ID,
                f"⚠️ <b>При старте бота не удалось подключиться к PRmotion!</b>\n\n"
                f"{info}\n\n"
                "Пока это не исправится, оплаченные заказы не будут автоматически уходить в работу.",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"⚠️ Не удалось отправить админу предупреждение о PRmotion: {e}")

    if config.NEWS_CHANNEL:
        print(f"📰 Канал новостей: {config.NEWS_CHANNEL}")
        asyncio.create_task(daily_report.daily_report_scheduler())
    else:
        print("📰 NEWS_CHANNEL не задан в .env — ежедневный отчёт отключён")


async def main():
    await startup_checks()
    await asyncio.gather(
        dp.start_polling(bot),
        admin_dp.start_polling(admin_bot)
    )


if __name__ == "__main__":
    asyncio.run(main())
