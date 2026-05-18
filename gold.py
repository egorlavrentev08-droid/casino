# gold.py
import asyncio
from datetime import datetime
from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import (
    TOTAL_GOLD, GOLD_BASE_PRICE, GOLD_SELL_FEE, 
    GOLD_SELL_FEE_ANON, GOLD_LISTING_MULTIPLIER, ADMIN_ID
)
from database import get_db, get_user, update_gold, update_balance, add_transaction, update_last_active
from utils import anti_flood


def register_gold(dp):
    
    # ========== ЗОЛОТО - ПРОВЕРКА ЦЕНЫ ==========
    @dp.message(Command("gold"))
    async def cmd_gold_handler(message: types.Message):
        user_id = message.from_user.id
        update_last_active(user_id)
        
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer(
                "🪙 **Золото — справка**\n\n"
                "`/gold check` — Средняя цена золота на аукционе\n"
                "`/gold my` — Сколько у вас золота\n"
                "`/gold auc` — Аукцион (страница 1)\n"
                "`/gold buy [номер лота]` — Купить лот\n"
                "`/gold sell [грамм] [цена за 1г]` — Выставить лот\n"
                "`/anon` / `/deanon` — Анонимность продажи\n\n"
                "💡 **Листинг:** 1г золота = +0.1% к итоговому курсу",
                parse_mode="Markdown"
            )
            return
        
        command = parts[1].lower()
        
        if command == "check":
            await gold_check(message)
        elif command == "my":
            await gold_my(message)
        elif command == "auc":
            await gold_auc(message, page=1)
        elif command == "buy":
            if len(parts) < 3:
                await message.answer("❌ Использование: `/gold buy [номер лота]`", parse_mode="Markdown")
                return
            try:
                lot_id = int(parts[2])
                await gold_buy(message, lot_id)
            except:
                await message.answer("❌ Некорректный номер лота", parse_mode="Markdown")
        elif command == "sell":
            if len(parts) < 4:
                await message.answer("❌ Использование: `/gold sell [грамм] [цена за 1г]`", parse_mode="Markdown")
                return
            try:
                amount = float(parts[2])
                price = float(parts[3])
                await gold_sell(message, amount, price)
            except:
                await message.answer("❌ Некорректные значения", parse_mode="Markdown")
        else:
            await message.answer("❌ Неизвестная команда. `/gold` — справка", parse_mode="Markdown")
    
    # ========== ПРОВЕРКА ЦЕНЫ ==========
    async def gold_check(message: types.Message):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT AVG(price) as avg_price FROM gold_auction 
                WHERE active = 1
            ''')
            result = cursor.fetchone()
            avg_price = result['avg_price'] if result and result['avg_price'] else GOLD_BASE_PRICE
        
        # Свободное золото на сервере
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT SUM(amount) as total FROM gold_auction WHERE active = 1')
            auction_gold = cursor.fetchone()['total'] or 0
            
            cursor.execute('SELECT SUM(gold) as total FROM users')
            user_gold = cursor.fetchone()['total'] or 0
        
        free_gold = TOTAL_GOLD - auction_gold - user_gold
        
        await message.answer(
            f"🪙 **Рынок золота**\n\n"
            f"💰 Средняя цена на аукционе: **{avg_price:.2f}₽/г**\n"
            f"🏦 Цена покупки с сервера: **{GOLD_BASE_PRICE}₽/г**\n"
            f"📊 Всего золота: **{TOTAL_GOLD:.0f} г**\n"
            f"🏪 В свободной продаже: **{free_gold:.2f} г**\n"
            f"👥 У игроков: **{user_gold:.2f} г**\n\n"
            f"💡 **Листинг:** 1г золота = +0.1% к курсу обмена",
            parse_mode="Markdown"
        )
    
    # ========== МОЁ ЗОЛОТО ==========
    async def gold_my(message: types.Message):
        user_id = message.from_user.id
        user = get_user(user_id)
        
        # Рассчитываем бонус к листингу
        listing_bonus = user['gold'] * GOLD_LISTING_MULTIPLIER * 100  # в процентах
        
        await message.answer(
            f"🪙 **Ваше золото**\n\n"
            f"💰 Баланс золота: **{user['gold']:.2f} г**\n"
            f"📈 Бонус к листингу: **+{listing_bonus:.2f}%**\n\n"
            f"💡 Чем больше золота, тем выше бонус при обмене на рубли",
            parse_mode="Markdown"
        )
    
    # ========== ВЫСТАВИТЬ ЛОТ ==========
    async def gold_sell(message: types.Message, amount: float, price: float):
        user_id = message.from_user.id
        
        if amount <= 0 or price <= 0:
            await message.answer("❌ Количество и цена должны быть больше 0", parse_mode="Markdown")
            return
        
        user = get_user(user_id)
        if user['gold'] < amount:
            await message.answer(
                f"❌ **Недостаточно золота**\n"
                f"У вас: {user['gold']:.2f} г\n"
                f"Требуется: {amount:.2f} г",
                parse_mode="Markdown"
            )
            return
        
        # Проверяем анонимность
        is_anon = user['anon_seller'] == 1
        fee = GOLD_SELL_FEE_ANON if is_anon else GOLD_SELL_FEE
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO gold_auction (seller_id, amount, price, anonymous, created_at, active)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (user_id, amount, price, 1 if is_anon else 0, datetime.now().isoformat()))
            lot_id = cursor.lastrowid
            conn.commit()
        
        # Списываем золото у пользователя
        update_gold(user_id, -amount)
        add_transaction(user_id, "gold_list", -amount, 0, lot_id)
        
        await message.answer(
            f"✅ **Лот выставлен!**\n\n"
            f"🆔 Номер лота: `{lot_id}`\n"
            f"🪙 Количество: {amount:.2f} г\n"
            f"💰 Цена: {price:.2f}₽/г\n"
            f"🔒 Анонимно: {'Да' if is_anon else 'Нет'}\n"
            f"📊 Комиссия при продаже: {fee*100:.0f}%",
            parse_mode="Markdown"
        )
    
    # ========== КУПИТЬ ЛОТ ==========
    async def gold_buy(message: types.Message, lot_id: int):
        user_id = message.from_user.id
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM gold_auction WHERE lot_id = ? AND active = 1', (lot_id,))
            lot = cursor.fetchone()
        
        if not lot:
            await message.answer(f"❌ Лот `{lot_id}` не найден или уже продан", parse_mode="Markdown")
            return
        
        total_price = lot['amount'] * lot['price']
        user = get_user(user_id)
        
        if user['balance'] < total_price:
            await message.answer(
                f"❌ **Недостаточно рублей**\n"
                f"Стоимость лота: {total_price:.2f}₽\n"
                f"Ваш баланс: {user['balance']:.2f}₽",
                parse_mode="Markdown"
            )
            return
        
        # Покупаем
        update_balance(user_id, -total_price)
        update_gold(user_id, lot['amount'])
        update_gold(lot['seller_id'], -lot['amount'])  # Золото уже списано при листе, но на всякий случай
        
        # Начисляем продавцу деньги (с комиссией)
        seller = get_user(lot['seller_id'])
        fee_rate = GOLD_SELL_FEE_ANON if lot['anonymous'] else GOLD_SELL_FEE
        fee_amount = total_price * fee_rate
        seller_get = total_price - fee_amount
        
        update_balance(lot['seller_id'], seller_get)
        
        # Закрываем лот
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE gold_auction SET active = 0 WHERE lot_id = ?', (lot_id,))
            conn.commit()
        
        # Логи
        add_transaction(user_id, "gold_buy", -total_price, 0, lot['seller_id'])
        add_transaction(lot['seller_id'], "gold_sell", seller_get, fee_amount, user_id)
        
        seller_name = f"`{lot['seller_id']}`" if not lot['anonymous'] else "🔒 Аноним"
        
        await message.answer(
            f"✅ **Покупка совершена!**\n\n"
            f"🆔 Лот: `{lot_id}`\n"
            f"👤 Продавец: {seller_name}\n"
            f"🪙 Золото: {lot['amount']:.2f} г\n"
            f"💰 Цена: {lot['price']:.2f}₽/г\n"
            f"💵 Итого: {total_price:.2f}₽\n"
            f"📊 Комиссия продавца: {fee_amount:.2f}₽ ({fee_rate*100:.0f}%)",
            parse_mode="Markdown"
        )
        
        # Уведомляем продавца
        try:
            await message.bot.send_message(
                lot['seller_id'],
                f"💰 **Ваш лот продан!**\n\n"
                f"🆔 Лот: `{lot_id}`\n"
                f"🪙 {lot['amount']:.2f} г по {lot['price']:.2f}₽/г\n"
                f"💵 Вы получили: {seller_get:.2f}₽\n"
                f"📊 Комиссия: {fee_amount:.2f}₽",
                parse_mode="Markdown"
            )
        except:
            pass
    
    # ========== АУКЦИОН (ПАГИНАЦИЯ) ==========
    async def gold_auc(message: types.Message, page: int = 1):
        user_id = message.from_user.id
        update_last_active(user_id)
        
        ITEMS_PER_PAGE = 7
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM gold_auction WHERE active = 1 ORDER BY created_at DESC')
            all_lots = cursor.fetchall()
        
        total_lots = len(all_lots)
        total_pages = (total_lots + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        
        if total_pages == 0:
            await message.answer("🏪 **Аукцион пуст**\n\nВы можете выставить золото: `/gold sell [грамм] [цена]`", parse_mode="Markdown")
            return
        
        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages
        
        start = (page - 1) * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        lots = all_lots[start:end]
        
        # Создаём кнопки для лотов
        keyboard = []
        for lot in lots:
            seller_name = f"`{lot['seller_id']}`" if not lot['anonymous'] else "🔒 Аноним"
            total_price = lot['amount'] * lot['price']
            button_text = f"🆔 {lot['lot_id']} | {lot['amount']:.1f}г | {lot['price']:.0f}₽/г | {total_price:.0f}₽"
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"gold_lot_{lot['lot_id']}")])
        
        # Кнопки навигации
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"gold_page_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"gold_page_{page+1}"))
        keyboard.append(nav_buttons)
        
        # Кнопка обновления
        keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"gold_refresh_{page}")])
        
        await message.answer(
            f"🏪 **Аукцион золота** — страница {page}/{total_pages}\n\n"
            f"🪙 Всего лотов: {total_lots}\n"
            f"💡 Нажми на лот для покупки",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    # ========== ОБРАБОТКА КНОПОК АУКЦИОНА ==========
    @dp.callback_query(lambda c: c.data.startswith('gold_'))
    async def gold_callback(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        data = callback.data.split('_')
        
        if data[1] == "page":
            page = int(data[2])
            await gold_auc(callback.message, page)
            await callback.answer()
        
        elif data[1] == "refresh":
            page = int(data[2])
            await gold_auc(callback.message, page)
            await callback.answer()
        
        elif data[1] == "lot":
            lot_id = int(data[2])
            await show_lot_details(callback, lot_id)
            await callback.answer()
    
    async def show_lot_details(callback, lot_id: int):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM gold_auction WHERE lot_id = ? AND active = 1', (lot_id,))
            lot = cursor.fetchone()
        
        if not lot:
            await callback.message.answer(f"❌ Лот `{lot_id}` уже продан", parse_mode="Markdown")
            return
        
        seller_name = f"`{lot['seller_id']}`" if not lot['anonymous'] else "🔒 Аноним"
        total_price = lot['amount'] * lot['price']
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Купить", callback_data=f"gold_buy_{lot_id}")],
            [InlineKeyboardButton(text="◀️ Назад к аукциону", callback_data="gold_back")]
        ])
        
        await callback.message.answer(
            f"📦 **Детали лота**\n\n"
            f"🆔 Номер: `{lot['lot_id']}`\n"
            f"👤 Продавец: {seller_name}\n"
            f"🪙 Количество: {lot['amount']:.2f} г\n"
            f"💰 Цена за 1г: {lot['price']:.2f}₽\n"
            f"💵 Общая стоимость: {total_price:.2f}₽\n"
            f"📅 Создан: {lot['created_at'][:19]}\n\n"
            f"💡 Нажми «Купить» для подтверждения",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    @dp.callback_query(lambda c: c.data.startswith('gold_buy_'))
    async def gold_buy_callback(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        lot_id = int(callback.data.split('_')[2])
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM gold_auction WHERE lot_id = ? AND active = 1', (lot_id,))
            lot = cursor.fetchone()
        
        if not lot:
            await callback.answer("❌ Лот уже продан!", show_alert=True)
            return
        
        total_price = lot['amount'] * lot['price']
        user = get_user(user_id)
        
        if user['balance'] < total_price:
            await callback.answer(f"❌ Не хватает {total_price - user['balance']:.2f}₽", show_alert=True)
            return
        
        # Покупаем
        update_balance(user_id, -total_price)
        update_gold(user_id, lot['amount'])
        
        fee_rate = GOLD_SELL_FEE_ANON if lot['anonymous'] else GOLD_SELL_FEE
        fee_amount = total_price * fee_rate
        seller_get = total_price - fee_amount
        
        update_balance(lot['seller_id'], seller_get)
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE gold_auction SET active = 0 WHERE lot_id = ?', (lot_id,))
            conn.commit()
        
        add_transaction(user_id, "gold_buy", -total_price, 0, lot['seller_id'])
        add_transaction(lot['seller_id'], "gold_sell", seller_get, fee_amount, user_id)
        
        await callback.message.edit_text(
            f"✅ **Покупка совершена!**\n\n"
            f"🆔 Лот: `{lot_id}`\n"
            f"🪙 Золото: {lot['amount']:.2f} г\n"
            f"💰 Цена: {lot['price']:.2f}₽/г\n"
            f"💵 Итого: {total_price:.2f}₽",
            parse_mode="Markdown"
        )
        
        # Уведомляем продавца
        try:
            await callback.bot.send_message(
                lot['seller_id'],
                f"💰 **Ваш лот продан!**\n\n"
                f"🆔 Лот: `{lot_id}`\n"
                f"🪙 {lot['amount']:.2f} г\n"
                f"💵 Вы получили: {seller_get:.2f}₽",
                parse_mode="Markdown"
            )
        except:
            pass
        
        await callback.answer()
    
    @dp.callback_query(lambda c: c.data == "gold_back")
    async def gold_back_callback(callback: types.CallbackQuery):
        await gold_auc(callback.message, page=1)
        await callback.answer()
