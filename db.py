import os
import psycopg2
from psycopg2 import OperationalError


def get_connection():
    # Пробуем взять переменную окружения (облако Render)
    database_url = os.environ.get('DATABASE_URL')

    if database_url:
        try:
            return psycopg2.connect(database_url)
        except OperationalError:
            return None

    # Если переменной нет — работаем локально
    try:
        conn = psycopg2.connect(
            host="localhost",
            port="5432",
            database="diploma_db",
            user="postgres",
            password="11111"
        )
        return conn
    except OperationalError:
        return None