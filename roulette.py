# roulette.py
import asyncio
import random
from datetime import datetime
from aiogram import types
from aiogram.filters import Command
from aiogram.types import FSInputFile

from config import MIN_BET, ROULETTE_RTP
from database import get_user, update_balance, add_transaction, update_last_active, get_db
from utils import anti_flood


# ========== КОНСТАНТЫ РУЛЕТКИ ==========
# Красные числа (европейская рулетка)
RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
BLACK_NUMBERS = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}


def get_roulette_result():
    """
    Возвращает (номер, цвет)
    Шанс каждого числа: 1/37
    """
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


def check_roulette_win(num, color, bet_type, bet_value):
    """Проверяет выигрыш и возвращает (win, multiplier)"""
    
    if bet_type == 'color':
        if bet_value == 'green':
            return (color == 'green', 35)
        return (color == bet_value, 2)
    
    elif bet_type == 'number':
        return (num == bet_value, 35)
    
    elif bet_type == 'range':
        start, end = bet_value
        return (start <= num <= end, 3)
    
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
            return '🔴 КРАСНОЕ'
        elif bet_value == 'black':
            return '⚫️ ЧЁРНОЕ'
        else:
            return '🟢 ЗЕЛЁНЫЙ (0)'
    elif bet_type == 'number':
        return f'🔢 ЧИСЛО {bet_value}'
    elif bet_type == 'range':
        return f'📊 ДИАПАЗОН {bet_value[0]}-{bet_value[1]}'
    elif bet_type == 'parity':
        return '✅ ЧЁТНОЕ' if bet_value == 'even' else '❌ НЕЧЁТНОЕ'
    elif bet_type == 'half':
        return '📉 1-18' if bet_value == 'low' else '📈 19-36'
    return '❓ НЕИЗВЕСТНО'


# ========== ОСНОВНАЯ ФУНКЦИЯ РУЛЕТКИ ==========
async def roulette_game(message: types.Message, bet: float, bet_type, bet_value):
    """Запускает игру в рулетку с гифкой"""
    
    user_id = message.from_user.id
    
    # Получаем результат
    win_num, win_color = get_roulette_result()
    
    # Описание ставки
    bet_desc = get_bet_description(bet_type, bet_value)
    
    # Отправляем гифку
    gif_path = "gifs/roulette_spin.gif"
    
    try:
        gif = FSInputFile(gif_path)
        gif_msg = await message.answer_animation(
            animation=gif,
            caption=f"🎡 **КРУТИМ РУЛЕТКУ**\n\n"
                   f"💰 Ставка: {bet:.2f}₽\n"
                   f"🎲 Ставка на: {bet_desc}\n\n"
                   f"⏳ Результат через несколько секунд...",
            parse_mode="Markdown"
        )
    except FileNotFoundError:
        await message.answer(
            f"❌ **Ошибка:** Гифка не найдена!\n"
            f"📁 Поместите файл `roulette_spin.gif` в папку `gifs/`",
            parse_mode="Markdown"
        )
        # Возвращаем ставку
        update_balance(user_id, bet)
        return
    
    # Ждём 5-11 секунд (рандомно)
    wait_time = random.uniform(5, 11)
    await asyncio.sleep(wait_time)
    
    # Удаляем сообщение с гифкой
    try:
        await gif_msg.delete()
    except:
        pass
    
    # Эмодзи для цвета
    color_emoji = {
        'red': '🔴',
        'black': '⚫️',
        'green': '🟢'
    }
    
    # Проверяем выигрыш
    is_win, fair_multiplier = check_roulette_win(win_num, win_color, bet_type, bet_value)
    
    if is_win:
        multiplier = fair_multiplier  # RTP уже учтён в настройках
        win_amount = bet * multiplier
        new_balance = update_balance(user_id, win_amount)
        add_transaction(user_id, "roulette_win", win_amount, 0)
        
        result_text = (
            f"🎉 **ПОБЕДА!** 🎉\n\n"
            f"{color_emoji[win_color]} **Выпало:** {win_num} ({win_color.upper()})\n"
            f"🎲 Ставка на: {bet_desc}\n"
            f"📈 Множитель: x{multiplier}\n"
            f"💰 Выигрыш: {win_amount:.2f}₽\n\n"
            f"💳 Новый баланс: {new_balance:.2f}₽"
        )
    else:
        result_text = (
            f"❌ **ПРОИГРЫШ** ❌\n\n"
            f"{color_emoji[win_color]} **Выпало:** {win_num} ({win_color.upper()})\n"
            f"🎲 Ставка на: {bet_desc}\n"
            f"💸 Проигрыш: {bet:.2f}₽"
        )
    
    await message.answer(result_text, parse_mode="Markdown")
    
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
                    "🔢 На число: `/roulette 7 500`\n"
                    "📊 На диапазон: `/roulette 4-9 1000`\n"
                    "✅ На чёт/нечет: `/roulette even 500`\n"
                    "📉 На 1-18: `/roulette 1-18 500`\n"
                    "📈 На 19-36: `/roulette 19-36 500`\n\n"
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
                    "`/roulette 4-9 1000`\n"
                    "`/roulette even 500`",
                    parse_mode="Markdown"
                )
                return
            
            bet_type, bet_value = parsed
            
            # Проверка баланса
            user = get_user(user_id)
            if user['balance'] < bet:
                await message.answer(
                    f"❌ **Недостаточно средств**\n"
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
