from aiogram import types
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
            f"📢 Канал: {order['channel']}\n"
            f"👥 Подписчиков: {order['count']}\n"
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
        f"📢 Канал: {order['channel']}\n"
        f"👥 Подписчиков: {order['count']}\n"
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
