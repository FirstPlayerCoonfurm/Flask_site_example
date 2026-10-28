from flask import Flask, render_template
from admin import admin_bp
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = Flask(__name__)
app.secret_key = os.getenv('APP_SECRET', 'dev_secret_key')
app.register_blueprint(admin_bp)

DB_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:password@db:5432/kraken_metrics')

@app.route('/')
def index():
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Получаем настройку видимости блока спонсоров
    cursor.execute("SELECT value FROM site_settings WHERE key = 'sponsors_block_enabled'")
    setting = cursor.fetchone()
    sponsors_block_enabled = setting['value'] == 'true' if setting else True

    # Разделяем услуги на основные и спонсорские
    cursor.execute("SELECT * FROM services WHERE is_active = TRUE AND is_sponsor = FALSE ORDER BY sort_order ASC")
    main_services = cursor.fetchall()

    cursor.execute("SELECT * FROM services WHERE is_active = TRUE AND is_sponsor = TRUE ORDER BY sort_order ASC")
    sponsor_services = cursor.fetchall()

    conn.close()

    return render_template('index.html',
                         main_services=main_services,
                         sponsor_services=sponsor_services,
                         sponsors_block_enabled=sponsors_block_enabled)

@app.route('/tariffs')
def tariffs():
    return render_template('tariffs.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/contacts')
def contacts():
    return render_template('contacts.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
