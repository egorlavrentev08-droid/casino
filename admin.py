# admin.py
from aiogram import types
from aiogram.filters import Command
from config import ADMIN_ID
from database import get_db, update_balance, add_transaction, get_user
from utils import reset_inactive_users

def register_admin(dp):
    
    @dp.message(Command("balic"))
    async def cmd_balic(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT SUM(balance) FROM users')
            total = cursor.fetchone()[0] or 0
        await message.answer(f"💰 Общая сумма: {total:.2f}₽")
    
    @dp.message(Command("players"))
    async def cmd_players(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            total = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM users WHERE julianday("now") - julianday(last_active) <= 7')
            active = cursor.fetchone()[0]
        await message.answer(f"👥 Всего: {total}\n🟢 Активных: {active}\n🔴 Неактивных: {total - active}")
    
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
            cursor.execute('SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT ?', (n,))
            top = cursor.fetchall()
        text = f"🏆 Топ {n}:\n\n"
        for i, row in enumerate(top, 1):
            text += f"{i}. `{row['user_id']}` — {row['balance']:.2f}₽\n"
        await message.answer(text, parse_mode="Markdown")
    
    @dp.message(Command("give"))
    async def cmd_give(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            target_id = int(parts[1])
            amount = float(parts[2])
            new_balance = update_balance(target_id, amount)
            add_transaction(target_id, "admin_give", amount, 0, ADMIN_ID)
            await message.answer(f"✅ Выдано {amount:.2f}₽ пользователю `{target_id}`", parse_mode="Markdown")
        except:
            await message.answer("❌ /give [user_id] [сумма]")
    
    @dp.message(Command("take"))
    async def cmd_take(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            target_id = int(parts[1])
            amount = float(parts[2])
            new_balance = update_balance(target_id, -amount)
            add_transaction(target_id, "admin_take", -amount, 0, ADMIN_ID)
            await message.answer(f"✅ Забрано {amount:.2f}₽ у `{target_id}`", parse_mode="Markdown")
        except:
            await message.answer("❌ /take [user_id] [сумма]")
    
    @dp.message(Command("reset"))
    async def cmd_reset(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            target_id = int(message.text.split()[1])
            user = get_user(target_id)
            update_balance(target_id, -user['balance'])
            add_transaction(target_id, "admin_reset", 0, 0, ADMIN_ID)
            await message.answer(f"✅ Баланс `{target_id}` сброшен", parse_mode="Markdown")
        except:
            await message.answer("❌ /reset [user_id]")
    
    @dp.message(Command("log"))
    async def cmd_log(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            target_id = int(message.text.split()[1])
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20', (target_id,))
                logs = cursor.fetchall()
            if not logs:
                await message.answer(f"Нет действий у `{target_id}`", parse_mode="Markdown")
                return
            text = f"📋 Логи `{target_id}`:\n\n"
            for log in logs:
                text += f"🕐 {log['timestamp'][:19]} | {log['type']}"
                if log['amount'] != 0:
                    text += f" | {log['amount']:.2f}₽"
                if log['fee'] > 0:
                    text += f" | комиссия {log['fee']:.2f}₽"
                text += "\n"
            await message.answer(text[:4000], parse_mode="Markdown")
        except:
            await message.answer("❌ /log [user_id]")
    
    @dp.message(Command("resetinactive"))
    async def cmd_reset_inactive(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            arg = message.text.split()[1].lower()
            if arg in ["день", "day"]:
                days = 1
            elif arg in ["неделя", "week"]:
                days = 7
            elif arg in ["месяц", "month"]:
                days = 30
            elif arg.startswith("х") or arg.startswith("x"):
                days = int(arg[1:])
            else:
                await message.answer("❌ /resetinactive [день/неделя/месяц/х7]")
                return
            count = reset_inactive_users(days)
            await message.answer(f"✅ Сброшено {count} неактивных игроков (> {days} дней)")
        except:
            await message.answer("❌ /resetinactive [день/неделя/месяц/х7]")
