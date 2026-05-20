# mines.py
import asyncio
import random
from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import MIN_BET, MINES_RTP, MINES_MULTIPLIERS
from database import get_user, update_balance, add_transaction, update_last_active
from utils import anti_flood


class MinesGame:
    """
    Правила игры:
    - Поле 5×5 (25 клеток)
    - Всегда 5 мин
    - 20 безопасных клеток
    - Множители из конфига (MINES_MULTIPLIERS)
    - При открытии мины → проигрыш
    - Можно забрать выигрыш в любой момент
    """
    
    def __init__(self, uid, bet, username):
        self.uid = uid
        self.owner_id = uid
        self.owner_username = username or f"id{uid}"
        self.bet = bet
        self.mines = 5  # Всегда 5 мин
        self.field = [[0]*5 for _ in range(5)]
        self.revealed = [[False]*5 for _ in range(5)]
        self.active = True
        self.last_update = 0
        self.opened_count = 0  # Количество открытых безопасных клеток
        
        # Размещаем 5 мин случайно
        positions = [(i, j) for i in range(5) for j in range(5)]
        mine_positions = random.sample(positions, self.mines)
        for i, j in mine_positions:
            self.field[i][j] = 1
    
    def get_multiplier(self):
        """Возвращает множитель по количеству открытых клеток"""
        return MINES_MULTIPLIERS.get(self.opened_count, 1.0)
    
    def reveal(self, row, col):
        """
        Открывает клетку
        Возвращает (статус, opened_count, multiplier)
        """
        if not self.active or self.revealed[row][col]:
            return None
        
        self.revealed[row][col] = True
        
        if self.field[row][col] == 1:
            # Попали на мину
            self.active = False
            return ('lose', self.opened_count, 0)
        else:
            # Безопасная клетка
            self.opened_count += 1
            mult = self.get_multiplier()
            return ('win', self.opened_count, mult)
    
    def cashout(self):
        """Забирает выигрыш"""
        if not self.active:
            return 0
        
        if self.opened_count == 0:
            return 0
        
        mult = self.get_multiplier()
        win = self.bet * mult
        update_balance(self.uid, win - self.bet)
        add_transaction(self.uid, "mines_win", win - self.bet, 0)
        self.active = False
        return win
    
    def get_final_board(self):
        """Показывает финальное поле с минами"""
        kb = InlineKeyboardBuilder()
        for i in range(5):
            for j in range(5):
                if self.field[i][j] == 1:
                    text = "💣"
                elif self.revealed[i][j]:
                    text = "⭐"
                else:
                    text = "❓"
                kb.button(text=text, callback_data="noop")
            kb.adjust(5)
        return kb.as_markup()
    
    def get_current_board(self):
        """Показывает текущее состояние игры"""
        kb = InlineKeyboardBuilder()
        for i in range(5):
            for j in range(5):
                if self.revealed[i][j]:
                    if self.field[i][j] == 1:
                        text = "💣"
                    else:
                        text = "⭐"
                else:
                    text = "❓"
                kb.button(text=text, callback_data=f"mine_{i}_{j}")
            kb.adjust(5)
        
        kb.row(
            InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="mine_cashout"),
            InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="mine_cancel")
        )
        return kb.as_markup()


# Хранилище активных игр (ключ = owner_id)
mines_games = {}


