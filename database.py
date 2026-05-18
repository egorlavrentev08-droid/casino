# database.py
import sqlite3
import threading
from datetime import datetime, timedelta

db_lock = threading.Lock()

def get_db():
    conn = sqlite3.connect('casino_bot.db', timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Пользователи
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0,
                gold REAL DEFAULT 0,
                last_bonus TEXT,
                anon_seller INTEGER DEFAULT 0,
                registered_at TEXT,
                last_active TEXT
            )
        ''')
        
        # Транзакции (для логов)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount REAL,
                fee REAL,
                target_id INTEGER,
                timestamp TEXT
            )
        ''')
        
        # Лимиты переводов (дневные)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_limits (
                user_id INTEGER,
                date TEXT,
                sent_amount REAL DEFAULT 0,
                received_amount REAL DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
        ''')
        
        # Аукцион золота
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gold_auction (
                lot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER,
                amount REAL,
                price REAL,  -- цена за 1 грамм
                anonymous INTEGER DEFAULT 0,
                created_at TEXT,
                active INTEGER DEFAULT 1
            )
        ''')
        
        conn.commit()

# ========== ОСНОВНЫЕ ФУНКЦИИ ==========
def get_user(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        if not user:
            now = datetime.now().isoformat()
            cursor.execute('''
                INSERT INTO users (user_id, balance, gold, registered_at, last_active)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, 0, 0, now, now))
            conn.commit()
            return get_user(user_id)
        return user

def update_balance(user_id, amount):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
        return get_user(user_id)['balance']

def update_gold(user_id, amount):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET gold = gold + ? WHERE user_id = ?', (amount, user_id))
        conn.commit()

def add_transaction(user_id, tx_type, amount, fee, target_id=None):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (user_id, type, amount, fee, target_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, tx_type, amount, fee, target_id, datetime.now().isoformat()))
        conn.commit()

def log_action(user_id, action, details):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (user_id, type, amount, fee, target_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, action, 0, 0, details, datetime.now().isoformat()))
        conn.commit()

def update_last_active(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET last_active = ? WHERE user_id = ?', 
                      (datetime.now().isoformat(), user_id))
        conn.commit()
