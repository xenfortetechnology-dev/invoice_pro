"""
Voice Command Service - Script-based implementation
No AI/API dependencies - Pure pattern matching
Supports English and Tamil/Tanglish commands
"""

import re
import logging
import json
import requests
import os
from datetime import datetime
from typing import Dict, Any, Optional
from types import SimpleNamespace

# Cloud API Configuration
CLOUD_API_BASE = os.environ.get("CLOUD_API_BASE", "http://44.208.164.236:5000/api")

from voice_patterns import PatternMatcher, get_command_suggestions

# Configure Logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =========================
# HELPER FUNCTIONS
# =========================

def fetch_cloud_clients():
    """Fetch all clients from cloud database"""
    try:
        response = requests.get(f"{CLOUD_API_BASE}/clients", timeout=5)
        if response.status_code == 200:
            return response.json()
        logging.warning(f"Cloud API returned status {response.status_code}")
        return []
    except Exception as e:
        logging.error(f"Cloud API error (clients): {e}")
        return []

def create_cloud_invoice(invoice_data):
    """Create invoice in cloud database"""
    try:
        response = requests.post(f"{CLOUD_API_BASE}/invoices", json=invoice_data, timeout=5)
        if response.status_code in (200, 201):
            return response.json()
        logging.error(f"Cloud API error (create invoice): {response.text}")
        return None
    except Exception as e:
        logging.error(f"Cloud API error (create invoice): {e}")
        return None

# =========================
# SESSION MANAGEMENT
# =========================

class VoiceSession:
    """Manage voice command session state"""
    
    def __init__(self):
        self.active_invoice = {
            "client": None,
            "client_id": None,
            "items": [],
            "created_at": None
        }
    
    def start_invoice(self, client):
        """Start a new invoice session"""
        # client can be dict or object, standardize to SimpleNamespace for attribute access if dict
        if isinstance(client, dict):
            client_obj = SimpleNamespace(**client)
        else:
            client_obj = client
            
        self.active_invoice = {
            "client": client_obj,
            "client_id": client_obj.id,
            "items": [],
            "created_at": datetime.utcnow()
        }
    
    def add_item(self, item_data: Dict[str, Any]):
        """Add item to current invoice"""
        self.active_invoice["items"].append(item_data)
    
    def get_total(self) -> float:
        """Calculate current total"""
        return sum(
            item.get("quantity", 1) * item.get("price", 0) 
            for item in self.active_invoice["items"]
        )
    
    def clear(self):
        """Clear session"""
        self.active_invoice = {
            "client": None,
            "client_id": None,
            "items": [],
            "created_at": None
        }
    
    def has_active_invoice(self) -> bool:
        """Check if there's an active invoice"""
        return self.active_invoice["client"] is not None


# Global session instance
voice_session = VoiceSession()


# =========================
# COMMAND HANDLERS
# =========================

