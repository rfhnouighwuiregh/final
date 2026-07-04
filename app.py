import asyncio
import os
from threading import Thread
from flask import Flask

# Импортируем твоего бота из основного файла
# Если твой основной бот называется bot.py:
from main import bot, dp

# Если основной файл называется main.py — раскомментируй эту строку и закомментируй верхнюю:
# from main import bot, dp

app = Flask(__name__)

@app.route('/')
def index():
    return "✅ Бот работает!"

@app.route('/health')
def health():
    return "OK", 200

def run_bot():
    """Запускает бота в отдельном потоке."""
    print("🚀 Запуск бота...")
    asyncio.run(dp.start_polling(bot))

if __name__ == '__main__':
    # Запускаем бота в фоновом потоке
    bot_thread = Thread(target=run_bot)
    bot_thread.start()
    
    # Запускаем Flask-сервер для Render
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 Запуск веб-сервера на порту {port}...")
    app.run(host='0.0.0.0', port=port)