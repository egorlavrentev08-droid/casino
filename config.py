# config.py
API_TOKEN = "8839921122:AAEz5S6wZpCGffxaduTyKtzuZlWVIO3avMs"
ADMIN_ID = 6595788533  # Твой Telegram ID

# Коды доступа
ADMIN_CODE = "14916253649"

# Бонусы и лимиты
DAILY_BONUS = 10000
MAX_BALANCE_FOR_BONUS = 50000  # Если баланс >50к, бонус не даётся

# Лимиты переводов
DAILY_TRANSFER_LIMIT_FREE = 5000      # До 5к — без комиссии
DAILY_TRANSFER_LIMIT_LOW = 25000      # 25к — комиссия 13%
DAILY_TRANSFER_LIMIT_HIGH = 50000     # 50к — комиссия 25%

TRANSFER_FEE_LOW = 0.13   # 13%
TRANSFER_FEE_HIGH = 0.25  # 25%

# Лимиты на получение денег
DAILY_RECEIVE_LIMIT_FREE = 10000      # До 10к — без комиссии
DAILY_RECEIVE_LIMIT_MEDIUM = 50000    # До 50к — комиссия 20%
RECEIVE_FEE_MEDIUM = 0.20
RECEIVE_FEE_HIGH = 0.50

# Матожидание игр (RTP)
MINES_RTP = 0.88
ROULETTE_RTP = 0.90

# Золото
TOTAL_GOLD = 100000          # Всего золота на сервере
GOLD_BASE_PRICE = 1000       # Цена 1 грамма в рублях (если покупается с сервера)
GOLD_SELL_FEE = 0.07         # Комиссия при продаже 7%
GOLD_SELL_FEE_ANON = 0.11    # Комиссия при анонимной продаже 11%
GOLD_LISTING_MULTIPLIER = 0.001  # 1 грамм = +0.1% к листингу

# Ставки
MIN_BET = 10

# Время неактивности для сброса
INACTIVE_DAYS = 30
