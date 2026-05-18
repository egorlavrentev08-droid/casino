# joker.py
import asyncio
import random
from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import MIN_BET, JOKER_RTP
from database import get_user, update_balance, add_transaction, update_last_active
from utils import anti_flood


class JokerGame:
    """
    Правила игры:
    - 3 карты в ряду
    - 1 джокер (проигрыш), 2 безопасные карты (победа)
    - При открытии безопасной карты → победа в раунде, даётся +30% +5% за каждый предыдущий раунд
    - При открытии джокера → мгновенный проигрыш всей игры
    - После каждой победы добавляется новый ряд (3 карты: 1 джокер, 2 безопасные)
    - Можно забрать выигрыш в любой момент
    """
    
    def __init__(self, uid, bet):
        self.uid = uid
        self.bet = bet
        self.rows = []           # [['🎴', '🃏', '🎴'], ...]
        self.safe_positions = [] # [[True, False, True], ...]  True = безопасная
        self.won_rounds = 0      # Количество выигранных раундов
        self.active = True
        self.last_update = 0
        self.add_first_row()
    
    def add_first_row(self):
        """Создаёт первый ряд: 1 джокер (проигрыш), 2 безопасные (победа)"""
        cards = ['🎴', '🎴', '🎴']
        safe = [True, True, True]
        
        # Выбираем случайную позицию для джокера (проигрыш)
        joker_pos = random.randint(0, 2)
        cards[joker_pos] = '🃏'
        safe[joker_pos] = False  # Джокер = проигрыш
        
        self.rows = [cards]
        self.safe_positions = [safe]
    
    def add_row(self):
        """Добавляет новый ряд после победы: 1 джокер, 2 безопасные"""
        cards = ['🎴', '🎴', '🎴']
        safe = [True, True, True]
        
        joker_pos = random.randint(0, 2)
        cards[joker_pos] = '🃏'
        safe[joker_pos] = False
        
        self.rows.append(cards)
        self.safe_positions.append(safe)
    
    def reveal(self, row_idx, col_idx):
        """
        Открывает карту
        Возвращает:
        - 'win' + множитель раунда, если открыта безопасная карта
        - 'lose', если открыт джокер
        - None, если карта уже открыта
        """
        if not self.active:
            return None
        
        if row_idx >= len(self.rows):
            return None
        
        card = self.rows[row_idx][col_idx]
        
        # Уже открыта?
        if card == '✅' or card == '❌':
            return None
        
        is_safe = self.safe_positions[row_idx][col_idx]
        
        if is_safe:
            # Победа в раунде
            self.rows[row_idx][col_idx] = '✅'
            self.won_rounds += 1
            self.add_row()  # Добавляем новый ряд
            
            # Рассчитываем множитель для этого раунда
            # База 1.0 + (0.30 + 0.05 * (раунд-1))
            # Раунд 1: +30% → 1.30x
            # Раунд 2: +35% → 1.65x
            # Раунд 3: +40% → 2.05x
            round_multiplier = 1.0 + (0.30 + 0.05 * (self.won_rounds - 1))
            
            # Применяем RTP к множителю раунда
            round_multiplier = round_multiplier * JOKER_RTP
            
            return ('win', round_multiplier)
        else:
            # Проигрыш — джокер
            self.rows[row_idx][col_idx] = '❌'
            self.active = False
            return ('lose', 0)
    
    def get_total_multiplier(self):
        """Рассчитывает общий множитель по всем раундам с учётом RTP"""
        if self.won_rounds == 0:
            return 1.0
        
        total = 1.0
        for i in range(self.won_rounds):
            # Каждый раунд: +30% + 5% за каждый предыдущий
            total += 0.30 + (i * 0.05)
        
        # Применяем RTP
        return total * JOKER_RTP
    
    def get_total_win(self):
        """Рассчитывает общий выигрыш по всем раундам"""
        if self.won_rounds == 0:
            return 0
        return self.bet * self.get_total_multiplier()
    
    def cashout(self):
        """Забирает выигрыш"""
        if not self.active:
            return 0
        
        win = self.get_total_win()
        if win > 0:
            update_balance(self.uid, win - self.bet)
            add_transaction(self.uid, "joker_win", win - self.bet, 0)
        
        self.active = False
        return win
    
    def get_final_board(self):
        """Показывает все карты в конце игры"""
        kb = InlineKeyboardBuilder()
        for row in self.rows:
            for card in row:
                if card == '🃏':
                    text = "💀"  # Джокер = проигрыш
                elif card == '🎴':
                    text = "✅"  # Неоткрытая безопасная
                else:
                    text = card
                kb.button(text=text, callback_data="noop")
            kb.adjust(3)
        return kb.as_markup()
    
    def get_current_board(self):
        """Показывает текущее состояние игры"""
        kb = InlineKeyboardBuilder()
        for r, row in enumerate(self.rows):
            for c, card in enumerate(row):
                if card == '✅' or card == '❌':
                    text = card
                else:
                    text = "❓"
                kb.button(text=text, callback_data=f"joker_{r}_{c}")
            kb.adjust(3)
        
        kb.row(InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="joker_cashout"))
        return kb.as_markup()


# Хранилище активных игр
joker_games = {}


