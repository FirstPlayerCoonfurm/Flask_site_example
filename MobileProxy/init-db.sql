-- =============================================
-- Инициализация базы данных MobileProxy
-- Выполняется автоматически при первом запуске
-- =============================================

-- 1. База для метрик Kraken (создаётся отдельно, т.к. мы уже в базе umami)
CREATE DATABASE kraken_metrics;

-- 2. Подключаемся к базе kraken_metrics
\c kraken_metrics;

-- 3. Таблица метрик от Kraken Collector
CREATE TABLE IF NOT EXISTS kraken_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_traffic_gb FLOAT,
    active_sessions INT,
    total_users INT,
    revenue_rub FLOAT
);

-- 4. Таблица услуг (конструктор карточек на сайте)
CREATE TABLE IF NOT EXISTS services (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    subtitle VARCHAR(255),
    description TEXT,
    icon VARCHAR(50) DEFAULT '🌐',
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INT DEFAULT 0,
    is_sponsor BOOLEAN DEFAULT FALSE,
    is_enabled BOOLEAN DEFAULT TRUE
);

-- 5. Таблица глобальных настроек сайта
CREATE TABLE IF NOT EXISTS site_settings (
    key VARCHAR(50) PRIMARY KEY,
    value TEXT NOT NULL
);

-- 6. Настройка видимости блока спонсоров (по умолчанию включен)
INSERT INTO site_settings (key, value)
VALUES ('sponsors_block_enabled', 'true')
ON CONFLICT (key) DO NOTHING;

-- 7. Начальные карточки услуг (как на фото + спонсоры для теста)
INSERT INTO services (title, subtitle, description, icon, sort_order, is_sponsor) VALUES
('Мобильные прокси', 'приват', 'Выделенные мобильные IP для безопасной работы', '📶', 1, FALSE),
('Мобильные прокси', 'shared', 'Общие мобильные IP для массовых задач', '📡', 2, FALSE),
('Арбитражные прокси', 'для трафика', 'Оптимизированы для Facebook, Google Ads', '🎯', 3, FALSE),
('Резидентные прокси', 'ISP', 'Статические домашние IP адреса', '🏠', 4, FALSE),
('IPv4 с ротацией', 'автосмена', 'Автоматическая смена IP каждые 5 мин', '4️⃣', 5, FALSE),
('IPv6 с ротацией', 'дешевле', 'Бюджетные прокси для парсинга', '6️⃣', 6, FALSE),
('Продление прокси', 'сервис', 'Услуга продления срока действия', '🔑', 7, FALSE),
('Прокси от PartnerX', 'спонсор', 'Специальное предложение для наших клиентов', '🤝', 8, TRUE),
('Бонусный трафик', 'реклама', 'Дополнительные пакеты по сниженной цене', '🎁', 9, TRUE);
