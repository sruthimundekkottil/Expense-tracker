from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here_change_in_production'

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'expense_tracker'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            
            # Log activity
            cursor = mysql.connection.cursor()
            cursor.execute("INSERT INTO activity_logs (user_id, action) VALUES (%s, %s)", 
                         (user['user_id'], 'Login'))
            mysql.connection.commit()
            cursor.close()
            
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        cursor = mysql.connection.cursor()
        
        # Check if user exists
        cursor.execute("SELECT * FROM users WHERE email = %s OR username = %s", (email, username))
        existing_user = cursor.fetchone()
        
        if existing_user:
            flash('Username or email already exists', 'error')
            cursor.close()
            return render_template('register.html')
        
        # Create user
        password_hash = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                      (username, email, password_hash))
        mysql.connection.commit()
        
        # Get the new user
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        # Create default categories
        default_categories = [
            ('Food & Dining', 'expense'),
            ('Transportation', 'expense'),
            ('Shopping', 'expense'),
            ('Entertainment', 'expense'),
            ('Bills & Utilities', 'expense'),
            ('Healthcare', 'expense'),
            ('Income', 'income'),
            ('Other', 'expense')
        ]
        
        for cat_name, cat_type in default_categories:
            cursor.execute("INSERT INTO categories (user_id, name, type) VALUES (%s, %s, %s)",
                         (user['user_id'], cat_name, cat_type))
        
        mysql.connection.commit()
        cursor.close()
        
        # Auto login
        session['user_id'] = user['user_id']
        session['username'] = user['username']
        
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    cursor = mysql.connection.cursor()
    
    # Get current balance
    cursor.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN c.type = 'income' THEN t.amount ELSE -t.amount END), 0) as balance
        FROM transactions t
        JOIN categories c ON t.category_id = c.category_id
        WHERE t.user_id = %s
    """, (user_id,))
    balance_result = cursor.fetchone()
    current_balance = float(balance_result['balance']) if balance_result else 0
    
    # Get monthly profit (current month income)
    cursor.execute("""
        SELECT COALESCE(SUM(t.amount), 0) as monthly_profit
        FROM transactions t
        JOIN categories c ON t.category_id = c.category_id
        WHERE t.user_id = %s 
        AND c.type = 'income'
        AND MONTH(t.transaction_date) = MONTH(CURRENT_DATE())
        AND YEAR(t.transaction_date) = YEAR(CURRENT_DATE())
    """, (user_id,))
    profit_result = cursor.fetchone()
    monthly_profit = float(profit_result['monthly_profit']) if profit_result else 0
    
    # Get monthly loss (current month expenses)
    cursor.execute("""
        SELECT COALESCE(SUM(t.amount), 0) as monthly_loss
        FROM transactions t
        JOIN categories c ON t.category_id = c.category_id
        WHERE t.user_id = %s 
        AND c.type = 'expense'
        AND MONTH(t.transaction_date) = MONTH(CURRENT_DATE())
        AND YEAR(t.transaction_date) = YEAR(CURRENT_DATE())
    """, (user_id,))
    loss_result = cursor.fetchone()
    monthly_loss = float(loss_result['monthly_loss']) if loss_result else 0
    
    # Get recent transactions
    cursor.execute("""
        SELECT t.*, c.name as category_name, c.type as transaction_type
        FROM transactions t
        JOIN categories c ON t.category_id = c.category_id
        WHERE t.user_id = %s
        ORDER BY t.transaction_date DESC
        LIMIT 20
    """, (user_id,))
    transactions = cursor.fetchall()
    
    # Get categories
    cursor.execute("SELECT * FROM categories WHERE user_id = %s", (user_id,))
    categories = cursor.fetchall()
    
    # Get spending by category for current month
    cursor.execute("""
        SELECT c.name, COALESCE(SUM(t.amount), 0) as total
        FROM categories c
        LEFT JOIN transactions t ON c.category_id = t.category_id 
            AND MONTH(t.transaction_date) = MONTH(CURRENT_DATE())
            AND YEAR(t.transaction_date) = YEAR(CURRENT_DATE())
        WHERE c.user_id = %s AND c.type = 'expense'
        GROUP BY c.category_id, c.name
    """, (user_id,))
    category_spending = cursor.fetchall()
    
    cursor.close()
    
    return render_template('dashboard.html', 
                         username=session['username'],
                         current_balance=current_balance,
                         monthly_profit=monthly_profit,
                         monthly_loss=monthly_loss,
                         transactions=transactions,
                         categories=categories,
                         category_spending=category_spending)

@app.route('/add_transaction', methods=['POST'])
@login_required
def add_transaction():
    user_id = session['user_id']
    amount = request.form.get('amount')
    transaction_type = request.form.get('type')
    description = request.form.get('description')
    date = request.form.get('date')
    category_name = request.form.get('category')
    
    cursor = mysql.connection.cursor()
    
    # Get category_id
    cursor.execute("SELECT category_id FROM categories WHERE user_id = %s AND name = %s", 
                  (user_id, category_name))
    category = cursor.fetchone()
    
    if category:
        cursor.execute("""
            INSERT INTO transactions (user_id, category_id, amount, description, transaction_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, category['category_id'], amount, description, date))
        mysql.connection.commit()
        
        # Log activity
        cursor.execute("INSERT INTO activity_logs (user_id, action) VALUES (%s, %s)",
                     (user_id, f'Added transaction: {description}'))
        mysql.connection.commit()
    
    cursor.close()
    return redirect(url_for('dashboard'))

@app.route('/delete_transaction/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    user_id = session['user_id']
    cursor = mysql.connection.cursor()
    
    cursor.execute("DELETE FROM transactions WHERE transaction_id = %s AND user_id = %s",
                  (transaction_id, user_id))
    mysql.connection.commit()
    cursor.close()
    
    return jsonify({'success': True})

@app.route('/logout')
def logout():
    if 'user_id' in session:
        cursor = mysql.connection.cursor()
        cursor.execute("INSERT INTO activity_logs (user_id, action) VALUES (%s, %s)",
                     (session['user_id'], 'Logout'))
        mysql.connection.commit()
        cursor.close()
    
    session.clear()
    return redirect(url_for('login'))

@app.route('/profile')
@login_required
def profile():
    user_id = session['user_id']
    cursor = mysql.connection.cursor()
    
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    
    cursor.execute("""
        SELECT * FROM activity_logs 
        WHERE user_id = %s 
        ORDER BY log_time DESC 
        LIMIT 10
    """, (user_id,))
    logs = cursor.fetchall()
    
    cursor.close()
    return render_template('profile.html', user=user, logs=logs)

if __name__ == '__main__':
    app.run(debug=True)