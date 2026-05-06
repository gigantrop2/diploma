import psycopg2
from psycopg2 import OperationalError

def get_connection():
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