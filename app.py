from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
from calendar import monthrange
import json

# ML imports
try:
    from ml_model.data_processor import DataProcessor
    from ml_model.spending_analyzer import SpendingAnalyzer
    from ml_model.recommendation_engine import RecommendationEngine
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("Warning: ML modules not found. ML features will be disabled.")

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

# ============= AUTHENTICATION ROUTES =============

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
        cursor.execute("SELECT * FROM users WHERE email = %s OR username = %s", (email, username))
        existing_user = cursor.fetchone()
        
        if existing_user:
            flash('Username or email already exists', 'error')
            cursor.close()
            return render_template('register.html')
        
        password_hash = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                      (username, email, password_hash))
        mysql.connection.commit()
        
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
        
        session['user_id'] = user['user_id']
        session['username'] = user['username']
        
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

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

# ============= DASHBOARD =============

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
    
    # Get monthly profit
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
    
    # Get monthly loss
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
    
    # Get spending by category
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

# ============= TRANSACTION ROUTES =============

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
    cursor.execute("SELECT category_id FROM categories WHERE user_id = %s AND name = %s", 
                  (user_id, category_name))
    category = cursor.fetchone()
    
    if category:
        cursor.execute("""
            INSERT INTO transactions (user_id, category_id, amount, description, transaction_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, category['category_id'], amount, description, date))
        mysql.connection.commit()
        
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

# ============= LOGS PAGE =============

@app.route('/logs')
@login_required
def logs():
    user_id = session['user_id']
    cursor = mysql.connection.cursor()
    
    # Get filter parameters
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    category = request.args.get('category', '')
    trans_type = request.args.get('type', '')
    
    # Build query
    query = """
        SELECT t.*, c.name as category_name, c.type as transaction_type
        FROM transactions t
        JOIN categories c ON t.category_id = c.category_id
        WHERE t.user_id = %s
    """
    params = [user_id]
    
    if start_date:
        query += " AND DATE(t.transaction_date) >= %s"
        params.append(start_date)
    
    if end_date:
        query += " AND DATE(t.transaction_date) <= %s"
        params.append(end_date)
    
    if category:
        query += " AND c.name = %s"
        params.append(category)
    
    if trans_type:
        query += " AND c.type = %s"
        params.append(trans_type)
    
    query += " ORDER BY t.transaction_date DESC"
    
    cursor.execute(query, params)
    transactions = cursor.fetchall()
    
    # Calculate statistics
    total_income = sum(t['amount'] for t in transactions if t['transaction_type'] == 'income')
    total_expense = sum(t['amount'] for t in transactions if t['transaction_type'] == 'expense')
    
    # Get categories
    cursor.execute("SELECT * FROM categories WHERE user_id = %s", (user_id,))
    categories = cursor.fetchall()
    
    cursor.close()
    
    return render_template('logs.html',
                         transactions=transactions,
                         categories=categories,
                         total_count=len(transactions),
                         total_income=total_income,
                         total_expense=total_expense,
                         start_date=start_date,
                         end_date=end_date,
                         category=category,
                         trans_type=trans_type)

# ============= BUDGET ROUTES =============

@app.route('/budget')
@login_required
def budget():
    user_id = session['user_id']
    cursor = mysql.connection.cursor()
    
    # Get categories
    cursor.execute("SELECT * FROM categories WHERE user_id = %s", (user_id,))
    categories = cursor.fetchall()
    
    # Get budgets with spending data
    cursor.execute("""
        SELECT 
            b.budget_id,
            b.limit_amount,
            b.month_year,
            c.name as category_name,
            c.category_id,
            COALESCE(SUM(t.amount), 0) as spent
        FROM budgets b
        LEFT JOIN categories c ON b.category_id = c.category_id
        LEFT JOIN transactions t ON c.category_id = t.category_id 
            AND DATE_FORMAT(t.transaction_date, '%%Y-%%m') = b.month_year
        WHERE b.user_id = %s
        GROUP BY b.budget_id, b.limit_amount, b.month_year, c.name, c.category_id
        ORDER BY b.month_year DESC, c.name
    """, (user_id,))
    budgets = cursor.fetchall()
    
    # Calculate budget status and alerts
    budget_alerts = []
    for budget in budgets:
        spent = float(budget['spent'])
        limit = float(budget['limit_amount'])
        percentage = (spent / limit * 100) if limit > 0 else 0
        
        budget['percentage'] = percentage
        budget['status'] = 'safe' if percentage < 75 else ('warning' if percentage < 100 else 'danger')
        
        # Generate alerts for over-budget or close to limit
        if percentage >= 100:
            budget_alerts.append({
                'level': 'danger',
                'icon': '🚨',
                'message': f'{budget["category_name"]} is over budget! Spent ₹{spent:.2f} of ₹{limit:.2f}'
            })
        elif percentage >= 85:
            budget_alerts.append({
                'level': 'warning',
                'icon': '⚠️',
                'message': f'{budget["category_name"]} is at {percentage:.0f}% of budget limit'
            })
    
    cursor.close()
    
    return render_template('budget.html',
                         categories=categories,
                         budgets=budgets,
                         budget_alerts=budget_alerts,
                         min=min)

@app.route('/create_budget', methods=['POST'])
@login_required
def create_budget():
    user_id = session['user_id']
    category_name = request.form.get('category')
    limit_amount = request.form.get('limit_amount')
    month_year = request.form.get('month_year')
    
    cursor = mysql.connection.cursor()
    
    # Get category_id
    cursor.execute("SELECT category_id FROM categories WHERE user_id = %s AND name = %s",
                  (user_id, category_name))
    category = cursor.fetchone()
    
    if category:
        # Check if budget already exists
        cursor.execute("""
            SELECT * FROM budgets 
            WHERE user_id = %s AND category_id = %s AND month_year = %s
        """, (user_id, category['category_id'], month_year))
        
        existing = cursor.fetchone()
        
        if existing:
            flash('Budget already exists for this category and month', 'error')
        else:
            cursor.execute("""
                INSERT INTO budgets (user_id, category_id, limit_amount, month_year)
                VALUES (%s, %s, %s, %s)
            """, (user_id, category['category_id'], limit_amount, month_year))
            mysql.connection.commit()
            flash('Budget created successfully!', 'success')
    
    cursor.close()
    return redirect(url_for('budget'))

@app.route('/delete_budget/<int:budget_id>', methods=['POST'])
@login_required
def delete_budget(budget_id):
    user_id = session['user_id']
    cursor = mysql.connection.cursor()
    
    cursor.execute("DELETE FROM budgets WHERE budget_id = %s AND user_id = %s",
                  (budget_id, user_id))
    mysql.connection.commit()
    cursor.close()
    
    return jsonify({'success': True})

# ============= VISUAL PAGE =============

@app.route('/visual')
@login_required
def visual():
    user_id = session['user_id']
    cursor = mysql.connection.cursor()
    
    # 1. Category spending for current month (for pie chart)
    cursor.execute("""
        SELECT c.name, COALESCE(SUM(t.amount), 0) as total
        FROM categories c
        LEFT JOIN transactions t ON c.category_id = t.category_id 
            AND MONTH(t.transaction_date) = MONTH(CURRENT_DATE())
            AND YEAR(t.transaction_date) = YEAR(CURRENT_DATE())
        WHERE c.user_id = %s AND c.type = 'expense'
        GROUP BY c.category_id, c.name
        ORDER BY total DESC
    """, (user_id,))
    category_spending = cursor.fetchall()
    
    # 2. Monthly trend for last 6 months (for line/bar charts)
    monthly_data = []
    for i in range(5, -1, -1):
        date = datetime.now() - timedelta(days=i*30)
        month = date.strftime('%b %y')
        
        # Income
        cursor.execute("""
            SELECT COALESCE(SUM(t.amount), 0) as income
            FROM transactions t
            JOIN categories c ON t.category_id = c.category_id
            WHERE t.user_id = %s 
            AND c.type = 'income'
            AND MONTH(t.transaction_date) = %s
            AND YEAR(t.transaction_date) = %s
        """, (user_id, date.month, date.year))
        income_result = cursor.fetchone()
        
        # Expense
        cursor.execute("""
            SELECT COALESCE(SUM(t.amount), 0) as expense
            FROM transactions t
            JOIN categories c ON t.category_id = c.category_id
            WHERE t.user_id = %s 
            AND c.type = 'expense'
            AND MONTH(t.transaction_date) = %s
            AND YEAR(t.transaction_date) = %s
        """, (user_id, date.month, date.year))
        expense_result = cursor.fetchone()
        
        monthly_data.append({
            'month': month,
            'income': float(income_result['income']),
            'expense': float(expense_result['expense'])
        })
    
    # 3. Daily spending for current month
    now = datetime.now()
    days_in_month = monthrange(now.year, now.month)[1]
    daily_spending = []
    
    for day in range(1, days_in_month + 1):
        cursor.execute("""
            SELECT COALESCE(SUM(t.amount), 0) as amount
            FROM transactions t
            JOIN categories c ON t.category_id = c.category_id
            WHERE t.user_id = %s 
            AND c.type = 'expense'
            AND DAY(t.transaction_date) = %s
            AND MONTH(t.transaction_date) = %s
            AND YEAR(t.transaction_date) = %s
        """, (user_id, day, now.month, now.year))
        result = cursor.fetchone()
        
        daily_spending.append({
            'day': str(day),
            'amount': float(result['amount'])
        })
    
    cursor.close()
    
    return render_template('visual.html',
                         category_spending=category_spending,
                         monthly_data=monthly_data,
                         daily_spending=daily_spending)

# ============= PROFILE =============

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

# ============= ML INSIGHTS ROUTES (ET-AI) =============

@app.route('/insights')
@login_required
def insights():
    if not ML_AVAILABLE:
        flash('ML features are currently unavailable. Please check ML module installation.', 'warning')
        return redirect(url_for('dashboard'))
    return render_template('insights.html', username=session.get('username'))

# API: Get ML Insights
@app.route('/api/ml/insights', methods=['GET'])
@login_required
def api_ml_insights():
    if not ML_AVAILABLE:
        return jsonify({
            'success': False,
            'message': 'ML features are not available. Please install required ML modules.'
        }), 503
    
    user_id = session['user_id']
    
    try:
        # Initialize ML components
        data_processor = DataProcessor(mysql)
        analyzer = SpendingAnalyzer()
        rec_engine = RecommendationEngine()
        
        # Get transaction data
        df = data_processor.get_user_transactions(user_id, months=6)
        
        if df is None or len(df) == 0:
            return jsonify({
                'success': False,
                'message': 'Not enough data. Add at least 10 transactions to get insights.'
            }), 400
        
        # Extract features
        features = data_processor.extract_features(df)
        
        if features is None:
            return jsonify({
                'success': False,
                'message': 'Unable to extract features from your transactions.'
            }), 400
        
        # Prepare data for clustering
        feature_vector = data_processor.prepare_clustering_data(features)
        
        # Predict cluster
        cluster_id = analyzer.predict_cluster(feature_vector)
        cluster_insights = analyzer.get_cluster_insights(cluster_id, features)
        
        # Get income for better recommendations
        income = data_processor.get_income_data(user_id, months=6)
        monthly_income = income / 6 if income > 0 else None
        
        # Generate recommendations
        recommendations = rec_engine.generate_recommendations(
            features, 
            cluster_insights, 
            monthly_income
        )
        
        # Prioritize recommendations
        recommendations = rec_engine.prioritize_recommendations(recommendations)
        
        # Calculate total savings potential
        total_savings = rec_engine.calculate_total_savings_potential(recommendations)
        
        # Calculate savings rate
        savings_rate = data_processor.calculate_savings_rate(user_id, months=6)
        
        # Store insights in database
        store_ml_insights(user_id, cluster_id, cluster_insights, recommendations, total_savings)
        
        return jsonify({
            'success': True,
            'cluster_insights': cluster_insights,
            'recommendations': recommendations,
            'total_savings_potential': total_savings,
            'savings_rate': savings_rate,
            'category_breakdown': features['category_stats'].to_dict('records'),
            'spending_summary': {
                'total_expense': features['total_expense'],
                'num_transactions': features['num_transactions'],
                'avg_transaction': features['avg_transaction'],
                'top_category': features['top_category'],
                'top_category_percentage': features['top_category_percentage']
            }
        })
        
    except Exception as e:
        print(f"Error generating insights: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }), 500

# API: Retrain ML Model
@app.route('/api/ml/retrain', methods=['POST'])
@login_required
def api_retrain_model():
    if not ML_AVAILABLE:
        return jsonify({
            'success': False,
            'message': 'ML features are not available.'
        }), 503
    
    try:
        data_processor = DataProcessor(mysql)
        analyzer = SpendingAnalyzer()
        
        user_id = session['user_id']
        df = data_processor.get_user_transactions(user_id, months=6)
        
        if df is None or len(df) < 10:
            return jsonify({
                'success': False,
                'message': 'Not enough data to train model'
            }), 400
        
        # Extract features
        features = data_processor.extract_features(df)
        feature_vector = data_processor.prepare_clustering_data(features)
        
        # Train model
        analyzer.train_model(feature_vector)
        
        return jsonify({
            'success': True,
            'message': 'Model retrained successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retraining model: {str(e)}'
        }), 500

# Helper function to store ML insights
def store_ml_insights(user_id, cluster_id, insights, recommendations, total_savings):
    try:
        cur = mysql.connection.cursor()
        
        # Create table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ml_insights (
                insight_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                cluster_id INT,
                spending_persona VARCHAR(50),
                top_category VARCHAR(100),
                top_category_percentage DECIMAL(5,2),
                potential_savings DECIMAL(10,2),
                recommendations TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        # Prepare recommendations as JSON string
        rec_json = json.dumps([
            {
                'message': r['message'],
                'savings': r.get('potential_savings', 0),
                'priority': r.get('priority', 'low')
            } 
            for r in recommendations[:5]
        ])
        
        # Insert insights
        cur.execute("""
            INSERT INTO ml_insights 
            (user_id, cluster_id, spending_persona, top_category, top_category_percentage, 
             potential_savings, recommendations)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            cluster_id,
            insights.get('persona', 'Unknown'),
            insights.get('main_focus', 'General'),
            insights.get('top_category_percentage', 0),
            total_savings,
            rec_json
        ))
        
        mysql.connection.commit()
        cur.close()
        
        return True
    except Exception as e:
        print(f"Error storing insights: {e}")
        import traceback
        traceback.print_exc()
        return False

# API: Get Insight History
@app.route('/api/ml/history', methods=['GET'])
@login_required
def api_insight_history():
    if not ML_AVAILABLE:
        return jsonify({
            'success': False,
            'message': 'ML features are not available.'
        }), 503
    
    user_id = session['user_id']
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT 
                spending_persona,
                potential_savings,
                created_at
            FROM ml_insights
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 10
        """, (user_id,))
        
        history = cur.fetchall()
        cur.close()
        
        formatted_history = []
        for h in history:
            formatted_history.append({
                'persona': h['spending_persona'],
                'savings': float(h['potential_savings']),
                'date': h['created_at'].strftime('%b %d, %Y')
            })
        
        return jsonify({
            'success': True,
            'history': formatted_history
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching history: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(debug=True)