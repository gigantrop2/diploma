import os
import psycopg2
from psycopg2 import OperationalError


def get_connection():
    database_url = os.environ.get('DATABASE_URL')

    if database_url:
        try:
            conn = psycopg2.connect(database_url)
            conn.set_client_encoding('UTF8')
            return conn
        except OperationalError:
            return None

    try:
        conn = psycopg2.connect(
            host="localhost",
            port="5432",
            database="diploma_db",
            user="postgres",
            password="11111"
        )
        conn.set_client_encoding('UTF8')
        return conn
    except OperationalError:
        return None