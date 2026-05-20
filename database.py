# database.py
import sqlite3
import threading
from datetime import datetime

# ========== БЛОКИРОВКА ДЛЯ ПОТОКОВ ==========
db_lock = threading.Lock()


def get_db():
    """Создаёт новое соединение с БД"""
    conn = sqlite3.connect('casino_bot.db', timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Инициализация базы данных: создание всех таблиц"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0,
                gold REAL DEFAULT 0,
                last_bonus TEXT,
                anon_seller INTEGER DEFAULT 0,
                registered_at TEXT,
                last_active TEXT
            )
        ''')
        
        # Таблица транзакций (логи)
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
        
        # Таблица логов пользователей (расширенная)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                action TEXT,
                amount_rub REAL DEFAULT 0,
                amount_gold REAL DEFAULT 0,
                target_id INTEGER,
                timestamp TEXT
            )
        ''')
        
        # Таблица дневных лимитов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_limits (
                user_id INTEGER,
                date TEXT,
                sent_amount REAL DEFAULT 0,
                received_amount REAL DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
        ''')
        
        # Таблица аукциона золота
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gold_auction (
                lot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER,
                amount REAL,
                price REAL,
                anonymous INTEGER DEFAULT 0,
                created_at TEXT,
                active INTEGER DEFAULT 1
            )
        ''')
        
        # Создаём индексы для ускорения запросов
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_logs_user_id ON user_logs(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_logs_timestamp ON user_logs(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gold_auction_active ON gold_auction(active)')
        
        conn.commit()


# ========== ПОЛЬЗОВАТЕЛИ ==========

def get_user(user_id):
    """Получает пользователя по ID, создаёт если не существует"""
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


def get_user_by_username(username):
    """Ищет пользователя по юзернейму (без @)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username.lower(),))
        return cursor.fetchone()


def get_user_by_id_or_username(identifier: str):
    """
    Преобразует @username или число (user_id) в user_id
    Возвращает (user_id, user_dict) или (None, None)
    """
    identifier = identifier.strip().lstrip('@')
    
    # Если число — ищем по ID
    if identifier.isdigit():
        user_id = int(identifier)
        user = get_user(user_id)
        if user:
            return user_id, user
        return None, None
    
    # Ищем по username
    user = get_user_by_username(identifier)
    if user:
        return user['user_id'], user
    
    return None, None


def update_username(user_id, username):
    """Обновляет username пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET username = ? WHERE user_id = ?', 
                      (username.lower() if username else None, user_id))
        conn.commit()


def update_last_active(user_id):
    """Обновляет время последней активности"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET last_active = ? WHERE user_id = ?', 
                      (datetime.now().isoformat(), user_id))
        conn.commit()


# ========== БАЛАНС ==========

def update_balance(user_id, amount):
    """Обновляет баланс пользователя, возвращает новый баланс"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
        return get_user(user_id)['balance']


def get_balance(user_id):
    """Возвращает баланс пользователя"""
    return get_user(user_id)['balance']


# ========== ЗОЛОТО ==========

def update_gold(user_id, amount):
    """Обновляет количество золота, возвращает новое количество"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET gold = gold + ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
        return get_user(user_id)['gold']


def get_gold(user_id):
    """Возвращает количество золота"""
    return get_user(user_id)['gold']


# ========== ТРАНЗАКЦИИ (ЛОГИ) ==========

def add_transaction(user_id, tx_type, amount, fee, target_id=None):
    """Добавляет запись о транзакции"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (user_id, type, amount, fee, target_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, tx_type, amount, fee, target_id, datetime.now().isoformat()))
        conn.commit()


def get_user_transactions(user_id, limit=50):
    """Получает последние транзакции пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM transactions 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, limit))
        return cursor.fetchall()


# ========== РАСШИРЕННЫЕ ЛОГИ ПОЛЬЗОВАТЕЛЕЙ ==========

def add_user_log(user_id, username, action, amount_rub=0, amount_gold=0, target_id=None):
    """Добавляет запись в расширенный лог пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_logs (user_id, username, action, amount_rub, amount_gold, target_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, action, amount_rub, amount_gold, target_id, datetime.now().isoformat()))
        conn.commit()


def get_user_logs(user_id, limit=50):
    """Получает последние логи пользователя"""
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
    """Получает последние логи всех пользователей"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM user_logs 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (limit,))
        return cursor.fetchall()


# ========== БОНУСЫ ==========

def set_bonus_time(user_id):
    """Записывает время получения бонуса"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET last_bonus = ? WHERE user_id = ?', 
                      (datetime.now().isoformat(), user_id))
        conn.commit()


def get_bonus_time(user_id):
    """Возвращает время последнего бонуса"""
    user = get_user(user_id)
    return user['last_bonus']


# ========== АНОНИМНОСТЬ ==========

def set_anon_seller(user_id, anon: bool):
    """Устанавливает режим анонимности продавца"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET anon_seller = ? WHERE user_id = ?', (1 if anon else 0, user_id))
        conn.commit()


def is_anon_seller(user_id):
    """Проверяет, включена ли анонимность у продавца"""
    user = get_user(user_id)
    return user['anon_seller'] == 1


# ========== ДНЕВНЫЕ ЛИМИТЫ ==========

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


# ========== ЗОЛОТО - АУКЦИОН ==========

def add_auction_lot(seller_id, amount, price, anonymous):
    """Добавляет лот на аукцион, возвращает lot_id"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO gold_auction (seller_id, amount, price, anonymous, created_at, active)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (seller_id, amount, price, 1 if anonymous else 0, datetime.now().isoformat()))
        lot_id = cursor.lastrowid
        conn.commit()
        return lot_id


def get_active_lots():
    """Возвращает все активные лоты"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM gold_auction 
            WHERE active = 1 
            ORDER BY created_at DESC
        ''')
        return cursor.fetchall()


def get_lot(lot_id):
    """Возвращает лот по ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM gold_auction WHERE lot_id = ?', (lot_id,))
        return cursor.fetchone()


def close_lot(lot_id):
    """Закрывает лот (помечает как проданный)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE gold_auction SET active = 0 WHERE lot_id = ?', (lot_id,))
        conn.commit()


def get_free_gold():
    """Возвращает количество свободного золота на сервере"""
    from config import TOTAL_GOLD
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(amount) as total FROM gold_auction WHERE active = 1')
        auction_gold = cursor.fetchone()['total'] or 0
        
        cursor.execute('SELECT SUM(gold) as total FROM users')
        user_gold = cursor.fetchone()['total'] or 0
    
    return TOTAL_GOLD - auction_gold - user_gold


# ========== СТАТИСТИКА ==========

def get_total_balance():
    """Возвращает общую сумму денег у всех игроков"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(balance) FROM users')
        return cursor.fetchone()[0] or 0


def get_players_stats():
    """Возвращает статистику игроков (всего, активных за 7 дней, неактивных)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        total = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE julianday("now") - julianday(last_active) <= 7')
        active = cursor.fetchone()[0]
        
        return total, active, total - active


def get_top_players(limit=10):
    """Возвращает топ богатейших игроков"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, username, balance FROM users 
            ORDER BY balance DESC 
            LIMIT ?
        ''', (limit,))
        return cursor.fetchall()
