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

# Конфигурация
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'change_me_please')
KRAKEN_API_URL = os.getenv('KRAKEN_API_URL', 'https://api.kraken.dev')
KRAKEN_API_KEY = os.getenv('KRAKEN_API_KEY', '')
DB_URL = os.getenv('DATABASE_URL', 'postgresql://umami:umami@umami-db:5432/umami')


def get_db():
    return psycopg2.connect(DB_URL)


def get_kraken_headers():
    return {'Authorization': f'Bearer {KRAKEN_API_KEY}'}


def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function


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


@admin_bp.route('/')
@login_required
def dashboard():
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT 
            date_trunc('day', timestamp) as day,
            SUM(total_traffic_gb) as traffic,
            AVG(active_sessions) as avg_sessions,
            SUM(revenue_rub) as revenue
        FROM kraken_metrics
        WHERE timestamp >= NOW() - INTERVAL '7 days'
        GROUP BY day
        ORDER BY day
    """)
    kraken_week = cursor.fetchall()
    
    cursor.execute("""
        SELECT * FROM kraken_metrics 
        ORDER BY timestamp DESC LIMIT 1
    """)
    latest = cursor.fetchone()
    
    try:
        cursor.execute("""
            SELECT COUNT(DISTINCT session_id) as visits
            FROM website_event
            WHERE created_at >= NOW() - INTERVAL '7 days'
        """)
        site_visits = cursor.fetchone()['visits']
    except:
        site_visits = 0
    
    conn.close()
    
    return render_template('admin/dashboard.html',
                         kraken_week=kraken_week,
                         latest=latest,
                         site_visits=site_visits)


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
    
    cursor.execute(f"""
        SELECT * FROM kraken_metrics
        WHERE timestamp >= NOW() - {interval}
        ORDER BY timestamp DESC
    """)
    rows = cursor.fetchall()
    
    conn.close()
    
    return render_template('admin/metrics.html', rows=rows, period=period)


@admin_bp.route('/analytics')
@login_required
def analytics():
    return render_template('admin/analytics.html')


@admin_bp.route('/api/kraken/live')
@login_required
def kraken_live():
    if not KRAKEN_API_KEY:
        return jsonify({'error': 'Kraken API key not configured'}), 500
    
    try:
        headers = get_kraken_headers()
        stats = requests.get(f'{KRAKEN_API_URL}/api/v1/stats', 
                           headers=headers, timeout=5).json()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============ НОВЫЕ РОУТЫ: ПОЛЬЗОВАТЕЛИ ============

@admin_bp.route('/users')
@login_required
def users():
    """Список пользователей из Kraken API"""
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort', 'name')
    order = request.args.get('order', 'asc')
    
    users_list = []
    error = None
    
    if KRAKEN_API_KEY:
        try:
            headers = get_kraken_headers()
            # Получаем список пользователей
            response = requests.get(f'{KRAKEN_API_URL}/api/v1/users', 
                                  headers=headers, timeout=10)
            response.raise_for_status()
            raw_users = response.json()
            
            # Адаптируй под реальный формат ответа Kraken
            # Обычно это список объектов с полями id, name, email, traffic, balance и т.д.
            if isinstance(raw_users, list):
                users_list = raw_users
            elif isinstance(raw_users, dict) and 'users' in raw_users:
                users_list = raw_users['users']
            else:
                users_list = [raw_users] if isinstance(raw_users, dict) else []
            
            # Фильтрация по поиску
            if search:
                search_lower = search.lower()
                users_list = [
                    u for u in users_list
                    if search_lower in str(u.get('name', '')).lower()
                    or search_lower in str(u.get('email', '')).lower()
                    or search_lower in str(u.get('id', '')).lower()
                ]
            
            # Сортировка
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
    """Детальная страница пользователя"""
    user_data = None
    user_metrics = []
    error = None
    
    if KRAKEN_API_KEY:
        try:
            headers = get_kraken_headers()
            
            # Получаем данные пользователя
            user_response = requests.get(f'{KRAKEN_API_URL}/api/v1/users/{user_id}', 
                                        headers=headers, timeout=10)
            user_response.raise_for_status()
            user_data = user_response.json()
            
            # Получаем метрики пользователя (трафик по дням)
            period = request.args.get('period', '7d')
            intervals = {'24h': 24, '7d': 168, '30d': 720}
            hours = intervals.get(period, 168)
            
            metrics_response = requests.get(
                f'{KRAKEN_API_URL}/api/v1/users/{user_id}/traffic?hours={hours}',
                headers=headers, timeout=10
            )
            metrics_response.raise_for_status()
            raw_metrics = metrics_response.json()
            
            # Адаптируй под формат Kraken
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
                         period=period if 'period' in locals() else '7d',
                         error=error)


@admin_bp.route('/api/users/<user_id>/stats')
@login_required
def user_stats_api(user_id):
    """API для получения статистики пользователя (для графиков)"""
    if not KRAKEN_API_KEY:
        return jsonify({'error': 'API key not configured'}), 500
    
    try:
        headers = get_kraken_headers()
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