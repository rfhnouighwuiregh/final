from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import config
import database
from bots import bot, admin_bot, admin_dp
from prmotion import precheck_order



# Единый механизм "жду свободный текст от админа" — используется и для
# ответа в поддержку, и для причины отклонения заказа. Раньше это были два
# независимых словаря, из-за чего один сценарий мог перебить другой.
# Значение: ('reply', user_id) или ('reject_reason', order_id).
admin_pending = {}


# ========== ПОДТВЕРЖДЕНИЕ / ОТКЛОНЕНИЕ ЗАКАЗА ==========
@admin_dp.callback_query(lambda call: call.data.startswith("confirm_"))
async def confirm_order(callback: types.CallbackQuery):
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ У вас нет прав!", show_alert=True)
        return
    order_id = int(callback.data.split("_")[1])
    order = database.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['status'] != 'ожидает_подтверждения':
        await callback.answer(f"⚠️ Заказ уже {order['status']}", show_alert=True)
        return

    await callback.answer("🔍 Проверяю PRmotion...")

    # Свежая проверка прямо в момент подтверждения — не полагаемся только на
    # фоновую проверку при создании заказа, т.к. между созданием и
    # подтверждением могло пройти много времени, баланс мог измениться.
    ok, error_text = await precheck_order(order)

    if not ok:
        # ВАЖНО: кнопки "Подтвердить/Отклонить" на исходном сообщении НЕ
        # трогаем — чтобы можно было вернуться и подтвердить позже (например,
        # после пополнения баланса PRmotion), без необходимости всё пересоздавать.
        await callback.message.answer(
            f"⚠️ <b>Не могу подтвердить заказ #{order_id} — проверка PRmotion не прошла</b>\n\n"
            f"👤 Клиент: @{order['username']}\n"
            f"🆔 ID: <code>{order['user_id']}</code>\n"
            f"{database.format_order_target(order)}\n"
            f"🔢 {database.format_order_quantity_label(order)}: {order['count']}\n"
            f"💰 Сумма: {order['price']:.2f} ₽\n\n"
            f"🔴 Причина: {error_text}\n\n"
            "Заказ пока НЕ подтверждён и НЕ отклонён, оплата у клиента не запрошена.\n\n"
            "Напиши текст, который увидит клиент при отклонении заказа — "
            "или отправь /cancel, чтобы ничего не отклонять и вернуться к "
            "заказу позже (кнопки «Подтвердить/Отклонить» на карточке заказа всё ещё активны).",
            parse_mode="HTML"
        )
        admin_pending[config.ADMIN_ID] = ('reject_reason', order_id)
        return

    database.update_order_status(order_id, 'ожидает_оплаты')
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Заказ #{order_id} подтверждён!")

    await bot.send_message(
        order['user_id'],
        f"✅ <b>Заказ #{order_id} подтверждён!</b>\n\n"
        f"{database.format_order_target(order)}\n"
        f"🔢 {database.format_order_quantity_label(order)}: {order['count']}\n"
        f"💰 Сумма: {order['price']:.2f} ₽\n\n"
        f"Нажмите кнопку ниже, чтобы оплатить:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", callback_data=f"pay_{order_id}")],
                [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel_order_{order_id}")]
            ]
        )
    )


@admin_dp.callback_query(lambda call: call.data.startswith("complete_order_"))
async def complete_order(callback: types.CallbackQuery):
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ У вас нет прав!", show_alert=True)
        return
    order_id = int(callback.data.split("_")[2])
    order = database.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['status'] != 'в_работе':
        await callback.answer(f"⚠️ Заказ уже {order['status']}", show_alert=True)
        return

    database.update_order_status(order_id, 'выполнен')
    await callback.answer("✅ Отмечено как выполнено!")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Заказ #{order_id} отмечен выполненным, клиенту отправлен запрос на оценку.")

    rating_kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=f"{n}⭐", callback_data=f"rate_{order_id}_{n}")
            for n in range(1, 6)
        ]]
    )
    try:
        await bot.send_message(
            order['user_id'],
            f"✅ <b>Заказ #{order_id} выполнен!</b>\n\n"
            "Оцените, пожалуйста, качество работы бота:",
            parse_mode="HTML",
            reply_markup=rating_kb
        )
    except Exception as e:
        await callback.message.answer(f"⚠️ Не удалось отправить запрос на оценку клиенту: {e}")


@admin_dp.message(Command("addreview"))
async def add_test_review(message: types.Message):
    if message.from_user.id != config.ADMIN_ID:
        return

    rating_kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=f"{n}⭐", callback_data=f"testrate_{n}")
            for n in range(1, 6)
        ]]
    )
    await message.answer(
        "🧪 <b>Тестовый отзыв</b>\n\nОцените, пожалуйста, качество работы бота:",
        parse_mode="HTML",
        reply_markup=rating_kb
    )


@admin_dp.callback_query(lambda call: call.data.startswith("testrate_"))
async def test_rate(callback: types.CallbackQuery):
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ У вас нет прав!", show_alert=True)
        return

    rating = int(callback.data.split("_")[1])
    order_id = database.create_test_review(rating)

    await callback.answer()
    await callback.message.edit_text(f"Спасибо за оценку: {'⭐' * rating}")

    comment_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Оставить комментарий", callback_data=f"testcomment_{order_id}")],
            [InlineKeyboardButton(text="Пропустить", callback_data=f"testskip_{order_id}")]
        ]
    )
    await callback.message.answer("Хотите добавить комментарий? Это по желанию.", reply_markup=comment_kb)


