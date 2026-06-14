from flask import Flask, render_template, request, redirect, session, jsonify
from db import get_connection
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string
from datetime import datetime, timedelta
from functools import wraps
import qrcode
import io
import base64
import json
from flask import send_file
app = Flask(__name__)
app.secret_key = 'diploma-super-secret-key-2026'


def generate_qr_code(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # Конвертируем в base64 для вставки в HTML
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_base64}"

# =====================================================
# Декораторы для ролей
# =====================================================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT is_admin FROM users WHERE user_id = %s", (session['user_id'],))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if not user or not user[0]:
            return "Доступ запрещён. Только для администраторов.", 403
        return f(*args, **kwargs)

    return decorated_function


def admin_or_manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT is_admin, is_manager FROM users WHERE user_id = %s", (session['user_id'],))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if not user or (not user[0] and not user[1]):
            return "Доступ запрещён. Только для сотрудников.", 403
        return f(*args, **kwargs)

    return decorated_function


# =====================================================
# Автоопределение бренда
# =====================================================
KNOWN_BRANDS = ['Apple', 'Samsung', 'Xiaomi', 'Redmi', 'Huawei', 'Honor',
                'Nokia', 'Sony', 'LG', 'OnePlus', 'Google', 'Realme', 'Poco',
                'Motorola', 'Asus', 'ZTE', 'BQ', 'TECNO', 'Infinix']


def extract_brand(product_name):
    if not product_name:
        return None
    name_lower = product_name.lower()
    for brand in KNOWN_BRANDS:
        brand_lower = brand.lower()
        if (name_lower.startswith(brand_lower) or
                f' {brand_lower} ' in name_lower or
                name_lower.startswith(f'{brand_lower} ') or
                f'-{brand_lower}' in name_lower):
            return brand
    for brand in KNOWN_BRANDS:
        if brand.lower() in name_lower:
            return brand
    return None


# =====================================================
# Главная
# =====================================================
@app.route('/')
def index():
    return render_template('index.html')


# =====================================================
# Товары (клиентская часть с фильтрами)
# =====================================================
@app.route('/products')
def products():
    category_id = request.args.get('category', '')
    sort = request.args.get('sort', 'name_asc')
    search_query = request.args.get('search', '').strip()
    brand = request.args.get('brand', '')
    price_min = request.args.get('price_min', '')
    price_max = request.args.get('price_max', '')
    page = request.args.get('page', 1, type=int)
    per_page = 12

    conn = get_connection()
    if conn is None:
        return render_template('products.html', products=[], categories=[], brands=[], stores_list=[], total_count=0,
                               stores_count=0, page=1, total_pages=1)

    cur = conn.cursor()

    # Базовый запрос
    query = """
        SELECT p.product_id, p.product_name, p.price, 
               COALESCE(c.category_name, 'Без категории') as category_name,
               p.brand
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.category_id
        WHERE 1=1
    """
    params = []

    if category_id and category_id.isdigit():
        cat_id = int(category_id)
        if cat_id == 5:
            query += " AND p.category_id IN (5, 7, 8)"
        elif cat_id == 2:
            query += " AND p.category_id IN (2, 3, 4, 10, 11)"
        else:
            query += " AND p.category_id = %s"
            params.append(cat_id)

    if search_query:
        query += " AND p.product_name ILIKE %s"
        params.append(f'%{search_query}%')

    if brand:
        query += " AND p.brand = %s"
        params.append(brand)

    if price_min:
        query += " AND p.price >= %s"
        params.append(float(price_min))
    if price_max:
        query += " AND p.price <= %s"
        params.append(float(price_max))

    if sort == 'price_asc':
        query += " ORDER BY p.price ASC"
    elif sort == 'price_desc':
        query += " ORDER BY p.price DESC"
    else:
        query += " ORDER BY p.product_name ASC"

    try:
        cur.execute(query, params)
        all_items = cur.fetchall()
    except Exception:
        all_items = []

    total_count = len(all_items)
    offset = (page - 1) * per_page
    items = all_items[offset:offset + per_page]
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

    # Категории
    try:
        cur.execute("SELECT category_id, category_name FROM categories ORDER BY category_name")
        categories = cur.fetchall()
    except Exception:
        categories = []

    # Бренды
    try:
        if category_id and category_id.isdigit():
            cat_id = int(category_id)
            if cat_id == 5:
                cur.execute(
                    "SELECT DISTINCT brand FROM products WHERE category_id IN (5,7,8) AND brand IS NOT NULL AND brand != '' ORDER BY brand")
            elif cat_id == 2:
                cur.execute(
                    "SELECT DISTINCT brand FROM products WHERE category_id IN (2,3,4,10,11) AND brand IS NOT NULL AND brand != '' ORDER BY brand")
            else:
                cur.execute(
                    "SELECT DISTINCT brand FROM products WHERE category_id = %s AND brand IS NOT NULL AND brand != '' ORDER BY brand",
                    (cat_id,))
        else:
            cur.execute("SELECT DISTINCT brand FROM products WHERE brand IS NOT NULL AND brand != '' ORDER BY brand")
        brands = cur.fetchall()
    except Exception:
        brands = []

    # Магазины
    try:
        cur.execute("SELECT store_id, store_name, city FROM stores ORDER BY store_name")
        stores_list = cur.fetchall()
        stores_count = len(stores_list)
    except Exception:
        stores_list = []
        stores_count = 0

    cur.close()
    conn.close()

    return render_template('products.html',
                           products=items,
                           categories=categories,
                           brands=brands,
                           stores_list=stores_list,
                           selected_category=category_id,
                           selected_sort=sort,
                           selected_brand=brand,
                           price_min=price_min,
                           price_max=price_max,
                           total_count=total_count,
                           stores_count=stores_count,
                           page=page,
                           total_pages=total_pages,
                           per_page=per_page)

