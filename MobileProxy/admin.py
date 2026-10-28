import os
import functools
from datetime import datetime, timedelta
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash, jsonify
)
import psycopg2
from psycopg2.extras import RealDictCursor
import requests

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'change_me_please')
KRAKEN_API_URL = os.getenv('KRAKEN_API_URL', 'https://api.kraken.dev')
KRAKEN_API_KEY = os.getenv('KRAKEN_API_KEY', '')
DB_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:password@db:5432/kraken_metrics')


def get_db():
    return psycopg2.connect(DB_URL)


def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== АВТОРИЗАЦИЯ ====================

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Неверный пароль', 'error')
    return render_template('admin/login.html')


@admin_bp.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin.login'))


# ==================== ДАШБОРД ====================

@admin_bp.route('/')
@login_required
def dashboard():
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("""
            SELECT date_trunc('day', timestamp) as day,
                   SUM(total_traffic_gb) as traffic,
                   AVG(active_sessions) as avg_sessions,
                   SUM(revenue_rub) as revenue
            FROM kraken_metrics
            WHERE timestamp >= NOW() - INTERVAL '7 days'
            GROUP BY day
            ORDER BY day
        """)
        kraken_week = cursor.fetchall()

        cursor.execute("SELECT * FROM kraken_metrics ORDER BY timestamp DESC LIMIT 1")
        latest = cursor.fetchone()
    except Exception as e:
        print(f"Kraken metrics error: {e}")
        kraken_week = []
        latest = None

    # Безопасный запрос к таблице Umami (её может не быть в этой БД)
    site_visits = 0
    try:
        cursor.execute("""
            SELECT COUNT(DISTINCT session_id) as visits
            FROM website_event
            WHERE created_at >= NOW() - INTERVAL '7 days'
        """)
        row = cursor.fetchone()
        if row:
            site_visits = row['visits']
    except Exception as e:
        print(f"Umami table not available: {e}")

    conn.close()
    return render_template('admin/dashboard.html',
                           kraken_week=kraken_week,
                           latest=latest,
                           site_visits=site_visits)


# ==================== МЕТРИКИ KRAKEN ====================

@admin_bp.route('/metrics')
@login_required
def metrics():
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    period = request.args.get('period', '7d')
    intervals = {
        '24h': "INTERVAL '24 hours'",
        '7d': "INTERVAL '7 days'",
        '30d': "INTERVAL '30 days'",
    }
    interval = intervals.get(period, intervals['7d'])

    try:
        cursor.execute(f"""
            SELECT * FROM kraken_metrics
            WHERE timestamp >= NOW() - {interval}
            ORDER BY timestamp DESC
        """)
        rows = cursor.fetchall()
    except Exception as e:
        print(f"Metrics error: {e}")
        rows = []

    conn.close()
    return render_template('admin/metrics.html', rows=rows, period=period)


@admin_bp.route('/api/kraken/live')
@login_required
def kraken_live():
    if not KRAKEN_API_KEY:
        return jsonify({'error': 'Kraken API key not configured'}), 500
    try:
        headers = {'Authorization': f'Bearer {KRAKEN_API_KEY}'}
        stats = requests.get(f'{KRAKEN_API_URL}/api/v1/stats', headers=headers, timeout=5).json()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== АНАЛИТИКА ====================

@admin_bp.route('/analytics')
@login_required
def analytics():
    return render_template('admin/analytics.html')


# ==================== ПОЛЬЗОВАТЕЛИ ====================

@admin_bp.route('/users')
@login_required
def users():
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort', 'name')
    order = request.args.get('order', 'asc')

    users_list = []
    error = None

    if KRAKEN_API_KEY:
        try:
            headers = {'Authorization': f'Bearer {KRAKEN_API_KEY}'}
            response = requests.get(f'{KRAKEN_API_URL}/api/v1/users', headers=headers, timeout=10)
            response.raise_for_status()
            raw_users = response.json()

            if isinstance(raw_users, list):
                users_list = raw_users
            elif isinstance(raw_users, dict) and 'users' in raw_users:
                users_list = raw_users['users']
            else:
                users_list = [raw_users] if isinstance(raw_users, dict) else []

            if search:
                search_lower = search.lower()
                users_list = [
                    u for u in users_list
                    if search_lower in str(u.get('name', '')).lower()
                    or search_lower in str(u.get('email', '')).lower()
                    or search_lower in str(u.get('id', '')).lower()
                ]

            reverse = (order == 'desc')
            if sort_by == 'traffic':
                users_list.sort(key=lambda x: float(x.get('traffic_gb', 0) or 0), reverse=reverse)
            elif sort_by == 'balance':
                users_list.sort(key=lambda x: float(x.get('balance', 0) or 0), reverse=reverse)
            elif sort_by == 'name':
                users_list.sort(key=lambda x: str(x.get('name', '')).lower(), reverse=reverse)

        except requests.exceptions.RequestException as e:
            error = f'Ошибка подключения к Kraken API: {str(e)}'
        except Exception as e:
            error = f'Ошибка обработки данных: {str(e)}'
    else:
        error = 'Kraken API key не настроен'

    return render_template('admin/users.html',
                           users=users_list,
                           search=search,
                           sort_by=sort_by,
                           order=order,
                           error=error)


