-- Создаём базу для метрик Kraken
CREATE DATABASE kraken_metrics;

-- Создаём таблицу для метрик
\c kraken_metrics;

CREATE TABLE IF NOT EXISTS kraken_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_traffic_gb FLOAT,
    active_sessions INT,
    total_users INT,
    revenue_rub FLOAT
);
