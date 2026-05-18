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
    
    # Если число — возвращаем как есть
    if mention.isdigit():
        return int(mention)
    
    # Ищем по username в БД
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
            cursor.execute('''
                SELECT user_id, username, balance FROM users 
                ORDER BY balance DESC 
                LIMIT ?
            ''', (n,))
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
                await message.answer("❌ Использование: `/give [@username или id] [сумма]`", parse_mode="Markdown")
                return
            
            target = parts[1]
            amount = float(parts[2])
            
            target_id = get_user_id_by_mention(target)
            if not target_id:
                await message.answer(f"❌ Пользователь {target} не найден в БД\n\n💡 Напишите `/start` перед первой выдачей", parse_mode="Markdown")
                return
            
            new_balance = update_balance(target_id, amount)
            add_transaction(target_id, "admin_give", amount, 0, ADMIN_ID)
            
            await message.answer(
                f"✅ **Выдано {amount:.2f}₽**\n\n"
                f"👤 Пользователь: {target}\n"
                f"💰 Новый баланс: {new_balance:.2f}₽",
                parse_mode="Markdown"
            )
            
            try:
                await message.bot.send_message(
                    target_id,
                    f"💰 **Вам выданы деньги админом!**\n\n"
                    f"➕ +{amount:.2f}₽\n"
                    f"📊 Ваш баланс: {new_balance:.2f}₽",
                    parse_mode="Markdown"
                )
            except:
                pass
                
        except ValueError:
            await message.answer("❌ Сумма должна быть числом", parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")
    
    # ===== ЗАБОР РУБЛЕЙ =====
    @dp.message(Command("take"))
    async def cmd_take(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            if len(parts) < 3:
                await message.answer("❌ Использование: `/take [@username или id] [сумма]`", parse_mode="Markdown")
                return
            
            target = parts[1]
            amount = float(parts[2])
            
            target_id = get_user_id_by_mention(target)
            if not target_id:
                await message.answer(f"❌ Пользователь {target} не найден", parse_mode="Markdown")
                return
            
            user = get_user(target_id)
            if user['balance'] < amount:
                await message.answer(
                    f"❌ **Недостаточно средств**\n\n"
                    f"👤 Пользователь: {target}\n"
                    f"💰 У него: {user['balance']:.2f}₽\n"
                    f"📊 Запрошено: {amount:.2f}₽",
                    parse_mode="Markdown"
                )
                return
            
            new_balance = update_balance(target_id, -amount)
            add_transaction(target_id, "admin_take", -amount, 0, ADMIN_ID)
            
            await message.answer(
                f"✅ **Забрано {amount:.2f}₽**\n\n"
                f"👤 Пользователь: {target}\n"
                f"💰 Новый баланс: {new_balance:.2f}₽",
                parse_mode="Markdown"
            )
            
            try:
                await message.bot.send_message(
                    target_id,
                    f"💰 **У вас забрали деньги админом!**\n\n"
                    f"➖ -{amount:.2f}₽\n"
                    f"📊 Ваш баланс: {new_balance:.2f}₽",
                    parse_mode="Markdown"
                )
            except:
                pass
                
        except ValueError:
            await message.answer("❌ Сумма должна быть числом", parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")
    
    # ===== ВЫДАЧА ЗОЛОТА =====
    @dp.message(Command("ggive"))
    async def cmd_ggive(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            if len(parts) < 3:
                await message.answer("❌ Использование: `/ggive [@username или id] [количество]`", parse_mode="Markdown")
                return
            
            target = parts[1]
            amount = float(parts[2])
            
            target_id = get_user_id_by_mention(target)
            if not target_id:
                await message.answer(f"❌ Пользователь {target} не найден", parse_mode="Markdown")
                return
            
            update_gold(target_id, amount)
            add_transaction(target_id, "admin_ggive", amount, 0, ADMIN_ID)
            
            user = get_user(target_id)
            await message.answer(
                f"✅ **Выдано золото**\n\n"
                f"👤 Пользователь: {target}\n"
                f"🪙 Количество: {amount:.2f} г\n"
                f"📊 Всего золота: {user['gold']:.2f} г",
                parse_mode="Markdown"
            )
            
            try:
                await message.bot.send_message(
                    target_id,
                    f"🪙 **Вам выдано золото админом!**\n\n"
                    f"➕ +{amount:.2f} г\n"
                    f"📊 Ваш баланс золота: {user['gold']:.2f} г",
                    parse_mode="Markdown"
                )
            except:
                pass
                
        except ValueError:
            await message.answer("❌ Количество должно быть числом", parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")
    
    # ===== ЗАБОР ЗОЛОТА =====
    @dp.message(Command("gtake"))
    async def cmd_gtake(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            if len(parts) < 3:
                await message.answer("❌ Использование: `/gtake [@username или id] [количество]`", parse_mode="Markdown")
                return
            
            target = parts[1]
            amount = float(parts[2])
            
            target_id = get_user_id_by_mention(target)
            if not target_id:
                await message.answer(f"❌ Пользователь {target} не найден", parse_mode="Markdown")
                return
            
            user = get_user(target_id)
            if user['gold'] < amount:
                await message.answer(
                    f"❌ **Недостаточно золота**\n\n"
                    f"👤 Пользователь: {target}\n"
                    f"🪙 У него: {user['gold']:.2f} г\n"
                    f"📊 Запрошено: {amount:.2f} г",
                    parse_mode="Markdown"
                )
                return
            
            update_gold(target_id, -amount)
            add_transaction(target_id, "admin_gtake", -amount, 0, ADMIN_ID)
            
            user_after = get_user(target_id)
            await message.answer(
                f"✅ **Забрано золото**\n\n"
                f"👤 Пользователь: {target}\n"
                f"🪙 Количество: {amount:.2f} г\n"
                f"📊 Осталось золота: {user_after['gold']:.2f} г",
                parse_mode="Markdown"
            )
            
            try:
                await message.bot.send_message(
                    target_id,
                    f"🪙 **У вас забрали золото админом!**\n\n"
                    f"➖ -{amount:.2f} г\n"
                    f"📊 Ваш баланс золота: {user_after['gold']:.2f} г",
                    parse_mode="Markdown"
                )
            except:
                pass
                
        except ValueError:
            await message.answer("❌ Количество должно быть числом", parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")
    
    # ===== СБРОС ИГРОКА =====
    @dp.message(Command("reset"))
    async def cmd_reset(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer("❌ Использование: `/reset [@username или id]`", parse_mode="Markdown")
                return
            
            target = parts[1]
            
            target_id = get_user_id_by_mention(target)
            if not target_id:
                await message.answer(f"❌ Пользователь {target} не найден", parse_mode="Markdown")
                return
            
            user = get_user(target_id)
            update_balance(target_id, -user['balance'])
            add_transaction(target_id, "admin_reset", 0, 0, ADMIN_ID)
            
            await message.answer(f"✅ Баланс пользователя {target} сброшен до 0₽", parse_mode="Markdown")
            
            try:
                await message.bot.send_message(
                    target_id,
                    f"⚠️ **Ваш баланс был сброшен админом до 0₽**",
                    parse_mode="Markdown"
                )
            except:
                pass
                
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")
    
    # ===== ЛОГИ ИГРОКА =====
    @dp.message(Command("log"))
    async def cmd_log(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer("❌ Использование: `/log [@username или id]`", parse_mode="Markdown")
                return
            
            target = parts[1]
            
            target_id = get_user_id_by_mention(target)
            if not target_id:
                await message.answer(f"❌ Пользователь {target} не найден", parse_mode="Markdown")
                return
            
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
                await message.answer(f"📋 Нет действий у {target}", parse_mode="Markdown")
                return
            
            text = f"📋 **Логи {target}** (последние 20):\n\n"
            for log in logs:
                text += f"🕐 {log['timestamp'][:19]}\n"
                text += f"📌 {log['type']}"
                if log['amount'] != 0:
                    text += f" | {log['amount']:.2f}"
                    if 'gold' in log['type']:
                        text += " г"
                    else:
                        text += "₽"
                if log['fee'] > 0:
                    text += f" | комиссия: {log['fee']:.2f}₽"
                if log['target_id']:
                    text += f" | → {log['target_id']}"
                text += "\n\n"
            
            await message.answer(text[:4000], parse_mode="Markdown")
            
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")
    
    # ===== СБРОС НЕАКТИВНЫХ =====
    @dp.message(Command("resetinactive"))
    async def cmd_reset_inactive(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer(
                    "❌ Использование: `/resetinactive [день/неделя/месяц/х7]`\n\n"
                    "Примеры:\n"
                    "/resetinactive день\n"
                    "/resetinactive неделя\n"
                    "/resetinactive месяц\n"
                    "/resetinactive х30",
                    parse_mode="Markdown"
                )
                return
            
            arg = parts[1].lower()
            
            if arg in ["день", "day"]:
                days = 1
            elif arg in ["неделя", "week"]:
                days = 7
            elif arg in ["месяц", "month"]:
                days = 30
            elif arg.startswith("х") or arg.startswith("x"):
                try:
                    days = int(arg[1:])
                except:
                    await message.answer("❌ Неверный формат. Пример: `/resetinactive х30`", parse_mode="Markdown")
                    return
            else:
                await message.answer("❌ Использование: `/resetinactive [день/неделя/месяц/х7]`", parse_mode="Markdown")
                return
            
            count = reset_inactive_users(days)
            await message.answer(
                f"✅ **Сброшено {count} неактивных игроков**\n\n"
                f"📊 Неактивны более {days} дней",
                parse_mode="Markdown"
            )
            
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")
