import asyncio
import re

from aiogram import types
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

import config
import database
from bots import bot, dp, admin_bot
from prmotion import precheck_order

async def _notify_admin_if_precheck_fails(order_id: int):
    """
    Фоновая проверка PRmotion сразу после создания заказа. Молчит, если всё
    в порядке (чтобы не спамить админа на каждый нормальный заказ) — пишет
    только если уже сейчас видна проблема (не хватает денег, не тот
    SERVICE_ID, количество вне лимитов услуги), чтобы админ узнал об этом
    заранее, а не только в момент нажатия "Подтвердить".
    """
    order = database.get_order(order_id)
    if not order:
        return
    try:
        ok, error_text = await precheck_order(order)
    except Exception as e:
        print(f"⚠️ Фоновая проверка PRmotion для заказа #{order_id} упала: {e}")
        return

    if not ok:
        try:
            await admin_bot.send_message(
                config.ADMIN_ID,
                f"⚠️ <b>Предварительная проверка заказа #{order_id}</b>\n\n"
                f"Уже сейчас видна проблема: {error_text}\n\n"
                "Можешь решить проблему заранее — к моменту, когда нажмёшь "
                "«Подтвердить», бот проверит ещё раз.",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"⚠️ Не удалось отправить фоновое предупреждение по заказу #{order_id}: {e}")


# ========== СОСТОЯНИЯ ==========
class OrderStates(StatesGroup):
    waiting_for_order_type = State()
    waiting_for_reaction_type = State()
    waiting_for_count = State()
    waiting_for_channel = State()
    waiting_for_post_link = State()


class SupportStates(StatesGroup):
    waiting_for_question = State()


# ========== КЛАВИАТУРЫ ==========
cancel_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❌ Отменить заказ")]
    ],
    resize_keyboard=True
)

main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🛒 Новый заказ")],
        [KeyboardButton(text="📞 Поддержка")],
        [KeyboardButton(text="📋 Мои заказы")]
    ],
    resize_keyboard=True
)


