# limits.py
from datetime import datetime
from database import get_db


def get_daily_sent(user_id):
    """Возвращает сумму отправленных сегодня денег"""
    today = datetime.now().date().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT sent_amount FROM daily_limits 
            WHERE user_id = ? AND date = ?
        ''', (user_id, today))
        row = cursor.fetchone()
        return row['sent_amount'] if row else 0


def get_daily_received(user_id):
    """Возвращает сумму полученных сегодня денег"""
    today = datetime.now().date().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT received_amount FROM daily_limits 
            WHERE user_id = ? AND date = ?
        ''', (user_id, today))
        row = cursor.fetchone()
        return row['received_amount'] if row else 0


def update_daily_sent(user_id, amount):
    """Обновляет сумму отправленных сегодня денег"""
    today = datetime.now().date().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO daily_limits (user_id, date, sent_amount)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
            sent_amount = sent_amount + ?
        ''', (user_id, today, amount, amount))
        conn.commit()


def update_daily_received(user_id, amount):
    """Обновляет сумму полученных сегодня денег"""
    today = datetime.now().date().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO daily_limits (user_id, date, received_amount)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
            received_amount = received_amount + ?
        ''', (user_id, today, amount, amount))
        conn.commit()


def check_transfer_limit(user_id, amount):
    """
    Проверяет лимиты и комиссию для исходящего перевода
    Возвращает (комиссия, итоговая_сумма_получателю_до_его_комиссии)
    
    Лимиты:
    - До 5000₽ в день: комиссия 0%
    - 5000-25000₽ в день: комиссия 13%
    - Более 25000₽ в день: комиссия 25%
    """
    from config import DAILY_TRANSFER_LIMIT_FREE, DAILY_TRANSFER_LIMIT_LOW, TRANSFER_FEE_LOW, TRANSFER_FEE_HIGH
    
    sent_today = get_daily_sent(user_id)
    new_total = sent_today + amount
    
    if new_total <= DAILY_TRANSFER_LIMIT_FREE:
        fee = 0
        final_amount = amount
    elif new_total <= DAILY_TRANSFER_LIMIT_LOW:
        fee = amount * TRANSFER_FEE_LOW
        final_amount = amount - fee
    else:
        fee = amount * TRANSFER_FEE_HIGH
        final_amount = amount - fee
    
    # Обновляем лимит
    update_daily_sent(user_id, amount)
    
    return fee, final_amount


def check_receive_limit(user_id, amount):
    """
    Проверяет лимиты и комиссию для входящего перевода
    Возвращает (комиссия, итоговая_сумма_получателю)
    
    Лимиты:
    - До 10000₽ в день: комиссия 0%
    - 10000-50000₽ в день: комиссия 20%
    - Более 50000₽ в день: комиссия 50%
    """
    from config import DAILY_RECEIVE_LIMIT_FREE, DAILY_RECEIVE_LIMIT_MEDIUM, RECEIVE_FEE_MEDIUM, RECEIVE_FEE_HIGH
    
    received_today = get_daily_received(user_id)
    new_total = received_today + amount
    
    if new_total <= DAILY_RECEIVE_LIMIT_FREE:
        fee = 0
        final_amount = amount
    elif new_total <= DAILY_RECEIVE_LIMIT_MEDIUM:
        fee = amount * RECEIVE_FEE_MEDIUM
        final_amount = amount - fee
    else:
        fee = amount * RECEIVE_FEE_HIGH
        final_amount = amount - fee
    
    # Обновляем лимит
    update_daily_received(user_id, amount)
    
    return fee, final_amount


def check_transfer_full(user_id, amount):
    """
    Полная проверка перевода с учётом обеих комиссий
    Возвращает (комиссия_отправителя, комиссия_получателя, итоговая_сумма_получателю)
    """
    transfer_fee, after_sender_fee = check_transfer_limit(user_id, amount)
    receive_fee, final_amount = check_receive_limit(user_id, after_sender_fee)
    
    return transfer_fee, receive_fee, final_amount


def get_transfer_info(user_id, amount):
    """
    Возвращает информацию о переводе для отображения пользователю
    """
    from config import DAILY_TRANSFER_LIMIT_FREE, DAILY_TRANSFER_LIMIT_LOW, TRANSFER_FEE_LOW, TRANSFER_FEE_HIGH
    from config import DAILY_RECEIVE_LIMIT_FREE, DAILY_RECEIVE_LIMIT_MEDIUM, RECEIVE_FEE_MEDIUM, RECEIVE_FEE_HIGH
    
    sent_today = get_daily_sent(user_id)
    new_sent_total = sent_today + amount
    
    if new_sent_total <= DAILY_TRANSFER_LIMIT_FREE:
        transfer_fee_percent = 0
        transfer_fee_amount = 0
        after_transfer = amount
    elif new_sent_total <= DAILY_TRANSFER_LIMIT_LOW:
        transfer_fee_percent = TRANSFER_FEE_LOW * 100
        transfer_fee_amount = amount * TRANSFER_FEE_LOW
        after_transfer = amount - transfer_fee_amount
    else:
        transfer_fee_percent = TRANSFER_FEE_HIGH * 100
        transfer_fee_amount = amount * TRANSFER_FEE_HIGH
        after_transfer = amount - transfer_fee_amount
    
    # Для получателя считаем отдельно (но показываем приблизительно)
    receive_fee_percent = 0
    receive_fee_amount = 0
    
    return {
        'amount': amount,
        'transfer_fee_percent': transfer_fee_percent,
        'transfer_fee_amount': transfer_fee_amount,
        'after_transfer': after_transfer,
        'receive_fee_percent': receive_fee_percent,
        'receive_fee_amount': receive_fee_amount,
        'final_amount': after_transfer
    }


def reset_daily_limits_for_user(user_id):
    """Сбрасывает дневные лимиты пользователя (для админа)"""
    today = datetime.now().date().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM daily_limits WHERE user_id = ? AND date = ?', (user_id, today))
        conn.commit()


def get_user_daily_stats(user_id):
    """Возвращает статистику лимитов пользователя за сегодня"""
    sent = get_daily_sent(user_id)
    received = get_daily_received(user_id)
    
    from config import DAILY_TRANSFER_LIMIT_FREE, DAILY_TRANSFER_LIMIT_LOW, DAILY_RECEIVE_LIMIT_FREE, DAILY_RECEIVE_LIMIT_MEDIUM
    
    return {
        'sent_today': sent,
        'sent_limit_free': DAILY_TRANSFER_LIMIT_FREE,
        'sent_limit_low': DAILY_TRANSFER_LIMIT_LOW,
        'received_today': received,
        'received_limit_free': DAILY_RECEIVE_LIMIT_FREE,
        'received_limit_medium': DAILY_RECEIVE_LIMIT_MEDIUM
  }
