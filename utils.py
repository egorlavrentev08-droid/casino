# utils.py
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from database import get_db, get_user, update_balance, add_transaction


# ========== АНТИФЛУД ==========
user_last_command = defaultdict(float)


async def anti_flood(user_id, cooldown=1):
    """
    Защита от флуда
    Возвращает False, если команду нельзя выполнить (слишком часто)
    """
    now = asyncio.get_event_loop().time()
    if now - user_last_command[user_id] < cooldown:
        return False
    user_last_command[user_id] = now
    return True


# ========== СБРОС НЕАКТИВНЫХ ==========
def reset_inactive_users(days):
    """
    Сбрасывает баланс неактивных пользователей
    Возвращает количество сброшенных пользователей
    """
    cutoff = datetime.now() - timedelta(days=days)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET balance = 0 
            WHERE last_active < ? AND balance > 0
        ''', (cutoff.isoformat(),))
        count = cursor.rowcount
        conn.commit()
        return count


# ========== ФОРМАТИРОВАНИЕ ==========
def format_number(num):
    """Форматирует число с разделителями тысяч"""
    return f"{num:,.0f}".replace(",", " ")


def format_balance(balance):
    """Форматирует баланс с двумя знаками после запятой"""
    return f"{balance:.2f}₽"


def format_gold(gold):
    """Форматирует золото с двумя знаками после запятой"""
    return f"{gold:.2f} г"


# ========== ВРЕМЯ ==========
def time_until_next_bonus(last_bonus):
    """Возвращает строку с временем до следующего бонуса"""
    if not last_bonus:
        return "доступно сейчас"
    
    try:
        last_time = datetime.fromisoformat(last_bonus)
        delta = timedelta(days=1) - (datetime.now() - last_time)
        
        if delta.total_seconds() <= 0:
            return "доступно сейчас"
        
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        
        if delta.days > 0:
            return f"через {delta.days} д {hours} ч"
        elif hours > 0:
            return f"через {hours} ч {minutes} мин"
        else:
            return f"через {minutes} мин"
    except:
        return "доступно сейчас"


# ========== ВАЛИДАЦИЯ ==========
def validate_bet(bet, min_bet, balance):
    """
    Проверяет ставку
    Возвращает (is_valid, error_message)
    """
    if bet < min_bet:
        return False, f"Минимальная ставка: {min_bet}₽"
    
    if bet > balance:
        return False, f"Недостаточно средств! Баланс: {balance:.2f}₽"
    
    return True, None


def validate_mines_count(mines):
    """Проверяет количество мин"""
    if mines < 3 or mines > 24:
        return False, "Количество мин должно быть от 3 до 24"
    return True, None


def validate_roulette_bet(bet_str):
    """Проверяет ставку в рулетке"""
    import re
    bet_str = bet_str.lower().strip()
    
    # Цвета
    if bet_str in ['black', 'чёрный', 'черный', 'red', 'красный', 'green', 'зеленый', 'зелёный']:
        return True, None
    
    # Число
    if bet_str.isdigit() and 0 <= int(bet_str) <= 36:
        return True, None
    
    # Диапазон
    if '-' in bet_str:
        parts = bet_str.split('-')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            if 0 <= int(parts[0]) <= 36 and 0 <= int(parts[1]) <= 36:
                return True, None
    
    # Чёт/нечет
    if bet_str in ['even', 'чёт', 'чет', 'odd', 'нечет', 'нечёт']:
        return True, None
    
    # 1-18 / 19-36
    if bet_str in ['1-18', 'low', 'меньше', '19-36', 'high', 'больше']:
        return True, None
    
    return False, "Неверный формат ставки"


# ========== ГЕНЕРАЦИЯ ==========
def generate_lot_id():
    """Генерирует 5-значный номер лота"""
    import random
    return random.randint(10000, 99999)


def get_emoji_by_color(color):
    """Возвращает эмодзи по цвету рулетки"""
    emojis = {
        'red': '🔴',
        'black': '⚫️',
        'green': '🟢'
    }
    return emojis.get(color, '❓')


# ========== СТАТИСТИКА ==========
def get_player_stats(user_id):
    """Возвращает краткую статистику игрока"""
    user = get_user(user_id)
    
    return {
        'balance': user['balance'],
        'gold': user['gold'],
        'registered_at': user['registered_at'],
        'last_active': user['last_active']
    }


def get_global_stats():
    """Возвращает глобальную статистику"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        total_players = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(balance) FROM users')
        total_balance = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(gold) FROM users')
        total_gold = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE julianday("now") - julianday(last_active) <= 7')
        active_players = cursor.fetchone()[0]
    
    return {
        'total_players': total_players,
        'active_players': active_players,
        'inactive_players': total_players - active_players,
        'total_balance': total_balance,
        'total_gold': total_gold
    }


# ========== ОЧИСТКА ==========
def clear_expired_games(games_dict, max_age_seconds=3600):
    """
    Очищает старые игры (по умолчанию через 1 час)
    """
    now = asyncio.get_event_loop().time()
    expired = []
    
    for user_id, game in games_dict.items():
        if hasattr(game, 'last_update') and now - game.last_update > max_age_seconds:
            expired.append(user_id)
    
    for user_id in expired:
        # Возвращаем ставку, если игра ещё активна
        game = games_dict.get(user_id)
        if game and game.active and hasattr(game, 'bet'):
            update_balance(user_id, game.bet)
            add_transaction(user_id, "game_expired", game.bet, 0)
        del games_dict[user_id]
    
    return len(expired)


# ========== РАБОТА С ЮЗЕРНЕЙМАМИ ==========
def parse_mention(mention: str):
    """Преобразует @username в чистый username (без @)"""
    return mention.strip().lstrip('@').lower()


def is_mention(text: str):
    """Проверяет, является ли строка упоминанием (@username)"""
    return text.startswith('@') and len(text) > 1
