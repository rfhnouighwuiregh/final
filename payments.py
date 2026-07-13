from aiogram import types
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery
)
from datetime import datetime  # ← Добавили импорт

import config
import database
from bots import bot, dp, admin_bot
from prmotion import send_to_prmotion, precheck_order


def _order_id_from_callback(data: str, index: int) -> int:
    return int(data.split("_")[index])


# ========== КЛИЕНТ НАЖАЛ "ОПЛАТИТЬ" ==========
@dp.callback_query(
    lambda call: call.data.startswith("pay_")
    and not call.data.startswith("pay_stars_")
    and not call.data.startswith("pay_card_")
)
async def client_pay(callback: types.CallbackQuery):
    order_id = _order_id_from_callback(callback.data, 1)
    order = database.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['user_id'] != callback.from_user.id:
        await callback.answer("⛔ Это не ваш заказ!", show_alert=True)
        return
    if order['status'] != 'ожидает_оплаты':
        await callback.answer(f"⚠️ Заказ уже {order['status']}", show_alert=True)
        return
    await callback.answer()

    await callback.message.edit_reply_markup(reply_markup=None)

    count = order['count']
    price_stars = round(count * config.PRICE_PER_SUBSCRIBER_STARS)
    price_rub = count * config.PRICE_PER_SUBSCRIBER_RUB

    pay_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Оплатить Stars", callback_data=f"pay_stars_{order_id}")],
            [InlineKeyboardButton(text="🏦 Оплатить картой (временно не работает)", callback_data=f"pay_card_{order_id}")],
            [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel_order_{order_id}")]
        ]
    )
    await callback.message.answer(
        f"💳 <b>Выберите способ оплаты для заказа #{order_id}</b>\n\n"
        f"💰 Сумма: {price_rub:.2f} ₽\n"
        f"⭐ В Stars: {price_stars} Stars",
        parse_mode="HTML",
        reply_markup=pay_kb
    )


@dp.callback_query(lambda call: call.data.startswith("pay_card_"))
async def pay_card(callback: types.CallbackQuery):
    order_id = _order_id_from_callback(callback.data, 2)
    order = database.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['user_id'] != callback.from_user.id:
        await callback.answer("⛔ Это не ваш заказ!", show_alert=True)
        return
    await callback.answer("Оплата картой временно не работает", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"🏦 <b>Оплата картой / СБП пока не работает</b>\n\n"
        "Мы дорабатываем приём платежей картой и СБП, скоро всё заработает.\n"
        "Сейчас доступна оплата через ⭐ Stars.",
        parse_mode="HTML"
    )


@dp.callback_query(lambda call: call.data.startswith("cancel_order_"))
async def cancel_order_by_client(callback: types.CallbackQuery):
    order_id = _order_id_from_callback(callback.data, 2)
    order = database.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['user_id'] != callback.from_user.id:
        await callback.answer("⛔ Это не ваш заказ!", show_alert=True)
        return
    if order['status'] not in ('ожидает_подтверждения', 'ожидает_оплаты'):
        await callback.answer(f"⚠️ Заказ уже {order['status']}, отменить нельзя", show_alert=True)
        return

    database.update_order_status(order_id, 'отменен_клиентом')
    await callback.answer("❌ Заказ отменён")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"❌ Заказ #{order_id} отменён.")

    await admin_bot.send_message(
        config.ADMIN_ID,
        f"❌ <b>Клиент отменил заказ #{order_id}</b>\n"
        f"👤 @{order['username']}\n"
        f"📢 Канал: {order['channel']}",
        parse_mode="HTML"
    )


@dp.callback_query(lambda call: call.data.startswith("pay_stars_"))
async def pay_stars(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    order = database.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден!", show_alert=True)
        return
    if order['user_id'] != callback.from_user.id:
        await callback.answer("⛔ Это не ваш заказ!", show_alert=True)
        return
    await callback.answer()

    count = order['count']
    price_stars = round(count * config.PRICE_PER_SUBSCRIBER_STARS)

    try:
        await bot.send_invoice(
            chat_id=callback.message.chat.id,
            title=f"Накрутка подписчиков #{order_id}",
            description=f"Канал: {order['channel']}\nПодписчиков: {count}",
            payload=f"stars_order_{order_id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"{count} подписчиков", amount=price_stars)],
            start_parameter=f"order_{order_id}",
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            is_flexible=False
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)}")


@dp.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: PreCheckoutQuery):
    payload = pre_checkout_query.invoice_payload
    if payload.startswith("stars_order_"):
        order_id = int(payload.split("_")[2])
    else:
        order_id = int(payload.split("_")[1])

    order = database.get_order(order_id)
    if not order:
        await pre_checkout_query.answer(ok=False, error_message="Заказ не найден!")
        return

    # Проверка перед оплатой
    ok, error_text = await precheck_order(order)
    
    if not ok:
        await pre_checkout_query.answer(ok=False, error_message=error_text[:180])

        # Улучшенное уведомление для админа
        await admin_bot.send_message(
            config.ADMIN_ID,
            f"⚠️ <b>Оплата заказа #{order_id} ОТКЛОНЕНА</b>\n\n"
            f"👤 Клиент: @{order.get('username', 'нет_юзернейма')}\n"
            f"🆔 ID: <code>{order['user_id']}</code>\n"
            f"📢 Канал: {order['channel']}\n"
            f"👥 {order['count']} подписчиков\n"
            f"💰 Сумма: {order['price']:.2f} ₽\n\n"
            f"🔍 Причина:\n{error_text}\n\n"
            f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
            parse_mode="HTML"
        )
        print(f"🚫 Оплата #{order_id} отклонена: {error_text}")
        return

    await pre_checkout_query.answer(ok=True)
    print(f"✅ Pre-checkout для заказа #{order_id}")


@dp.message(lambda message: message.successful_payment is not None)
async def successful_payment_handler(message: types.Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    if payload.startswith("stars_order_"):
        order_id = int(payload.split("_")[2])
    else:
        order_id = int(payload.split("_")[1])
    
    database.update_order_status(order_id, "оплачено")
    await message.answer("✅ Оплата прошла успешно! Заказ отправлен в работу.")
    await send_to_prmotion(order_id)