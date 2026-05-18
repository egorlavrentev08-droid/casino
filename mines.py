# mines.py
import asyncio
import random
from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import MIN_BET, MINES_RTP
from database import get_user, update_balance, add_transaction, update_last_active
from utils import anti_flood


class MinesGame:
    def __init__(self, uid, bet, mines):
        self.uid = uid
        self.bet = bet
        self.mines = mines
        self.field = [[0]*5 for _ in range(5)]
        self.revealed = [[False]*5 for _ in range(5)]
        self.active = True
        self.last_update = 0
        
        # Размещаем мины
        positions = [(i, j) for i in range(5) for j in range(5)]
        mine_positions = random.sample(positions, mines)
        for i, j in mine_positions:
            self.field[i][j] = 1
    
    def get_multiplier(self, opened):
        """
        Рассчитывает множитель с учётом RTP = 0.88
        Формула: multiplier = (safe_cells / (safe_cells - opened)) * RTP
        """
        if opened == 0:
            return 1.0
        
        safe_cells = 25 - self.mines
        if opened >= safe_cells:
            return (safe_cells / 1) * MINES_RTP
        
        # Честный множитель (без учёта RTP)
        fair_mult = (safe_cells / (safe_cells - opened))
        
        # Применяем RTP
        return fair_mult * MINES_RTP
    
    def reveal(self, row, col):
        """Открывает клетку, возвращает (статус, открыто, множитель)"""
        if not self.active or self.revealed[row][col]:
            return None
        
        self.revealed[row][col] = True
        opened = sum(sum(row) for row in self.revealed)
        
        if self.field[row][col] == 1:
            # Попали на мину
            self.active = False
            return ('lose', opened, 0)
        else:
            # Безопасная клетка
            mult = self.get_multiplier(opened)
            return ('win', opened, mult)
    
    def cashout(self):
        """Забирает выигрыш"""
        if not self.active:
            return 0
        
        opened = sum(sum(row) for row in self.revealed)
        if opened == 0:
            return 0
        
        mult = self.get_multiplier(opened)
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
                text = "💣" if self.field[i][j] else "⭐"
                kb.button(text=text, callback_data="noop")
            kb.adjust(5)
        return kb.as_markup()
    
    def get_current_board(self):
        """Показывает текущее состояние игры"""
        kb = InlineKeyboardBuilder()
        for i in range(5):
            for j in range(5):
                if self.revealed[i][j]:
                    text = "💣" if self.field[i][j] else "⭐"
                else:
                    text = "❓"
                kb.button(text=text, callback_data=f"mine_{i}_{j}")
            kb.adjust(5)
        
        kb.row(
            InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="mine_cashout"),
            InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="mine_cancel")
        )
        return kb.as_markup()


# Хранилище активных игр
mines_games = {}


