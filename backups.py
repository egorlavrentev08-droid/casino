# backups.py
import os
import shutil
import asyncio
from datetime import datetime, timedelta


class BackupManager:
    def __init__(self, db_path="casino_bot.db"):
        self.db_path = db_path
        # Используем SHARED_DIR если есть, иначе ./shared
        self.shared_dir = os.environ.get("SHARED_DIR", "./shared")
        self.backup_dir = os.path.join(self.shared_dir, "backups")
        self.max_backups = 15  # максимум 15 бэкапов
        self.backup_interval = 60  # каждую минуту (60 секунд)
        
        # Создаём папку для бэкапов
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def get_backup_filename(self):
        """Генерирует имя бэкапа с меткой времени"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"casino_bot_backup_{timestamp}.db"
    
    def make_backup(self):
        """Создаёт один бэкап"""
        if not os.path.exists(self.db_path):
            print(f"⚠️ База данных {self.db_path} не найдена")
            return None
        
        try:
            backup_name = self.get_backup_filename()
            backup_path = os.path.join(self.backup_dir, backup_name)
            shutil.copy2(self.db_path, backup_path)
            print(f"✅ Бэкап создан: {backup_name}")
            return backup_path
        except Exception as e:
            print(f"❌ Ошибка бэкапа: {e}")
            return None
    
    def cleanup_old_backups(self):
        """Удаляет старые бэкапы, оставляя максимум max_backups"""
        try:
            backups = sorted([f for f in os.listdir(self.backup_dir) if f.endswith('.db')])
            
            # Удаляем лишние (кроме последнего)
            to_delete = len(backups) - self.max_backups
            if to_delete > 0:
                for old_file in backups[:to_delete]:
                    old_path = os.path.join(self.backup_dir, old_file)
                    os.remove(old_path)
                    print(f"🗑️ Удалён старый бэкап: {old_file}")
        except Exception as e:
            print(f"⚠️ Ошибка очистки бэкапов: {e}")
    
    def restore_latest_backup(self):
        """Восстанавливает последний бэкап"""
        try:
            backups = sorted([f for f in os.listdir(self.backup_dir) if f.endswith('.db')])
            if not backups:
                print("📁 Нет бэкапов для восстановления")
                return False
            
            latest = backups[-1]
            latest_path = os.path.join(self.backup_dir, latest)
            
            # Восстанавливаем
            shutil.copy2(latest_path, self.db_path)
            print(f"✅ База данных восстановлена из {latest}")
            return True
        except Exception as e:
            print(f"❌ Ошибка восстановления: {e}")
            return False
    
    async def start_backup_loop(self):
        """Запускает бесконечный цикл бэкапов"""
        print("🔄 Система авто-бэкапа запущена (каждую минуту)")
        print(f"📁 Папка бэкапов: {self.backup_dir}")
        print(f"📦 Максимум бэкапов: {self.max_backups}")
        
        # При запуске создаём первый бэкап
        self.make_backup()
        
        while True:
            await asyncio.sleep(self.backup_interval)
            self.make_backup()
            self.cleanup_old_backups()


# Глобальный экземпляр для использования в боте
backup_manager = BackupManager()


def get_shared_dir():
    """Возвращает путь к общей папке"""
    return backup_manager.shared_dir
