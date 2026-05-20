# backups.py
import os
import glob
import shutil
from datetime import datetime, timedelta

from config import BACKUP_DIR, BACKUP_RETENTION_DAYS


def get_latest_backup():
    """Найти самый свежий бэкап"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        return None
    backups = glob.glob(os.path.join(BACKUP_DIR, "casino_bot.db.backup_*.db"))
    if not backups:
        return None
    return max(backups, key=os.path.getctime)


def restore_from_backup(backup_path):
    """Восстановить базу из бэкапа"""
    try:
        if not os.path.exists(backup_path):
            return False
        shutil.copy2(backup_path, 'casino_bot.db')
        print(f"✅ База данных восстановлена из бэкапа: {backup_path}")
        return True
    except Exception as e:
        print(f"❌ Ошибка восстановления: {e}")
        return False


def check_and_restore_db():
    """Проверить базу при запуске и восстановить при необходимости"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    if os.path.exists('casino_bot.db'):
        if os.path.getsize('casino_bot.db') > 0:
            print("✅ База данных найдена, проверка пройдена")
            return True
        else:
            print("⚠️ База данных повреждена (0 байт)!")
    
    print("⚠️ База данных отсутствует или повреждена! Пытаюсь восстановить из бэкапа...")
    
    latest = get_latest_backup()
    if latest and restore_from_backup(latest):
        print("✅ База данных успешно восстановлена из последнего бэкапа")
        return True
    
    print("⚠️ Бэкапов не найдено. Будет создана новая база данных.")
    return True


def auto_backup():
    """Автоматическое создание бэкапа базы данных"""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        
        db_path = 'casino_bot.db'
        if not os.path.exists(db_path):
            print(f"⚠️ База данных не найдена по пути {db_path}, бэкап не создан")
            return
        
        if os.path.getsize(db_path) == 0:
            print("⚠️ База данных пуста, бэкап не создан")
            return
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"casino_bot.db.backup_{timestamp}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        shutil.copy2(db_path, backup_path)
        
        # Удаляем старые бэкапы
        backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "casino_bot.db.backup_*.db")))
        cutoff = datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS)
        
        for backup in backups[:-1]:  # оставляем последний
            try:
                date_str = backup.split('_')[-1].replace('.db', '')
                backup_date = datetime.strptime(date_str, '%Y%m%d_%H%M%S')
                if backup_date < cutoff:
                    os.remove(backup)
                    print(f"🗑️ Удалён старый бэкап: {os.path.basename(backup)}")
            except (ValueError, IndexError):
                continue
            except Exception as e:
                print(f"❌ Ошибка при удалении старого бэкапа: {e}")
        
        size = os.path.getsize(backup_path) / 1024
        print(f"💾 Автобэкап создан: {backup_name} ({size:.1f} КБ)")
        
    except Exception as e:
        print(f"❌ Ошибка автобэкапа: {e}")
