"""
Поиск ID услуг PRmotion — удобно смотреть список перед добавлением новой функции боту.

Запуск:
    python get_services.py                → показать ВСЕ услуги
    python get_services.py telegram        → только те, где "telegram" встречается в названии/категории
    python get_services.py instagram views → можно несколько слов, ищет по каждому отдельно (ИЛИ)
    python get_services.py --all-with-free → не прятать бесплатные услуги (по умолчанию они скрыты)
"""
import asyncio
import sys

from prmotion import get_services


def matches(service: dict, keywords: list[str]) -> bool:
    if not keywords:
        return True
    haystack = f"{service.get('name', '')} {service.get('category', '')}".lower()
    return any(kw in haystack for kw in keywords)


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_free = "--all-with-free" in sys.argv
    keywords = [a.lower() for a in args]

    print("🔍 Загружаю список услуг PRmotion...")
    services = await get_services()

    if services is None:
        print("❌ Не удалось получить список услуг (сайт недоступен или ошибка API — см. лог выше).")
        return

    filtered = [s for s in services if matches(s, keywords)]
    if not show_free:
        filtered = [s for s in filtered if "free" not in s.get("name", "").lower()]

    if not filtered:
        print("❌ Ничего не найдено по заданным словам.")
        print("\n📂 Доступные категории (для подсказки):")
        categories = sorted({s.get("category", "?") for s in services if s.get("category")})
        for cat in categories:
            print(f"   - {cat}")
        return

    filtered.sort(key=lambda s: (s.get("category", ""), s.get("name", "")))

    label = f"по «{', '.join(args)}»" if keywords else "(все)"
    print(f"\n✅ Найдено {len(filtered)} услуг {label}:\n")
    print("=" * 70)

    current_category = None
    for s in filtered:
        category = s.get("category", "?")
        if category != current_category:
            print(f"\n📂 {category}")
            current_category = category
        print(f"  ID: {s.get('service'):<8} {s.get('name')}")
        print(f"      💰 Цена: {s.get('rate', '?')}   📊 Мин/Макс: {s.get('min', '?')}/{s.get('max', '?')}")

    print("\n" + "=" * 70)
    print("Скопируй нужный ID и укажи его в .env как PRMOTION_SERVICE_ID (или для новой услуги).")


if __name__ == "__main__":
    asyncio.run(main())
