import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class DataProcessor:
    """Process transaction data for ML model"""
    
    def __init__(self, mysql_connection):
        self.mysql = mysql_connection
    
    def get_user_transactions(self, user_id, months=6):
        """Fetch user transactions from database"""
        cur = self.mysql.connection.cursor()
        
        # Get transactions from last N months
        query = """
            SELECT 
                t.transaction_id,
                t.amount,
                t.description,
                t.transaction_date,
                c.name as category_name,
                c.type as category_type
            FROM transactions t
            JOIN categories c ON t.category_id = c.category_id
            WHERE t.user_id = %s 
            AND t.transaction_date >= DATE_SUB(CURRENT_DATE(), INTERVAL %s MONTH)
            ORDER BY t.transaction_date DESC
        """
        
        cur.execute(query, (user_id, months))
        transactions = cur.fetchall()
        cur.close()
        
        if not transactions:
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(transactions)
        df['transaction_date'] = pd.to_datetime(df['transaction_date'])
        df['amount'] = df['amount'].astype(float)
        
        return df
    
    def extract_features(self, df):
        """Extract ML features from transaction data"""
        if df is None or len(df) == 0:
            return None
        
        # Filter only expenses
        expenses_df = df[df['category_type'] == 'expense'].copy()
        
        if len(expenses_df) == 0:
            return None
        
        # Calculate total expenses
        total_expense = expenses_df['amount'].sum()
        
        # Category-wise aggregation
        category_stats = expenses_df.groupby('category_name').agg({
            'amount': ['sum', 'mean', 'count', 'std', 'max']
        }).reset_index()
        
        category_stats.columns = ['category', 'total', 'avg', 'count', 'std', 'max']
        
        # Calculate percentages
        category_stats['percentage'] = (category_stats['total'] / total_expense * 100).round(2)
        
        # Fill NaN standard deviations with 0 (for categories with only 1 transaction)
        category_stats['std'] = category_stats['std'].fillna(0)
        
        # Add temporal features
        expenses_df['day_of_week'] = expenses_df['transaction_date'].dt.dayofweek
        expenses_df['is_weekend'] = expenses_df['day_of_week'].isin([5, 6]).astype(int)
        
        # Weekend vs weekday spending
        weekend_spending = expenses_df[expenses_df['is_weekend'] == 1]['amount'].sum()
        weekday_spending = expenses_df[expenses_df['is_weekend'] == 0]['amount'].sum()
        
        # Create feature vector for clustering
        features = {
            'total_expense': total_expense,
            'num_transactions': len(expenses_df),
            'avg_transaction': expenses_df['amount'].mean(),
            'std_transaction': expenses_df['amount'].std(),
            'max_transaction': expenses_df['amount'].max(),
            'weekend_spending_ratio': weekend_spending / total_expense if total_expense > 0 else 0,
            'category_stats': category_stats,
            'num_categories': len(category_stats),
            'top_category': category_stats.nlargest(1, 'total').iloc[0]['category'] if len(category_stats) > 0 else None,
            'top_category_percentage': category_stats.nlargest(1, 'total').iloc[0]['percentage'] if len(category_stats) > 0 else 0
        }
        
        return features
    
    def prepare_clustering_data(self, features):
        """Prepare feature vector for K-Means clustering"""
        if features is None:
            return None
        
        category_stats = features['category_stats']
        
        # Create a feature vector with percentages for each category
        feature_vector = []
        
        # Standard categories (ensure consistency across users)
        standard_categories = [
            'Food & Dining', 'Transportation', 'Shopping', 
            'Entertainment', 'Bills & Utilities', 'Healthcare', 'Other'
        ]
        
        for cat in standard_categories:
            cat_data = category_stats[category_stats['category'] == cat]
            if len(cat_data) > 0:
                feature_vector.append(cat_data.iloc[0]['percentage'])
            else:
                feature_vector.append(0.0)
        
        # Add behavioral features
        feature_vector.extend([
            features['avg_transaction'] / 1000,  # Normalize to thousands
            features['std_transaction'] / 1000,
            features['weekend_spending_ratio'] * 100,
            features['num_transactions'] / 10  # Normalize transaction count
        ])
        
        return np.array(feature_vector).reshape(1, -1)
    
    def get_income_data(self, user_id, months=6):
        """Get income data for comparison"""
        cur = self.mysql.connection.cursor()
        
        query = """
            SELECT COALESCE(SUM(t.amount), 0) as total_income
            FROM transactions t
            JOIN categories c ON t.category_id = c.category_id
            WHERE t.user_id = %s 
            AND c.type = 'income'
            AND t.transaction_date >= DATE_SUB(CURRENT_DATE(), INTERVAL %s MONTH)
        """
        
        cur.execute(query, (user_id, months))
        result = cur.fetchone()
        cur.close()
        
        return float(result['total_income']) if result else 0.0
    
    def calculate_savings_rate(self, user_id, months=6):
        """Calculate user's savings rate"""
        df = self.get_user_transactions(user_id, months)
        
        if df is None or len(df) == 0:
            return 0.0
        
        total_income = df[df['category_type'] == 'income']['amount'].sum()
        total_expense = df[df['category_type'] == 'expense']['amount'].sum()
        
        if total_income == 0:
            return 0.0
        
        savings = total_income - total_expense
        savings_rate = (savings / total_income) * 100
        
        return round(savings_rate, 2)