# =====================================================
# Поиск
# =====================================================
@app.route('/search')
def search():
    query = request.args.get('query', '')
    if not query:
        return redirect('/')
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT product_id, product_name, price 
        FROM products 
        WHERE product_name ILIKE %s
        ORDER BY product_name
        LIMIT 50
    """, (f'%{query}%',))
    results = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('search_results.html', query=query, results=results)


# =====================================================
# Детальная страница товара
# =====================================================
@app.route('/product/<int:product_id>')
def product_detail(product_id):
    conn = get_connection()
    if conn is None:
        return "База данных недоступна", 503

    cur = conn.cursor()

    # Проверяем группу
    try:
        cur.execute("SELECT group_id FROM products WHERE product_id = %s", (product_id,))
        group_result = cur.fetchone()
        if group_result and group_result[0] is not None and group_result[0] != product_id:
            cur.close()
            conn.close()
            return redirect(f'/product/{group_result[0]}')
    except Exception:
        pass

    # Получаем товар
    try:
        cur.execute(
            "SELECT product_id, product_name, price, params, group_name, image_url, product_code, brand, specifications FROM products WHERE product_id = %s",
            (product_id,))
        product = cur.fetchone()
        if not product:
            return "Товар не найден", 404
    except Exception:
        return "Ошибка базы данных", 500

    # Парсим JSON
    import json
    specs = {}
    if product[8]:
        try:
            specs = json.loads(product[8])
        except:
            specs = {}

    # Получаем товары из группы
    variants = {}
    try:
        cur.execute(
            "SELECT product_id, product_name, price, params FROM products WHERE group_id = %s OR product_id = %s",
            (product_id, product_id))
        group_products = cur.fetchall()
        for p in group_products:
            params = p[3] if p[3] else {}
            for key, value in params.items():
                if key not in variants:
                    variants[key] = []
                if not any(v['value'] == value for v in variants[key]):
                    variants[key].append({'value': value, 'product_id': p[0]})
    except Exception:
        pass

    # Получаем остатки
    stocks = []
    try:
        cur.execute("""
            SELECT s.store_id, s.store_name, s.city, s.address, 
                   sb.quantity, sb.reserved, 
                   (sb.quantity - sb.reserved) as available,
                   s.latitude, s.longitude
            FROM stock_balances sb
            JOIN stores s ON sb.store_id = s.store_id
            WHERE sb.product_id = %s AND sb.quantity > 0
            ORDER BY s.city, s.store_name
        """, (product_id,))
        stocks = cur.fetchall()
    except Exception:
        stocks = []

    cur.close()
    conn.close()

    return render_template('product_detail.html',
                           product=product,
                           stocks=stocks,
                           specs=specs,
                           variants=variants)


# =====================================================
# Список магазинов
# =====================================================
@app.route('/stores')
def stores():
    conn = get_connection()
    if conn is None:
        return render_template('stores.html', stores=[])

    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT store_id, store_name, city, address, 
                   latitude, longitude, working_hours 
            FROM stores 
            WHERE is_visible = TRUE
            ORDER BY city, store_name
        """)
        stores_list = cur.fetchall()
    except Exception:
        stores_list = []

    cur.close()
    conn.close()

    return render_template('stores.html', stores=stores_list)


# =====================================================
# Карта
# =====================================================
@app.route('/map')
def map_view():
    conn = get_connection()
    if conn is None:
        return render_template('map.html', stores=[])

    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT store_id, store_name, city, address, 
                   store_type, latitude, longitude, working_hours
            FROM stores 
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND is_visible = TRUE
            ORDER BY city, store_name
        """)
        stores = cur.fetchall()
    except Exception:
        stores = []

    cur.close()
    conn.close()

    return render_template('map.html', stores=stores)


# =====================================================
# Регистрация
# =====================================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        phone = request.form['phone'].strip()
        password = request.form['password']
        full_name = request.form['full_name'].strip()
        if not email or '@' not in email:
            return "Некорректный email"
        if len(phone) < 10:
            return "Некорректный телефон"
        if len(password) < 4:
            return "Пароль должен быть минимум 4 символа"
        if not full_name:
            return "Введите имя"
        password_hash = generate_password_hash(password)
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT email, phone FROM users WHERE email = %s OR phone = %s", (email, phone))
            if cur.fetchone():
                return "Пользователь с таким email или телефоном уже существует"
            cur.execute("""
                INSERT INTO users (email, phone, password_hash, full_name)
                VALUES (%s, %s, %s, %s)
                RETURNING user_id
            """, (email, phone, password_hash, full_name))
            user_id = cur.fetchone()[0]
            conn.commit()
            session['user_id'] = user_id
            session['user_name'] = full_name
            session['is_admin'] = False
            session['is_manager'] = False
            return redirect('/')
        except Exception as e:
            conn.rollback()
            return f"Ошибка: {e}"
        finally:
            cur.close()
            conn.close()
    return render_template('register.html')


# =====================================================
# Вход
# =====================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, full_name, password_hash, is_admin, is_manager
            FROM users 
            WHERE email = %s AND is_active = true
        """, (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['user_name'] = user[1]
            session['is_admin'] = user[3]
            session['is_manager'] = user[4]
            return redirect('/')
        else:
            return "Неверный email или пароль"
    return render_template('login.html')


# =====================================================
# Выход
# =====================================================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# =====================================================
# Личный кабинет
# =====================================================
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect('/login')
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT email, phone, full_name, created_at, is_admin, is_manager FROM users WHERE user_id = %s",
                (session['user_id'],))
    user = cur.fetchone()
    cur.execute("""
        SELECT o.order_id, o.order_number, o.order_date, s.status_name, o.total_amount
        FROM orders o
        JOIN order_statuses s ON o.status_id = s.status_id
        WHERE o.user_id = %s
        ORDER BY o.order_date DESC
    """, (session['user_id'],))
    orders = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('profile.html', user=user, orders=orders)


# =====================================================
# Корзина и заказы (без изменений)
# =====================================================
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        return redirect('/login')
    product_id = request.form['product_id']
    store_id = request.form['store_id']
    quantity = int(request.form['quantity'])
    price = float(request.form['price'])
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT cart_id FROM carts WHERE user_id = %s", (session['user_id'],))
        cart = cur.fetchone()
        if not cart:
            cur.execute("INSERT INTO carts (user_id, store_id) VALUES (%s, %s) RETURNING cart_id",
                        (session['user_id'], store_id))
            cart_id = cur.fetchone()[0]
        else:
            cart_id = cart[0]
            cur.execute("UPDATE carts SET store_id = %s WHERE cart_id = %s", (store_id, cart_id))
        cur.execute("""
            INSERT INTO cart_items (cart_id, product_id, quantity, price)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (cart_id, product_id) DO UPDATE
            SET quantity = cart_items.quantity + EXCLUDED.quantity
        """, (cart_id, product_id, quantity, price))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"Ошибка: {e}"
    finally:
        cur.close()
        conn.close()
    return redirect('/cart')