def register_joker(dp):
    
    @dp.message(Command("joker"))
    async def cmd_joker(message: types.Message):
        user_id = message.from_user.id
        update_last_active(user_id)
        
        # Защита от флуда
        if not await anti_flood(user_id, cooldown=1):
            await message.answer("⏳ Слишком часто! Подожди секунду.", parse_mode="Markdown")
            return
        
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer(
                    "❌ **Использование:** `/joker [ставка]`\n\n"
                    "Пример: `/joker 1000`\n"
                    f"💰 Минимальная ставка: {MIN_BET}₽\n\n"
                    "🎴 **Правила:**\n"
                    "• В каждом ряду 3 карты: 1 джокер ❌, 2 безопасные ✅\n"
                    "• Открывай безопасные карты — получай +30% +5% за каждый раунд\n"
                    "• Откроешь джокера — проиграешь всё\n"
                    "• После каждой победы добавляется новый ряд\n"
                    "• Можно забрать выигрыш в любой момент\n\n"
                    f"📊 RTP: {JOKER_RTP*100:.0f}%",
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
            add_transaction(user_id, "joker_bet", -bet, 0)
            
            # Создаём игру
            game = JokerGame(user_id, bet)
            joker_games[user_id] = game
            
            await message.answer(
                f"🃏 **ДЖОКЕР**\n\n"
                f"🎲 Ставка: {bet:.2f}₽\n"
                f"📈 Начальный множитель: x1.0\n"
                f"📊 RTP: {JOKER_RTP*100:.0f}%\n\n"
                f"🎴 **Правила:**\n"
                f"• ✅ Безопасная карта — победа (+30% +5% за раунд)\n"
                f"• ❌ Джокер — мгновенный проигрыш\n"
                f"• После каждой победы добавляется новый ряд\n\n"
                f"❓ Открывай безопасные карты!",
                reply_markup=game.get_current_board(),
                parse_mode="Markdown"
            )
            
        except ValueError:
            await message.answer("❌ Неверный формат! Пример: `/joker 1000`", parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")
    
    # ========== ОБРАБОТКА КНОПОК ДЖОКЕРА ==========
    @dp.callback_query(lambda c: c.data.startswith('joker_'))
    async def joker_callback(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        update_last_active(user_id)
        
        game = joker_games.get(user_id)
        
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
        
        # ===== ЗАБРАТЬ ВЫИГРЫШ =====
        if callback.data == "joker_cashout":
            win = game.cashout()
            
            if win > 0:
                total_mult = win / game.bet
                await callback.message.edit_text(
                    f"💰 **Ты забрал {win:.2f}₽!**\n\n"
                    f"🎲 Ставка: {game.bet:.2f}₽\n"
                    f"📈 Итоговый множитель: x{total_mult:.3f}\n"
                    f"✅ Выигранных раундов: {game.won_rounds}",
                    parse_mode="Markdown"
                )
            else:
                await callback.message.edit_text(
                    f"❌ **Ты не выиграл ни одного раунда!**\n\n"
                    f"Ставка не возвращается.",
                    parse_mode="Markdown"
                )
            
            del joker_games[user_id]
            await callback.answer()
            return
        
        # ===== ОТКРЫТИЕ КАРТЫ =====
        try:
            _, r, c = callback.data.split('_')
            row, col = int(r), int(c)
        except:
            await callback.answer()
            return
        
        res = game.reveal(row, col)
        
        if res is None:
            await callback.answer("Эта карта уже открыта!", show_alert=False)
            return
        
        # ===== ПРОИГРЫШ (ДЖОКЕР) =====
        if res[0] == 'lose':
            final_board = game.get_final_board()
            await callback.message.edit_text(
                f"💀 **Ты открыл ДЖОКЕРА!** 💀\n\n"
                f"🎲 Ставка: {game.bet:.2f}₽\n"
                f"❌ Проигрыш: {game.bet:.2f}₽\n"
                f"✅ Выигранных раундов: {game.won_rounds}\n\n"
                f"**Вот где были карты:**",
                reply_markup=final_board,
                parse_mode="Markdown"
            )
            add_transaction(user_id, "joker_lose", -game.bet, 0)
            del joker_games[user_id]
            await callback.answer()
            return
        
        # ===== ПОБЕДА В РАУНДЕ =====
        if res[0] == 'win':
            round_mult = res[1]
            total_mult = game.get_total_multiplier()
            current_win = game.get_total_win()
            
            # Формируем сообщение с прогрессом
            await callback.message.edit_text(
                f"🃏 **ДЖОКЕР**\n\n"
                f"🎲 Ставка: {game.bet:.2f}₽\n"
                f"✅ Выигранных раундов: {game.won_rounds}\n"
                f"📈 Текущий множитель: x{total_mult:.3f}\n"
                f"💰 Возможный выигрыш: {current_win:.2f}₽\n\n"
                f"🎉 **Раунд {game.won_rounds} выигран!** +{round_mult:.2f}x\n\n"
                f"❓ Продолжай открывать безопасные карты или забери выигрыш!",
                reply_markup=game.get_current_board(),
                parse_mode="Markdown"
            )
            
            await callback.answer(f"✅ Победа в раунде {game.won_rounds}! +{round_mult:.2f}x")
            return
    
    # ========== ЗАГЛУШКА ДЛЯ NOOP ==========
    @dp.callback_query(lambda c: c.data == "noop")
    async def noop_callback(callback: types.CallbackQuery):
        await callback.answer()