def register_mines(dp):
    
    @dp.message(Command("mines"))
    async def cmd_mines(message: types.Message):
        user_id = message.from_user.id
        update_last_active(user_id)
        
        # Защита от флуда
        if not await anti_flood(user_id, cooldown=1):
            await message.answer("⏳ Слишком часто! Подожди секунду.", parse_mode="Markdown")
            return
        
        try:
            parts = message.text.split()
            if len(parts) < 3:
                await message.answer(
                    "❌ **Использование:** `/mines [мин] [ставка]`\n\n"
                    "Пример: `/mines 5 1000`\n"
                    "🎲 Мин: от 3 до 24\n"
                    f"💰 Минимальная ставка: {MIN_BET}₽",
                    parse_mode="Markdown"
                )
                return
            
            mines = int(parts[1])
            bet = float(parts[2])
            
            # Проверки
            if mines < 3 or mines > 24:
                await message.answer("❌ Количество мин должно быть от 3 до 24", parse_mode="Markdown")
                return
            
            if bet < MIN_BET:
                await message.answer(f"❌ Минимальная ставка: {MIN_BET}₽", parse_mode="Markdown")
                return
            
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
            add_transaction(user_id, "mines_bet", -bet, 0)
            
            # Создаём игру
            game = MinesGame(user_id, bet, mines)
            mines_games[user_id] = game
            
            # Показываем поле
            await message.answer(
                f"💣 **МИНЫ** | RTP: {MINES_RTP*100:.0f}%\n\n"
                f"🎲 Ставка: {bet:.2f}₽\n"
                f"💣 Мин на поле: {mines}\n"
                f"📈 Начальный множитель: x{game.get_multiplier(0):.3f}\n\n"
                f"❓ Открывай клетки, но не наступи на мину!\n"
                f"💰 Забрать выигрыш можно в любой момент.",
                reply_markup=game.get_current_board(),
                parse_mode="Markdown"
            )
            
        except ValueError:
            await message.answer("❌ Неверный формат! Пример: `/mines 5 1000`", parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")
    
    # ========== ОБРАБОТКА КНОПОК МИН ==========
    @dp.callback_query(lambda c: c.data.startswith('mine_'))
    async def mines_callback(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        update_last_active(user_id)
        
        game = mines_games.get(user_id)
        
        if not game:
            await callback.answer("❌ У тебя нет активной игры!", show_alert=True)
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
            # Возвращаем ставку
            update_balance(user_id, game.bet)
            add_transaction(user_id, "mines_cancel", game.bet, 0)
            del mines_games[user_id]
            await callback.message.edit_text("❌ Игра отменена. Ставка возвращена.", parse_mode="Markdown")
            await callback.answer()
            return
        
        # ===== ЗАБРАТЬ ВЫИГРЫШ =====
        if action[1] == 'cashout':
            win = game.cashout()
            final_board = game.get_final_board()
            
            if win > 0:
                await callback.message.edit_text(
                    f"💰 **Ты забрал {win:.2f}₽!**\n\n"
                    f"🎲 Ставка: {game.bet:.2f}₽\n"
                    f"📈 Итоговый множитель: x{win/game.bet:.3f}\n\n"
                    f"💣 **Где были мины:**",
                    reply_markup=final_board,
                    parse_mode="Markdown"
                )
            else:
                await callback.message.edit_text(
                    f"❌ **Ты не открыл ни одной клетки!**\n\n"
                    f"Ставка не возвращается.",
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
                f"💥 **Ты наступил на мину!**\n\n"
                f"🎲 Ставка: {game.bet:.2f}₽\n"
                f"❌ Проигрыш: {game.bet:.2f}₽\n\n"
                f"💣 **Где были мины:**",
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
        
        # Проверка: все безопасные клетки открыты?
        safe_cells = 25 - game.mines
        if opened == safe_cells:
            # Победа! Все клетки открыты
            win = game.cashout()
            final_board = game.get_final_board()
            await callback.message.edit_text(
                f"🎉 **ПОБЕДА!** 🎉\n\n"
                f"🎲 Ставка: {game.bet:.2f}₽\n"
                f"📈 Множитель: x{mult:.3f}\n"
                f"💰 Выигрыш: {win:.2f}₽\n\n"
                f"💣 **Где были мины:**",
                reply_markup=final_board,
                parse_mode="Markdown"
            )
            add_transaction(user_id, "mines_win", win - game.bet, 0)
            del mines_games[user_id]
            await callback.answer()
            return
        
        # Обновляем поле
        await callback.message.edit_text(
            f"💣 **МИНЫ** | RTP: {MINES_RTP*100:.0f}%\n\n"
            f"🎲 Ставка: {game.bet:.2f}₽\n"
            f"✅ Открыто клеток: {opened}/{safe_cells}\n"
            f"📈 Текущий множитель: x{mult:.3f}\n"
            f"💰 Возможный выигрыш: {current_win:.2f}₽\n\n"
            f"❓ Продолжай открывать клетки или забери выигрыш!",
            reply_markup=game.get_current_board(),
            parse_mode="Markdown"
        )
        
        await callback.answer()
    
    # ========== ЗАГЛУШКА ДЛЯ NOOP ==========
    @dp.callback_query(lambda c: c.data == "noop")
    async def noop_callback(callback: types.CallbackQuery):
        await callback.answer()
