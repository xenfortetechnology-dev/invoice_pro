def _get_analytics_data_dict(time_range='12m'):
    """Helper to gather all analytics data as a dictionary"""
    analytics_data = {
        'revenue_trends': analytics_engine.get_revenue_trends(time_range),
        'client_performance': analytics_engine.get_client_performance_metrics(),
        'payment_analytics': analytics_engine.get_payment_analytics(),
        'profitability_analysis': analytics_engine.get_profitability_analysis(),
        'ai_predictions': {},
        'blockchain_insights': {}
    }
    
    # AI-powered predictions
    if app.config.get("AI_FEATURES_ENABLED") and predictive_analytics:
        try:
            analytics_data['ai_predictions'] = {
                'cash_flow': predictive_analytics.predict_cash_flow(6),
                'payment_patterns': predictive_analytics.analyze_client_payment_patterns()
            }
        except Exception as e:
            logging.error(f"AI predictions failed: {e}")
    
    # Blockchain analytics
    if app.config.get("BLOCKCHAIN_ENABLED") and blockchain_service:
        try:
            analytics_data['blockchain_insights'] = blockchain_service.get_blockchain_stats()
        except Exception as e:
            logging.error(f"Blockchain analytics failed: {e}")
            
    return analytics_data
