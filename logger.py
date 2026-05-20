# logger.py
import sqlite3
from datetime import datetime
from database import get_db


def log_action(user_id, username, action, amount_rub=0, amount_gold=0, target_id=None, item=None):
    """Логирование действий пользователя"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO transactions (user_id, type, amount, fee, target_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, action, amount_rub, amount_gold, target_id, datetime.now().isoformat()))
            conn.commit()
            
            # Также логируем username в таблицу users_log если нужно
            cursor.execute('''
                INSERT INTO user_logs (user_id, username, action, amount_rub, amount_gold, target_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, action, amount_rub, amount_gold, target_id, datetime.now().isoformat()))
            conn.commit()
    except Exception as e:
        print(f"⚠️ Ошибка логирования: {e}")


def get_user_logs(user_id, limit=50):
    """Получить логи пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM user_logs 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, limit))
        return cursor.fetchall()


def get_all_logs(limit=100):
    """Получить последние логи всех пользователей"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM user_logs 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (limit,))
        return cursor.fetchall()
