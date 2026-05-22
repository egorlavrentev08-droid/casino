# admin.py
import os
import asyncio
from datetime import datetime, timedelta
from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMIN_ID, BACKUP_DIR
from database import get_db, update_balance, add_transaction, get_user, update_gold
from utils import reset_inactive_users
from backups import get_latest_backup, restore_from_backup, auto_backup
from logger import get_user_logs, get_all_logs, log_action


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


def escape_markdown(text: str) -> str:
    """Экранирует спецсимволы для Markdown"""
    if not text:
        return ""
    chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for ch in chars:
        text = text.replace(ch, f'\\{ch}')
    return text


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
            log_action(target_id, target, "admin_give", amount_rub=amount)
            
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
            log_action(target_id, target, "admin_take", amount_rub=-amount)
            
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
            add_transaction(target_id, "admin_ggive", 0, amount, ADMIN_ID)
            log_action(target_id, target, "admin_ggive", amount_gold=amount)
            
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
            add_transaction(target_id, "admin_gtake", 0, -amount, ADMIN_ID)
            log_action(target_id, target, "admin_gtake", amount_gold=-amount)
            
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
            log_action(target_id, target, "admin_reset")
            
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
    
    # ===== ЛОГИ ИГРОКА (РАСШИРЕННЫЕ) =====
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
            
            logs = get_user_logs(target_id, 30)
            
            if not logs:
                await message.answer(f"📋 Нет действий у {target}", parse_mode="Markdown")
                return
            
            safe_target = escape_markdown(target)
            text = f"📋 **Логи {safe_target}** (последние 30):\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for log in logs:
                time_str = log['timestamp'][:19] if log['timestamp'] else "?"
                text += f"🕐 {time_str}\n"
                text += f"📌 {log['action']}"
                
                if log['amount_rub'] != 0:
                    sign = '+' if log['amount_rub'] > 0 else ''
                    text += f" | {sign}{log['amount_rub']:.2f}₽"
                
                if log['amount_gold'] != 0:
                    sign = '+' if log['amount_gold'] > 0 else ''
                    text += f" | {sign}{log['amount_gold']:.2f} г"
                
                if log['target_id']:
                    text += f" | → {log['target_id']}"
                
                text += "\n\n"
            
            await message.answer(text[:4000], parse_mode="Markdown")
            
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")
    
    # ===== ВСЕ ЛОГИ (АДМИН) =====
    @dp.message(Command("alllogs"))
    async def cmd_alllogs(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        
        try:
            limit = 50
            parts = message.text.split()
            if len(parts) > 1:
                limit = int(parts[1])
                if limit > 200:
                    limit = 200
            
            logs = get_all_logs(limit)
            
            if not logs:
                await message.answer("📋 Нет логов", parse_mode="Markdown")
                return
            
            text = f"📋 **Общие логи** (последние {len(logs)}):\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for log in logs:
                time_str = log['timestamp'][:19] if log['timestamp'] else "?"
                username = log['username'] or f"id:{log['user_id']}"
                safe_username = escape_markdown(username)
                
                text += f"🕐 {time_str}\n"
                text += f"👤 {safe_username}\n"
                text += f"📌 {log['action']}"
                
                if log['amount_rub'] != 0:
                    sign = '+' if log['amount_rub'] > 0 else ''
                    text += f" | {sign}{log['amount_rub']:.2f}₽"
                
                if log['amount_gold'] != 0:
                    sign = '+' if log['amount_gold'] > 0 else ''
                    text += f" | {sign}{log['amount_gold']:.2f} г"
                
                if log['target_id']:
                    text += f" | → {log['target_id']}"
                
                text += "\n\n"
                
                if len(text) > 3800:
                    await message.answer(text, parse_mode="Markdown")
                    text = ""
            
            if text:
                await message.answer(text, parse_mode="Markdown")
                
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")
    
    # ===== БЭКАП (СОЗДАТЬ) =====
    @dp.message(Command("backup"))
    async def cmd_backup(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            await message.answer("❌ Доступ запрещён")
            return
        
        auto_backup()
        log_action(ADMIN_ID, "admin", "manual_backup")
        await message.answer("✅ **Бэкап создан!**\n\n📁 Папка: " + BACKUP_DIR, parse_mode="Markdown")
    
    # ===== ВОССТАНОВИТЬ ИЗ ПОСЛЕДНЕГО БЭКАПА =====
    @dp.message(Command("restore"))
    async def cmd_restore(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            await message.answer("❌ Доступ запрещён")
            return
        
        latest = get_latest_backup()
        if not latest:
            await message.answer("❌ Нет доступных бэкапов!")
            return
        
        # Кнопки подтверждения
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, восстановить", callback_data="confirm_restore"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_restore")
            ]
        ])
        
        backup_name = os.path.basename(latest)
        await message.answer(
            f"⚠️ **Восстановление из бэкапа**\n\n"
            f"📁 Бэкап: `{backup_name}`\n"
            f"🔄 Это перезапишет текущую базу данных!\n\n"
            f"Подтвердите действие:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    # ===== ОБРАБОТЧИК ПОДТВЕРЖДЕНИЯ ВОССТАНОВЛЕНИЯ =====
    @dp.callback_query(lambda c: c.data == "confirm_restore")
    async def confirm_restore(callback: types.CallbackQuery):
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("❌ Доступ запрещён", show_alert=True)
            return
        
        latest = get_latest_backup()
        if not latest:
            await callback.message.edit_text("❌ Нет доступных бэкапов!", parse_mode="Markdown")
            await callback.answer()
            return
        
        if restore_from_backup(latest):
            log_action(ADMIN_ID, "admin", "restore_from_backup")
            await callback.message.edit_text(
                "✅ **База данных восстановлена из бэкапа!**\n\n"
                "🔄 Бот будет перезапущен...",
                parse_mode="Markdown"
            )
            await callback.answer()
            os._exit(0)
        else:
            await callback.message.edit_text("❌ **Ошибка восстановления!**", parse_mode="Markdown")
            await callback.answer()
    
    @dp.callback_query(lambda c: c.data == "cancel_restore")
    async def cancel_restore(callback: types.CallbackQuery):
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("❌ Доступ запрещён", show_alert=True)
            return
        
        await callback.message.edit_text("❌ Восстановление отменено", parse_mode="Markdown")
        await callback.answer()
    
    # ===== СПИСОК БЭКАПОВ =====
    @dp.message(Command("backups"))
    async def cmd_backups(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            await message.answer("❌ Доступ запрещён")
            return
        
        import glob
        backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "casino_bot.db.backup_*.db")))
        
        if not backups:
            await message.answer("📁 **Нет бэкапов**", parse_mode="Markdown")
            return
        
        text = "💾 **Список бэкапов**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, backup in enumerate(backups[-15:], 1):
            name = os.path.basename(backup)
            size = os.path.getsize(backup) / 1024
            text += f"{i}. `{name}` — {size:.1f} КБ\n"
        
        text += "\n💡 `/restore` — восстановить последний бэкап\n💡 `/backup` — создать новый бэкап"
        await message.answer(text, parse_mode="Markdown")
    
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
            log_action(ADMIN_ID, "admin", "reset_inactive", amount_rub=count)
            await message.answer(
                f"✅ **Сброшено {count} неактивных игроков**\n\n"
                f"📊 Неактивны более {days} дней",
                parse_mode="Markdown"
            )
            
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")