# =====================================================
# API: получение остатков и цены для выбранного варианта товара
# =====================================================
@app.route('/get_stocks/<int:product_id>')
def get_stocks(product_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT price FROM products WHERE product_id = %s", (product_id,))
    price = cur.fetchone()[0]

    cur.execute("""
        SELECT s.store_id, s.store_name, s.city, s.address, 
               (sb.quantity - sb.reserved) as available,
               s.latitude, s.longitude
        FROM stock_balances sb
        JOIN stores s ON sb.store_id = s.store_id
        WHERE sb.product_id = %s AND sb.quantity > 0
    """, (product_id,))

    stocks = []
    for row in cur.fetchall():
        stocks.append({
            'id': row[0],
            'name': row[1],
            'city': row[2],
            'address': row[3],
            'quantity': row[4],
            'latitude': row[5],
            'longitude': row[6]
        })

    cur.close()
    conn.close()
    return jsonify({'price': price, 'stocks': stocks})


@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect('/login')

    conn = get_connection()
    if conn is None:
        return render_template('cart.html', items=[], total=0, all_stores=[])

    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT c.cart_id, c.store_id, s.store_name, s.city
            FROM carts c
            JOIN stores s ON c.store_id = s.store_id
            WHERE c.user_id = %s
        """, (session['user_id'],))
        cart_info = cur.fetchone()
    except Exception:
        cart_info = None

    if not cart_info:
        cur.close()
        conn.close()
        return render_template('cart.html', items=[], total=0, all_stores=[])

    cart_id = cart_info[0]

    try:
        cur.execute("""
            SELECT ci.product_id, p.product_name, ci.quantity, ci.price,
                   (ci.quantity * ci.price) as subtotal
            FROM cart_items ci
            JOIN products p ON ci.product_id = p.product_id
            WHERE ci.cart_id = %s
        """, (cart_id,))
        items = cur.fetchall()
        total = sum(item[4] for item in items)
    except Exception:
        items = []
        total = 0

    try:
        cur.execute("SELECT store_id, store_name, city FROM stores ORDER BY city")
        all_stores = cur.fetchall()
    except Exception:
        all_stores = []

    cur.close()
    conn.close()

    return render_template('cart.html', cart=cart_info, items=items, total=total, all_stores=all_stores)


@app.route('/update_cart_store', methods=['POST'])
def update_cart_store():
    if 'user_id' not in session:
        return redirect('/login')
    store_id = request.form['store_id']
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE carts SET store_id = %s WHERE user_id = %s", (store_id, session['user_id']))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/cart')


@app.route('/remove_from_cart', methods=['POST'])
def remove_from_cart():
    if 'user_id' not in session:
        return redirect('/login')
    product_id = request.form['product_id']
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT cart_id FROM carts WHERE user_id = %s", (session['user_id'],))
    cart = cur.fetchone()
    if cart:
        cur.execute("DELETE FROM cart_items WHERE cart_id = %s AND product_id = %s", (cart[0], product_id))
        cur.execute("SELECT COUNT(*) FROM cart_items WHERE cart_id = %s", (cart[0],))
        if cur.fetchone()[0] == 0:
            cur.execute("DELETE FROM carts WHERE cart_id = %s", (cart[0],))
        conn.commit()
    cur.close()
    conn.close()
    return redirect('/cart')


@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        return redirect('/login')
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.cart_id, c.store_id, s.store_name, s.city
        FROM carts c
        JOIN stores s ON c.store_id = s.store_id
        WHERE c.user_id = %s
    """, (session['user_id'],))
    cart = cur.fetchone()
    if not cart:
        return redirect('/cart')
    cart_id = cart[0]
    store_id = cart[1]
    cur.execute("""
        SELECT ci.product_id, p.product_name, ci.quantity, ci.price,
               sb.quantity as stock_quantity, sb.reserved
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.product_id
        JOIN stock_balances sb ON sb.store_id = %s AND sb.product_id = ci.product_id
        WHERE ci.cart_id = %s
    """, (store_id, cart_id))
    items = cur.fetchall()
    if not items:
        return redirect('/cart')
    if request.method == 'POST':
        try:
            for item in items:
                available = item[4] - item[5]
                if item[2] > available:
                    return f"Недостаточно товара {item[1]} на складе"
            order_number = 'ORD-' + datetime.now().strftime('%Y%m%d-') + ''.join(random.choices(string.digits, k=4))
            total_amount = sum(item[2] * item[3] for item in items)
            cur.execute("""
                INSERT INTO orders (order_number, user_id, customer_name, customer_phone, target_store_id, status_id, total_amount)
                VALUES (%s, %s, %s, %s, %s, 1, %s)
                RETURNING order_id
            """, (order_number, session['user_id'], session['user_name'], '', store_id, total_amount))
            order_id = cur.fetchone()[0]
            for item in items:
                cur.execute("""
                    INSERT INTO order_items (order_id, product_id, quantity, price)
                    VALUES (%s, %s, %s, %s)
                """, (order_id, item[0], item[2], item[3]))
            cur.execute("DELETE FROM cart_items WHERE cart_id = %s", (cart_id,))
            cur.execute("DELETE FROM carts WHERE cart_id = %s", (cart_id,))
            conn.commit()
            return redirect(f'/order/{order_id}')
        except Exception as e:
            conn.rollback()
            return f"Ошибка при оформлении заказа: {e}"
        finally:
            cur.close()
            conn.close()
    total = sum(item[2] * item[3] for item in items)
    cur.close()
    conn.close()
    return render_template('checkout.html', cart=cart, items=items, total=total)


