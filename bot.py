# bot.py
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from config import API_TOKEN, BACKUP_INTERVAL_MINUTES
from database import init_db
from core import register_core
from admin import register_admin
from roulette import register_roulette
from mines import register_mines
from joker import register_joker
from gold import register_gold
from backups import check_and_restore_db, auto_backup


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()


# ========== НАСТРОЙКА КОМАНД В МЕНЮ ==========
async def set_commands():
    """Устанавливает список команд в меню бота"""
    commands = [
        BotCommand(command="start", description="🚀 Главное меню"),
        BotCommand(command="balance", description="💰 Баланс"),
        BotCommand(command="bonus", description="🎁 Ежедневный бонус"),
        BotCommand(command="pay", description="📤 Перевести деньги"),
        BotCommand(command="mines", description="💣 Мины (ставка)"),
        BotCommand(command="roulette", description="🎡 Рулетка (ставка)"),
        BotCommand(command="joker", description="🃏 Джокер (ставка)"),
        BotCommand(command="gold", description="🪙 Золото и аукцион"),
        BotCommand(command="anon", description="🕵️ Анонимная продажа"),
        BotCommand(command="deanon", description="👤 Публичная продажа"),
    ]
    await bot.set_my_commands(commands)


# ========== РЕГИСТРАЦИЯ ВСЕХ ОБРАБОТЧИКОВ ==========
def register_all_handlers():
    """Регистрирует все команды из модулей"""
    register_core(dp)      # /start, /balance, /bonus, /pay, /anon, /deanon
    register_admin(dp)     # Админ-команды
    register_roulette(dp)  # /roulette
    register_mines(dp)     # /mines
    register_joker(dp)     # /joker
    register_gold(dp)      # /gold
    logger.info("✅ Все обработчики зарегистрированы")


# ========== ФОНОВЫЙ БЭКАП ==========
async def backup_loop():
    """Фоновый процесс для автоматического бэкапа"""
    while True:
        await asyncio.sleep(60 * BACKUP_INTERVAL_MINUTES)  # каждые N минут
        auto_backup()
        logger.info("💾 Автоматический бэкап выполнен")


# ========== ЗАПУСК БОТА ==========
async def main():
    """Главная функция запуска"""
    logger.info("🚀 Запуск бота...")
    
    # Проверка и восстановление базы данных при запуске
    if not check_and_restore_db():
        logger.critical("❌ Не удалось восстановить базу данных! Бот не может запуститься.")
        return
    
    # Инициализация базы данных
    init_db()
    logger.info("✅ База данных инициализирована")
    
    # Настройка команд в меню
    await set_commands()
    logger.info("✅ Команды меню установлены")
    
    # Регистрация всех обработчиков
    register_all_handlers()
    
    # Запускаем фоновый процесс бэкапов
    asyncio.create_task(backup_loop())
    logger.info(f"💾 Автобэкап запущен (каждые {BACKUP_INTERVAL_MINUTES} минут)")
    
    # Запуск поллинга
    logger.info("🎰 Бот запущен и готов к работе!")
    print("🎰 КАЗИНО БОТ ЗАПУЩЕН!")
    print(f"📊 Бот @{(await bot.get_me()).username}")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("🛑 Бот остановлен")


# ========== ТОЧКА ВХОДА ==========
if __name__ == "__main__":
    asyncio.run(main())
