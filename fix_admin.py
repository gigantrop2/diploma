from db import get_connection
from werkzeug.security import generate_password_hash

email = 'admin@mail.ru'
password = 'admin123'

password_hash = generate_password_hash(password)

conn = get_connection()
cur = conn.cursor()

# Удаляем старых админов
cur.execute("DELETE FROM users WHERE is_staff = true")

# Добавляем нового
cur.execute("""
    INSERT INTO users (email, phone, password_hash, full_name, is_staff, is_active)
    VALUES (%s, %s, %s, %s, true, true)
""", (email, '00000000000', password_hash, 'Администратор'))

conn.commit()
cur.close()
conn.close()

print(f"Админ создан: {email} / {password}")