@admin_dp.callback_query(lambda call: call.data.startswith("testcomment_"))
async def test_request_comment(callback: types.CallbackQuery):
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ У вас нет прав!", show_alert=True)
        return

    order_id = int(callback.data.split("_")[1])
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    admin_pending[config.ADMIN_ID] = ('test_review_comment', order_id)
    await callback.message.answer("✏️ Напишите комментарий одним сообщением:")


@admin_dp.callback_query(lambda call: call.data.startswith("testskip_"))
async def test_skip_comment(callback: types.CallbackQuery):
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ У вас нет прав!", show_alert=True)
        return

    order_id = int(callback.data.split("_")[1])
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ Тестовый отзыв добавлен (заказ #{order_id}).\n"
        "Проверьте раздел «⭐ Отзывы» в клиентском боте.\n"
        "Удалить его можно через /reviews → 🗑 Удалить."
    )


@admin_dp.message(Command("reviews"))
async def list_reviews(message: types.Message):
    if message.from_user.id != config.ADMIN_ID:
        return

    avg_rating, total = database.get_rating_stats()
    if total == 0:
        await message.answer("Отзывов пока нет.")
        return

    await message.answer(f"⭐ Средняя оценка: {avg_rating:.1f} из 5 ({total} оценок)")

    for r in database.get_reviews(limit=20):
        stars = "⭐" * r['rating']
        text = f"{stars} — Заказ #{r['id']}"
        if r.get('review_comment'):
            text += f"\n«{r['review_comment']}»"
        await message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🗑 Удалить отзыв", callback_data=f"delete_review_{r['id']}")]]
            )
        )


@admin_dp.callback_query(lambda call: call.data.startswith("delete_review_"))
async def delete_review(callback: types.CallbackQuery):
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ У вас нет прав!", show_alert=True)
        return
    order_id = int(callback.data.split("_")[2])
    if database.delete_review(order_id):
        await callback.answer("🗑 Отзыв удалён")
        await callback.message.edit_text(f"🗑 Отзыв по заказу #{order_id} удалён.")
    else:
        await callback.answer("❌ Заказ не найден!", show_alert=True)


@admin_dp.callback_query(lambda call: call.data.startswith("reject_"))
async def reject_order(callback: types.CallbackQuery):
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ У вас нет прав!", show_alert=True)
        return
    order_id = int(callback.data.split("_")[1])
    order = database.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['status'] != 'ожидает_подтверждения':
        await callback.answer(f"⚠️ Заказ уже {order['status']}", show_alert=True)
        return
    database.update_order_status(order_id, 'отклонен')
    await callback.answer("❌ Заказ отклонён!")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"❌ Заказ #{order_id} отклонён!")
    await bot.send_message(order['user_id'], f"❌ Заказ #{order_id} отклонён! Свяжитесь с поддержкой.", parse_mode="HTML")


# ========== ОТВЕТЫ В ПОДДЕРЖКУ ==========
@admin_dp.callback_query(lambda call: call.data.startswith("reply_"))
async def handle_reply(callback: types.CallbackQuery):
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ У вас нет прав!", show_alert=True)
        return
    user_id = int(callback.data.split("_")[1])
    await callback.answer("✏️ Введите ваш ответ")
    admin_pending[config.ADMIN_ID] = ('reply', user_id)
    await callback.message.answer(f"✏️ Введите ответ для клиента (ID: {user_id}):")


# ========== ЕДИНЫЙ ОБРАБОТЧИК СВОБОДНОГО ТЕКСТА ОТ АДМИНА ==========
@admin_dp.message(lambda message: message.from_user.id == config.ADMIN_ID)
async def admin_free_text(message: types.Message):
    if config.ADMIN_ID not in admin_pending:
        return

    action, target = admin_pending[config.ADMIN_ID]
    text = (message.text or "").strip()

    if message.text == "/cancel":
        del admin_pending[config.ADMIN_ID]
        await message.answer("❌ Отменено.")
        return

    if action == 'reply':
        user_id = target
        if len(text) < 2:
            await message.answer("❌ Слишком коротко.")
            return
        try:
            await bot.send_message(user_id, f"📩 <b>Ответ администратора:</b>\n\n{text}", parse_mode="HTML")
            del admin_pending[config.ADMIN_ID]
            await message.answer("✅ Ответ отправлен!")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}")

    elif action == 'reject_reason':
        order_id = target
        order = database.get_order(order_id)
        if not order:
            await message.answer("❌ Заказ уже не найден.")
            del admin_pending[config.ADMIN_ID]
            return
        if order['status'] != 'ожидает_подтверждения':
            await message.answer(f"⚠️ Заказ уже {order['status']} — отклонять больше не нужно.")
            del admin_pending[config.ADMIN_ID]
            return
        if len(text) < 2:
            await message.answer("❌ Слишком коротко, напиши причину подробнее (или /cancel).")
            return

        database.update_order_status(order_id, 'отклонен')
        del admin_pending[config.ADMIN_ID]
        await message.answer(f"❌ Заказ #{order_id} отклонён с указанной причиной.")
        try:
            await bot.send_message(
                order['user_id'],
                f"❌ <b>Заказ #{order_id} отклонён.</b>\n\nПричина: {text}",
                parse_mode="HTML"
            )
        except Exception as e:
            await message.answer(f"⚠️ Заказ отклонён, но не удалось уведомить клиента: {e}")

    elif action == 'test_review_comment':
        order_id = target
        if len(text) < 1:
            await message.answer("❌ Пустой комментарий, напишите текст (или /cancel).")
            return
        database.set_order_review_comment(order_id, text)
        del admin_pending[config.ADMIN_ID]
        await message.answer(
            f"✅ Тестовый отзыв добавлен (заказ #{order_id}).\n"
            "Проверьте раздел «⭐ Отзывы» в клиентском боте.\n"
            "Удалить его можно через /reviews → 🗑 Удалить."
        )