class CommandHandlers:
    """Handle different voice command intents"""
    
    @staticmethod
    def handle_create_invoice(entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle create invoice command"""
        try:
            client_name = entities.get("client_name")
            
            if not client_name:
                return {
                    "success": False,
                    "message": "Client name not found. Please say 'Create invoice for [client name]'",
                    "intent": "create_invoice"
                }
            
            # Search for client in Cloud
            cloud_clients = fetch_cloud_clients()
            
            # Filter by name (case insensitive)
            client_name_lower = client_name.lower()
            matching_clients = [
                c for c in cloud_clients 
                if client_name_lower in (c.get('name') or '').lower()
            ]
            
            client = None
            if matching_clients:
                # Exact match preference
                exact_matches = [c for c in matching_clients if (c.get('name') or '').lower() == client_name_lower]
                client_data = exact_matches[0] if exact_matches else matching_clients[0]
                
                # Convert to SimpleNamespace for object-like access
                client = SimpleNamespace(**client_data)
            
            if not client:
                return {
                    "success": False,
                    "message": f"Client '{client_name}' not found. Please check the name and try again.",
                    "intent": "create_invoice"
                }
            
            # Start new invoice session
            voice_session.start_invoice(client)
            
            return {
                "success": True,
                "message": f"Invoice started for {client.name}. You can now add items.",
                "intent": "create_invoice",
                "client_id": client.id,
                "client_name": client.name
            }
            
        except Exception as e:
            logging.error(f"Create invoice error: {e}")
            return {
                "success": False,
                "message": "Error creating invoice. Please try again.",
                "error": str(e),
                "intent": "create_invoice"
            }
    
    @staticmethod
    def handle_add_item(entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle add item command"""
        try:
            # Check if there's an active invoice
            if not voice_session.has_active_invoice():
                return {
                    "success": False,
                    "message": "No active invoice. Please create an invoice first.",
                    "intent": "add_item",
                    "suggestion": "Say 'Create invoice for [client name]'"
                }
            
            # Extract item details
            item_description = entities.get("item_description", "Unknown Item")
            quantity = entities.get("quantity", 1)
            amount = entities.get("amount", 0)
            unit = entities.get("unit", "Nos")
            tax = entities.get("tax", 18)
            hsn_code = entities.get("hsn_code")
            
            # Validate
            if amount == 0:
                return {
                    "success": False,
                    "message": f"Please specify the price for {item_description}",
                    "intent": "add_item"
                }
            
            # Create item data
            item_data = {
                "name": item_description,
                "description": item_description,
                "quantity": quantity,
                "price": amount,
                "unit": unit,
                "tax": tax,
                "hsn_code": hsn_code,
                "total": quantity * amount
            }
            
            # Add to session
            voice_session.add_item(item_data)
            
            # Calculate running total
            current_total = voice_session.get_total()
            item_count = len(voice_session.active_invoice["items"])
            
            return {
                "success": True,
                "message": f"Added {item_description} (Qty: {quantity}, Price: ₹{amount}). Total items: {item_count}, Amount: ₹{current_total}",
                "intent": "add_item",
                "entities": entities,
                "item_count": item_count,
                "current_total": current_total
            }
            
        except Exception as e:
            logging.error(f"Add item error: {e}")
            return {
                "success": False,
                "message": "Error adding item. Please try again.",
                "error": str(e),
                "intent": "add_item"
            }
    
    @staticmethod
    def handle_save_invoice() -> Dict[str, Any]:
        """Handle save invoice command"""
        try:
            # Check if there's an active invoice
            if not voice_session.has_active_invoice():
                return {
                    "success": False,
                    "message": "No active invoice to save.",
                    "intent": "save_invoice"
                }
            
            # Check if there are items
            if not voice_session.active_invoice["items"]:
                return {
                    "success": False,
                    "message": "Cannot save empty invoice. Please add items first.",
                    "intent": "save_invoice"
                }
            
            # Prepare invoice data for Cloud API
            client = voice_session.active_invoice["client"]
            items = voice_session.active_invoice["items"]
            
            # Calculate totals
            subtotal = sum(item["total"] for item in items)
            # Simple tax calculation (assuming inclusive or exclusive? defaulting to exclusive logic for simplicity)
            # Actually line items usually have tax info. 
            total_tax = sum(item["total"] * (item.get("tax", 0) / 100) for item in items)
            grand_total = subtotal + total_tax

            invoice_payload = {
                "client_id": client.id,
                "invoice_date": datetime.now().strftime('%Y-%m-%d'),
                "due_date": datetime.now().strftime('%Y-%m-%d'), # Default due today
                "items": [
                    {
                        "description": item["description"],
                        "quantity": item["quantity"],
                        "unit_price": item["price"],
                        "unit": item.get("unit", "Nos"),
                        "hsn_code": item.get("hsn_code"),
                        "tax_rate": item.get("tax", 0)
                    } for item in items
                ],
                "notes": "Created via Voice Command",
                "payment_status": "Unpaid"
            }
            
            # Post to Cloud
            res = create_cloud_invoice(invoice_payload)
            
            if res:
                 # Get client name for message
                client_name = client.name
                item_count = len(items)
                
                # Clear session
                voice_session.clear()
                
                return {
                    "success": True,
                    "message": f"Invoice saved successfully for {client_name}. Total: ₹{grand_total:.2f}, Items: {item_count}",
                    "intent": "save_invoice",
                    "invoice_id": res.get("id"),
                    "total_amount": grand_total,
                    "item_count": item_count
                }
            else:
                 return {
                    "success": False,
                    "message": "Failed to save invoice to Cloud.",
                    "intent": "save_invoice"
                }
            
        except Exception as e:
            logging.error(f"Save invoice error: {e}")
            return {
                "success": False,
                "message": "Error saving invoice. Please try again.",
                "error": str(e),
                "intent": "save_invoice"
            }
    
    @staticmethod
    def handle_calculate_total() -> Dict[str, Any]:
        """Handle calculate total command"""
        try:
            # Check if there's an active invoice
            if not voice_session.has_active_invoice():
                return {
                    "success": False,
                    "message": "No active invoice. Please create an invoice first.",
                    "intent": "calculate_total"
                }
            
            # Check if there are items
            if not voice_session.active_invoice["items"]:
                return {
                    "success": False,
                    "message": "No items added yet. Total is ₹0",
                    "intent": "calculate_total"
                }
            
            # Calculate total
            total = voice_session.get_total()
            item_count = len(voice_session.active_invoice["items"])
            
            return {
                "success": True,
                "message": f"Current total: ₹{total} for {item_count} items",
                "intent": "calculate_total",
                "total_amount": total,
                "item_count": item_count
            }
            
        except Exception as e:
            logging.error(f"Calculate total error: {e}")
            return {
                "success": False,
                "message": "Error calculating total.",
                "error": str(e),
                "intent": "calculate_total"
            }
    
    @staticmethod
    def handle_search_client(entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle search client command"""
        try:
            client_name = entities.get("client_name")
            
            if not client_name:
                return {
                    "success": False,
                    "message": "Please specify a client name to search.",
                    "intent": "search_client"
                }
            
            # Search for clients
            cloud_clients = fetch_cloud_clients()
            
            client_name_lower = client_name.lower()
            clients = [
                c for c in cloud_clients 
                if client_name_lower in (c.get('name') or '').lower()
            ]
            
            if not clients:
                return {
                    "success": False,
                    "message": f"No clients found matching '{client_name}'",
                    "intent": "search_client"
                }
            
            if len(clients) == 1:
                client = clients[0]
                # Invoice count would need another fetch, skipping for now or fetching invoices
                invoice_count = 0 # Placeholder
                
                return {
                    "success": True,
                    "message": f"Found {client.get('name')}. Email: {client.get('email')}, Phone: {client.get('phone')}",
                    "intent": "search_client",
                    "client": {
                        "id": client.get('id'),
                        "name": client.get('name'),
                        "email": client.get('email'),
                        "phone": client.get('phone'),
                        "invoice_count": invoice_count
                    }
                }
            else:
                names = ", ".join([c.get('name') for c in clients[:5]])
                return {
                    "success": True,
                    "message": f"Found {len(clients)} clients: {names}",
                    "intent": "search_client",
                    "clients": [
                        {"id": c.get('id'), "name": c.get('name'), "email": c.get('email')}
                        for c in clients[:5]
                    ]
                }
                
        except Exception as e:
            logging.error(f"Search client error: {e}")
            return {
                "success": False,
                "message": "Error searching for client.",
                "error": str(e),
                "intent": "search_client"
            }
    
    @staticmethod
    def handle_unknown(original_text: str) -> Dict[str, Any]:
        """Handle unknown commands"""
        suggestions = get_command_suggestions()
        
        return {
            "success": False,
            "message": "I didn't understand that command. Here are some examples:",
            "intent": "unknown",
            "suggestions": suggestions[:5],  # Show first 5 suggestions
            "original_text": original_text
        }


# =========================
# MAIN PROCESSOR
# =========================

class VoiceCommandProcessor:
    """Main voice command processor using pattern matching"""
    
    def process(self, text: str, language: str = "en-IN") -> Dict[str, Any]:
        """
        Process voice command using pattern matching
        
        Args:
            text: Voice command text
            language: Language code (en-IN or ta-IN)
        
        Returns:
            Response dictionary with success, message, and data
        """
        try:
            # Explicit terminal debug output
            print(f"\n🎤 [VOICE DEBUG] Processing: '{text}' (Lang: {language})")
            
            logger.info("="*50)
            logger.info(f"🎤 VOICE PROCESSOR RECEIVED: '{text}' (Language: {language})")
            logger.info("="*50)
            
            # Match command pattern
            match_result = PatternMatcher.match_command(text)
            
            intent = match_result.get("intent")
            entities = match_result.get("entities", {})
            confidence = match_result.get("confidence", 0.0)
            
            print(f"🧠 [VOICE DEBUG] Intent: {intent} | Confidence: {confidence}")
            if entities:
                print(f"🔍 [VOICE DEBUG] Entities: {entities}")

            logger.info(f"🧠 Matched intent: {intent} (Confidence: {confidence})")
            logger.debug(f"🔍 Entities found: {entities}")
            
            # Route to appropriate handler
            if intent == "create_invoice":
                return CommandHandlers.handle_create_invoice(entities)
            
            elif intent == "add_item":
                return CommandHandlers.handle_add_item(entities)
            
            elif intent == "save_invoice":
                return CommandHandlers.handle_save_invoice()
            
            elif intent == "calculate_total":
                return CommandHandlers.handle_calculate_total()
            
            elif intent == "search_client":
                return CommandHandlers.handle_search_client(entities)
            
            else:
                return CommandHandlers.handle_unknown(text)
                
        except Exception as e:
            logging.error(f"❌ Voice processing error: {e}")
            return {
                "success": False,
                "message": "Sorry, something went wrong. Please try again.",
                "error": str(e),
                "intent": "error"
            }


# =========================
# INITIALIZATION
# =========================
# Global processor instance
voice_processor = VoiceCommandProcessor()

def get_voice_processor():
    """Get the global voice processor instance"""
    return voice_processor

def get_voice_session():
    """Get the global voice session instance"""
    return voice_session
