# roulette.py
import asyncio
import random
from datetime import datetime
from aiogram import types
from aiogram.filters import Command
from aiogram.types import FSInputFile

from config import MIN_BET
from database import get_user, update_balance, add_transaction, update_last_active, get_db
from utils import anti_flood


# ========== КОНСТАНТЫ РУЛЕТКИ ==========
RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
BLACK_NUMBERS = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}


def get_roulette_result():
    """Возвращает (номер, цвет) с честными вероятностями 1/37"""
    num = random.randint(0, 36)
    if num == 0:
        color = 'green'
    elif num in RED_NUMBERS:
        color = 'red'
    else:
        color = 'black'
    return num, color


def parse_roulette_bet(bet_str):
    """Парсит ставку: цвет, число, диапазон, чёт/нечет, 1-18/19-36"""
    bet_str = bet_str.lower().strip()
    
    # Цвета
    if bet_str in ['black', 'чёрный', 'черный']:
        return ('color', 'black')
    if bet_str in ['red', 'красный']:
        return ('color', 'red')
    if bet_str in ['green', 'зеленый', 'зелёный', '0']:
        return ('color', 'green')
    
    # Одно число
    try:
        num = int(bet_str)
        if 0 <= num <= 36:
            return ('number', num)
    except:
        pass
    
    # Диапазон (например 4-9)
    if '-' in bet_str:
        try:
            parts = bet_str.split('-')
            start = int(parts[0])
            end = int(parts[1])
            if 0 <= start <= 36 and 0 <= end <= 36 and start < end:
                count = end - start + 1
                if count <= 30:  # Максимум 30 чисел в диапазоне
                    return ('range', (start, end))
        except:
            pass
    
    # Чёт/нечет
    if bet_str in ['even', 'чёт', 'чет']:
        return ('parity', 'even')
    if bet_str in ['odd', 'нечет', 'нечёт']:
        return ('parity', 'odd')
    
    # 1-18 / 19-36
    if bet_str in ['1-18', 'low', 'меньше']:
        return ('half', 'low')
    if bet_str in ['19-36', 'high', 'больше']:
        return ('half', 'high')
    
    return None


def get_range_multiplier(start, end):
    """Рассчитывает множитель для диапазона"""
    count = end - start + 1
    
    # Таблица множителей для диапазонов
    multipliers = {
        1: 32.0,
        2: 16.0,
        3: 10.67,
        4: 8.0,
        5: 6.4,
        6: 5.33,
        7: 4.57,
        8: 4.0,
        9: 3.56,
        10: 3.2,
        11: 2.91,
        12: 2.67,
        13: 2.46,
        14: 2.29,
        15: 2.13,
        16: 2.0,
        17: 1.88,
        18: 1.78,
        19: 1.68,
        20: 1.6,
        21: 1.52,
        22: 1.45,
        23: 1.39,
        24: 1.33,
        25: 1.28,
        26: 1.23,
        27: 1.19,
        28: 1.14,
        29: 1.10,
        30: 1.07,
    }
    
    return multipliers.get(count, 1.0)


def check_roulette_win(num, color, bet_type, bet_value):
    """Проверяет выигрыш и возвращает (is_win, multiplier)"""
    if bet_type == 'color':
        if bet_value == 'green':
            return (color == 'green', 35)
        return (color == bet_value, 2)
    
    elif bet_type == 'number':
        return (num == bet_value, 32)
    
    elif bet_type == 'range':
        start, end = bet_value
        is_win = start <= num <= end
        multiplier = get_range_multiplier(start, end)
        return (is_win, multiplier)
    
    elif bet_type == 'parity':
        if bet_value == 'even':
            return (num != 0 and num % 2 == 0, 2)
        else:
            return (num != 0 and num % 2 == 1, 2)
    
    elif bet_type == 'half':
        if bet_value == 'low':
            return (1 <= num <= 18, 2)
        else:
            return (19 <= num <= 36, 2)
    
    return (False, 0)


def get_bet_description(bet_type, bet_value):
    """Возвращает текстовое описание ставки"""
    if bet_type == 'color':
        if bet_value == 'red':
            return '🔴 КРАСНОЕ (x2)'
        elif bet_value == 'black':
            return '⚫️ ЧЁРНОЕ (x2)'
        else:
            return '🟢 ЗЕЛЁНЫЙ (0) (x35)'
    elif bet_type == 'number':
        return f'🔢 ЧИСЛО {bet_value} (x32)'
    elif bet_type == 'range':
        start, end = bet_value
        count = end - start + 1
        mult = get_range_multiplier(start, end)
        return f'📊 ДИАПАЗОН {start}-{end} ({count} чисел, x{mult:.2f})'
    elif bet_type == 'parity':
        return '✅ ЧЁТНОЕ (x2)' if bet_value == 'even' else '❌ НЕЧЁТНОЕ (x2)'
    elif bet_type == 'half':
        return '📉 1-18 (x2)' if bet_value == 'low' else '📈 19-36 (x2)'
    return '❓ НЕИЗВЕСТНО'