def register_mines(dp):
    
    @dp.message(Command("mines"))
    async def cmd_mines(message: types.Message):
        user_id = message.from_user.id
        username = message.from_user.username
        update_last_active(user_id)
        
        # Проверка на активную игру
        if user_id in mines_games:
            await message.answer(
                "❌ У тебя уже есть активная игра!\n"
                "Закончи её или забери выигрыш.",
                parse_mode="Markdown"
            )
            return
        
        # Защита от флуда
        if not await anti_flood(user_id, cooldown=1):
            await message.answer("⏳ Слишком часто! Подожди секунду.", parse_mode="Markdown")
            return
        
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer(
                    "❌ **Использование:** `/mines [ставка]`\n\n"
                    "Пример: `/mines 1000`\n"
                    f"💰 Минимальная ставка: {MIN_BET}₽\n\n"
                    "💣 **Правила:**\n"
                    "• Поле 5×5, всегда 5 мин\n"
                    "• 20 безопасных клеток\n"
                    "• Открывай безопасные клетки\n"
                    "• Чем больше откроешь, тем выше множитель\n"
                    "• Наступишь на мину — проиграешь всё\n"
                    "• Можно забрать выигрыш в любой момент",
                    parse_mode="Markdown"
                )
                return
            
            bet = float(parts[1])
            
            if bet < MIN_BET:
                await message.answer(f"❌ Минимальная ставка: {MIN_BET}₽", parse_mode="Markdown")
                return
            
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
            add_transaction(user_id, "mines_bet", -bet, 0)
            
            # Создаём игру
            game = MinesGame(user_id, bet, username)
            mines_games[user_id] = game
            
            await message.answer(
                f"💣 **МИНЫ** | 👤 @{username or f'id{user_id}'}\n"
                f"🎲 Ставка: {bet:.2f}₽\n"
                f"📈 Множитель: x1.0\n\n"
                f"❓ Открывай клетки, но не наступи на мину!\n"
                f"💰 Забрать можно в любой момент.",
                reply_markup=game.get_current_board(),
                parse_mode="Markdown"
            )
            
        except ValueError:
            await message.answer("❌ Неверный формат! Пример: `/mines 1000`", parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")
    
    # ========== ОБРАБОТКА КНОПОК МИН ==========
    @dp.callback_query(lambda c: c.data.startswith('mine_'))
    async def mines_callback(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        update_last_active(user_id)
        
        # Проверяем, есть ли игра у этого пользователя
        game = mines_games.get(user_id)
        
        if not game:
            await callback.answer("❌ У тебя нет активной игры! Используй /mines", show_alert=True)
            return
        
        if not game.active:
            await callback.answer("❌ Эта игра уже завершена!", show_alert=True)
            return
        
        # Защита от флуда
        now = asyncio.get_event_loop().time()
        if now - game.last_update < 0.5:
            await callback.answer("⏳ Не так быстро!", show_alert=False)
            return
        game.last_update = now
        
        action = callback.data.split('_')
        
        # ===== ОТМЕНА =====
        if action[1] == 'cancel':
            update_balance(user_id, game.bet)
            add_transaction(user_id, "mines_cancel", game.bet, 0)
            del mines_games[user_id]
            await callback.message.edit_text(
                f"❌ Игра отменена | 👤 @{game.owner_username}",
                parse_mode="Markdown"
            )
            await callback.answer()
            return
        
        # ===== ЗАБРАТЬ ВЫИГРЫШ =====
        if action[1] == 'cashout':
            win = game.cashout()
            final_board = game.get_final_board()
            
            if win > 0:
                mult = win / game.bet
                await callback.message.edit_text(
                    f"💰 **@{game.owner_username} забрал {win:.2f}₽!**\n"
                    f"🎲 {game.bet:.2f}₽ → x{mult:.2f} | ⭐ {game.opened_count}/20",
                    reply_markup=final_board,
                    parse_mode="Markdown"
                )
            else:
                await callback.message.edit_text(
                    f"❌ **@{game.owner_username} не открыл ни одной клетки!**\n"
                    f"🎲 {game.bet:.2f}₽ проиграно",
                    parse_mode="Markdown"
                )
            
            del mines_games[user_id]
            await callback.answer()
            return
        
        # ===== ОТКРЫТИЕ КЛЕТКИ =====
        try:
            row, col = int(action[1]), int(action[2])
        except:
            await callback.answer()
            return
        
        res = game.reveal(row, col)
        
        # Проигрыш (мина)
        if res[0] == 'lose':
            final_board = game.get_final_board()
            await callback.message.edit_text(
                f"💥 **@{game.owner_username} наступил на мину!**\n"
                f"🎲 {game.bet:.2f}₽ проиграно | ⭐ {game.opened_count}/20",
                reply_markup=final_board,
                parse_mode="Markdown"
            )
            add_transaction(user_id, "mines_lose", -game.bet, 0)
            del mines_games[user_id]
            await callback.answer()
            return
        
        # Победа (продолжаем)
        opened, mult = res[1], res[2]
        current_win = game.bet * mult
        
        # Проверка: все безопасные клетки открыты? (20 клеток)
        if opened == 20:
            win = game.cashout()
            final_board = game.get_final_board()
            await callback.message.edit_text(
                f"🎉 **@{game.owner_username} собрал всё поле!**\n"
                f"🎲 {game.bet:.2f}₽ → x{mult:.2f} = {win:.2f}₽",
                reply_markup=final_board,
                parse_mode="Markdown"
            )
            del mines_games[user_id]
            await callback.answer()
            return
        
        # Обновляем поле
        await callback.message.edit_text(
            f"💣 **МИНЫ** | 👤 @{game.owner_username}\n"
            f"🎲 Ставка: {game.bet:.2f}₽\n"
            f"⭐ Открыто: {opened}/20 | 📈 x{mult:.2f}\n"
            f"💰 Выигрыш: {current_win:.2f}₽",
            reply_markup=game.get_current_board(),
            parse_mode="Markdown"
        )
        
        await callback.answer()
    
    # ========== ЗАГЛУШКА ДЛЯ NOOP ==========
    @dp.callback_query(lambda c: c.data == "noop")
    async def noop_callback(callback: types.CallbackQuery):
        await callback.answer()