def cancel_created_order_kb(order_id: int) -> ReplyKeyboardMarkup:
    """Закреплённая снизу клавиатура с кнопкой отмены конкретного заказа."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=f"❌ Отменить заказ #{order_id}")]],
        resize_keyboard=True
    )


order_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👥 Подписчики")],
        [KeyboardButton(text="❤️ Реакции на пост")],
        [KeyboardButton(text="❌ Отменить заказ")]
    ],
    resize_keyboard=True
)

reaction_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👍 Хорошие реакции")],
        [KeyboardButton(text="👎 Плохие реакции")],
        [KeyboardButton(text="❌ Отменить заказ")]
    ],
    resize_keyboard=True
)


# ========== СТАРТ / МЕНЮ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Я бот для заказа накрутки подписчиков и реакций на посты.\n\n"
        f"💰 <b>Подписчики:</b> {config.PRICE_PER_SUBSCRIBER_RUB} ₽ ({config.MIN_ORDER}–{config.MAX_ORDER} шт.)\n"
        f"❤️ <b>Реакции:</b> {config.PRICE_PER_REACTION_RUB} ₽ ({config.MIN_REACTIONS_ORDER}–{config.MAX_REACTIONS_ORDER} шт.)\n\n"
        "🛒 <b>Новый заказ</b> — оформить накрутку\n"
        "📞 <b>Поддержка</b> — задать вопрос администратору\n"
        "📋 <b>Мои заказы</b> — посмотреть статус заказов\n\n"
        "Выберите действие:",
        reply_markup=main_menu_kb,
        parse_mode="HTML"
    )


@dp.message(lambda message: message.text == "🛒 Новый заказ")
async def new_order(message: types.Message, state: FSMContext):
    await message.answer(
        "Что хотите заказать?",
        reply_markup=order_type_kb
    )
    await state.set_state(OrderStates.waiting_for_order_type)


@dp.message(OrderStates.waiting_for_order_type)
async def get_order_type(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await cmd_cancel(message, state)
        return

    if message.text == "👥 Подписчики":
        await state.update_data(order_type='subscribers')
        await message.answer(
            f"📝 Введите количество подписчиков (от {config.MIN_ORDER} до {config.MAX_ORDER}):",
            reply_markup=cancel_kb
        )
        await state.set_state(OrderStates.waiting_for_count)
    elif message.text == "❤️ Реакции на пост":
        await state.update_data(order_type='reactions')
        await message.answer(
            "Какие реакции нужны?",
            reply_markup=reaction_type_kb
        )
        await state.set_state(OrderStates.waiting_for_reaction_type)
    else:
        await message.answer("❌ Выберите вариант с клавиатуры.", reply_markup=order_type_kb)


@dp.message(OrderStates.waiting_for_reaction_type)
async def get_reaction_type(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await cmd_cancel(message, state)
        return

    if message.text == "👍 Хорошие реакции":
        reaction_type = 'good'
    elif message.text == "👎 Плохие реакции":
        reaction_type = 'bad'
    else:
        await message.answer("❌ Выберите вариант с клавиатуры.", reply_markup=reaction_type_kb)
        return

    await state.update_data(reaction_type=reaction_type)
    await message.answer(
        f"📝 Введите количество реакций (от {config.MIN_REACTIONS_ORDER} до {config.MAX_REACTIONS_ORDER}):",
        reply_markup=cancel_kb
    )
    await state.set_state(OrderStates.waiting_for_count)


def _build_orders_text(user_id: int) -> str:
    user_orders = sorted(
        (o for o in database.orders.values() if o['user_id'] == user_id),
        key=lambda o: o['id']
    )
    if not user_orders:
        return "📭 У вас пока нет заказов."

    status_map = {
        'ожидает_подтверждения': '⏳ Ожидает подтверждения',
        'ожидает_оплаты': '💳 Ожидает оплаты',
        'оплачено': '✅ Оплачено',
        'в_работе': '🔄 В работе (PRmotion)',
        'выполнен': '🎉 Выполнен!',
        'отклонен': '❌ Отклонён',
        'отменен_клиентом': '🚫 Отменён вами'
    }

    text = "📋 <b>Ваши заказы:</b>\n\n"
    for order in user_orders[-database.MAX_ORDERS_PER_USER:]:
        text += (
            f"─────────────────\n"
            f"🆔 Заказ #{order['id']}\n"
            f"{database.format_order_target(order)}\n"
            f"🔢 {database.format_order_quantity_label(order)}: {order['count']}\n"
            f"💰 {order['price']:.2f} ₽\n"
            f"📊 Статус: {status_map.get(order['status'], order['status'])}\n"
        )
    return text


ORDERS_REFRESH_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_orders")]
    ]
)


@dp.message(lambda message: message.text == "📋 Мои заказы")
async def my_orders(message: types.Message):
    text = _build_orders_text(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=ORDERS_REFRESH_KB)


@dp.callback_query(lambda call: call.data == "refresh_orders")
async def refresh_orders(callback: types.CallbackQuery):
    text = _build_orders_text(callback.from_user.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=ORDERS_REFRESH_KB)
        await callback.answer("Обновлено ✅")
    except Exception:
        # Telegram ругается, если текст не изменился — это не ошибка
        await callback.answer("Изменений нет")


@dp.message(Command("support"))
@dp.message(lambda message: message.text == "📞 Поддержка")
async def support_start(message: types.Message, state: FSMContext):
    await message.answer(
        "📞 <b>Служба поддержки</b>\n\nОпишите вашу проблему.\n✏️ Напишите текст обращения:",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    await state.set_state(SupportStates.waiting_for_question)


@dp.message(Command("cancel"))
@dp.message(lambda message: message.text == "❌ Отменить заказ")
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено!", reply_markup=main_menu_kb)


@dp.message(lambda message: bool(message.text) and message.text.startswith("❌ Отменить заказ #"))
async def cancel_created_order(message: types.Message, state: FSMContext):
    try:
        order_id = int(message.text.rsplit("#", 1)[1])
    except (IndexError, ValueError):
        await message.answer("❌ Не удалось определить номер заказа.", reply_markup=main_menu_kb)
        return

    order = database.get_order(order_id)
    if not order or order['user_id'] != message.from_user.id:
        await message.answer("❌ Заказ не найден.", reply_markup=main_menu_kb)
        return
    if order['status'] not in ('ожидает_подтверждения', 'ожидает_оплаты'):
        await message.answer(f"⚠️ Заказ уже {order['status']}, отменить нельзя.", reply_markup=main_menu_kb)
        return

    database.update_order_status(order_id, 'отменен_клиентом')
    await message.answer(f"❌ Заказ #{order_id} отменён.", reply_markup=main_menu_kb)

    await admin_bot.send_message(
        config.ADMIN_ID,
        f"❌ <b>Клиент отменил заказ #{order_id}</b>\n"
        f"👤 @{order['username']}\n"
        f"{database.format_order_target(order)}",
        parse_mode="HTML"
    )


@dp.message(SupportStates.waiting_for_question)
async def support_question(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await cmd_cancel(message, state)
        return
    if len(message.text.strip()) < 5:
        await message.answer("❌ Напишите более развёрнутое сообщение.")
        return

    admin_message = (
        f"📞 <b>НОВОЕ ОБРАЩЕНИЕ В ПОДДЕРЖКУ</b>\n"
        f"─────────────────\n"
        f"👤 Клиент: @{message.from_user.username or 'нет юзернейма'}\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"─────────────────\n"
        f"📝 <b>Сообщение:</b>\n"
        f"{message.text}\n"
        f"─────────────────\n"
        f"⏳ Статус: <b>Ожидает ответа</b>"
    )

    reply_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Ответить", callback_data=f"reply_{message.from_user.id}")]
        ]
    )

    await admin_bot.send_message(config.ADMIN_ID, admin_message, parse_mode="HTML", reply_markup=reply_keyboard)
    await message.answer("✅ Обращение отправлено!", reply_markup=main_menu_kb, parse_mode="HTML")
    await state.clear()


def normalize_channel_username(channel: str) -> str:
    """
    Telegram Bot API в get_chat() принимает ТОЛЬКО '@username', полные ссылки
    вида https://t.me/username он не понимает и вернёт "chat not found".
    Приводим любой из разрешённых форматов к '@username'.
    """
    channel = channel.strip()
    match = re.match(r'^https?://(?:t\.me|telegram\.me)/([\w_]+)$', channel, re.IGNORECASE)
    if match:
        return f"@{match.group(1)}"
    return channel


async def validate_channel(channel: str):
    """
    Проверяет, что канал реально существует и доступен боту, и что в нём
    достаточно подписчиков.

    ВАЖНО: Bot API Telegram не даёт способа узнать количество постов в
    канале (ни через get_chat, ни через любой другой метод) — это
    ограничение самого API, а не библиотеки. Поэтому проверяем только
    существование канала и число подписчиков.

    Возвращает (ok, error_text, chat).
    """
    channel = normalize_channel_username(channel)
    try:
        chat = await bot.get_chat(channel)
    except TelegramForbiddenError:
        return False, (
            "❌ Бот не может получить доступ к этому каналу.\n"
            "Убедитесь, что канал публичный (есть @username), и что бот не заблокирован в нём."
        ), None
    except TelegramBadRequest:
        return False, (
            "❌ Канал не найден.\n"
            "Проверьте ссылку — возможно, опечатка, канал приватный или был удалён."
        ), None
    except Exception as e:
        print(f"❌ Ошибка проверки канала {channel}: {e}")
        return False, "❌ Не удалось проверить канал. Попробуйте ещё раз чуть позже.", None

    if chat.type != "channel":
        return False, "❌ Эта ссылка ведёт не на канал (группа/чат/пользователь). Укажите именно канал.", None

    try:
        members_count = await bot.get_chat_member_count(chat.id)
    except Exception as e:
        print(f"⚠️ Не удалось получить число подписчиков {channel}: {e}")
        members_count = None

    if members_count is not None and members_count < config.MIN_CHANNEL_SUBSCRIBERS:
        return False, (
            f"❌ В канале должно быть минимум {config.MIN_CHANNEL_SUBSCRIBERS} подписчиков "
            f"(сейчас: {members_count})."
        ), None

    return True, None, chat


async def _finalize_order(message: types.Message, state: FSMContext, order_id: int, order_summary_html: str):
    """
    Общий хвост оформления заказа — что для подписчиков, что для реакций:
    карточка админу на подтверждение, фоновая проверка PRmotion, ответ клиенту.
    """
    order = database.get_order(order_id)

    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{order_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{order_id}")]
        ]
    )

    order_text = (
        f"🔔 <b>НОВЫЙ ЗАКАЗ #{order_id}</b>\n─────────────────\n"
        f"👤 Клиент: @{message.from_user.username or 'нет юзернейма'}\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"{order_summary_html}"
        f"─────────────────\n"
        f"📅 Создан: {order['created_at']}\n"
        f"⏳ Статус: <b>Ожидает подтверждения</b>"
    )

    print(f"📤 Отправляю заказ #{order_id} в админ-бота (ADMIN_ID: {config.ADMIN_ID})")
    try:
        await admin_bot.send_message(config.ADMIN_ID, order_text, parse_mode="HTML", reply_markup=admin_kb)
        print(f"✅ Заказ #{order_id} отправлен в админ-бота")
    except Exception as e:
        print(f"❌ Ошибка при отправке в админ-бота: {e}")
        await message.answer(f"❌ Ошибка при создании заказа: {str(e)}")
        return

    # Параллельно (не задерживая ответ клиенту) пингуем PRmotion — если уже
    # сейчас видно проблему с балансом/лимитами, админ узнает об этом сразу,
    # не дожидаясь момента, когда сам нажмёт "Подтвердить".
    asyncio.create_task(_notify_admin_if_precheck_fails(order_id))

    await message.answer(
        f"✅ <b>Заказ #{order_id} создан!</b>\n\n"
        f"💰 Стоимость: {order['price']:.2f} ₽\n\n"
        "Администратор подтвердит заказ в ближайшее время, после чего пришлю кнопку оплаты.\n\n"
        "Передумали? Можно отменить, пока он не подтверждён — кнопка снизу 👇",
        reply_markup=cancel_created_order_kb(order_id),
        parse_mode="HTML"
    )
    await state.clear()


POST_LINK_RE = re.compile(r'^https?://(?:t\.me|telegram\.me)/([\w_]+)/(\d+)$', re.IGNORECASE)


# ========== ЗАКАЗ (КОЛИЧЕСТВО) ==========
@dp.message(OrderStates.waiting_for_count)
async def get_count(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await cmd_cancel(message, state)
        return

    data = await state.get_data()
    order_type = data.get('order_type', 'subscribers')
    min_v, max_v = (
        (config.MIN_ORDER, config.MAX_ORDER) if order_type == 'subscribers'
        else (config.MIN_REACTIONS_ORDER, config.MAX_REACTIONS_ORDER)
    )

    try:
        count = int(message.text)
    except ValueError:
        await message.answer(f"❌ Введите число от {min_v} до {max_v}.", parse_mode="HTML")
        return
    if count < min_v or count > max_v:
        await message.answer(f"❌ Введите число от {min_v} до {max_v}.", parse_mode="HTML")
        return
    await state.update_data(count=count)

    if order_type == 'subscribers':
        price_rub = count * config.PRICE_PER_SUBSCRIBER_RUB
        price_stars = round(count * config.PRICE_PER_SUBSCRIBER_STARS)
        await message.answer(
            f"✅ Принято! <b>{count}</b> подписчиков.\n"
            f"💰 Стоимость: <b>{price_rub:.2f} ₽</b>\n"
            f"⭐ В Stars: <b>{price_stars} Stars</b>\n\n"
            "📢 Теперь укажите ссылку на канал.\nПример: @my_channel или https://t.me/my_channel",
            reply_markup=cancel_kb,
            parse_mode="HTML"
        )
        await state.set_state(OrderStates.waiting_for_channel)
    else:
        price_rub = count * config.PRICE_PER_REACTION_RUB
        price_stars = round(count * config.PRICE_PER_REACTION_STARS)
        await message.answer(
            f"✅ Принято! <b>{count}</b> реакций.\n"
            f"💰 Стоимость: <b>{price_rub:.2f} ₽</b>\n"
            f"⭐ В Stars: <b>{price_stars} Stars</b>\n\n"
            "🔗 Теперь укажите ссылку на конкретный пост.\nПример: https://t.me/my_channel/123",
            reply_markup=cancel_kb,
            parse_mode="HTML"
        )
        await state.set_state(OrderStates.waiting_for_post_link)


@dp.message(OrderStates.waiting_for_channel)
async def get_channel(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await cmd_cancel(message, state)
        return
    channel = message.text.strip()
    if not re.match(r'^@[\w_]{5,}$|^https?://(t\.me|telegram\.me)/[\w_]{5,}$', channel, re.IGNORECASE):
        await message.answer("❌ Неверный формат! Используйте: @my_channel или https://t.me/my_channel", reply_markup=cancel_kb, parse_mode="HTML")
        return

    checking_msg = await message.answer("🔍 Проверяю канал...")
    ok, error_text, chat = await validate_channel(channel)
    await checking_msg.delete()

    if not ok:
        await message.answer(error_text, reply_markup=cancel_kb, parse_mode="HTML")
        return

    # Дальше используем @username из get_chat — он точнее того, что ввёл клиент
    channel = f"@{chat.username}" if chat.username else channel

    data = await state.get_data()
    count = data['count']
    price_rub = count * config.PRICE_PER_SUBSCRIBER_RUB
    price_stars = round(count * config.PRICE_PER_SUBSCRIBER_STARS)

    order_id = database.create_order(
        user_id=message.from_user.id,
        username=message.from_user.username or "нет юзернейма",
        order_type='subscribers',
        channel=channel,
        count=count,
        price=price_rub,
        payment="Stars"  # реальный способ оплаты выбирается позже, после подтверждения; карта пока не работает
    )

    summary = (
        f"👥 Подписчиков: <b>{count}</b>\n"
        f"📢 Канал: <b>{channel}</b>\n"
        f"💰 Стоимость: <b>{price_rub:.2f} ₽</b> (~{price_stars} Stars)\n"
    )
    await _finalize_order(message, state, order_id, summary)


@dp.message(OrderStates.waiting_for_post_link)
async def get_post_link(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить заказ":
        await cmd_cancel(message, state)
        return

    post_link = message.text.strip()
    match = POST_LINK_RE.match(post_link)
    if not match:
        await message.answer(
            "❌ Неверный формат! Нужна ссылка именно на пост, например:\nhttps://t.me/my_channel/123",
            reply_markup=cancel_kb,
            parse_mode="HTML"
        )
        return

    channel_username, message_id = match.group(1), match.group(2)

    checking_msg = await message.answer("🔍 Проверяю канал...")
    ok, error_text, chat = await validate_channel(f"@{channel_username}")
    await checking_msg.delete()

    if not ok:
        await message.answer(error_text, reply_markup=cancel_kb, parse_mode="HTML")
        return

    # Нормализуем ссылку под точный @username канала, как в validate_channel для подписчиков
    if chat.username:
        post_link = f"https://t.me/{chat.username}/{message_id}"

    data = await state.get_data()
    count = data['count']
    reaction_type = data['reaction_type']
    price_rub = count * config.PRICE_PER_REACTION_RUB
    price_stars = round(count * config.PRICE_PER_REACTION_STARS)

    order_id = database.create_order(
        user_id=message.from_user.id,
        username=message.from_user.username or "нет юзернейма",
        order_type='reactions',
        post_link=post_link,
        reaction_type=reaction_type,
        count=count,
        price=price_rub,
        payment="Stars"
    )

    reaction_label = "👍 Хорошие" if reaction_type == 'good' else "👎 Плохие"
    summary = (
        f"❤️ Тип: <b>Реакции ({reaction_label})</b>\n"
        f"🔗 Пост: <b>{post_link}</b>\n"
        f"🔢 Количество: <b>{count}</b>\n"
        f"💰 Стоимость: <b>{price_rub:.2f} ₽</b> (~{price_stars} Stars)\n"
    )
    await _finalize_order(message, state, order_id, summary)


