from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
import hashlib
import random
from datetime import datetime  # Импортируйте datetime

app = Flask(__name__)


app.secret_key = 'your_secret_key'  # Установите свой секретный ключ

DATABASE = 'wallet.db'


def init_db():
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY,
                        username TEXT UNIQUE,
                        password TEXT,
                        balance_zhenyacoin REAL DEFAULT 0,
                        balance_bitcoin REAL DEFAULT 0,
                        balance_ethereum REAL DEFAULT 0,
                        balance_usdt REAL DEFAULT 0,
                        balance_ton REAL DEFAULT 0,
                        wallet_address TEXT UNIQUE
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER,
                        amount REAL,
                        currency TEXT,
                        transaction_type TEXT,
                        recipient_wallet TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(user_id) REFERENCES users(id)
                    )''')
        conn.commit()


def alter_transactions_table():
    """Добавление столбца recipient_wallet, если он отсутствует."""
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        try:
            c.execute("ALTER TABLE transactions ADD COLUMN recipient_wallet TEXT")
            conn.commit()
            print("Столбец recipient_wallet успешно добавлен в таблицу transactions.")
        except sqlite3.OperationalError:
            print("Столбец recipient_wallet уже существует.")


def generate_wallet_address():
    """Генерация уникального адреса кошелька."""
    return hashlib.sha256(str(random.getrandbits(256)).encode()).hexdigest()


def get_user_info(wallet_address):
    """Получение информации о пользователе по адресу кошелька."""
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        user_info = c.execute("SELECT username FROM users WHERE wallet_address = ?", (wallet_address,)).fetchone()
        return user_info if user_info else None


@app.template_filter('datetimeformat')
def datetimeformat(value):
    """Фильтр для форматирования даты и времени."""
    if isinstance(value, str):
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').strftime('%d-%m-%Y %H:%M:%S')
    return value


@app.route('/')
def home():
    if 'username' in session:
        username = session['username']
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            user_info = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            return render_template('home.html', user_info=user_info)
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            user = c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
            if user:
                session['username'] = username
                session['user_id'] = user[0]
                return redirect(url_for('home'))
            else:
                flash('Неверные учетные данные! Попробуйте снова.')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Генерация адреса кошелька
        wallet_address = generate_wallet_address()
        
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            try:
                c.execute("INSERT INTO users (username, password, wallet_address) VALUES (?, ?, ?)", 
                           (username, password, wallet_address))
                conn.commit()
                flash('Регистрация успешна! Вы можете войти в систему.')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Это имя пользователя уже занято. Попробуйте другое.')
    return render_template('register.html')


@app.route('/top_up', methods=['GET', 'POST'])
def top_up():
    if request.method == 'POST':
        currency = request.form.get('currency')
        amount = float(request.form.get('amount'))
        user_id = session.get('user_id')

        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            if currency == 'ZhenyaCoin':
                c.execute("UPDATE users SET balance_zhenyacoin = balance_zhenyacoin + ? WHERE id = ?", (amount, user_id))
            elif currency == 'Bitcoin':
                c.execute("UPDATE users SET balance_bitcoin = balance_bitcoin + ? WHERE id = ?", (amount, user_id))
            elif currency == 'Ethereum':
                c.execute("UPDATE users SET balance_ethereum = balance_ethereum + ? WHERE id = ?", (amount, user_id))
            elif currency == 'USDT':
                c.execute("UPDATE users SET balance_usdt = balance_usdt + ? WHERE id = ?", (amount, user_id))
            elif currency == 'TON':
                c.execute("UPDATE users SET balance_ton = balance_ton + ? WHERE id = ?", (amount, user_id))

            c.execute("INSERT INTO transactions (user_id, amount, currency, transaction_type) VALUES (?, ?, ?, 'Пополнение')", (user_id, amount, currency))
            conn.commit()
            flash('Баланс успешно пополнен!')
            return redirect(url_for('home'))
    return render_template('top_up.html')


@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    if request.method == 'POST':
        recipient_wallet = request.form.get('recipient_wallet')
        amount = request.form.get('amount')
        currency = request.form.get('currency')

        # Проверка на заполненность всех полей
        if not recipient_wallet or not amount or not currency:
            flash('Пожалуйста, заполните все поля!')
            return redirect(url_for('transfer'))

        try:
            amount = float(amount)  # Преобразование суммы в число
        except ValueError:
            flash('Введите корректную сумму!')
            return redirect(url_for('transfer'))

        user_id = session.get('user_id')

        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()

            # Получение баланса пользователя
            user_balance_query = f"SELECT balance_{currency.lower()} FROM users WHERE id = ?"
            user_balance = c.execute(user_balance_query, (user_id,)).fetchone()

            if user_balance is None:
                flash('Пользователь не найден!')
                return redirect(url_for('transfer'))

            user_balance = user_balance[0]

            # Проверка на достаточность средств
            if user_balance >= amount:
                # Проверяем адрес получателя
                recipient_query = "SELECT id FROM users WHERE wallet_address = ?"
                recipient_id = c.execute(recipient_query, (recipient_wallet,)).fetchone()

                if recipient_id is None:
                    flash('Получатель не найден!')
                    return redirect(url_for('transfer'))

                # Обновляем баланс отправителя
                c.execute(f"UPDATE users SET balance_{currency.lower()} = balance_{currency.lower()} - ? WHERE id = ?", (amount, user_id))
                # Обновляем баланс получателя
                c.execute(f"UPDATE users SET balance_{currency.lower()} = balance_{currency.lower()} + ? WHERE id = ?", (amount, recipient_id[0]))

                # Записываем транзакцию
                c.execute("INSERT INTO transactions (user_id, amount, currency, transaction_type, recipient_wallet) VALUES (?, ?, ?, 'Перевод', ?)", (user_id, amount, currency, recipient_wallet))

                conn.commit()  # Коммит транзакции
                flash('Перевод выполнен успешно!')
            else:
                flash('Недостаточно средств для перевода!')

        return redirect(url_for('home'))

    return render_template('transfer.html')


@app.route('/transaction_history')
def transaction_history():
    user_id = session.get('user_id')
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        # Обновленный запрос для получения имен отправителя и получателя
        transactions = c.execute('''
            SELECT t.id, sender.username AS sender_name, receiver.username AS receiver_name, 
                   t.amount, t.currency, t.transaction_type
            FROM transactions t
            JOIN users sender ON t.user_id = sender.id
            LEFT JOIN users receiver ON t.recipient_wallet = receiver.wallet_address
            WHERE t.user_id = ? OR t.recipient_wallet IN (SELECT wallet_address FROM users WHERE id = ?)
        ''', (user_id, user_id)).fetchall()
    return render_template('transaction_history.html', transactions=transactions)

user_data = {
    'username': 'Имя пользователя',  # Замените на нужное имя пользователя
    'profile_image': 'profile_image.png',  # Имя файла изображения в папке static
}

@app.route('/profile')
def profile():
    # Предположим, что вы получаете user_info из базы данных или сессии
    user_info = [None, user_data['username'], user_data['profile_image']]
    
    return render_template('profile.html', user_info=user_info)



@app.route('/exchange', methods=['GET', 'POST'])
def exchange():
    if request.method == 'POST':
        user_id = session.get('user_id')
        from_currency = request.form.get('from_currency')
        to_currency = request.form.get('to_currency')
        amount = float(request.form.get('amount'))

        # Пример обменного курса (нужно заменить реальными курсами)
        exchange_rates = {
            'zhenyacoin': 1.0,  # Обменный курс для ZhenyaCoin
            'bitcoin': 50000.0,  # 1 BTC = 50000 ZHY
            'ethereum': 4000.0,  # 1 ETH = 4000 ZHY
            'usdt': 1.0,        # 1 USDT = 1 ZHY
            'ton': 0.5,        # 1 TON = 0.5 ZHY
        }

        if from_currency not in exchange_rates or to_currency not in exchange_rates:
            flash('Неверная валюта для обмена!')
            return redirect(url_for('exchange'))

        # Проверка наличия средств
        user_balance_query = f"SELECT balance_{from_currency} FROM users WHERE id = ?"
        user_balance = sqlite3.connect(DATABASE).execute(user_balance_query, (user_id,)).fetchone()

        if user_balance is None or user_balance[0] < amount:
            flash('Недостаточно средств для обмена!')
            return redirect(url_for('exchange'))

        # Рассчет обмена
        amount_in_to_currency = (amount * exchange_rates[from_currency]) / exchange_rates[to_currency]

        # Обновляем балансы
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute(f"UPDATE users SET balance_{from_currency} = balance_{from_currency} - ? WHERE id = ?", (amount, user_id))
            c.execute(f"UPDATE users SET balance_{to_currency} = balance_{to_currency} + ? WHERE id = ?", (amount_in_to_currency, user_id))
            conn.commit()

        flash(f'Успешно обменяно {amount} {from_currency} на {amount_in_to_currency} {to_currency}!')
        return redirect(url_for('home'))

    return render_template('exchange.html')


@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('user_id', None)
    flash('Вы вышли из системы.')
    return redirect(url_for('login'))


if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()
    alter_transactions_table()
    app.run(debug=True)
