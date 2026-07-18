import json
import os
from datetime import datetime

ORDERS_FILE = "orders.json"
MAX_ORDERS_PER_USER = 10

# Заказы в этих статусах никогда не удаляются автоматически — они либо
# в процессе, либо деньги уже приняты, историю по ним нужно сохранять.
ACTIVE_STATUSES = {'ожидает_подтверждения', 'ожидает_оплаты', 'оплачено', 'в_работе'}

orders = {}
order_counter = 0


def load_orders():
    global orders, order_counter
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            orders = {int(k): v for k, v in data.get('orders', {}).items()}
            order_counter = data.get('order_counter', 0)
        print(f"📂 Загружено {len(orders)} заказов из файла")
    else:
        orders = {}
        order_counter = 0
        print("📂 Создан новый файл заказов")


def save_orders():
    with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'orders': orders,
            'order_counter': order_counter
        }, f, ensure_ascii=False, indent=2)


def prune_old_orders(user_id):
    """Оставляет не больше MAX_ORDERS_PER_USER заказов на клиента.
    Удаляет только САМЫЕ СТАРЫЕ завершённые заказы (отклонён/отменён/выполнен) —
    активные и оплаченные заказы никогда не трогаем."""
    user_order_ids = sorted(
        oid for oid, o in orders.items() if o['user_id'] == user_id
    )
    excess = len(user_order_ids) - MAX_ORDERS_PER_USER
    if excess <= 0:
        return

    removed = 0
    for oid in user_order_ids:
        if removed >= excess:
            break
        if orders[oid]['status'] not in ACTIVE_STATUSES:
            del orders[oid]
            removed += 1

    if removed:
        save_orders()


def create_order(user_id, username, count, price, payment,
                  order_type='subscribers', channel=None, post_link=None, reaction_type=None):
    """
    order_type: 'subscribers' | 'reactions'
    Для 'subscribers' — заполняется channel, post_link/reaction_type пустые.
    Для 'reactions' — заполняется post_link и reaction_type ('good'/'bad'), channel пустой.
    """
    global order_counter
    order_counter += 1
    order_id = order_counter

    orders[order_id] = {
        'id': order_id,
        'user_id': user_id,
        'username': username,
        'order_type': order_type,
        'channel': channel,
        'post_link': post_link,
        'reaction_type': reaction_type,
        'count': count,
        'price': price,
        'payment': payment,
        'status': 'ожидает_подтверждения',
        'prmotion_order_id': None,
        'created_at': datetime.now().strftime("%d.%m.%Y %H:%M"),
        'updated_at': datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    save_orders()
    prune_old_orders(user_id)
    return order_id


def format_order_target(order: dict) -> str:
    """Строка с адресом заказа для сообщений — канал (подписчики) или пост+тип (реакции).
    order.get(...) — на случай старых заказов в orders.json, созданных до этой фичи."""
    if order.get('order_type', 'subscribers') == 'reactions':
        label = '👍 Хорошие' if order.get('reaction_type') == 'good' else '👎 Плохие'
        return f"🔗 Пост: {order.get('post_link')}\n❤️ Реакции: {label}"
    return f"📢 Канал: {order.get('channel')}"


def format_order_quantity_label(order: dict) -> str:
    """'Подписчиков' или 'Реакций' — для сообщений вида '{count} {label}'."""
    return "Подписчиков" if order.get('order_type', 'subscribers') == 'subscribers' else "Реакций"


def get_order(order_id):
    return orders.get(order_id)


def update_order_status(order_id, status):
    if order_id in orders:
        orders[order_id]['status'] = status
        orders[order_id]['updated_at'] = datetime.now().strftime("%d.%m.%Y %H:%M")
        save_orders()
        return True
    return False


def update_prmotion_order_id(order_id, prmotion_id):
    if order_id in orders:
        orders[order_id]['prmotion_order_id'] = prmotion_id
        save_orders()
        return True
    return False


# Загружаем заказы сразу при импорте модуля (как было в оригинале)
load_orders()

