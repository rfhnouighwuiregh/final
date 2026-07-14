"""
Диагностика подключения к PRmotion API.
Запуск: python check_prmotion.py
"""
import asyncio
import config
from prmotion import check_prmotion_balance, get_services


async def main():
    print("=" * 50)
    print("🔍 Диагностика PRmotion API")
    print("=" * 50)

    print(f"URL:        {config.PRMOTION_API_URL}")
    print(f"API_KEY:    {config.PRMOTION_API_KEY[:6]}..." if config.PRMOTION_API_KEY else "API_KEY:    ❌ НЕ ЗАДАН")
    print(f"SERVICE_ID: {config.PRMOTION_SERVICE_ID}")
    print("-" * 50)

    if not config.PRMOTION_API_KEY:
        print("❌ PRMOTION_API_KEY не найден в .env — дальше проверять нечего.")
        return

    # 1. Проверка баланса — с учётом валюты (PRmotion может отдавать баланс в USD)
    print("1️⃣ Проверяю баланс (action=balance)...")
    balance_rub, raw_balance, raw_currency = await check_prmotion_balance()
    if balance_rub is None:
        print("   ❌ Не удалось получить баланс — см. ошибку выше.")
    else:
        print(f"   Сырой ответ от API: {raw_balance} {raw_currency}")
        print(f"   ✅ В пересчёте на рубли: {balance_rub:.2f} ₽")
        if raw_currency != 'RUB':
            print(f"   ⚠️ Учти: сайт может показывать баланс в рублях в личном кабинете,")
            print(f"      а API отдаёт его в {raw_currency} — это две разные вещи у SMM-панелей.")
            print(f"      Если хочешь, чтобы API тоже отдавал RUB — проверь настройки валюты в личном кабинете PRmotion.")

    print("-" * 50)

    # 2. Проверка существования указанного SERVICE_ID в списке услуг
    print("2️⃣ Проверяю список услуг (action=services)...")
    services = await get_services()
    if services is None:
        print("   ❌ Не удалось получить список услуг — см. ошибку выше.")
    else:
        print(f"   ✅ Получено услуг: {len(services)}")
        matching = [s for s in services if str(s.get("service")) == str(config.PRMOTION_SERVICE_ID)]
        if matching:
            print(f"   ✅ SERVICE_ID {config.PRMOTION_SERVICE_ID} найден: {matching[0].get('name')}")
        else:
            print(f"   ❌ SERVICE_ID {config.PRMOTION_SERVICE_ID} НЕ найден в списке услуг!")
            print("      Проверь PRMOTION_SERVICE_ID в .env — заказы будут падать с этой услугой.")
        print("      Полный список услуг с ID и лимитами: python get_services.py")

    print("=" * 50)
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
