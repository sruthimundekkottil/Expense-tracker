import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import joblib
import os

class SpendingAnalyzer:
    """ML Model for analyzing spending patterns"""
    
    def __init__(self, n_clusters=3):
        self.n_clusters = n_clusters
        self.model = None
        self.scaler = StandardScaler()
        self.cluster_labels = {
            0: "Budget Master",
            1: "Balanced Saver", 
            2: "Needs Improvement"
        }
        self.model_path = os.path.join('models', 'kmeans_model.pkl')
        self.scaler_path = os.path.join('models', 'scaler.pkl')
    
    def train_model(self, feature_vectors):
        """Train K-Means clustering model"""
        if len(feature_vectors) < self.n_clusters:
            # Not enough data, use default clustering
            self.model = KMeans(n_clusters=min(len(feature_vectors), 3), random_state=42)
        else:
            self.model = KMeans(n_clusters=self.n_clusters, random_state=42, n_init=10)
        
        # Standardize features
        scaled_features = self.scaler.fit_transform(feature_vectors)
        
        # Train model
        self.model.fit(scaled_features)
        
        # Save model
        self._save_model()
        
        return self.model
    
    def predict_cluster(self, feature_vector):
        """Predict which cluster a user belongs to"""
        if self.model is None:
            self._load_model()
        
        if self.model is None:
            # No model trained yet, return default
            return 1  # Balanced Saver
        
        # Standardize features
        scaled_features = self.scaler.transform(feature_vector)
        
        # Predict cluster
        cluster = self.model.predict(scaled_features)[0]
        
        return cluster
    
    def get_cluster_name(self, cluster_id):
        """Get human-readable cluster name"""
        # Adjust based on cluster characteristics
        return self.cluster_labels.get(cluster_id, "Average Spender")
    
    def analyze_cluster_characteristics(self, features, cluster_id):
        """Analyze what makes this cluster unique"""
        category_stats = features['category_stats']
        
        # Get top spending categories
        top_categories = category_stats.nlargest(3, 'percentage')
        
        characteristics = {
            'spending_level': self._classify_spending_level(features['total_expense']),
            'top_categories': top_categories.to_dict('records'),
            'transaction_frequency': self._classify_frequency(features['num_transactions']),
            'spending_consistency': self._classify_consistency(features['std_transaction'], features['avg_transaction']),
            'weekend_bias': self._classify_weekend_spending(features['weekend_spending_ratio'])
        }
        
        return characteristics
    
    def _classify_spending_level(self, total_expense):
        """Classify overall spending level"""
        if total_expense < 20000:
            return "Low"
        elif total_expense < 50000:
            return "Moderate"
        else:
            return "High"
    
    def _classify_frequency(self, num_transactions):
        """Classify transaction frequency"""
        if num_transactions < 20:
            return "Occasional"
        elif num_transactions < 50:
            return "Regular"
        else:
            return "Frequent"
    
    def _classify_consistency(self, std, mean):
        """Classify spending consistency"""
        if mean == 0:
            return "Stable"
        
        cv = (std / mean) * 100  # Coefficient of variation
        
        if cv < 50:
            return "Very Consistent"
        elif cv < 100:
            return "Moderately Consistent"
        else:
            return "Highly Variable"
    
    def _classify_weekend_spending(self, ratio):
        """Classify weekend spending behavior"""
        if ratio < 0.2:
            return "Weekday Focused"
        elif ratio < 0.4:
            return "Balanced"
        else:
            return "Weekend Heavy"
    
    def _save_model(self):
        """Save trained model to disk"""
        try:
            # Create models directory if it doesn't exist
            os.makedirs('models', exist_ok=True)
            
            # Save model and scaler
            joblib.dump(self.model, self.model_path)
            joblib.dump(self.scaler, self.scaler_path)
            
            return True
        except Exception as e:
            print(f"Error saving model: {e}")
            return False
    
    def _load_model(self):
        """Load trained model from disk"""
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                return True
            return False
        except Exception as e:
            print(f"Error loading model: {e}")
            return False
    
    def get_cluster_insights(self, cluster_id, features):
        """Generate insights based on cluster assignment"""
        characteristics = self.analyze_cluster_characteristics(features, cluster_id)
        cluster_name = self.get_cluster_name(cluster_id)
        
        insights = {
            'persona': cluster_name,
            'spending_level': characteristics['spending_level'],
            'main_focus': characteristics['top_categories'][0]['category'] if characteristics['top_categories'] else 'General',
            'frequency': characteristics['transaction_frequency'],
            'consistency': characteristics['spending_consistency'],
            'weekend_pattern': characteristics['weekend_bias']
        }
        
        return insights