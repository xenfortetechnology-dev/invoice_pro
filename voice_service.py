"""
Voice Command Service - Script-based implementation
No AI/API dependencies - Pure pattern matching
Supports English and Tamil/Tanglish commands
"""

import re
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional
from app import db
from models import Client, Invoice, InvoiceLineItem
from voice_patterns import PatternMatcher, get_command_suggestions

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
    
    def start_invoice(self, client: Client):
        """Start a new invoice session"""
        self.active_invoice = {
            "client": client,
            "client_id": client.id,
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
            
            # Search for client
            client = Client.query.filter(
                Client.name.ilike(f"%{client_name}%")
            ).first()
            
            if not client:
                # Try to find similar clients
                similar = Client.query.filter(
                    Client.name.ilike(f"%{client_name.split()[0]}%")
                ).limit(3).all()
                
                if similar:
                    names = ", ".join([c.name for c in similar])
                    return {
                        "success": False,
                        "message": f"Client '{client_name}' not found. Did you mean: {names}?",
                        "intent": "create_invoice",
                        "similar_clients": [{"id": c.id, "name": c.name} for c in similar]
                    }
                else:
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
            
            # Create invoice
            invoice = Invoice(
                client_id=voice_session.active_invoice["client_id"],
                invoice_date=datetime.utcnow(),
                total_amount=0,
                payment_status="Unpaid"
            )
            db.session.add(invoice)
            db.session.flush()
            
            # Add line items
            total = 0
            for item in voice_session.active_invoice["items"]:
                line_item = InvoiceLineItem(
                    invoice_id=invoice.id,
                    description=item["description"],
                    quantity=item["quantity"],
                    unit_price=item["price"],
                    total=item["total"],
                    unit=item.get("unit", "Nos"),
                    hsn_code=item.get("hsn_code")
                )
                total += item["total"]
                db.session.add(line_item)
            
            # Update invoice total
            invoice.total_amount = total
            db.session.commit()
            
            # Get client name for message
            client_name = voice_session.active_invoice["client"].name
            item_count = len(voice_session.active_invoice["items"])
            
            # Clear session
            voice_session.clear()
            
            return {
                "success": True,
                "message": f"Invoice saved successfully for {client_name}. Total: ₹{total}, Items: {item_count}",
                "intent": "save_invoice",
                "invoice_id": invoice.id,
                "total_amount": total,
                "item_count": item_count
            }
            
        except Exception as e:
            logging.error(f"Save invoice error: {e}")
            db.session.rollback()
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
            clients = Client.query.filter(
                Client.name.ilike(f"%{client_name}%")
            ).limit(5).all()
            
            if not clients:
                return {
                    "success": False,
                    "message": f"No clients found matching '{client_name}'",
                    "intent": "search_client"
                }
            
            if len(clients) == 1:
                client = clients[0]
                invoice_count = Invoice.query.filter_by(client_id=client.id).count()
                
                return {
                    "success": True,
                    "message": f"Found {client.name}. Email: {client.email}, Phone: {client.phone}, Invoices: {invoice_count}",
                    "intent": "search_client",
                    "client": {
                        "id": client.id,
                        "name": client.name,
                        "email": client.email,
                        "phone": client.phone,
                        "invoice_count": invoice_count
                    }
                }
            else:
                names = ", ".join([c.name for c in clients])
                return {
                    "success": True,
                    "message": f"Found {len(clients)} clients: {names}",
                    "intent": "search_client",
                    "clients": [
                        {"id": c.id, "name": c.name, "email": c.email}
                        for c in clients
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
            logging.info(f"🎤 Processing voice command: '{text}' (Language: {language})")
            
            # Match command pattern
            match_result = PatternMatcher.match_command(text)
            
            intent = match_result.get("intent")
            entities = match_result.get("entities", {})
            confidence = match_result.get("confidence", 0.0)
            
            logging.info(f"🧠 Matched intent: {intent} (Confidence: {confidence})")
            
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
