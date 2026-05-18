# admin.py
from aiogram import types
from aiogram.filters import Command
from config import ADMIN_ID
from database import get_db, update_balance, add_transaction, get_user, update_gold
from utils import reset_inactive_users


def get_user_id_by_mention(mention: str) -> int:
    """
    Преобразует @username или число (user_id) в user_id
    """
    mention = mention.strip().lstrip('@')
    
    if mention.isdigit():
        return int(mention)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE username = ?', (mention.lower(),))
        row = cursor.fetchone()
        if row:
            return row['user_id']
    
    return None


def register_admin(dp):
    
    # ===== ОБЩАЯ СУММА ДЕНЕГ =====
    @dp.message(Command("balic"))
    async def cmd_balic(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            await message.answer("❌ Доступ запрещён")
            return
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT SUM(balance) FROM users')
            total = cursor.fetchone()[0] or 0
        await message.answer(f"💰 Общая сумма: {total:.2f}₽")
    
    # ===== СТАТИСТИКА ИГРОКОВ =====
    @dp.message(Command("players"))
    async def cmd_players(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            await message.answer("❌ Доступ запрещён")
            return
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            total = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM users WHERE julianday("now") - julianday(last_active) <= 7')
            active = cursor.fetchone()[0]
        await message.answer(
            f"📊 **Статистика**\n\n👥 Всего: {total}\n🟢 Активных: {active}\n🔴 Неактивных: {total - active}",
            parse_mode="Markdown"
        )
    
    # ===== ТОП БОГАТЕЙШИХ =====
    @dp.message(Command("top"))
    async def cmd_top(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            await message.answer("❌ Доступ запрещён")
            return
        try:
            n = int(message.text.split()[1])
            if n > 100:
                n = 100
        except:
            n = 10
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, username, balance FROM users ORDER BY balance DESC LIMIT ?', (n,))
            top = cursor.fetchall()
        text = f"🏆 **Топ {n}** 🏆\n\n"
        for i, row in enumerate(top, 1):
            name = f"@{row['username']}" if row['username'] else f"`{row['user_id']}`"
            text += f"{i}. {name} — {row['balance']:.2f}₽\n"
        await message.answer(text, parse_mode="Markdown")
    
    # ===== ВЫДАЧА РУБЛЕЙ =====
    @dp.message(Command("give"))
    async def cmd_give(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            if len(parts) < 3:
                await message.answer("❌ /give [@username или id] [сумма]")
                return
            target = parts[1]
            amount = float(parts[2])
            target_id = get_user_id_by_mention(target)
            if not target_id:
                await message.answer(f"❌ {target} не найден")
                return
            new_balance = update_balance(target_id, amount)
            add_transaction(target_id, "admin_give", amount, 0, ADMIN_ID)
            await message.answer(f"✅ Выдано {amount:.2f}₽ пользователю {target}. Новый баланс: {new_balance:.2f}₽")
        except:
            await message.answer("❌ /give [@username] [сумма]")
    
    # ===== ЗАБОР РУБЛЕЙ =====
    @dp.message(Command("take"))
    async def cmd_take(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            if len(parts) < 3:
                await message.answer("❌ /take [@username или id] [сумма]")
                return
            target = parts[1]
            amount = float(parts[2])
            target_id = get_user_id_by_mention(target)
            if not target_id:
                await message.answer(f"❌ {target} не найден")
                return
            user = get_user(target_id)
            if user['balance'] < amount:
                await message.answer(f"❌ У {target} только {user['balance']:.2f}₽")
                return
            new_balance = update_balance(target_id, -amount)
            add_transaction(target_id, "admin_take", -amount, 0, ADMIN_ID)
            await message.answer(f"✅ Забрано {amount:.2f}₽ у {target}. Новый баланс: {new_balance:.2f}₽")
        except:
            await message.answer("❌ /take [@username] [сумма]")
    
    # ===== ВЫДАЧА ЗОЛОТА =====
    @dp.message(Command("ggive"))
    async def cmd_ggive(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            if len(parts) < 3:
                await message.answer("❌ /ggive [@username или id] [количество]")
                return
            target = parts[1]
            amount = float(parts[2])
            target_id = get_user_id_by_mention(target)
            if not target_id:
                await message.answer(f"❌ {target} не найден")
                return
            update_gold(target_id, amount)
            add_transaction(target_id, "admin_ggive", amount, 0, ADMIN_ID)
            user = get_user(target_id)
            await message.answer(f"✅ Выдано {amount:.2f} г золота {target}. Всего: {user['gold']:.2f} г")
        except:
            await message.answer("❌ /ggive [@username] [количество]")
    
    # ===== ЗАБОР ЗОЛОТА =====
    @dp.message(Command("gtake"))
    async def cmd_gtake(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            if len(parts) < 3:
                await message.answer("❌ /gtake [@username или id] [количество]")
                return
            target = parts[1]
            amount = float(parts[2])
            target_id = get_user_id_by_mention(target)
            if not target_id:
                await message.answer(f"❌ {target} не найден")
                return
            user = get_user(target_id)
            if user['gold'] < amount:
                await message.answer(f"❌ У {target} только {user['gold']:.2f} г")
                return
            update_gold(target_id, -amount)
            add_transaction(target_id, "admin_gtake", -amount, 0, ADMIN_ID)
            user_after = get_user(target_id)
            await message.answer(f"✅ Забрано {amount:.2f} г у {target}. Осталось: {user_after['gold']:.2f} г")
        except:
            await message.answer("❌ /gtake [@username] [количество]")
    
    # ===== СБРОС ИГРОКА =====
    @dp.message(Command("reset"))
    async def cmd_reset(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer("❌ /reset [@username или id]")
                return
            target = parts[1]
            target_id = get_user_id_by_mention(target)
            if not target_id:
                await message.answer(f"❌ {target} не найден")
                return
            user = get_user(target_id)
            update_balance(target_id, -user['balance'])
            add_transaction(target_id, "admin_reset", 0, 0, ADMIN_ID)
            await message.answer(f"✅ Баланс {target} сброшен до 0₽")
        except:
            await message.answer("❌ /reset [@username]")
    
    # ===== ЛОГИ ИГРОКА =====
    @dp.message(Command("log"))
    async def cmd_log(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer("❌ /log [@username или id]")
                return
            target = parts[1]
            target_id = get_user_id_by_mention(target)
            if not target_id:
                await message.answer(f"❌ {target} не найден")
                return
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20', (target_id,))
                logs = cursor.fetchall()
            if not logs:
                await message.answer(f"📋 Нет действий у {target}")
                return
            text = f"📋 **Логи {target}** (20):\n\n"
            for log in logs:
                text += f"🕐 {log['timestamp'][:19]} | {log['type']}"
                if log['amount'] != 0:
                    text += f" | {log['amount']:.2f}"
                    if 'gold' in log['type']:
                        text += " г"
                    else:
                        text += "₽"
                if log['fee'] > 0:
                    text += f" | комиссия {log['fee']:.2f}₽"
                text += "\n"
            await message.answer(text[:4000])
        except:
            await message.answer("❌ /log [@username]")
    
    # ===== СБРОС НЕАКТИВНЫХ =====
    @dp.message(Command("resetinactive"))
    async def cmd_reset_inactive(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer("❌ /resetinactive [день/неделя/месяц/х7]")
                return
            arg = parts[1].lower()
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
