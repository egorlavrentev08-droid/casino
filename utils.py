# utils.py
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from database import get_user, update_balance, add_transaction, get_db

user_last_command = defaultdict(float)
daily_sent = defaultdict(float)
daily_received = defaultdict(float)

async def anti_flood(user_id, cooldown=1):
    now = asyncio.get_event_loop().time()
    if now - user_last_command[user_id] < cooldown:
        return False
    user_last_command[user_id] = now
    return True

def get_daily_key(user_id):
    return f"{user_id}_{datetime.now().date().isoformat()}"

def check_transfer_limit(user_id, amount):
    """Проверяет лимиты и комиссию для перевода"""
    key = get_daily_key(user_id)
    sent_today = daily_sent[key]
    
    if sent_today + amount <= 5000:
        return 0, amount
    elif sent_today + amount <= 25000:
        fee = amount * 0.13
        return fee, amount - fee
    else:
        fee = amount * 0.25
        return fee, amount - fee

def check_receive_limit(user_id, amount):
    """Проверяет лимиты и комиссию для получения"""
    key = get_daily_key(user_id)
    received_today = daily_received[key]
    
    if received_today + amount <= 10000:
        return 0, amount
    elif received_today + amount <= 50000:
        fee = amount * 0.20
        return fee, amount - fee
    else:
        fee = amount * 0.50
        return fee, amount - fee

def can_get_bonus(user_id):
    user = get_user(user_id)
    if user['balance'] > 50000:
        return False, "Баланс превышает 50 000₽"
    
    if user['last_bonus']:
        last = datetime.fromisoformat(user['last_bonus'])
        if datetime.now() - last < timedelta(days=1):
            return False, "Бонус можно получить раз в 24 часа"
    
    return True, ""

def reset_inactive_users(days):
    """Сбрасывает баланс неактивных пользователей"""
    cutoff = datetime.now() - timedelta(days=days)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET balance = 0 
            WHERE last_active < ? AND balance > 0
        ''', (cutoff.isoformat(),))
        conn.commit()
        return cursor.rowcount
