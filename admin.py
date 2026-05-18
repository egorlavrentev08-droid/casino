# admin.py
from aiogram import types
from aiogram.filters import Command
from database import get_db, update_balance, add_transaction, get_user
from config import ADMIN_ID

def register_admin(dp):
    
    @dp.message(Command("balic"))
    async def cmd_balic(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            await message.answer("❌ Доступ только у админа")
            return
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT SUM(balance) FROM users')
            total = cursor.fetchone()[0] or 0
        
        await message.answer(f"💰 Общая сумма денег у всех игроков: {total:.2f}₽")
    
    @dp.message(Command("players"))
    async def cmd_players(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            await message.answer("❌ Доступ только у админа")
            return
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            total = cursor.fetchone()[0]
            
            cursor.execute('''
                SELECT COUNT(*) FROM users 
                WHERE julianday('now') - julianday(last_active) <= 7
            ''')
            active = cursor.fetchone()[0]
            
            inactive = total - active
        
        await message.answer(
            f"📊 **Статистика игроков**\n\n"
            f"👥 Всего: {total}\n"
            f"🟢 Активных (за 7 дней): {active}\n"
            f"🔴 Неактивных: {inactive}",
            parse_mode="Markdown"
        )
    
    @dp.message(Command("top"))
    async def cmd_top(message: types.Message):
        try:
            n = int(message.text.split()[1])
            if n > 100:
                n = 100
        except:
            n = 10
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, balance FROM users 
                ORDER BY balance DESC 
                LIMIT ?
            ''', (n,))
            top = cursor.fetchall()
        
        text = f"🏆 **Топ {n} богатейших игроков** 🏆\n\n"
        for i, row in enumerate(top, 1):
            text += f"{i}. `{row['user_id']}` — {row['balance']:.2f}₽\n"
        
        await message.answer(text, parse_mode="Markdown")
    
    @dp.message(Command("give"))
    async def cmd_give(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            await message.answer("❌ Доступ только у админа")
            return
        
        try:
            parts = message.text.split()
            target_id = int(parts[1])
            amount = float(parts[2])
            
            new_balance = update_balance(target_id, amount)
            add_transaction(target_id, "admin_give", amount, 0, ADMIN_ID)
            
            await message.answer(f"✅ Выдано {amount:.2f}₽ пользователю `{target_id}`. Новый баланс: {new_balance:.2f}₽",
                                parse_mode="Markdown")
            
            try:
                await message.bot.send_message(target_id, f"💰 Админ выдал вам {amount:.2f}₽!")
            except:
                pass
        except:
            await message.answer("❌ Использование: /give [user_id] [сумма]")
    
    @dp.message(Command("take"))
    async def cmd_take(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            await message.answer("❌ Доступ только у админа")
            return
        
        try:
            parts = message.text.split()
            target_id = int(parts[1])
            amount = float(parts[2])
            
            new_balance = update_balance(target_id, -amount)
            add_transaction(target_id, "admin_take", -amount, 0, ADMIN_ID)
            
            await message.answer(f"✅ Забрано {amount:.2f}₽ у пользователя `{target_id}`. Новый баланс: {new_balance:.2f}₽",
                                parse_mode="Markdown")
        except:
            await message.answer("❌ Использование: /take [user_id] [сумма]")
    
    @dp.message(Command("reset"))
    async def cmd_reset(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            await message.answer("❌ Доступ только у админа")
            return
        
        try:
            target_id = int(message.text.split()[1])
            update_balance(target_id, -get_user(target_id)['balance'])
            add_transaction(target_id, "admin_reset", 0, 0, ADMIN_ID)
            await message.answer(f"✅ Баланс пользователя `{target_id}` сброшен до 0", parse_mode="Markdown")
        except:
            await message.answer("❌ Использование: /reset [user_id]")
    
    @dp.message(Command("log"))
    async def cmd_log(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            await message.answer("❌ Доступ только у админа")
            return
        
        try:
            target_id = int(message.text.split()[1])
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM transactions 
                    WHERE user_id = ? 
                    ORDER BY timestamp DESC 
                    LIMIT 20
                ''', (target_id,))
                logs = cursor.fetchall()
            
            if not logs:
                await message.answer(f"📋 Нет действий у пользователя `{target_id}`", parse_mode="Markdown")
                return
            
            text = f"📋 **Последние 20 действий пользователя `{target_id}`** 📋\n\n"
            for log in logs:
                text += f"🕐 {log['timestamp'][:19]}\n"
                text += f"📌 {log['type']}"
                if log['amount'] != 0:
                    text += f" | {log['amount']:.2f}₽"
                if log['fee'] > 0:
                    text += f" | Комиссия: {log['fee']:.2f}₽"
                if log['target_id']:
                    text += f" | {log['target_id']}"
                text += "\n\n"
            
            await message.answer(text[:4000], parse_mode="Markdown")
        except:
            await message.answer("❌ Использование: /log [user_id]")
    
    @dp.message(Command("resetinactive"))
    async def cmd_reset_inactive(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            await message.answer("❌ Доступ только у админа")
            return
        
        try:
            arg = message.text.split()[1].lower()
            
            # Парсим время
            if arg == "день" or arg == "day":
                days = 1
            elif arg.startswith("х") or arg.startswith("x"):
                days = int(arg[1:])
            elif arg == "неделя" or arg == "week":
                days = 7
            elif arg.startswith("недель") or arg.startswith("week"):
                days = int(arg[6:]) * 7
            elif arg == "месяц" or arg == "month":
                days = 30
            elif arg.startswith("месяц"):
                days = int(arg[5:]) * 30
            else:
                await message.answer("❌ Формат: /resetinactive день / неделя / месяц / х7 / 7дней")
                return
            
            count = reset_inactive_users(days)
            await message.answer(f"✅ Сброшено {count} неактивных игроков (неактивны > {days} дней)")
        except:
            await message.answer("❌ Использование: /resetinactive [день/неделя/месяц/х7]")
