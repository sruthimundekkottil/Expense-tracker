class RecommendationEngine:
    """Generate personalized spending recommendations"""
    
    def __init__(self):
        # Optimal spending benchmarks (as percentage of income)
        self.optimal_ranges = {
            'Food & Dining': (15, 25),
            'Transportation': (10, 15),
            'Shopping': (5, 15),
            'Entertainment': (5, 10),
            'Bills & Utilities': (15, 25),
            'Healthcare': (5, 10),
            'Other': (5, 10)
        }
        
        # Reduction targets based on overspending
        self.reduction_targets = {
            'mild': 0.10,    # 10% reduction
            'moderate': 0.20, # 20% reduction
            'severe': 0.30   # 30% reduction
        }
    
    def generate_recommendations(self, features, cluster_insights, income=None):
        """Generate personalized recommendations"""
        recommendations = []
        category_stats = features['category_stats']
        total_expense = features['total_expense']
        
        # 1. High-Spend Category Recommendations
        high_spend_recs = self._analyze_high_spending(category_stats, total_expense)
        recommendations.extend(high_spend_recs)
        
        # 2. Weekend Spending Recommendations
        if features['weekend_spending_ratio'] > 0.35:
            weekend_rec = self._weekend_spending_recommendation(features)
            recommendations.append(weekend_rec)
        
        # 3. Transaction Frequency Recommendations
        freq_rec = self._frequency_recommendation(features)
        if freq_rec:
            recommendations.append(freq_rec)
        
        # 4. Budget Recommendations (if income provided)
        if income and income > 0:
            budget_recs = self._budget_recommendations(category_stats, income)
            recommendations.extend(budget_recs)
        
        # 5. Cluster-Specific Recommendations
        cluster_rec = self._cluster_based_recommendation(cluster_insights, features)
        if cluster_rec:
            recommendations.append(cluster_rec)
        
        return recommendations
    
    def _analyze_high_spending(self, category_stats, total_expense):
        """Identify high-spend categories and calculate savings"""
        recommendations = []
        
        # Sort by percentage descending
        sorted_cats = category_stats.sort_values('percentage', ascending=False)
        
        for idx, row in sorted_cats.head(3).iterrows():
            category = row['category']
            percentage = row['percentage']
            amount = row['total']
            
            # Determine severity and reduction target
            if percentage > 35:
                severity = 'severe'
                message_prefix = "⚠️ HIGH ALERT"
            elif percentage > 25:
                severity = 'moderate'
                message_prefix = "⚡ OPPORTUNITY"
            elif percentage > 20:
                severity = 'mild'
                message_prefix = "💡 SUGGESTION"
            else:
                continue  # Skip categories below 20%
            
            reduction_pct = self.reduction_targets[severity]
            potential_savings = amount * reduction_pct
            
            recommendation = {
                'type': 'high_spend',
                'priority': self._get_priority(severity),
                'category': category,
                'current_percentage': percentage,
                'current_amount': amount,
                'severity': severity,
                'reduction_percentage': reduction_pct * 100,
                'potential_savings': potential_savings,
                'message': f"{message_prefix}: You spend {percentage:.1f}% on {category}. "
                          f"Reducing this by {int(reduction_pct * 100)}% could save you ₹{potential_savings:,.0f}/month",
                'actionable_tip': self._get_category_tip(category, severity)
            }
            
            recommendations.append(recommendation)
        
        return recommendations
    
    def _weekend_spending_recommendation(self, features):
        """Recommendation for high weekend spending"""
        weekend_ratio = features['weekend_spending_ratio']
        total_expense = features['total_expense']
        weekend_amount = total_expense * weekend_ratio
        
        # Target: reduce weekend spending to 30%
        target_ratio = 0.30
        if weekend_ratio > target_ratio:
            potential_savings = total_expense * (weekend_ratio - target_ratio)
            
            return {
                'type': 'weekend_spending',
                'priority': 'medium',
                'current_percentage': weekend_ratio * 100,
                'current_amount': weekend_amount,
                'potential_savings': potential_savings,
                'message': f"🌴 You spend {weekend_ratio * 100:.1f}% on weekends. "
                          f"Setting a weekend budget could save ₹{potential_savings:,.0f}/month",
                'actionable_tip': "Try meal prepping for weekends or planning free activities"
            }
        
        return None
    
    def _frequency_recommendation(self, features):
        """Recommendation based on transaction frequency"""
        num_transactions = features['num_transactions']
        avg_transaction = features['avg_transaction']
        
        # If many small transactions, suggest consolidation
        if num_transactions > 100 and avg_transaction < 500:
            potential_savings = avg_transaction * num_transactions * 0.15  # 15% reduction
            
            return {
                'type': 'frequency',
                'priority': 'low',
                'transaction_count': num_transactions,
                'avg_amount': avg_transaction,
                'potential_savings': potential_savings,
                'message': f"🔄 You made {num_transactions} transactions. "
                          f"Consolidating small purchases could save ₹{potential_savings:,.0f}/month",
                'actionable_tip': "Use a shopping list and buy in bulk to reduce impulse purchases"
            }
        
        return None
    
    def _budget_recommendations(self, category_stats, income):
        """Budget allocation recommendations based on income"""
        recommendations = []
        
        for idx, row in category_stats.iterrows():
            category = row['category']
            current_amount = row['total']
            current_pct = (current_amount / income) * 100
            
            if category in self.optimal_ranges:
                min_pct, max_pct = self.optimal_ranges[category]
                
                if current_pct > max_pct:
                    # Overspending
                    optimal_amount = income * (max_pct / 100)
                    savings = current_amount - optimal_amount
                    
                    recommendations.append({
                        'type': 'budget_alignment',
                        'priority': 'high',
                        'category': category,
                        'current_percentage': current_pct,
                        'optimal_range': f"{min_pct}-{max_pct}%",
                        'potential_savings': savings,
                        'message': f"📊 {category}: {current_pct:.1f}% of income (optimal: {min_pct}-{max_pct}%). "
                                  f"Aligning to budget could save ₹{savings:,.0f}/month",
                        'actionable_tip': f"Set a monthly {category} budget of ₹{optimal_amount:,.0f}"
                    })
        
        return recommendations
    
    def _cluster_based_recommendation(self, cluster_insights, features):
        """Recommendations based on cluster persona"""
        persona = cluster_insights.get('persona', 'Average Spender')
        
        if persona == "Needs Improvement":
            total_savings = features['total_expense'] * 0.25  # Target 25% reduction
            
            return {
                'type': 'persona',
                'priority': 'critical',
                'persona': persona,
                'potential_savings': total_savings,
                'message': f"🎯 Your spending pattern shows room for improvement. "
                          f"Following our top recommendations could save ₹{total_savings:,.0f}/month",
                'actionable_tip': "Start with your highest expense category and set strict weekly limits"
            }
        elif persona == "Budget Master":
            return {
                'type': 'persona',
                'priority': 'low',
                'persona': persona,
                'message': f"🌟 Excellent! You're a {persona}. Keep up the great financial habits!",
                'actionable_tip': "Consider investing your savings for long-term wealth building"
            }
        
        return None
    
    def _get_priority(self, severity):
        """Map severity to priority"""
        priority_map = {
            'severe': 'critical',
            'moderate': 'high',
            'mild': 'medium'
        }
        return priority_map.get(severity, 'low')
    
    def _get_category_tip(self, category, severity):
        """Get actionable tip for specific category"""
        tips = {
            'Food & Dining': {
                'severe': "Cook at home 5 days/week, limit dining out to special occasions",
                'moderate': "Meal prep on weekends, pack lunch 3 days/week",
                'mild': "Try cooking one new recipe weekly instead of ordering out"
            },
            'Shopping': {
                'severe': "Implement a 30-day rule: wait 30 days before any non-essential purchase",
                'moderate': "Set a weekly shopping budget and stick to it",
                'mild': "Make a shopping list and avoid impulse buys"
            },
            'Entertainment': {
                'severe': "Switch to free activities: parks, hiking, home movie nights",
                'moderate': "Limit paid entertainment to 2 times per month",
                'mild': "Look for early-bird discounts and group deals"
            },
            'Transportation': {
                'severe': "Consider carpooling or public transport for daily commute",
                'moderate': "Combine errands to reduce fuel costs",
                'mild': "Maintain vehicle regularly to improve fuel efficiency"
            },
            'Bills & Utilities': {
                'severe': "Audit all subscriptions, cancel unused services",
                'moderate': "Switch to energy-efficient appliances",
                'mild': "Turn off lights/AC when not in use"
            }
        }
        
        category_tips = tips.get(category, {
            'severe': "Track every expense and set strict category limits",
            'moderate': "Review this category weekly and find alternatives",
            'mild': "Look for ways to optimize spending"
        })
        
        return category_tips.get(severity, category_tips.get('mild'))
    
    def prioritize_recommendations(self, recommendations):
        """Sort recommendations by priority and impact"""
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        
        sorted_recs = sorted(
            recommendations,
            key=lambda x: (
                priority_order.get(x.get('priority', 'low'), 4),
                -x.get('potential_savings', 0)
            )
        )
        
        return sorted_recs
    
    def calculate_total_savings_potential(self, recommendations):
        """Calculate total potential savings from all recommendations"""
        total = sum(rec.get('potential_savings', 0) for rec in recommendations)
        return round(total, 2)