def get_color_emoji(color):
    """Возвращает эмодзи для цвета"""
    emojis = {
        'red': '🔴',
        'black': '⚫️',
        'green': '🟢'
    }
    return emojis.get(color, '❓')


# ========== ОСНОВНАЯ ФУНКЦИЯ РУЛЕТКИ ==========
async def roulette_game(message: types.Message, bet: float, bet_type, bet_value):
    """Запускает игру в рулетку"""
    
    user_id = message.from_user.id
    
    # Получаем результат
    win_num, win_color = get_roulette_result()
    
    # Описание ставки
    bet_desc = get_bet_description(bet_type, bet_value)
    
    # Отправляем начальное сообщение
    msg = await message.answer(
        f"🎡 **КРУТИМ РУЛЕТКУ**\n\n"
        f"💰 Ставка: {bet:.2f}₽\n"
        f"🎲 Ставка на: {bet_desc}\n\n"
        f"⏳ Результат через несколько секунд...",
        parse_mode="Markdown"
    )
    
    # Ждём 3-5 секунд
    wait_time = random.uniform(3, 5)
    await asyncio.sleep(wait_time)
    
    # Проверяем выигрыш
    is_win, multiplier = check_roulette_win(win_num, win_color, bet_type, bet_value)
    
    color_emoji = get_color_emoji(win_color)
    
    if is_win:
        win_amount = bet * multiplier
        new_balance = update_balance(user_id, win_amount)
        add_transaction(user_id, "roulette_win", win_amount, 0)
        
        result_text = (
            f"🎉 **ПОБЕДА!** 🎉\n\n"
            f"{color_emoji} **Выпало:** {win_num} ({win_color.upper()})\n"
            f"🎲 Ставка на: {bet_desc}\n"
            f"📈 Множитель: x{multiplier:.2f}\n"
            f"💰 Выигрыш: {win_amount:.2f}₽\n\n"
            f"💳 Новый баланс: {new_balance:.2f}₽"
        )
    else:
        result_text = (
            f"❌ **ПРОИГРЫШ** ❌\n\n"
            f"{color_emoji} **Выпало:** {win_num} ({win_color.upper()})\n"
            f"🎲 Ставка на: {bet_desc}\n"
            f"💸 Проигрыш: {bet:.2f}₽"
        )
    
    await msg.edit_text(result_text, parse_mode="Markdown")
    
    # Логируем
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (user_id, type, amount, fee, target_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, "roulette_spin", bet, 0, win_num, datetime.now().isoformat()))
        conn.commit()


# ========== КОМАНДА РУЛЕТКИ ==========
def register_roulette(dp):
    
    @dp.message(Command("roulette"))
    async def cmd_roulette(message: types.Message):
        user_id = message.from_user.id
        update_last_active(user_id)
        
        # Защита от флуда
        if not await anti_flood(user_id, cooldown=2):
            await message.answer("⏳ Слишком часто! Подожди пару секунд.", parse_mode="Markdown")
            return
        
        try:
            parts = message.text.split()
            if len(parts) < 3:
                await message.answer(
                    "❌ **Использование:** `/roulette [ставка] [сумма]`\n\n"
                    "**Примеры:**\n"
                    "🎨 На цвет: `/roulette red 1000`\n"
                    "🔢 На число: `/roulette 7 500` (x32)\n"
                    "📊 На диапазон: `/roulette 4-9 1000` (макс 30 чисел)\n"
                    "✅ На чёт/нечет: `/roulette even 500` (x2)\n"
                    "📉 На 1-18: `/roulette 1-18 500` (x2)\n"
                    "📈 На 19-36: `/roulette 19-36 500` (x2)\n\n"
                    f"💰 Минимальная ставка: {MIN_BET}₽",
                    parse_mode="Markdown"
                )
                return
            
            # Парсим ставку
            bet = float(parts[-1])
            bet_str = ' '.join(parts[1:-1])
            parsed = parse_roulette_bet(bet_str)
            
            if bet < MIN_BET:
                await message.answer(f"❌ Минимальная ставка: {MIN_BET}₽", parse_mode="Markdown")
                return
            
            if not parsed:
                await message.answer(
                    "❌ **Неверная ставка!**\n\n"
                    "Примеры:\n"
                    "`/roulette red 1000`\n"
                    "`/roulette 7 500`\n"
                    "`/roulette 4-9 1000` (макс 30 чисел)\n"
                    "`/roulette even 500`",
                    parse_mode="Markdown"
                )
                return
            
            bet_type, bet_value = parsed
            
            # Проверка баланса
            user = get_user(user_id)
            if user['balance'] < bet:
                await message.answer(
                    f"❌ **Недостаточно средств**\n\n"
                    f"💰 Ваш баланс: {user['balance']:.2f}₽\n"
                    f"🎲 Требуется: {bet:.2f}₽",
                    parse_mode="Markdown"
                )
                return
            
            # Списываем ставку
            update_balance(user_id, -bet)
            add_transaction(user_id, "roulette_bet", -bet, 0)
            
            # Запускаем игру
            await roulette_game(message, bet, bet_type, bet_value)
            
        except ValueError:
            await message.answer("❌ Неверный формат суммы! Пример: `/roulette red 1000`", parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")
