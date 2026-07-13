import asyncio
from datetime import datetime, time, timedelta

from aiogram import types
from aiogram.filters import Command

import config
from bots import admin_bot, admin_dp

# Хранилище изменений за сегодня.
# ВАЖНО: это просто список в памяти процесса — при рестарте бота (а на
# Render это происходит при каждом деплое, и иногда само по себе) список
# обнулится. Если это станет проблемой, стоит хранить в database.py/файле,
# как это уже сделано для заказов.
today_changes = []
REPORT_TIME = time(hour=20, minute=0)


def _resolve_channel():
    """NEWS_CHANNEL из .env — это '@username', его и используем как chat_id напрямую."""
    if not config.NEWS_CHANNEL:
        return None
    return config.NEWS_CHANNEL


async def send_daily_report(force: bool = False):
    """
    Отправляет отчёт в канал новостей.
    force=True — отправить даже если сегодня не было ни одного /addchange
    (используется командой /sendnow для теста).
    """
    channel = _resolve_channel()
    if not channel:
        print("❌ NEWS_CHANNEL не задан в .env — некуда отправлять отчёт.")
        return False, "NEWS_CHANNEL не задан в .env"

    if not today_changes and not force:
        print("📝 Изменений сегодня не было — отчёт не отправляю.")
        return True, "Изменений не было, отчёт пропущен"

    if today_changes:
        report_text = f"📋 <b>Что изменилось в боте за {datetime.now().strftime('%d.%m.%Y')}</b>\n\n"
        for change in today_changes:
            report_text += f"• {change}\n"
        report_text += "\nПродолжаем развивать проект! 🚀"
    else:
        report_text = "📋 Тестовое сообщение — изменений сегодня пока не добавлено."

    try:
        await admin_bot.send_message(chat_id=channel, text=report_text, parse_mode="HTML")
        print("✅ Отчёт отправлен в канал")
        today_changes.clear()
        return True, "Отправлено"
    except Exception as e:
        print(f"❌ Ошибка отправки в канал: {e}")
        return False, f"{type(e).__name__}: {e}"


# ВАЖНО: обе команды зарегистрированы на admin_dp (админ-бот) и проверяют
# ADMIN_ID — иначе любой человек в клиентском боте мог бы триггерить
# публикацию в ваш канал.

@admin_dp.message(Command("addchange"))
async def add_change(message: types.Message):
    if message.from_user.id != config.ADMIN_ID:
        return

    text = message.text.replace("/addchange", "", 1).strip()
    if len(text) < 5:
        await message.answer("❌ Коротко. Опиши изменение (минимум 5 символов).\nПример: /addchange Ускорили обработку заказов")
        return

    today_changes.append(text)
    count = len(today_changes)
    await message.answer(
        f"✅ Добавлено ({count} изменени{'е' if count == 1 else 'й'} за сегодня).\n"
        f"Отчёт уйдёт в канал в {REPORT_TIME.strftime('%H:%M')}, либо сразу — командой /sendnow"
    )


@admin_dp.message(Command("sendnow"))
async def send_now(message: types.Message):
    """Тестовая команда — отправляет отчёт в канал немедленно, не дожидаясь вечера."""
    if message.from_user.id != config.ADMIN_ID:
        return

    ok, info = await send_daily_report(force=True)
    if ok:
        await message.answer(f"✅ {info}")
    else:
        await message.answer(f"❌ Не получилось: {info}")


async def daily_report_scheduler():
    """Раз в сутки, в REPORT_TIME, отправляет накопленные изменения в канал."""
    while True:
        now = datetime.now()
        target = datetime.combine(now.date(), REPORT_TIME)
        if now >= target:
            target += timedelta(days=1)  # было target.replace(day=target.day + 1) — падало в конце месяца
        await asyncio.sleep((target - now).total_seconds())
        await send_daily_report()
