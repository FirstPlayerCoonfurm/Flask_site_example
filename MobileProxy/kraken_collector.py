import os
import time
import requests
import psycopg2
from datetime import datetime

KRAKEN_API_URL = os.getenv('KRAKEN_API_URL', 'https://api.kraken.dev')
KRAKEN_API_KEY = os.getenv('KRAKEN_API_KEY', '')
DB_URL = os.getenv('DATABASE_URL', 'postgresql://umami:umami@umami-db:5432/umami')

def get_db():
    return psycopg2.connect(DB_URL)

def init_db():
    """Создаём таблицу при запуске, если её нет"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kraken_metrics (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            total_traffic_gb FLOAT,
            active_sessions INT,
            total_users INT,
            revenue_rub FLOAT
        )
    """)
    conn.commit()
    conn.close()
    print("✅ Таблица kraken_metrics проверена/создана.")

def collect_and_save():
    if not KRAKEN_API_KEY or KRAKEN_API_KEY == 'your_kraken_api_key_here':
        print("⚠️ Kraken API ключ не настроен. Пропускаю сбор.")
        return

    try:
        headers = {'Authorization': f'Bearer {KRAKEN_API_KEY}'}
        # ВНИМАНИЕ: Замени этот URL на реальный эндпоинт статистики твоего Kraken API
        response = requests.get(f'{KRAKEN_API_URL}/api/v1/stats', headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Адаптируй ключи под реальный ответ твоего API
        metrics = {
            'total_traffic_gb': float(data.get('total_traffic_gb', 0)),
            'active_sessions': int(data.get('active_sessions', 0)),
            'total_users': int(data.get('total_users', 0)),
            'revenue_rub': float(data.get('revenue', 0))
        }

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO kraken_metrics (total_traffic_gb, active_sessions, total_users, revenue_rub)
            VALUES (%s, %s, %s, %s)
        """, (metrics['total_traffic_gb'], metrics['active_sessions'], metrics['total_users'], metrics['revenue_rub']))
        conn.commit()
        conn.close()

        print(f"✅ Метрики сохранены: Трафик={metrics['total_traffic_gb']} ГБ, Сессии={metrics['active_sessions']}")

    except Exception as e:
        print(f"❌ Ошибка сбора метрик: {e}")

if __name__ == '__main__':
    print("🚀 Запуск Kraken Collector...")
    init_db()
    while True:
        collect_and_save()
        time.sleep(300)  # Сбор каждые 5 минут