@admin_bp.route('/users/<user_id>')
@login_required
def user_detail(user_id):
    user_data = None
    user_metrics = []
    error = None
    period = request.args.get('period', '7d')

    if KRAKEN_API_KEY:
        try:
            headers = {'Authorization': f'Bearer {KRAKEN_API_KEY}'}
            user_response = requests.get(f'{KRAKEN_API_URL}/api/v1/users/{user_id}',
                                         headers=headers, timeout=10)
            user_response.raise_for_status()
            user_data = user_response.json()

            intervals = {'24h': 24, '7d': 168, '30d': 720}
            hours = intervals.get(period, 168)

            metrics_response = requests.get(
                f'{KRAKEN_API_URL}/api/v1/users/{user_id}/traffic?hours={hours}',
                headers=headers, timeout=10
            )
            metrics_response.raise_for_status()
            raw_metrics = metrics_response.json()

            if isinstance(raw_metrics, list):
                user_metrics = raw_metrics
            elif isinstance(raw_metrics, dict) and 'data' in raw_metrics:
                user_metrics = raw_metrics['data']

        except requests.exceptions.RequestException as e:
            error = f'Ошибка подключения к Kraken API: {str(e)}'
        except Exception as e:
            error = f'Ошибка обработки данных: {str(e)}'

    return render_template('admin/user_detail.html',
                           user_id=user_id,
                           user_data=user_data,
                           user_metrics=user_metrics,
                           period=period,
                           error=error)


@admin_bp.route('/api/users/<user_id>/stats')
@login_required
def user_stats_api(user_id):
    if not KRAKEN_API_KEY:
        return jsonify({'error': 'API key not configured'}), 500
    try:
        headers = {'Authorization': f'Bearer {KRAKEN_API_KEY}'}
        period = request.args.get('period', '7d')
        intervals = {'24h': 24, '7d': 168, '30d': 720}
        hours = intervals.get(period, 168)

        response = requests.get(
            f'{KRAKEN_API_URL}/api/v1/users/{user_id}/traffic?hours={hours}',
            headers=headers, timeout=10
        )
        response.raise_for_status()
        return jsonify(response.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== УСЛУГИ (КОНСТРУКТОР) ====================

@admin_bp.route('/services')
@login_required
def services_list():
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM services ORDER BY sort_order ASC")
    services = cursor.fetchall()

    try:
        cursor.execute("SELECT value FROM site_settings WHERE key = 'sponsors_block_enabled'")
        setting = cursor.fetchone()
        sponsors_enabled = setting['value'] == 'true' if setting else True
    except:
        sponsors_enabled = True

    conn.close()
    return render_template('admin/services.html', services=services, sponsors_enabled=sponsors_enabled)


@admin_bp.route('/services/add', methods=['GET', 'POST'])
@login_required
def service_add():
    if request.method == 'POST':
        title = request.form.get('title')
        subtitle = request.form.get('subtitle')
        description = request.form.get('description')
        icon = request.form.get('icon', '🌐')
        is_sponsor = request.form.get('is_sponsor') == 'on'

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO services (title, subtitle, description, icon, is_sponsor)
            VALUES (%s, %s, %s, %s, %s)
        """, (title, subtitle, description, icon, is_sponsor))
        conn.commit()
        conn.close()
        flash('Услуга добавлена!', 'success')
        return redirect(url_for('admin.services_list'))

    return render_template('admin/service_form.html', service=None)


@admin_bp.route('/services/edit/<int:service_id>', methods=['GET', 'POST'])
@login_required
def service_edit(service_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == 'POST':
        title = request.form.get('title')
        subtitle = request.form.get('subtitle')
        description = request.form.get('description')
        icon = request.form.get('icon', '')
        is_sponsor = request.form.get('is_sponsor') == 'on'

        cursor.execute("""
            UPDATE services SET title=%s, subtitle=%s, description=%s, icon=%s, is_sponsor=%s
            WHERE id=%s
        """, (title, subtitle, description, icon, is_sponsor, service_id))
        conn.commit()
        conn.close()
        flash('Услуга обновлена!', 'success')
        return redirect(url_for('admin.services_list'))

    cursor.execute("SELECT * FROM services WHERE id = %s", (service_id,))
    service = cursor.fetchone()
    conn.close()

    if not service:
        flash('Услуга не найдена', 'error')
        return redirect(url_for('admin.services_list'))

    return render_template('admin/service_form.html', service=service)


@admin_bp.route('/services/delete/<int:service_id>')
@login_required
def service_delete(service_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM services WHERE id = %s", (service_id,))
    conn.commit()
    conn.close()
    flash('Услуга удалена', 'success')
    return redirect(url_for('admin.services_list'))


@admin_bp.route('/settings/toggle-sponsors', methods=['POST'])
@login_required
def toggle_sponsors():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM site_settings WHERE key = 'sponsors_block_enabled'")
    current = cursor.fetchone()
    new_value = 'false' if (current and current[0] == 'true') else 'true'

    cursor.execute("""
        INSERT INTO site_settings (key, value)
        VALUES ('sponsors_block_enabled', %s)
        ON CONFLICT (key) DO UPDATE SET value = %s
    """, (new_value, new_value))
    conn.commit()
    conn.close()

    flash(f'Блок спонсоров {"включен" if new_value == "true" else "выключен"}', 'success')
    return redirect(url_for('admin.services_list'))
