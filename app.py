"""
Точка входа для Render (Web Service, бесплатный тариф).

На бесплатном тарифе Render нет типа сервиса "Background Worker" — доступен
только "Web Service", который ОБЯЗАН слушать $PORT, иначе Render считает
деплой нездоровым и убивает его. Сам бот (main.py) никакой порт не слушает —
это обычный long-polling процесс. Поэтому здесь поднимаем:
  1) полноценный Flask-сервер, который просто отвечает "OK" на /health —
     чтобы Render видел, что сервис жив;
  2) оба бота (клиентский и админский) в фоновом потоке, через polling.

ВАЖНО: бесплатный Web Service на Render "засыпает" после ~15 минут без
ВХОДЯЩИХ HTTP-запросов. Long-polling самого бота Render не считает
активностью (это исходящие запросы к Telegram, а не входящие к нам). Значит
бот всё равно уснёт, если никто не дёргает /health снаружи. Если это важно —
настрой внешний пинг (например, UptimeRobot или cron-задачу) на
https://<твой-сервис>.onrender.com/health каждые 5-10 минут.
"""

import asyncio
import os
from threading import Thread

from flask import Flask

# Импорт main.py запускает регистрацию всех хэндлеров (client_bot, payments,
# admin_bot) на dp / admin_dp — точно так же, как при обычном запуске
# `python main.py`, только без вызова его polling-цикла напрямую.
from main import bot, admin_bot, dp, admin_dp

app = Flask(__name__)


@app.route('/')
def index():
    return "✅ Бот работает!"


@app.route('/health')
def health():
    return "OK", 200


async def _run_both_bots():
    """
    Запускает polling ОБОИХ ботов одновременно.

    handle_signals=False — ОБЯЗАТЕЛЬНО для запуска в фоновом потоке: по
    умолчанию aiogram пытается повесить обработчик SIGINT/SIGTERM для
    аккуратного завершения, а это возможно только в главном потоке
    интерпретатора. У нас главный поток занят Flask-сервером, боты крутятся
    в отдельном Thread — без этого флага polling падает сразу при старте с
    RuntimeError: set_wakeup_fd only works in main thread of the main interpreter.
    """
    await asyncio.gather(
        dp.start_polling(bot, handle_signals=False),
        admin_dp.start_polling(admin_bot, handle_signals=False)
    )


def run_bots():
    print("🚀 Запуск ботов (клиентский + админский)...")
    asyncio.run(_run_both_bots())


if __name__ == '__main__':
    bot_thread = Thread(target=run_bots, daemon=True)
    bot_thread.start()

    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 Запуск веб-сервера на порту {port}...")
    app.run(host='0.0.0.0', port=port)
