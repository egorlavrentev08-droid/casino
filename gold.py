# gold.py
import asyncio
from datetime import datetime
from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import (
    TOTAL_GOLD, GOLD_BASE_PRICE, GOLD_SELL_FEE, 
    GOLD_SELL_FEE_ANON, GOLD_LISTING_MULTIPLIER
)
from database import (
    get_db, get_user, update_gold, update_balance, 
    add_transaction, update_last_active, get_free_gold,
    add_auction_lot, get_active_lots, get_lot, close_lot,
    is_anon_seller
)
from utils import anti_flood


def register_gold(dp):
    
    # ========== ОСНОВНОЙ ОБРАБОТЧИК ==========
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
                "`/gold lots` — **Ваши активные лоты**\n"
                "`/gold buys [грамм]` — Купить золото с сервера (1000₽/г)\n"
                "`/gold buy [номер лота]` — Купить лот на аукционе\n"
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
            page = 1
            if len(parts) > 2 and parts[2].isdigit():
                page = int(parts[2])
            await gold_auc(message, page=page)
        elif command == "lots":
            await gold_my_lots(message)
        elif command == "buys":
            if len(parts) < 3:
                await message.answer("❌ Использование: `/gold buys [грамм]`\n\nПример: `/gold buys 10`", parse_mode="Markdown")
                return
            try:
                grams = float(parts[2])
                await gold_buy_from_server(message, grams)
            except ValueError:
                await message.answer("❌ Неверное количество граммов", parse_mode="Markdown")
        elif command == "buy":
            if len(parts) < 3:
                await message.answer("❌ Использование: `/gold buy [номер лота]`", parse_mode="Markdown")
                return
            try:
                lot_id = int(parts[2])
                await gold_buy_lot(message, lot_id)
            except ValueError:
                await message.answer("❌ Некорректный номер лота", parse_mode="Markdown")
        elif command == "sell":
            if len(parts) < 4:
                await message.answer("❌ Использование: `/gold sell [грамм] [цена за 1г]`\n\nПример: `/gold sell 5 1200`", parse_mode="Markdown")
                return
            try:
                amount = float(parts[2])
                price = float(parts[3])
                await gold_sell(message, amount, price)
            except ValueError:
                await message.answer("❌ Некорректные значения", parse_mode="Markdown")
        else:
            await message.answer("❌ Неизвестная команда. `/gold` — справка", parse_mode="Markdown")
    
    # ========== ПРОВЕРКА ЦЕНЫ ==========
    async def gold_check(message: types.Message):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT AVG(price) as avg_price FROM gold_auction WHERE active = 1')
            result = cursor.fetchone()
            avg_price = result['avg_price'] if result and result['avg_price'] else GOLD_BASE_PRICE
        
        free_gold = get_free_gold()
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT SUM(gold) as total FROM users')
            user_gold = cursor.fetchone()['total'] or 0
        
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
        
        listing_bonus = user['gold'] * GOLD_LISTING_MULTIPLIER * 100
        
        await message.answer(
            f"🪙 **Ваше золото**\n\n"
            f"💰 Баланс золота: **{user['gold']:.2f} г**\n"
            f"📈 Бонус к листингу: **+{listing_bonus:.2f}%**\n\n"
            f"💡 Чем больше золота, тем выше бонус при обмене на рубли",
            parse_mode="Markdown"
        )
    
    # ========== МОИ ЛОТЫ ==========
    async def gold_my_lots(message: types.Message):
        user_id = message.from_user.id
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM gold_auction 
                WHERE seller_id = ? AND active = 1 
                ORDER BY created_at DESC
            ''', (user_id,))
            lots = cursor.fetchall()
        
        if not lots:
            await message.answer("🏪 **У вас нет активных лотов**\n\nВы можете выставить золото: `/gold sell [грамм] [цена]`", parse_mode="Markdown")
            return
        
        keyboard = []
        for lot in lots:
            total_price = lot['amount'] * lot['price']
            fee = total_price * (GOLD_SELL_FEE_ANON if lot['anonymous'] else GOLD_SELL_FEE)
            seller_get = total_price - fee
            
            button_text = f"🆔 {lot['lot_id']} | {lot['amount']:.1f}г | {lot['price']:.0f}₽/г | +{seller_get:.0f}₽"
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"gold_mylot_{lot['lot_id']}")])
        
        keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="gold_mylots_refresh")])
        
        await message.answer(
            f"📦 **Ваши активные лоты**\n\n"
            f"🪙 Всего лотов: {len(lots)}\n"
            f"💡 Нажми на лот для управления",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    # ========== ДЕТАЛИ МОЕГО ЛОТА ==========
    async def show_my_lot_details(callback, lot_id: int):
        lot = get_lot(lot_id)
        
        if not lot or lot['active'] != 1:
            await callback.message.edit_text(f"❌ Лот `{lot_id}` уже неактивен", parse_mode="Markdown")
            return
        
        total_price = lot['amount'] * lot['price']
        fee_rate = GOLD_SELL_FEE_ANON if lot['anonymous'] else GOLD_SELL_FEE
        fee_amount = total_price * fee_rate
        seller_get = total_price - fee_amount
        
        seller_name = "🔒 Аноним" if lot['anonymous'] else f"`{lot['seller_id']}`"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Убрать лот", callback_data=f"gold_remove_lot_{lot_id}")],
            [InlineKeyboardButton(text="◀️ Назад к моим лотам", callback_data="gold_mylots_back")]
        ])
        
        await callback.message.edit_text(
            f"📦 **Детали вашего лота**\n\n"
            f"🆔 Номер: `{lot['lot_id']}`\n"
            f"👤 Продавец: {seller_name}\n"
            f"🪙 Количество: {lot['amount']:.2f} г\n"
            f"💰 Цена за 1г: {lot['price']:.2f}₽\n"
            f"💵 Общая стоимость: {total_price:.2f}₽\n"
            f"📊 Комиссия: {fee_amount:.2f}₽ ({fee_rate*100:.0f}%)\n"
            f"💰 Вы получите: {seller_get:.2f}₽\n"
            f"📅 Создан: {lot['created_at'][:19]}\n\n"
            f"💡 Нажми «Убрать лот» для снятия с продажи",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    # ========== ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ ЛОТА ==========
    async def confirm_remove_lot(callback, lot_id: int):
        lot = get_lot(lot_id)
        
        if not lot or lot['active'] != 1:
            await callback.message.edit_text(f"❌ Лот `{lot_id}` уже неактивен", parse_mode="Markdown")
            return
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, убрать", callback_data=f"gold_confirm_remove_{lot_id}"),
                InlineKeyboardButton(text="❌ Нет, оставить", callback_data=f"gold_cancel_remove_{lot_id}")
            ]
        ])
        
        await callback.message.edit_text(
            f"⚠️ **Подтверждение удаления лота**\n\n"
            f"🆔 Лот: `{lot['lot_id']}`\n"
            f"🪙 {lot['amount']:.2f} г по {lot['price']:.2f}₽/г\n\n"
            f"Вы уверены, что хотите снять лот с продажи?\n"
            f"Золото будет возвращено на ваш баланс.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    # ========== УДАЛЕНИЕ ЛОТА ==========
    async def remove_lot(callback, lot_id: int):
        lot = get_lot(lot_id)
        
        if not lot or lot['active'] != 1:
            await callback.message.edit_text(f"❌ Лот `{lot_id}` уже неактивен", parse_mode="Markdown")
            return
        
        update_gold(lot['seller_id'], lot['amount'])
        add_transaction(lot['seller_id'], "gold_remove_lot", lot['amount'], 0, lot_id)
        close_lot(lot_id)
        
        await callback.message.edit_text(
            f"✅ **Лот убран!**\n\n"
            f"🆔 Лот: `{lot_id}`\n"
            f"🪙 {lot['amount']:.2f} г возвращено на ваш баланс",
            parse_mode="Markdown"
        )
        
        await asyncio.sleep(2)
        await gold_my_lots(callback.message)
    
    # ========== ВЫСТАВИТЬ ЛОТ ==========
    async def gold_sell(message: types.Message, amount: float, price: float):
        user_id = message.from_user.id
        
        if amount <= 0 or price <= 0:
            await message.answer("❌ Количество и цена должны быть больше 0", parse_mode="Markdown")
            return
        
        user = get_user(user_id)
        if user['gold'] < amount:
            await message.answer(
                f"❌ **Недостаточно золота**\n\n"
                f"🪙 У вас: {user['gold']:.2f} г\n"
                f"📊 Требуется: {amount:.2f} г",
                parse_mode="Markdown"
            )
            return
        
        is_anon = is_anon_seller(user_id)
        fee = GOLD_SELL_FEE_ANON if is_anon else GOLD_SELL_FEE
        
        lot_id = add_auction_lot(user_id, amount, price, is_anon)
        update_gold(user_id, -amount)
        add_transaction(user_id, "gold_list", -amount, 0, lot_id)
        
        await message.answer(
            f"✅ **Лот выставлен!**\n\n"
            f"🆔 Номер лота: `{lot_id}`\n"
            f"🪙 Количество: {amount:.2f} г\n"
            f"💰 Цена: {price:.2f}₽/г\n"
            f"💵 Общая стоимость: {amount * price:.2f}₽\n"
            f"🔒 Анонимно: {'Да' if is_anon else 'Нет'}\n"
            f"📊 Комиссия при продаже: {fee*100:.0f}%",
            parse_mode="Markdown"
        )
    
    # ========== КУПИТЬ ЗОЛОТО С СЕРВЕРА ==========
    async def gold_buy_from_server(message: types.Message, grams: float):
        user_id = message.from_user.id
        
        if grams <= 0:
            await message.answer("❌ Количество граммов должно быть больше 0", parse_mode="Markdown")
            return
        
        free_gold = get_free_gold()
        
        if free_gold < grams:
            await message.answer(
                f"❌ **Недостаточно золота на сервере**\n\n"
                f"🪙 Доступно: {free_gold:.2f} г\n"
                f"📊 Запрошено: {grams:.2f} г",
                parse_mode="Markdown"
            )
            return
        
        total_price = grams * GOLD_BASE_PRICE
        user = get_user(user_id)
        
        if user['balance'] < total_price:
            await message.answer(
                f"❌ **Недостаточно рублей**\n\n"
                f"💰 Стоимость: {total_price:.2f}₽\n"
                f"💰 Ваш баланс: {user['balance']:.2f}₽",
                parse_mode="Markdown"
            )
            return
        
        update_balance(user_id, -total_price)
        update_gold(user_id, grams)
        add_transaction(user_id, "gold_buy_from_server", -total_price, 0, None)
        
        user_after = get_user(user_id)
        
        await message.answer(
            f"✅ **Золото куплено!**\n\n"
            f"🪙 Куплено: {grams:.2f} г\n"
            f"💰 Цена: {GOLD_BASE_PRICE}₽/г\n"
            f"💵 Итого: {total_price:.2f}₽\n\n"
            f"🪙 Ваше золото теперь: {user_after['gold']:.2f} г",
            parse_mode="Markdown"
        )
    
    # ========== КУПИТЬ ЛОТ НА АУКЦИОНЕ (ЧЕРЕЗ КОМАНДУ) ==========
    async def gold_buy_lot(message: types.Message, lot_id: int):
        user_id = message.from_user.id
        
        lot = get_lot(lot_id)
        
        if not lot or lot['active'] != 1:
            await message.answer(f"❌ Лот `{lot_id}` не найден или уже продан", parse_mode="Markdown")
            return
        
        # Запрет на покупку своего лота
        if lot['seller_id'] == user_id:
            await message.answer("❌ Нельзя купить свой собственный лот!", parse_mode="Markdown")
            return
        
        total_price = lot['amount'] * lot['price']
        user = get_user(user_id)
        
        if user['balance'] < total_price:
            await message.answer(
                f"❌ **Недостаточно рублей**\n\n"
                f"💰 Стоимость лота: {total_price:.2f}₽\n"
                f"💰 Ваш баланс: {user['balance']:.2f}₽",
                parse_mode="Markdown"
            )
            return
        
        # Покупаем
        update_balance(user_id, -total_price)
        update_gold(user_id, lot['amount'])
        
        fee_rate = GOLD_SELL_FEE_ANON if lot['anonymous'] else GOLD_SELL_FEE
        fee_amount = total_price * fee_rate
        seller_get = total_price - fee_amount
        
        update_balance(lot['seller_id'], seller_get)
        close_lot(lot_id)
        
        add_transaction(user_id, "gold_buy", -total_price, 0, lot['seller_id'])
        add_transaction(lot['seller_id'], "gold_sell", seller_get, fee_amount, user_id)
        
        # Показываем username для неанонимного продавца
        if not lot['anonymous']:
            seller = get_user(lot['seller_id'])
            seller_name = f"@{seller['username']}" if seller['username'] else f"`{lot['seller_id']}`"
        else:
            seller_name = "🔒 Аноним"
        
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
    
    # ========== АУКЦИОН С РЕДАКТИРОВАНИЕМ ==========
    async def gold_auc(message: types.Message, page: int = 1, edit_msg: types.Message = None):
        user_id = message.from_user.id
        update_last_active(user_id)
        
        ITEMS_PER_PAGE = 7
        
        all_lots = get_active_lots()
        total_lots = len(all_lots)
        total_pages = (total_lots + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total_lots > 0 else 1
        
        if total_lots == 0:
            text = "🏪 **Аукцион пуст**\n\nВы можете выставить золото: `/gold sell [грамм] [цена]`"
            if edit_msg:
                await edit_msg.edit_text(text, parse_mode="Markdown")
            else:
                await message.answer(text, parse_mode="Markdown")
            return
        
        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages
        
        start = (page - 1) * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        lots = all_lots[start:end]
        
        keyboard = []
        for lot in lots:
            total_price = lot['amount'] * lot['price']
            button_text = f"🆔 {lot['lot_id']} | {lot['amount']:.1f}г | {lot['price']:.0f}₽/г | {total_price:.0f}₽"
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"gold_lot_{lot['lot_id']}")])
        
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"gold_page_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"gold_page_{page+1}"))
        keyboard.append(nav_buttons)
        keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"gold_refresh_{page}")])
        
        text = f"🏪 **Аукцион золота** — страница {page}/{total_pages}\n\n🪙 Всего лотов: {total_lots}\n💡 Нажми на лот для покупки"
        
        if edit_msg:
            await edit_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
        else:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    
    # ========== ДЕТАЛИ ЛОТА ДЛЯ ПОКУПКИ ==========
    async def show_lot_details(callback, lot_id: int):
        lot = get_lot(lot_id)
        
        if not lot or lot['active'] != 1:
            await callback.message.edit_text(f"❌ Лот `{lot_id}` уже продан", parse_mode="Markdown")
            return
        
        # Показываем username для неанонимного продавца
        if not lot['anonymous']:
            seller = get_user(lot['seller_id'])
            seller_name = f"@{seller['username']}" if seller['username'] else f"`{lot['seller_id']}`"
        else:
            seller_name = "🔒 Аноним"
        
        total_price = lot['amount'] * lot['price']
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Купить", callback_data=f"gold_buy_{lot_id}")],
            [InlineKeyboardButton(text="◀️ Вернуться в аукцион", callback_data="gold_back_to_auc")]
        ])
        
        await callback.message.edit_text(
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
    
    # ========== ОБРАБОТЧИКИ КНОПОК АУКЦИОНА ==========
    @dp.callback_query(lambda c: c.data.startswith('gold_'))
    async def gold_callback(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        data = callback.data.split('_')
        
        if data[1] == "page":
            page = int(data[2])
            await gold_auc(callback.message, page, edit_msg=callback.message)
            await callback.answer()
        
        elif data[1] == "refresh":
            page = int(data[2])
            await gold_auc(callback.message, page, edit_msg=callback.message)
            await callback.answer()
        
        elif data[1] == "lot":
            lot_id = int(data[2])
            await show_lot_details(callback, lot_id)
            await callback.answer()
        
        elif data[1] == "buy":
            lot_id = int(data[2])
            await gold_buy_callback(callback, lot_id)
            await callback.answer()
        
        elif data[1] == "mylot":
            lot_id = int(data[2])
            await show_my_lot_details(callback, lot_id)
            await callback.answer()
        
        elif data[1] == "remove":
            lot_id = int(data[3])
            await confirm_remove_lot(callback, lot_id)
            await callback.answer()
        
        elif data[1] == "confirm":
            lot_id = int(data[3])
            await remove_lot(callback, lot_id)
            await callback.answer()
        
        elif data[1] == "cancel":
            lot_id = int(data[3])
            await show_my_lot_details(callback, lot_id)
            await callback.answer()
    
    @dp.callback_query(lambda c: c.data == "gold_back_to_auc")
    async def gold_back_to_auc_callback(callback: types.CallbackQuery):
        await gold_auc(callback.message, page=1, edit_msg=callback.message)
        await callback.answer()
    
    @dp.callback_query(lambda c: c.data == "gold_mylots_refresh")
    async def gold_mylots_refresh_callback(callback: types.CallbackQuery):
        await gold_my_lots(callback.message)
        await callback.answer()
    
    @dp.callback_query(lambda c: c.data == "gold_mylots_back")
    async def gold_mylots_back_callback(callback: types.CallbackQuery):
        await gold_my_lots(callback.message)
        await callback.answer()
    
    async def gold_buy_callback(callback, lot_id: int):
        user_id = callback.from_user.id
        lot = get_lot(lot_id)
        
        if not lot or lot['active'] != 1:
            await callback.answer("❌ Лот уже продан!", show_alert=True)
            return
        
        # Запрет на покупку своего лота
        if lot['seller_id'] == user_id:
            await callback.answer("❌ Нельзя купить свой собственный лот!", show_alert=True)
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
        close_lot(lot_id)
        
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
    
    @dp.callback_query(lambda c: c.data == "noop")
    async def noop_callback(callback: types.CallbackQuery):
        await callback.answer()
