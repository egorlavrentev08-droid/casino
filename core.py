# core.py
import asyncio
from datetime import datetime, timedelta
from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import DAILY_BONUS, MAX_BALANCE_FOR_BONUS, ADMIN_ID
from database import get_user, update_balance, add_transaction, update_last_active, get_db
from utils import anti_flood
from limits import check_transfer_limit, check_receive_limit


def register_core(dp):
    
    # ========== ОБНОВЛЕНИЕ USERNAME ПРИ СТАРТЕ ==========
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        user_id = message.from_user.id
        username = message.from_user.username
        update_last_active(user_id)
        
        # Обновляем username в БД
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET username = ? WHERE user_id = ?', 
                          (username.lower() if username else None, user_id))
            conn.commit()
        
        user = get_user(user_id)
        
        await message.answer(
            "🎰 **КАЗИНО ДОЛИНА** 🎰\n\n"
            "📜 **Команды:**\n"
            "🎲 `/mines [ставка]` — Мины (5 мин, 20 клеток)\n"
            "🎡 `/roulette [ставка] [сумма]` — Рулетка\n"
            "   Пример: `/roulette red 1000` или `/roulette 7 500`\n"
            "🃏 `/joker [ставка]` — Джокер\n"
            "💰 `/bonus` — Ежедневный бонус\n"
            "💳 `/balance` — Баланс\n"
            "📤 `/pay [сумма]` — Перевести деньги (ответом на сообщение)\n\n"
            "🪙 **Золото:**\n"
            "`/gold check` — Цена золота\n"
            "`/gold my` — Моё золото\n"
            "`/gold auc` — Аукцион\n"
            "`/gold buys [грамм]` — Купить золото с сервера\n"
            "`/anon` / `/deanon` — Анонимность продажи\n\n"
            f"💰 **Ваш баланс:** {user['balance']:.2f}₽\n"
            f"🪙 **Ваше золото:** {user['gold']:.2f} г",
            parse_mode="Markdown"
        )
    
    # ========== БАЛАНС ==========
    @dp.message(Command("balance"))
    async def cmd_balance(message: types.Message):
        user_id = message.from_user.id
        update_last_active(user_id)
        user = get_user(user_id)
        
        await message.answer(
            f"💰 **Ваш баланс:** {user['balance']:.2f}₽\n"
            f"🪙 **Ваше золото:** {user['gold']:.2f} г",
            parse_mode="Markdown"
        )
    
    # ========== ЕЖЕДНЕВНЫЙ БОНУС ==========
    @dp.message(Command("bonus"))
    async def cmd_bonus(message: types.Message):
        user_id = message.from_user.id
        update_last_active(user_id)
        user = get_user(user_id)
        
        # Проверка: баланс > 50к
        if user['balance'] > MAX_BALANCE_FOR_BONUS:
            await message.answer(
                f"❌ **Бонус недоступен**\n\n"
                f"Ваш баланс ({user['balance']:.2f}₽) превышает {MAX_BALANCE_FOR_BONUS}₽",
                parse_mode="Markdown"
            )
            return
        
        # Проверка: последний бонус
        if user['last_bonus']:
            try:
                last_time = datetime.fromisoformat(user['last_bonus'])
                if datetime.now() - last_time < timedelta(days=1):
                    hours_left = 24 - (datetime.now() - last_time).seconds // 3600
                    minutes_left = (60 - (datetime.now() - last_time).seconds // 60) % 60
                    await message.answer(
                        f"⏳ **Бонус уже получен**\n\n"
                        f"Следующий бонус через {hours_left} ч {minutes_left} мин",
                        parse_mode="Markdown"
                    )
                    return
            except:
                pass
        
        # Начисляем бонус
        new_balance = update_balance(user_id, DAILY_BONUS)
        add_transaction(user_id, "daily_bonus", DAILY_BONUS, 0)
        
        # Обновляем время бонуса
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET last_bonus = ? WHERE user_id = ?', 
                          (datetime.now().isoformat(), user_id))
            conn.commit()
        
        await message.answer(
            f"🎁 **Бонус получен!**\n\n"
            f"💰 +{DAILY_BONUS:.2f}₽\n"
            f"💳 Новый баланс: {new_balance:.2f}₽",
            parse_mode="Markdown"
        )
    
    # ========== ПЕРЕВОД ДЕНЕГ ==========
    @dp.message(Command("pay"))
    async def cmd_pay(message: types.Message):
        user_id = message.from_user.id
        update_last_active(user_id)
        
        # Защита от флуда
        if not await anti_flood(user_id, cooldown=2):
            await message.answer("⏳ Слишком часто! Подожди пару секунд.", parse_mode="Markdown")
            return
        
        # Проверка: ответ на сообщение
        if not message.reply_to_message:
            await message.answer(
                "❌ **Ошибка перевода**\n\n"
                "Ответьте на сообщение пользователя, которому хотите перевести деньги.\n\n"
                "Пример: `/pay 500` (ответом на сообщение)",
                parse_mode="Markdown"
            )
            return
        
        # Парсим сумму
        try:
            amount = float(message.text.split()[1])
            if amount <= 0:
                await message.answer("❌ Сумма должна быть больше 0", parse_mode="Markdown")
                return
        except:
            await message.answer("❌ **Ошибка**\nИспользование: `/pay [сумма]` (ответом на сообщение)", parse_mode="Markdown")
            return
        
        sender_id = user_id
        receiver_id = message.reply_to_message.from_user.id
        
        # Проверки
        if receiver_id == sender_id:
            await message.answer("❌ Нельзя перевести самому себе!", parse_mode="Markdown")
            return
        
        if receiver_id == (await message.bot.me()).id:
            await message.answer("❌ Нельзя переводить деньги боту!", parse_mode="Markdown")
            return
        
        sender = get_user(sender_id)
        if sender['balance'] < amount:
            await message.answer(
                f"❌ **Недостаточно средств**\n\n"
                f"💰 Ваш баланс: {sender['balance']:.2f}₽\n"
                f"📤 Требуется: {amount:.2f}₽",
                parse_mode="Markdown"
            )
            return
        
        # Кнопки подтверждения
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"pay_confirm_{receiver_id}_{amount}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="pay_cancel")
            ]
        ])
        
        # Получаем username получателя
        receiver = get_user(receiver_id)
        receiver_name = f"@{receiver['username']}" if receiver['username'] else f"`{receiver_id}`"
        
        await message.answer(
            f"💸 **Перевод средств**\n\n"
            f"📤 Отправитель: `{sender_id}`\n"
            f"📥 Получатель: {receiver_name}\n"
            f"💰 Сумма: **{amount:.2f}₽**\n\n"
            f"Подтвердите перевод:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    # ========== ОБРАБОТКА ПОДТВЕРЖДЕНИЯ ПЕРЕВОДА ==========
    @dp.callback_query(lambda c: c.data.startswith('pay_confirm_'))
    async def pay_confirm(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        
        # Парсим данные
        parts = callback.data.split('_')
        receiver_id = int(parts[2])
        amount = float(parts[3])
        
        # Проверяем, что подтверждает отправитель
        if user_id != callback.message.reply_to_message.from_user.id:
            await callback.answer("❌ Это не ваша транзакция!", show_alert=True)
            return
        
        sender_id = user_id
        
        # Повторно проверяем баланс
        sender = get_user(sender_id)
        if sender['balance'] < amount:
            await callback.message.edit_text(
                f"❌ **Ошибка перевода**\n\n"
                f"Недостаточно средств. Баланс: {sender['balance']:.2f}₽",
                parse_mode="Markdown"
            )
            await callback.answer()
            return
        
        # Проверяем лимиты отправителя
        transfer_fee, transfer_amount = check_transfer_limit(sender_id, amount)
        
        # Проверяем лимиты получателя
        receive_fee, receive_amount = check_receive_limit(receiver_id, amount - transfer_fee)
        
        # Итоговая комиссия и сумма
        total_fee = transfer_fee + receive_fee
        final_amount = amount - total_fee
        
        # Списываем у отправителя
        update_balance(sender_id, -amount)
        add_transaction(sender_id, "transfer_out", -amount, transfer_fee, receiver_id)
        
        # Начисляем получателю
        update_balance(receiver_id, receive_amount)
        add_transaction(receiver_id, "transfer_in", receive_amount, receive_fee, sender_id)
        
        # Получаем имена
        receiver = get_user(receiver_id)
        receiver_name = f"@{receiver['username']}" if receiver['username'] else f"`{receiver_id}`"
        
        await callback.message.edit_text(
            f"✅ **Перевод выполнен!**\n\n"
            f"📤 Отправитель: `{sender_id}`\n"
            f"📥 Получатель: {receiver_name}\n"
            f"💰 Сумма: {amount:.2f}₽\n"
            f"📊 Комиссия: {total_fee:.2f}₽\n"
            f"💵 Получено: {final_amount:.2f}₽",
            parse_mode="Markdown"
        )
        
        # Уведомляем получателя
        try:
            await callback.bot.send_message(
                receiver_id,
                f"💰 **Вам перевели деньги!**\n\n"
                f"📤 От: `{sender_id}`\n"
                f"💰 Сумма: {final_amount:.2f}₽\n"
                f"📊 Комиссия: {total_fee:.2f}₽",
                parse_mode="Markdown"
            )
        except:
            pass
        
        await callback.answer()
    
    # ========== ОТМЕНА ПЕРЕВОДА ==========
    @dp.callback_query(lambda c: c.data == "pay_cancel")
    async def pay_cancel(callback: types.CallbackQuery):
        await callback.message.edit_text("❌ Перевод отменён", parse_mode="Markdown")
        await callback.answer()
    
    # ========== АНОНИМНОСТЬ ==========
    @dp.message(Command("anon"))
    async def cmd_anon(message: types.Message):
        user_id = message.from_user.id
        update_last_active(user_id)
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET anon_seller = 1 WHERE user_id = ?', (user_id,))
            conn.commit()
        
        await message.answer(
            "🕵️ **Анонимный режим включён**\n\n"
            "Теперь ваши лоты на аукционе золота будут скрывать ваше имя.\n"
            "📊 Комиссия при продаже: **11%** (вместо 7%)",
            parse_mode="Markdown"
        )
    
    @dp.message(Command("deanon"))
    async def cmd_deanon(message: types.Message):
        user_id = message.from_user.id
        update_last_active(user_id)
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET anon_seller = 0 WHERE user_id = ?', (user_id,))
            conn.commit()
        
        await message.answer(
            "👤 **Анонимный режим выключён**\n\n"
            "Теперь ваши лоты на аукционе золота будут показывать ваше имя.\n"
            "📊 Комиссия при продаже: **7%**",
            parse_mode="Markdown"
          )