@app.route('/order/<int:order_id>')
def order_detail(order_id):
    if 'user_id' not in session:
        return redirect('/login')

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT o.order_id, o.order_number, o.order_date, o.total_amount,
               s.status_name, o.customer_name, o.customer_phone,
               st.store_name, st.city, st.address
        FROM orders o
        JOIN order_statuses s ON o.status_id = s.status_id
        JOIN stores st ON o.target_store_id = st.store_id
        WHERE o.order_id = %s AND o.user_id = %s
    """, (order_id, session['user_id']))

    order = cur.fetchone()

    if not order:
        return "Заказ не найден", 404

    cur.execute("""
        SELECT p.product_name, oi.quantity, oi.price, (oi.quantity * oi.price) as subtotal
        FROM order_items oi
        JOIN products p ON oi.product_id = p.product_id
        WHERE oi.order_id = %s
    """, (order_id,))

    items = cur.fetchall()
    cur.close()
    conn.close()

    # Генерируем QR-код с номером заказа
    qr_image = generate_qr_code(f"Заказ #{order[1]}")

    return render_template('order_detail.html', order=order, items=items, qr_image=qr_image)


# =====================================================
# Загрузка 1С
# =====================================================
@app.route('/upload_1c', methods=['GET', 'POST'])
def upload_1c():
    if request.method == 'POST':
        file = request.files['file']
        if not file:
            return "Файл не выбран"
        df = pd.read_csv(file, header=None, sep=';', encoding='utf-8-sig')
        start_row = None
        for i in range(len(df)):
            if df.iloc[i].astype(str).str.contains('Номенклатура').any():
                start_row = i + 1
                break
        if start_row is None:
            return "Не найден заголовок таблицы"
        data = df.iloc[start_row:].copy()
        conn = get_connection()
        cur = conn.cursor()
        store_id = 1
        cur.execute("DELETE FROM stock_balances WHERE store_id = %s", (store_id,))
        for _, row in data.iterrows():
            product_name = str(row[0]).strip()
            if not product_name or product_name in ['nan', 'Итого']:
                continue
            if 'Номенклатура' in product_name or 'Ед. изм' in product_name:
                continue
            if product_name == 'Элма МТС' or 'Итого' in product_name:
                continue
            try:
                quantity = float(str(row[3]).replace(',', '.').replace(' ', ''))
                price = float(str(row[7]).replace(',', '.').replace(' ', ''))
            except:
                continue
            if quantity == 0 or price == 0:
                continue
            brand = extract_brand(product_name)
            cur.execute("SELECT product_id FROM products WHERE product_name = %s", (product_name,))
            existing = cur.fetchone()
            if existing:
                product_id = existing[0]
                cur.execute("UPDATE products SET price = %s, brand = COALESCE(%s, brand) WHERE product_id = %s",
                            (price, brand, product_id))
            else:
                cur.execute("""
                    INSERT INTO products (product_name, brand, price)
                    VALUES (%s, %s, %s)
                    RETURNING product_id
                """, (product_name, brand, price))
                product_id = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO stock_balances (store_id, product_id, quantity, reserved)
                VALUES (%s, %s, %s, 0)
            """, (store_id, product_id, quantity))
        conn.commit()
        cur.close()
        conn.close()
        return "Загружено товаров"
    return '''
        <h2>Загрузка отчёта 1С</h2>
        <form method=post enctype=multipart/form-data>
            <input type=file name=file accept=".csv">
            <input type=submit value=Загрузить>
        </form>
    '''


@app.route('/payment')
def payment():
    if 'user_id' not in session:
        return redirect('/login')

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT order_id, order_number, total_amount
        FROM orders
        WHERE user_id = %s AND status_id = 1 AND payment_status != 'paid'
        ORDER BY order_date DESC
        LIMIT 1
    """, (session['user_id'],))

    order = cur.fetchone()
    cur.close()
    conn.close()

    if not order:
        return redirect('/cart')

    return render_template('payment.html',
                           order_number=order[1],
                           total_amount=order[2],
                           order_id=order[0])


@app.route('/payment/process/<int:order_id>', methods=['POST'])
def payment_process(order_id):
    if 'user_id' not in session:
        return redirect('/login')

    conn = get_connection()
    cur = conn.cursor()

    # Имитируем успешную оплату
    cur.execute("UPDATE orders SET payment_status = 'paid' WHERE order_id = %s AND user_id = %s",
                (order_id, session['user_id']))
    conn.commit()
    cur.close()
    conn.close()

    return render_template('payment_success.html', order_id=order_id)

# =====================================================
# АДМИНКА
# =====================================================

@app.route('/admin')
def admin_panel():
    if 'user_id' not in session:
        return redirect('/login')
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT is_admin, is_manager FROM users WHERE user_id = %s", (session['user_id'],))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if not user or (not user[0] and not user[1]):
        return "Доступ запрещён", 403
    return render_template('admin_panel.html', is_admin=user[0])


# ---------- Управление заказами ----------
@app.route('/admin/orders')
@admin_or_manager_required
def admin_orders():
    conn = get_connection()
    if conn is None:
        return render_template('admin_orders.html', orders=[])

    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT o.order_id, o.order_number, u.full_name, o.customer_phone,
                   o.order_date, s.status_name, o.total_amount,
                   st.store_name
            FROM orders o
            JOIN users u ON o.user_id = u.user_id
            JOIN order_statuses s ON o.status_id = s.status_id
            JOIN stores st ON o.target_store_id = st.store_id
            ORDER BY o.order_date DESC
        """)
        orders = cur.fetchall()
    except Exception:
        orders = []

    cur.close()
    conn.close()

    return render_template('admin_orders.html', orders=orders)


