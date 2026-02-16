import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
# import openai
from sqlalchemy import func
from extensions import db

# from models import Invoice, Client, InvoiceLineItem, AIInteraction, InventoryItem
# from openai import OpenAI
import ai_client

# Initialize OpenAI client
# openai.api_key = os.environ.get("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")



class AIInvoiceAssistant:
    """AI-powered invoice assistance with GPT-4o"""
    
    def __init__(self):
        pass
        
    def analyze_client_history(self, client_id: int) -> Dict[str, Any]:
        """Analyze client's invoice history to provide insights"""
        try:
            from models import Client, Invoice
            db_client = Client.query.get(client_id)
            if not db_client:
                return {"error": "Client not found"}
            
            # Get client's invoice history
            invoices = Invoice.query.filter_by(client_id=client_id).all()
            
            # Prepare data for AI analysis
            invoice_data = []
            for invoice in invoices:
                invoice_info = {
                    "date": invoice.invoice_date.strftime("%Y-%m-%d"),
                    "amount": float(invoice.total_amount),
                    "payment_status": invoice.payment_status,
                    "items": [{"description": item.description, "quantity": item.quantity, "price": item.unit_price} 
                             for item in invoice.line_items]
                }
                invoice_data.append(invoice_info)
            
            # AI analysis prompt
            if not ai_client.AI_AVAILABLE:
                return {"error": "AI unavailable", "reason": ai_client.LAST_AI_ERROR}
            
            prompt = f"""
            Analyze the following client invoice history and provide insights in JSON format:
            
            Client: {db_client.name}
            Invoice History: {json.dumps(invoice_data, indent=2)}
            
            Provide analysis in this JSON format:
            {{
                "payment_behavior": "description of payment patterns",
                "average_order_value": float,
                "preferred_products": ["list of frequently ordered items"],
                "seasonal_patterns": "description of seasonal trends",
                "risk_assessment": {{
                    "score": float between 0-1,
                    "factors": ["list of risk factors"]
                }},
                "recommendations": ["list of business recommendations"],
                "predicted_ltv": float,
                "next_order_prediction": {{
                    "likely_date": "YYYY-MM-DD",
                    "estimated_value": float,
                    "suggested_products": ["list"]
                }}
            }}
            """
            
            response = ai_client.client.chat.completions.create(
                model=ai_client.MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            analysis = json.loads(response.choices[0].message.content)
            
            # Update client with AI insights
            db_client.ai_risk_score = analysis.get("risk_assessment", {}).get("score", 0.0)
            db_client.predicted_ltv = analysis.get("predicted_ltv", 0.0)
            db_client.preferred_products = analysis.get("preferred_products", [])
            
            db.session.commit()
            
            return analysis
            
        except Exception as e:
            logging.error(f"AI client analysis failed: {e}")
            return {"error": str(e)}
    
    def suggest_invoice_items(self, client_id: int, context: str = "") -> List[Dict[str, Any]]:
        """AI-powered item suggestions based on client history and context"""
        try:
            from models import Client, Invoice, InventoryItem
            db_client = Client.query.get(client_id)
            if not db_client:
                return []
            
            # Get recent invoices for this client
            recent_invoices = Invoice.query.filter_by(client_id=client_id)\
                .order_by(Invoice.invoice_date.desc())\
                .limit(10).all()
            
            # Context builder
            client_history = []
            for invoice in recent_invoices:
                for item in invoice.line_items:
                    client_history.append({
                        "description": item.description,
                        "quantity": item.quantity,
                        "price": item.unit_price,
                        "date": invoice.invoice_date.strftime("%Y-%m-%d")
                    })
            
            # --- AI PATH ---
            if ai_client.AI_AVAILABLE:
                try:
                    inventory_items = InventoryItem.query.all()
                    inventory_context = [{"name": item.name, "description": item.description, 
                                        "price": item.selling_price, "stock": item.current_stock}
                                       for item in inventory_items if item.current_stock > 0]

                    prompt = f"""
                    Based on the client history and available inventory, suggest relevant invoice items:
                    
                    Client: {db_client.name}
                    Context: {context}
                    Client Purchase History: {json.dumps(client_history[-20:], indent=2)}
                    Available Inventory: {json.dumps(inventory_context[:50], indent=2)}
                    
                    Suggest 5-10 relevant items in JSON format:
                    {{
                        "suggestions": [
                            {{
                                "description": "item description",
                                "quantity": float,
                                "unit_price": float,
                                "reasoning": "why this item is suggested",
                                "confidence": float between 0-1
                            }}
                        ]
                    }}
                    """
                    
                    response = ai_client.client.chat.completions.create(
                        model=ai_client.MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"}
                    )
                    
                    suggestions = json.loads(response.choices[0].message.content)
                    return suggestions.get("suggestions", [])
                except Exception as e:
                    logging.error(f"AI suggestion failed, falling back to history: {e}")
                    
            # --- FALLBACK: HISTORICAL ITEMS ---
            # If AI is offline or fails, return top purchased items
            from collections import Counter
            item_counts = Counter(item['description'] for item in client_history)
            
            # Get unique items with their last price/qty
            fallback_suggestions = []
            seen_items = set()
            
            for item in reversed(client_history):
                if item['description'] not in seen_items:
                    fallback_suggestions.append({
                        "description": item['description'],
                        "quantity": item['quantity'],
                        "unit_price": item['price'],
                        "reasoning": "Based on previous purchase",
                        "confidence": 1.0
                    })
                    seen_items.add(item['description'])
                if len(fallback_suggestions) >= 5:
                    break
            
            return fallback_suggestions
            
        except Exception as e:
            logging.error(f"Item suggestion process failed: {e}")
            return []
    
    def optimize_pricing(self, items: List[Dict], client_id: int) -> List[Dict]:
        """AI-powered pricing optimization"""
        try:
            if not ai_client.AI_AVAILABLE:
                return items
            
            from models import Client
            db_client = Client.query.get(client_id)
            market_data = self._get_market_pricing_data()
            
            prompt = f"""
            Optimize pricing for the following items based on client profile and market data:
            
            Client Profile: Risk Score: {db_client.ai_risk_score}, LTV: {db_client.predicted_ltv}
            Items: {json.dumps(items, indent=2)}
            Market Data: {json.dumps(market_data, indent=2)}
            
            Provide optimized pricing in JSON format:
            {{
                "optimized_items": [
                    {{
                        "original_price": float,
                        "optimized_price": float,
                        "reasoning": "explanation for price change",
                        "confidence": float
                    }}
                ]
            }}
            """
            
            response = ai_client.client.chat.completions.create(
                model=ai_client.MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            optimization = json.loads(response.choices[0].message.content)
            return optimization.get("optimized_items", [])
            
        except Exception as e:
            logging.error(f"AI pricing optimization failed: {e}")
            return items
    
    def _get_market_pricing_data(self) -> Dict:
        """Get market pricing context from recent invoices"""
        from models import Invoice, InvoiceLineItem
        recent_items = db.session.query(InvoiceLineItem.description, 
                                      func.avg(InvoiceLineItem.unit_price).label('avg_price'))\
            .join(Invoice)\
            .filter(Invoice.invoice_date >= datetime.now() - timedelta(days=90))\
            .group_by(InvoiceLineItem.description)\
            .limit(100).all()
        
        return {item.description: float(item.avg_price) for item in recent_items}

class PredictiveAnalytics:
    """Advanced predictive analytics for business insights"""
    
    def __init__(self):
        self._cache = {}
    
    def predict_cash_flow(self, months_ahead: int = 6) -> Dict[str, Any]:
        """Predict cash flow for upcoming months"""
        # Check cache (valid for 60 min)
        if "predict_cash_flow" in self._cache:
             cached = self._cache["predict_cash_flow"]
             if (datetime.now() - cached["timestamp"]).total_seconds() < 3600:
                 return cached["data"]

        try:
            # Get historical data
            current_date = datetime.now()
            historical_data = []
            
            for i in range(12):  # Last 12 months
                month_start = current_date.replace(day=1) - timedelta(days=30*i)
                month_end = month_start + timedelta(days=30)
                
                from models import Invoice
                revenue = db.session.query(func.sum(Invoice.total_amount))\
                    .filter(Invoice.invoice_date.between(month_start.date(), month_end.date()))\
                    .filter(Invoice.payment_status == 'Paid').scalar() or 0
                
                outstanding = db.session.query(func.sum(Invoice.total_amount))\
                    .filter(Invoice.invoice_date.between(month_start.date(), month_end.date()))\
                    .filter(Invoice.payment_status.in_(['Unpaid', 'Partially Paid'])).scalar() or 0
                
                historical_data.append({
                    "month": month_start.strftime("%Y-%m"),
                    "revenue": float(revenue),
                    "outstanding": float(outstanding)
                })
            
            # Get upcoming invoices
            upcoming_invoices = Invoice.query.filter(
                Invoice.due_date >= current_date.date(),
                Invoice.payment_status.in_(['Unpaid', 'Partially Paid'])
            ).all()
            
            upcoming_data = [{"due_date": inv.due_date.strftime("%Y-%m-%d"), 
                            "amount": float(inv.total_amount)} for inv in upcoming_invoices]
            
            if not ai_client.AI_AVAILABLE:
                return {"error": "AI unavailable", "reason": ai_client.LAST_AI_ERROR}
            
            prompt = f"""
            Predict cash flow for the next {months_ahead} months based on historical data and upcoming payments:
            
            Historical Data (last 12 months): {json.dumps(historical_data, indent=2)}
            Upcoming Invoices: {json.dumps(upcoming_data, indent=2)}
            
            Provide predictions in JSON format:
            {{
                "monthly_predictions": [
                    {{
                        "month": "YYYY-MM",
                        "predicted_revenue": float,
                        "predicted_collections": float,
                        "confidence_level": float,
                        "key_factors": ["list of factors affecting prediction"]
                    }}
                ],
                "summary": {{
                    "total_predicted_revenue": float,
                    "cash_flow_trend": "improving/stable/declining",
                    "risk_factors": ["list of risks"],
                    "recommendations": ["list of recommendations"]
                }}
            }}
            """
            
            if ai_client.AI_AVAILABLE:
                try:
                    response = ai_client.client.chat.completions.create(
                        model=ai_client.MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"}
                    )
                    
                    prediction = json.loads(response.choices[0].message.content)
                    
                    # Cache the result
                    self._cache["predict_cash_flow"] = {
                        "data": prediction,
                        "timestamp": datetime.now()
                    }
                    
                    return prediction
                except Exception as e:
                    logging.error(f"AI Prediction failed, using fallback: {e}")

            # --- FALLBACK: SIMPLE PROJECTION ---
            logging.info("Using statistical fallback for cash flow")
            
            avg_revenue = sum(d["revenue"] for d in historical_data) / len(historical_data) if historical_data else 0
            monthly_predictions = []
            
            for i in range(months_ahead):
                future_date = datetime.now() + timedelta(days=30*(i+1))
                monthly_predictions.append({
                    "month": future_date.strftime("%Y-%m"),
                    "predicted_revenue": avg_revenue,
                    "predicted_collections": avg_revenue * 0.9,
                    "confidence_level": 0.5,
                    "key_factors": ["Based on historical average"]
                })
                
            prediction = {
                "monthly_predictions": monthly_predictions,
                "summary": {
                    "total_predicted_revenue": avg_revenue * months_ahead,
                    "cash_flow_trend": "stable",
                    "risk_factors": ["Limited data for precise prediction"],
                    "recommendations": ["Maintain current sales velocity"]
                }
            }
            
            # Cache the fallback too
            self._cache["predict_cash_flow"] = {
                "data": prediction,
                "timestamp": datetime.now()
            }
            return prediction
            
        except Exception as e:
            logging.error(f"Cash flow prediction failed: {e}")
            return {"error": str(e)}
    
    def analyze_client_payment_patterns(self) -> Dict[str, Any]:
        """Analyze payment patterns across all clients"""
        # Check cache
        if "analyze_client_payment_patterns" in self._cache:
             cached = self._cache["analyze_client_payment_patterns"]
             if (datetime.now() - cached["timestamp"]).total_seconds() < 3600:
                 return cached["data"]

        try:
            # Get payment data
            from models import Client, Invoice
            payment_data = db.session.query(
                Client.name,
                Client.id,
                func.avg(func.julianday(Invoice.payment_date) - func.julianday(Invoice.due_date)).label('avg_delay'),
                func.count(Invoice.id).label('invoice_count'),
                func.sum(Invoice.total_amount).label('total_business')
            ).join(Invoice)\
            .filter(Invoice.payment_status == 'Paid')\
            .filter(Invoice.payment_date.isnot(None))\
            .group_by(Client.id).all()
            
            analysis_data = []
            for data in payment_data:
                analysis_data.append({
                    "client_name": data.name,
                    "avg_payment_delay_days": float(data.avg_delay or 0),
                    "invoice_count": data.invoice_count,
                    "total_business": float(data.total_business)
                })
            
            # --- AI PATH ---
            if ai_client.AI_AVAILABLE:
                try:
                    prompt = f"""
                    Analyze client payment patterns and provide insights:
                    
                    Payment Data: {json.dumps(analysis_data[:50], indent=2)}
                    
                    Provide analysis in JSON format:
                    {{
                        "payment_behavior_segments": [
                            {{
                                "segment_name": "Early Payers/On-time/Late Payers",
                                "characteristics": "description",
                                "client_count": int,
                                "avg_delay_days": float,
                                "business_impact": "positive/neutral/negative"
                            }}
                        ],
                        "insights": {{
                            "best_performing_clients": ["list of client names"],
                            "at_risk_clients": ["list of client names"],
                            "overall_collection_health": "excellent/good/fair/poor",
                            "recommendations": ["list of recommendations"]
                        }},
                        "predictions": {{
                            "clients_likely_to_default": ["list with reasons"],
                            "improvement_opportunities": ["list of opportunities"]
                        }}
                    }}
                    """
                    
                    response = ai_client.client.chat.completions.create(
                        model=ai_client.MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"}
                    )
                    
                    analysis = json.loads(response.choices[0].message.content)
                    return analysis
                except Exception as e:
                    logging.error(f"AI Update failure: {e}")

            # --- FALLBACK: STATISTICAL ANALYSIS ---
            # Segment by delay
            early = [c for c in analysis_data if c['avg_payment_delay_days'] < 0]
            on_time = [c for c in analysis_data if 0 <= c['avg_payment_delay_days'] <= 5]
            late = [c for c in analysis_data if c['avg_payment_delay_days'] > 5]
            
            result = {
                "payment_behavior_segments": [
                    {
                        "segment_name": "Early Payers",
                        "characteristics": "Pays before due date",
                        "client_count": len(early),
                        "avg_delay_days": sum(c['avg_payment_delay_days'] for c in early) / len(early) if early else 0,
                        "business_impact": "positive"
                    },
                    {
                        "segment_name": "Late Payers",
                        "characteristics": "Pays after 5 days of due date",
                        "client_count": len(late),
                        "avg_delay_days": sum(c['avg_payment_delay_days'] for c in late) / len(late) if late else 0,
                        "business_impact": "negative"
                    }
                ],
                "insights": {
                    "best_performing_clients": [c['client_name'] for c in sorted(early, key=lambda x: x['total_business'], reverse=True)[:3]],
                    "at_risk_clients": [c['client_name'] for c in sorted(late, key=lambda x: x['avg_payment_delay_days'], reverse=True)[:3]],
                    "overall_collection_health": "fair" if len(late) < len(early) else "poor",
                    "recommendations": ["Follow up with late payers", "Offer discounts for early payment"]
                },
                "predictions": {
                    "clients_likely_to_default": [],
                    "improvement_opportunities": ["Automate reminders"]
                }
            }

            # Cache the fallback too
            self._cache["analyze_client_payment_patterns"] = {
                "data": result,
                "timestamp": datetime.now()
            }
            return result
            
        except Exception as e:
            logging.error(f"Payment pattern analysis failed: {e}")
            return {"error": str(e)}

class InventoryAI:
    """AI-powered inventory management and demand forecasting"""
    
    def __init__(self):
        pass
    
    def forecast_demand(self, item_id: int, days_ahead: int = 30) -> Dict[str, Any]:
        """Forecast demand for inventory items"""
        try:
            from models import InventoryItem, Invoice, InvoiceLineItem
            item = InventoryItem.query.get(item_id)
            if not item:
                return {"error": "Item not found"}
            
            # Get historical sales data
            sales_data = db.session.query(
                InvoiceLineItem.quantity,
                Invoice.invoice_date
            ).join(Invoice)\
            .filter(InvoiceLineItem.description.contains(item.name))\
            .filter(Invoice.payment_status == 'Paid')\
            .order_by(Invoice.invoice_date.desc())\
            .limit(100).all()
            
            historical_sales = [{"date": sale.invoice_date.strftime("%Y-%m-%d"), 
                               "quantity": float(sale.quantity)} for sale in sales_data]
            
            if not ai_client.AI_AVAILABLE:
                return {"error": "AI unavailable", "reason": ai_client.LAST_AI_ERROR}
            
            prompt = f"""
            Forecast demand for inventory item based on historical sales:
            
            Item: {item.name}
            Current Stock: {item.current_stock}
            Historical Sales: {json.dumps(historical_sales, indent=2)}
            Forecast Period: {days_ahead} days
            
            Provide forecast in JSON format:
            {{
                "demand_forecast": {{
                    "total_demand": float,
                    "daily_average": float,
                    "peak_demand_days": ["list of likely peak days"],
                    "confidence_level": float
                }},
                "reorder_recommendation": {{
                    "should_reorder": boolean,
                    "suggested_quantity": float,
                    "reorder_urgency": "low/medium/high",
                    "reasoning": "explanation"
                }},
                "seasonal_insights": {{
                    "pattern_detected": boolean,
                    "seasonal_factors": ["list of factors"],
                    "next_peak_period": "description"
                }}
            }}
            """
            
            response = ai_client.client.chat.completions.create(
                model=ai_client.MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            forecast = json.loads(response.choices[0].message.content)
            
            # Update item with AI insights
            item.ai_demand_forecast = forecast
            item.ai_reorder_suggestions = forecast.get("reorder_recommendation", {})
            db.session.commit()
            
            return forecast
            
        except Exception as e:
            logging.error(f"Demand forecasting failed: {e}")
            return {"error": str(e)}

# For OpenAI

# def initialize_ai_models():
#     global ai_assistant, predictive_analytics, inventory_ai
#     try:
#         print("🚀 Initializing AI services...")
#         print("🔑 OpenAI Key present:", bool(openai.api_key))

#         if not openai.api_key:
#             raise Exception("OpenAI API key not configured")

#         ai_assistant = AIInvoiceAssistant()
#         predictive_analytics = PredictiveAnalytics()
#         inventory_ai = InventoryAI()

#         print("✅ AI services initialized")
#         return True

#     except Exception as e:
#         print("❌ AI INIT FAILED:", e)
#         return False


# Global AI service instances
ai_assistant = None
predictive_analytics = None
inventory_ai = None


# For OpenRouter
def initialize_ai_models():
    """
    Initializes AI business services AFTER ai_client is ready
    """
    global ai_assistant, predictive_analytics, inventory_ai

    from ai_client import AI_AVAILABLE

    if not AI_AVAILABLE:
        logging.warning("⚠️ AI client unavailable — services not created")
        return False

    ai_assistant = AIInvoiceAssistant()
    predictive_analytics = PredictiveAnalytics()
    inventory_ai = InventoryAI()

    logging.info("✅ AI business services initialized")
    return True

