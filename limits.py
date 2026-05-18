# limits.py
from datetime import datetime
from database import get_db

def get_daily_key(user_id):
    return f"{user_id}_{datetime.now().date().isoformat()}"

def check_transfer_limit(user_id, amount):
    today = datetime.now().date().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT sent_amount FROM daily_limits 
            WHERE user_id = ? AND date = ?
        ''', (user_id, today))
        row = cursor.fetchone()
        sent_today = row['sent_amount'] if row else 0
    
    if sent_today + amount <= 5000:
        fee = 0
        final = amount
    elif sent_today + amount <= 25000:
        fee = amount * 0.13
        final = amount - fee
    else:
        fee = amount * 0.25
        final = amount - fee
    
    # Обновляем лимит
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO daily_limits (user_id, date, sent_amount)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
            sent_amount = sent_amount + ?
        ''', (user_id, today, amount, amount))
        conn.commit()
    
    return fee, final

def check_receive_limit(user_id, amount):
    today = datetime.now().date().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT received_amount FROM daily_limits 
            WHERE user_id = ? AND date = ?
        ''', (user_id, today))
        row = cursor.fetchone()
        received_today = row['received_amount'] if row else 0
    
    if received_today + amount <= 10000:
        fee = 0
        final = amount
    elif received_today + amount <= 50000:
        fee = amount * 0.20
        final = amount - fee
    else:
        fee = amount * 0.50
        final = amount - fee
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO daily_limits (user_id, date, received_amount)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
            received_amount = received_amount + ?
        ''', (user_id, today, amount, amount))
        conn.commit()
    
    return fee, final