@app.route('/admin/order/<int:order_id>')
@admin_required
def admin_order_detail(order_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT o.order_id, o.order_number, o.order_date, o.total_amount,
               s.status_name, o.customer_name, o.customer_phone,
               st.store_name, st.city, st.address,
               u.full_name, u.email
        FROM orders o
        JOIN order_statuses s ON o.status_id = s.status_id
        JOIN stores st ON o.target_store_id = st.store_id
        JOIN users u ON o.user_id = u.user_id
        WHERE o.order_id = %s
    """, (order_id,))

    order = cur.fetchone()

    if not order:
        return "Заказ не найден", 404

    cur.execute("""
        SELECT p.product_name, oi.quantity, oi.price, (oi.quantity * oi.price) as subtotal
        FROM order_items oi
        JOIN products p ON oi.product_id = p.product_id
        WHERE oi.order_id = %s
    """, (order_id,))

    items = cur.fetchall()
    cur.close()
    conn.close()

    # QR-код для админки
    qr_image = generate_qr_code(f"Заказ #{order[1]}")

    return render_template('admin_order_detail.html', order=order, items=items, qr_image=qr_image)


@app.route('/admin/order/<int:order_id>/status', methods=['POST'])
@admin_or_manager_required
def update_order_status(order_id):
    new_status = request.form['status_id']
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT target_store_id FROM orders WHERE order_id = %s", (order_id,))
    store_id = cur.fetchone()[0]
    cur.execute("SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
    items = cur.fetchall()
    if new_status == '2':
        for item in items:
            cur.execute("UPDATE stock_balances SET reserved = reserved + %s WHERE store_id = %s AND product_id = %s",
                        (item[1], store_id, item[0]))
    if new_status == '6':
        for item in items:
            cur.execute(
                "UPDATE stock_balances SET reserved = reserved - %s WHERE store_id = %s AND product_id = %s AND reserved >= %s",
                (item[1], store_id, item[0], item[1]))
    if new_status == '5':
        for item in items:
            cur.execute(
                "UPDATE stock_balances SET quantity = quantity - %s, reserved = reserved - %s WHERE store_id = %s AND product_id = %s",
                (item[1], item[1], store_id, item[0]))
    cur.execute("UPDATE orders SET status_id = %s WHERE order_id = %s", (new_status, order_id))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/admin/orders')


# ---------- Управление товарами (CRUD) ----------
@app.route('/admin/products')
@admin_or_manager_required
def admin_products():
    conn = get_connection()
    if conn is None:
        return render_template('admin_products.html', products=[])

    cur = conn.cursor()

    try:
        cur.execute("SELECT product_id, product_name, brand, price FROM products ORDER BY product_name")
        products = cur.fetchall()
    except Exception:
        products = []

    cur.close()
    conn.close()

    return render_template('admin_products.html', products=products)


@app.route('/admin/product/add', methods=['GET', 'POST'])
@admin_or_manager_required
def admin_product_add():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT category_id, category_name FROM categories ORDER BY category_name")
    categories = cur.fetchall()

    if request.method == 'POST':
        product_name = request.form['product_name']
        brand = request.form.get('brand') or extract_brand(product_name)
        price = float(request.form['price'])
        category_id = request.form.get('category_id') or None
        specifications = request.form.get('specifications') or None  # 👈 ДОБАВИТЬ ЭТУ СТРОКУ

        cur.execute("""
            INSERT INTO products (product_name, brand, price, category_id, specifications)
            VALUES (%s, %s, %s, %s, %s)
        """, (product_name, brand, price, category_id, specifications))
        conn.commit()
        cur.close()
        conn.close()
        return redirect('/admin/products')

    cur.close()
    conn.close()
    return render_template('admin_product_form.html', title="Добавить товар", categories=categories)


@app.route('/admin/product/<int:product_id>/edit', methods=['GET', 'POST'])
@admin_or_manager_required
def admin_product_edit(product_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT category_id, category_name FROM categories ORDER BY category_name")
    categories = cur.fetchall()

    if request.method == 'POST':
        product_name = request.form['product_name']
        brand = request.form.get('brand')
        price = float(request.form['price'])
        category_id = request.form.get('category_id') or None
        specifications = request.form.get('specifications') or None  # 👈 ДОБАВИТЬ ЭТУ СТРОКУ

        cur.execute("""
            UPDATE products 
            SET product_name=%s, brand=%s, price=%s, category_id=%s, specifications=%s
            WHERE product_id=%s
        """, (product_name, brand, price, category_id, specifications, product_id))
        conn.commit()
        cur.close()
        conn.close()
        return redirect('/admin/products')

    # Добавляем specifications в SELECT
    cur.execute("SELECT product_id, product_name, brand, price, category_id, specifications FROM products WHERE product_id=%s", (product_id,))
    product = cur.fetchone()
    cur.close()
    conn.close()

    if not product:
        return "Товар не найден", 404

    return render_template('admin_product_form.html', title="Редактировать товар", product=product, categories=categories)


@app.route('/admin/product/<int:product_id>/delete', methods=['POST'])
@admin_or_manager_required
def admin_product_delete(product_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE product_id=%s", (product_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/admin/products')


# =====================================================
# УПРАВЛЕНИЕ ХАРАКТЕРИСТИКАМИ ТОВАРА (цвет, память и т.д.)
# =====================================================
@app.route('/admin/product/<int:product_id>/attributes', methods=['GET', 'POST'])
@admin_or_manager_required
def admin_product_attributes(product_id):
    conn = get_connection()
    cur = conn.cursor()

    # Получаем товар
    cur.execute("SELECT product_id, product_name FROM products WHERE product_id = %s", (product_id,))
    product = cur.fetchone()
    if not product:
        return "Товар не найден", 404

    # Получаем все атрибуты
    cur.execute("SELECT attr_id, attr_name FROM attributes ORDER BY attr_id")
    attributes = cur.fetchall()

    # Получаем текущие значения
    cur.execute("SELECT attr_id, attr_value FROM product_attributes WHERE product_id = %s", (product_id,))
    current = {row[0]: row[1] for row in cur.fetchall()}

    # Собираем возможные значения для select'ов
    attr_values = {}
    for attr in attributes:
        cur.execute("""
            SELECT DISTINCT attr_value FROM product_attributes 
            WHERE attr_id = %s AND attr_value IS NOT NULL AND attr_value != ''
            LIMIT 20
        """, (attr[0],))
        attr_values[attr[0]] = [row[0] for row in cur.fetchall()]

    if request.method == 'POST':
        # Удаляем старые значения
        cur.execute("DELETE FROM product_attributes WHERE product_id = %s", (product_id,))

        # Вставляем новые
        for attr in attributes:
            attr_id = attr[0]
            value = request.form.get(f'attr_{attr_id}', '').strip()

            # Проверяем вариант "Другое"
            if request.form.get(f'attr_{attr_id}') == '__other__':
                value = request.form.get(f'attr_{attr_id}_other', '').strip()

            if value:
                cur.execute("""
                    INSERT INTO product_attributes (product_id, attr_id, attr_value)
                    VALUES (%s, %s, %s)
                """, (product_id, attr_id, value))

        conn.commit()
        cur.close()
        conn.close()
        return redirect('/admin/products')

    cur.close()
    conn.close()

    return render_template('admin_product_attributes.html',
                           product=product,
                           attributes=attributes,
                           current=current,
                           attr_values=attr_values)

# ---------- Управление пользователями (только админ) ----------
@app.route('/admin/users')
@admin_required
def admin_users():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id, email, full_name, is_admin, is_manager, is_active FROM users ORDER BY user_id")
    users = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin_users.html', users=users)


@app.route('/admin/user/<int:user_id>/role', methods=['POST'])
@admin_required
def admin_user_role(user_id):
    role = request.form['role_select']  # 'user', 'manager', 'admin'

    if role == 'admin':
        is_admin = True
        is_manager = False
    elif role == 'manager':
        is_admin = False
        is_manager = True
    else:
        is_admin = False
        is_manager = False

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_admin = %s, is_manager = %s WHERE user_id = %s", (is_admin, is_manager, user_id))
    conn.commit()
    cur.close()
    conn.close()

    return redirect('/admin/users')


@app.route('/admin/user/<int:user_id>/reset_password', methods=['POST'])
@admin_required
def admin_user_reset_password(user_id):
    new_password = request.form.get('new_password')
    if not new_password or len(new_password) < 4:
        return "Пароль должен быть не менее 4 символов"
    password_hash = generate_password_hash(new_password)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (password_hash, user_id))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/admin/users')


@app.route('/admin/merge_products', methods=['GET', 'POST'])
@admin_required
def admin_merge_products():
    conn = get_connection()
    cur = conn.cursor()

    # Получаем все товары
    cur.execute("SELECT product_id, product_name, price FROM products ORDER BY product_name")
    products = cur.fetchall()

    # Получаем все группы (товары, на которые есть ссылки в group_id)
    cur.execute("""
        SELECT p.product_id, p.product_name, p.price, p.params, p.group_name
        FROM products p
        WHERE p.product_id IN (SELECT DISTINCT group_id FROM products WHERE group_id IS NOT NULL)
        ORDER BY p.product_name
    """)
    groups = cur.fetchall()

    if request.method == 'POST':
        main_id = request.form.get('main_product_id')
        selected_ids = request.form.getlist('in_group')
        group_name = request.form.get('group_name', '').strip()

        if main_id and selected_ids:
            # Добавляем главный в группу, если его нет
            if main_id not in selected_ids:
                selected_ids.append(main_id)

            import json

            # Сохраняем название группы для главного товара
            if group_name:
                cur.execute("UPDATE products SET group_name = %s WHERE product_id = %s", (group_name, main_id))

            # Для каждого выбранного товара собираем параметры
            for pid in selected_ids:
                params = {}
                for key in request.form:
                    if key.startswith(f'param_key_{pid}_'):
                        idx = key.split('_')[-1]
                        param_key = request.form.get(f'param_key_{pid}_{idx}', '').strip()
                        param_value = request.form.get(f'param_value_{pid}_{idx}', '').strip()
                        if param_key and param_value:
                            params[param_key] = param_value

                cur.execute("""
                    UPDATE products 
                    SET group_id = %s, params = %s 
                    WHERE product_id = %s
                """, (main_id, json.dumps(params, ensure_ascii=False), pid))

            conn.commit()

        cur.close()
        conn.close()
        return redirect('/admin/products')

    cur.close()
    conn.close()
    return render_template('admin_merge_products.html', products=products, groups=groups)


@app.route('/admin/get_group/<int:group_id>')
@admin_required
def get_group(group_id):
    conn = get_connection()
    cur = conn.cursor()

    # Получаем все товары в группе
    cur.execute("""
        SELECT product_id, product_name, params 
        FROM products 
        WHERE group_id = %s OR product_id = %s
    """, (group_id, group_id))
    products_in_group = cur.fetchall()

    group_product_ids = [p[0] for p in products_in_group]
    product_params = {}
    for p in products_in_group:
        product_params[p[0]] = p[2] if p[2] else {}

    # Получаем название группы
    cur.execute("SELECT group_name FROM products WHERE product_id = %s", (group_id,))
    group_name_row = cur.fetchone()
    group_name = group_name_row[0] if group_name_row else None

    cur.close()
    conn.close()

    return jsonify({
        'main_product_id': group_id,
        'group_name': group_name,
        'group_product_ids': group_product_ids,
        'product_params': product_params
    })

# =====================================================
# Админка: загрузка CSV (простая, без проверок)
# =====================================================
@app.route('/admin/upload_csv_simple', methods=['GET', 'POST'])
@admin_or_manager_required
def admin_upload_csv_simple():
    if request.method == 'POST':
        file = request.files['file']
        if not file:
            return "Файл не выбран"

        # Пробуем разные кодировки
        raw = file.read()
        for enc in ['utf-8-sig', 'cp1251', 'latin1', 'cp866']:
            try:
                content = raw.decode(enc)
                break
            except:
                continue
        else:
            return "Не удалось определить кодировку файла"
        from io import StringIO
        df = pd.read_csv(StringIO(content), sep=';', header=None, dtype=str)

        conn = get_connection()
        cur = conn.cursor()

        store_id = 1
        inserted = 0

        for idx, row in df.iterrows():
            name = str(row[0]).strip()
            if not name or name in ['nan', 'None']:
                continue

            article = str(row[4]).strip() if len(row) > 4 else ''
            if not article or article == 'nan' or len(article) < 5:
                continue

            quantity = 0
            if len(row) > 6:
                try:
                    quantity = float(str(row[6]).replace(',', '.').replace(' ', '').replace(' ', ''))
                except:
                    pass
            if quantity == 0:
                continue

            price = 0
            if len(row) > 7:
                try:
                    price = float(str(row[7]).replace(',', '.').replace(' ', '').replace(' ', ''))
                except:
                    pass
            if price == 0:
                continue

            if name in ['Алеся', 'Горького', 'Торговая 4', 'Молочное', 'Элма', 'Элма МТС', 'Преминина', 'Форум', 'Апельсин',
                        'Товар Дилера', 'Телефоны', 'Кнопочные телефоны', 'Сенсорные телефоны', 'Итого']:
                continue

            brand = name.split()[0] if name else None

            cur.execute("""
                INSERT INTO products (product_name, brand, price, product_code)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (product_code) DO UPDATE
                SET product_name = EXCLUDED.product_name,
                    brand = COALESCE(EXCLUDED.brand, products.brand),
                    price = EXCLUDED.price
                RETURNING product_id
            """, (name, brand, price, article))

            product_id = cur.fetchone()[0]
            inserted += 1

            cur.execute("""
                INSERT INTO stock_balances (store_id, product_id, quantity, reserved)
                VALUES (%s, %s, %s, 0)
                ON CONFLICT (store_id, product_id) DO UPDATE
                SET quantity = EXCLUDED.quantity,
                    last_updated = CURRENT_TIMESTAMP
            """, (store_id, product_id, quantity))

        conn.commit()
        cur.close()
        conn.close()

        return f"""
        <div style="padding:20px; font-family:Arial;">
            <h2>Загрузка завершена</h2>
            <p>Товаров добавлено: <strong>{inserted}</strong></p>
            <a href="/admin/products">← Вернуться к товарам</a>
        </div>
        """

    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Загрузка CSV</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
        <div class="container mt-5" style="max-width: 600px;">
            <div class="card shadow">
                <div class="card-header bg-primary text-white">
                    <h3 class="mb-0">📂 Загрузка CSV</h3>
                </div>
                <div class="card-body">
                    <form method="post" enctype="multipart/form-data">
                        <input type="file" name="file" class="form-control" accept=".csv" required>
                        <button type="submit" class="btn btn-primary mt-3 w-100">Загрузить</button>
                    </form>
                </div>
            </div>
        </div>
    </body>
    </html>
    '''


# =====================================================
# Админка: загрузка из 1С (TXT с табуляцией)
# =====================================================
@app.route('/admin/upload_1c_txt', methods=['GET', 'POST'])
@admin_or_manager_required
def admin_upload_1c_txt():
    if request.method == 'POST':
        file = request.files['file']
        if not file:
            return "Файл не выбран"

        raw = file.read()

        # Пробуем кодировки
        content = None
        for enc in ['utf-8-sig', 'cp1251', 'windows-1251', 'latin1']:
            try:
                content = raw.decode(enc)
                break
            except:
                continue

        if content is None:
            return "Не удалось определить кодировку"

        from io import StringIO

        # Читаем файл построчно
        lines = content.split('\n')

        # Ищем заголовки
        header_line = None
        for i, line in enumerate(lines):
            if 'Магазин' in line and 'Номенклатура' in line:
                header_line = i
                break

        if header_line is None:
            return "Не найден заголовок с колонками"

        data_lines = lines[header_line + 1:]

        conn = get_connection()
        cur = conn.cursor()

        inserted = 0
        skipped = 0

        for line_num, line in enumerate(data_lines):
            if not line.strip():
                continue

            parts = line.split('\t')
            if len(parts) < 11:
                skipped += 1
                continue

            # Магазин (колонка 1)
            store_name = parts[1].strip()
            if not store_name or store_name in ['nan', 'None']:
                store_name = 'Главный магазин'

            # Название товара (колонка 3)
            name = parts[3].strip()
            if not name or name in ['nan', 'None', '']:
                skipped += 1
                continue

            # Артикул товара (колонка 9)
            article = parts[9].strip() if len(parts) > 9 else ''
            if not article or article in ['nan', 'None', '']:
                skipped += 1
                continue

            # Количество (колонка 4)
            quantity = 0
            try:
                quantity = float(parts[4].replace(',', '.').replace(' ', ''))
            except:
                pass
            if quantity == 0:
                skipped += 1
                continue

            # Цена (колонка 10)
            price = 0
            try:
                price = float(parts[10].replace(',', '.').replace(' ', '').replace(' ', ''))
            except:
                pass
            if price == 0:
                skipped += 1
                continue

            # Бренд (колонка 7)
            brand_name = parts[7].strip() if len(parts) > 7 else ''
            final_brand = brand_name if brand_name and brand_name not in ['nan', 'None'] else extract_brand(name)

            # Категория (колонка 8) и её код (колонка 9)
            category_name = parts[8].strip() if len(parts) > 8 else ''
            category_code = parts[9].strip() if len(parts) > 9 else ''

            # =====================================================
            # Определение категории (без дублирования)
            # =====================================================
            category_id = None

            if category_code and category_code not in ['nan', 'None', '']:
                cur.execute("SELECT category_id FROM categories WHERE code_1c = %s", (category_code,))
                row = cur.fetchone()
                if row:
                    category_id = row[0]

            if category_id is None and category_name and category_name not in ['nan', 'None', '']:
                cur.execute("SELECT category_id FROM categories WHERE category_name = %s", (category_name,))
                row = cur.fetchone()
                if row:
                    category_id = row[0]

            if category_id is None and category_name and category_name not in ['nan', 'None', '']:
                try:
                    cur.execute("""
                        INSERT INTO categories (category_name, code_1c)
                        VALUES (%s, %s)
                        RETURNING category_id
                    """, (category_name, category_code))
                    category_id = cur.fetchone()[0]
                except:
                    cur.execute("SELECT category_id FROM categories WHERE category_name = %s", (category_name,))
                    row = cur.fetchone()
                    if row:
                        category_id = row[0]

            # =====================================================
            # Магазин
            # =====================================================
            cur.execute("SELECT store_id FROM stores WHERE store_name = %s", (store_name,))
            store_row = cur.fetchone()
            if store_row:
                store_id = store_row[0]
            else:
                cur.execute("""
                    INSERT INTO stores (store_name, city, address)
                    VALUES (%s, %s, %s)
                    RETURNING store_id
                """, (store_name, 'Вологда', store_name))
                store_id = cur.fetchone()[0]

            # =====================================================
            # Вставка товара
            # =====================================================
            cur.execute("""
                INSERT INTO products (product_name, brand, price, product_code, category_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (product_code) DO UPDATE
                SET product_name = EXCLUDED.product_name,
                    brand = COALESCE(EXCLUDED.brand, products.brand),
                    price = EXCLUDED.price,
                    category_id = COALESCE(EXCLUDED.category_id, products.category_id)
                RETURNING product_id
            """, (name, final_brand, price, article, category_id))

            product_id = cur.fetchone()[0]
            inserted += 1

            # =====================================================
            # Остатки
            # =====================================================
            cur.execute("""
                INSERT INTO stock_balances (store_id, product_id, quantity, reserved)
                VALUES (%s, %s, %s, 0)
                ON CONFLICT (store_id, product_id) DO UPDATE
                SET quantity = EXCLUDED.quantity,
                    last_updated = CURRENT_TIMESTAMP
            """, (store_id, product_id, quantity))

        conn.commit()
        cur.close()
        conn.close()

        return f"""
        <div style="padding:20px; font-family:Arial;">
            <h2>Загрузка завершена</h2>
            <p>Товаров добавлено/обновлено: <strong>{inserted}</strong></p>
            <p>Пропущено строк: <strong>{skipped}</strong></p>
            <a href="/admin/products">← Вернуться к товарам</a>
        </div>
        """

    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Загрузка из 1С (TXT)</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
        <div class="container mt-5" style="max-width: 600px;">
            <div class="card shadow">
                <div class="card-header bg-primary text-white">
                    <h3 class="mb-0">📂 Загрузка товаров из 1С</h3>
                </div>
                <div class="card-body">
                    <form method="post" enctype="multipart/form-data">
                        <div class="mb-3">
                            <label class="form-label">Файл .txt (табуляция, UTF-8)</label>
                            <input type="file" name="file" class="form-control" accept=".txt" required>
                            <small class="text-muted">
                                Категории привязываются по коду 1С. Названия можно менять в админке.
                            </small>
                        </div>
                        <button type="submit" class="btn btn-primary w-100">Загрузить</button>
                    </form>
                </div>
            </div>
        </div>
    </body>
    </html>
    '''


# =====================================================
# Админка: отчёт по бренду
# =====================================================

@app.route('/admin/brand_report', methods=['GET', 'POST'])
@admin_or_manager_required
def admin_brand_report():
    conn = get_connection()
    cur = conn.cursor()

    # Получаем список брендов
    cur.execute("""
        SELECT DISTINCT brand 
        FROM products 
        WHERE brand IS NOT NULL AND brand != '' 
        ORDER BY brand
    """)
    brands = [row[0] for row in cur.fetchall()]

    report_data = None
    selected_brand = None

    if request.method == 'POST':
        selected_brand = request.form['brand']

        # Статистика по бренду
        cur.execute("""
            SELECT 
                MIN(price) as min_price,
                MAX(price) as max_price,
                AVG(price) as avg_price,
                COUNT(*) as product_count
            FROM products
            WHERE brand = %s
        """, (selected_brand,))

        stats = cur.fetchone()

        # Список товаров бренда
        cur.execute("""
            SELECT product_name, price, product_code
            FROM products
            WHERE brand = %s
            ORDER BY price
        """, (selected_brand,))

        products = cur.fetchall()

        report_data = {
            'min_price': stats[0],
            'max_price': stats[1],
            'avg_price': round(stats[2], 2) if stats[2] else 0,
            'product_count': stats[3],
            'products': products
        }

    cur.close()
    conn.close()

    return render_template('admin_brand_report.html',
                           brands=brands,
                           report=report_data,
                           selected_brand=selected_brand)


@app.route('/cart/count')
def cart_count():
    if 'user_id' not in session:
        return jsonify({'count': 0})

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT cart_id FROM carts WHERE user_id = %s", (session['user_id'],))
    cart = cur.fetchone()

    if not cart:
        cur.close()
        conn.close()
        return jsonify({'count': 0})

    cur.execute("SELECT SUM(quantity) as total FROM cart_items WHERE cart_id = %s", (cart[0],))
    total = cur.fetchone()[0] or 0

    cur.close()
    conn.close()

    return jsonify({'count': int(total)})


@app.route('/admin/categories')
@admin_required
def admin_categories():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.category_id, c.category_name, p.category_name as parent_name
        FROM categories c
        LEFT JOIN categories p ON c.parent_id = p.category_id
        ORDER BY c.category_id
    """)
    categories = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin_categories.html', categories=categories)

@app.route('/admin/category/add', methods=['POST'])
@admin_required
def admin_category_add():
    name = request.form['category_name'].strip()
    parent_id = request.form.get('parent_id') or None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO categories (category_name, parent_id) VALUES (%s, %s)", (name, parent_id))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/admin/categories')

@app.route('/admin/category/<int:category_id>/edit', methods=['POST'])
@admin_required
def admin_category_edit(category_id):
    name = request.form['category_name'].strip()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE categories SET category_name = %s WHERE category_id = %s", (name, category_id))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/admin/categories')

@app.route('/admin/category/<int:category_id>/delete', methods=['POST'])
@admin_required
def admin_category_delete(category_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM categories WHERE category_id = %s", (category_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/admin/categories')

@app.route('/admin/stores')
@admin_required
def admin_stores():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT store_id, store_name, city, address, latitude, longitude, working_hours, is_visible FROM stores ORDER BY store_name")
    stores = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin_stores.html', stores=stores)


@app.route('/admin/store/add', methods=['GET', 'POST'])
@admin_required
def admin_store_add():
    if request.method == 'POST':
        store_name = request.form['store_name']
        city = request.form.get('city', 'Вологда')
        address = request.form.get('address', '')
        latitude = request.form.get('latitude') or None
        longitude = request.form.get('longitude') or None
        working_hours = request.form.get('working_hours', '10:00–20:00')
        is_visible = request.form.get('is_visible') == 'on'

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO stores (store_name, city, address, latitude, longitude, working_hours, is_visible)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (store_name, city, address, latitude, longitude, working_hours, is_visible))
        conn.commit()
        cur.close()
        conn.close()
        return redirect('/admin/stores')

    return render_template('admin_store_form.html', title="Добавить магазин")

#точки
@app.route('/admin/store/<int:store_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_store_edit(store_id):
    conn = get_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        store_name = request.form['store_name']
        city = request.form.get('city', 'Вологда')
        address = request.form.get('address', '')

        # Обработка координат
        lat_raw = request.form.get('latitude')
        lon_raw = request.form.get('longitude')

        latitude = None
        longitude = None

        if lat_raw and lat_raw not in ('', 'None'):
            try:
                latitude = float(lat_raw)
            except:
                pass

        if lon_raw and lon_raw not in ('', 'None'):
            try:
                longitude = float(lon_raw)
            except:
                pass

        working_hours = request.form.get('working_hours', '10:00–20:00')
        is_visible = request.form.get('is_visible') == 'on'

        cur.execute("""
            UPDATE stores 
            SET store_name=%s, city=%s, address=%s, latitude=%s, longitude=%s, working_hours=%s, is_visible=%s
            WHERE store_id=%s
        """, (store_name, city, address, latitude, longitude, working_hours, is_visible, store_id))
        conn.commit()
        cur.close()
        conn.close()
        return redirect('/admin/stores')

    cur.execute(
        "SELECT store_id, store_name, city, address, latitude, longitude, working_hours, is_visible FROM stores WHERE store_id=%s",
        (store_id,))
    store = cur.fetchone()
    cur.close()
    conn.close()
    return render_template('admin_store_form.html', title="Редактировать магазин", store=store)


@app.route('/admin/store/<int:store_id>/delete', methods=['POST'])
@admin_required
def admin_store_delete(store_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM stores WHERE store_id=%s", (store_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/admin/stores')

# =====================================================
# Запуск
# =====================================================
if __name__ == '__main__':
    app.run(debug=True)
