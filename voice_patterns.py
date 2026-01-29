"""
Voice Command Patterns - Script-based pattern matching for English and Tamil/Tanglish
No AI/API dependencies - Pure regex pattern matching
"""

import re
from typing import Dict, Any, Optional, List, Tuple

# =========================
# TAMIL NUMBER WORDS
# =========================
TAMIL_NUMBERS = {
    # Basic numbers
    'onnu': 1, 'onu': 1,
    'rendu': 2, 'randu': 2, 'irandu': 2,
    'moonu': 3, 'munu': 3,
    'naalu': 4, 'nalu': 4, 'nangu': 4,
    'anju': 5, 'aindu': 5, 'aindhu': 5,
    'aaru': 6, 'aru': 6,
    'ezhu': 7, 'yezhu': 7,
    'ettu': 8, 'entu': 8,
    'onpathu': 9, 'ombathu': 9,
    'pathu': 10, 'patthu': 10,
    'pathinen': 18,
    
    # Larger numbers
    'nuru': 100, 'nooru': 100,
    'ayiram': 1000, 'aayiram': 1000,
    
    # Common combinations
    'pathinanju': 15, 'patinaindhu': 15,
    'irupathu': 20, 'irubathu': 20,
    'muppathu': 30, 'muppadu': 30,
    'nalpathu': 40, 'nalpadu': 40,
    'aimpathu': 50, 'aimbathu': 50, 'aimpadhu': 50,
    'arupathu': 60, 'arubathu': 60,
    'ezhupathu': 70, 'yezhubathu': 70,
    'enpathu': 80, 'embathu': 80,
    'thonnooru': 90, 'thonuru': 90,
}

# Tamil words to English
TAMIL_WORDS = {
    'ku': 'for',
    'podu': 'create',
    'pannu': 'do',
    'panu': 'do',
    'kandu': 'calculate',
    'pidu': 'show',
    'ruba': 'rupees',
    'ruva': 'rupees',
    'nos': 'nos',
    'quantity': 'quantity',
    'qty': 'quantity',
    'price': 'price',
    'rate': 'rate',
    'total': 'total',
    'save': 'save',
    'invoice': 'invoice',
}

# =========================
# COMMAND PATTERNS
# =========================

class CommandPatterns:
    """Pattern definitions for voice commands"""
    
    # CREATE INVOICE PATTERNS
    CREATE_INVOICE = [
        # English
        (r'create\s+invoice\s+for\s+(\w+)', 'en'),
        (r'new\s+invoice\s+for\s+(\w+)', 'en'),
        (r'make\s+invoice\s+for\s+(\w+)', 'en'),
        (r'start\s+invoice\s+for\s+(\w+)', 'en'),
        
        # Tamil/Tanglish
        (r'(\w+)\s+ku\s+invoice\s+podu', 'ta'),
        (r'(\w+)\s+ku\s+invoice', 'ta'),
        (r'invoice\s+for\s+(\w+)', 'en'),
    ]
    
    # ADD ITEM PATTERNS
    ADD_ITEM = [
        # English - Full format: "add pen quantity 2 price 10"
        (r'add\s+([a-zA-Z0-9\s]+?)\s+quantity\s+(\d+)\s+(?:price|rate)\s+(\d+)', 'en'),
        
        # English - Short format: "add pen 2 nos at 10"
        (r'add\s+([a-zA-Z0-9\s]+?)\s+(\d+)\s+(?:nos|kg|liters?|pieces?)\s+(?:at|rate|price)\s+(\d+)', 'en'),
        
        # English - Simple: "add pen 10 rupees"
        (r'add\s+([a-zA-Z0-9\s]+?)\s+(\d+)\s+(?:rupees?|rs)', 'en'),
        
        # Tamil/Tanglish: "pen rendu ruba pathu" (pen 2 rupees 10)
        (r'([a-zA-Z0-9\s]+?)\s+(\w+)\s+(?:ruba|ruva)\s+(\w+)', 'ta'),
        
        # Tamil/Tanglish: "pen pathu ruba" (pen 10 rupees, qty=1)
        (r'([a-zA-Z0-9\s]+?)\s+(\w+)\s+(?:ruba|ruva)', 'ta'),
        
        # Tamil with quantity: "add pen quantity rendu price pathu"
        (r'add\s+([a-zA-Z0-9\s]+?)\s+quantity\s+(\w+)\s+price\s+(\w+)', 'ta'),
    ]
    
    # SAVE INVOICE PATTERNS
    SAVE_INVOICE = [
        # English
        (r'save\s+invoice', 'en'),
        (r'save\s+this', 'en'),
        (r'finish\s+invoice', 'en'),
        (r'complete\s+invoice', 'en'),
        
        # Tamil/Tanglish
        (r'save\s+pannu', 'ta'),
        (r'save\s+panu', 'ta'),
        (r'invoice\s+save', 'en'),
    ]
    
    # CALCULATE TOTAL PATTERNS
    CALCULATE_TOTAL = [
        # English
        (r'calculate\s+total', 'en'),
        (r'total\s+amount', 'en'),
        (r'show\s+total', 'en'),
        (r'what(?:\'s|\s+is)\s+(?:the\s+)?total', 'en'),
        
        # Tamil/Tanglish
        (r'total\s+kandu\s+pidu', 'ta'),
        (r'total\s+sollu', 'ta'),
        (r'total\s+enna', 'ta'),
    ]
    
    # SEARCH CLIENT PATTERNS
    SEARCH_CLIENT = [
        # English
        (r'find\s+client\s+(\w+)', 'en'),
        (r'search\s+client\s+(\w+)', 'en'),
        (r'search\s+for\s+(\w+)', 'en'),
        
        # Tamil
        (r'(\w+)\s+yaar', 'ta'),
        (r'(\w+)\s+details', 'en'),
    ]


# =========================
# PATTERN MATCHER
# =========================

class PatternMatcher:
    """Match voice commands to patterns and extract entities"""
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize input text"""
        # Convert to lowercase
        text = text.lower().strip()
        
        # Remove filler words
        fillers = ['um', 'uh', 'er', 'ah', 'like', 'you know']
        for filler in fillers:
            text = re.sub(r'\b' + filler + r'\b', '', text, flags=re.IGNORECASE)
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    @staticmethod
    def convert_tamil_numbers(text: str) -> str:
        """Convert Tamil number words to digits"""
        for tamil_word, number in TAMIL_NUMBERS.items():
            text = re.sub(r'\b' + tamil_word + r'\b', str(number), text, flags=re.IGNORECASE)
        return text
    
    @staticmethod
    def match_create_invoice(text: str) -> Optional[Dict[str, Any]]:
        """Match create invoice patterns"""
        for pattern, lang in CommandPatterns.CREATE_INVOICE:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                client_name = match.group(1).strip().capitalize()
                return {
                    'intent': 'create_invoice',
                    'entities': {
                        'client_name': client_name
                    },
                    'language': lang,
                    'confidence': 1.0
                }
        return None
    
    @staticmethod
    def match_add_item(text: str) -> Optional[Dict[str, Any]]:
        """Match add item patterns"""
        # Convert Tamil numbers first
        text_converted = PatternMatcher.convert_tamil_numbers(text)
        
        for pattern, lang in CommandPatterns.ADD_ITEM:
            match = re.search(pattern, text_converted, re.IGNORECASE)
            if match:
                groups = match.groups()
                
                # Different patterns have different group structures
                if len(groups) == 3:
                    # Full format: item, quantity, price
                    item_desc = groups[0].strip()
                    quantity = int(groups[1]) if groups[1].isdigit() else 1
                    price = int(groups[2]) if groups[2].isdigit() else 0
                elif len(groups) == 2:
                    # Simple format: item, price (quantity=1)
                    item_desc = groups[0].strip()
                    quantity = 1
                    price = int(groups[1]) if groups[1].isdigit() else 0
                else:
                    continue
                
                # Extract additional details if present
                unit_match = re.search(r'\b(nos|kg|liters?|pieces?)\b', text, re.IGNORECASE)
                unit = unit_match.group(1).capitalize() if unit_match else 'Nos'
                
                tax_match = re.search(r'(?:tax|gst)\s+(\d+)', text, re.IGNORECASE)
                tax = int(tax_match.group(1)) if tax_match else 18
                
                hsn_match = re.search(r'(?:hsn|code)\s+(\w+)', text, re.IGNORECASE)
                hsn_code = hsn_match.group(1) if hsn_match else None
                
                return {
                    'intent': 'add_item',
                    'entities': {
                        'item_description': item_desc,
                        'quantity': quantity,
                        'amount': price,
                        'unit': unit,
                        'tax': tax,
                        'hsn_code': hsn_code
                    },
                    'language': lang,
                    'confidence': 1.0
                }
        return None
    
    @staticmethod
    def match_save_invoice(text: str) -> Optional[Dict[str, Any]]:
        """Match save invoice patterns"""
        for pattern, lang in CommandPatterns.SAVE_INVOICE:
            if re.search(pattern, text, re.IGNORECASE):
                return {
                    'intent': 'save_invoice',
                    'entities': {},
                    'language': lang,
                    'confidence': 1.0
                }
        return None
    
    @staticmethod
    def match_calculate_total(text: str) -> Optional[Dict[str, Any]]:
        """Match calculate total patterns"""
        for pattern, lang in CommandPatterns.CALCULATE_TOTAL:
            if re.search(pattern, text, re.IGNORECASE):
                return {
                    'intent': 'calculate_total',
                    'entities': {},
                    'language': lang,
                    'confidence': 1.0
                }
        return None
    
    @staticmethod
    def match_search_client(text: str) -> Optional[Dict[str, Any]]:
        """Match search client patterns"""
        for pattern, lang in CommandPatterns.SEARCH_CLIENT:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                client_name = match.group(1).strip().capitalize()
                return {
                    'intent': 'search_client',
                    'entities': {
                        'client_name': client_name
                    },
                    'language': lang,
                    'confidence': 1.0
                }
        return None
    
    @staticmethod
    def match_command(text: str) -> Dict[str, Any]:
        """
        Match text against all patterns and return best match
        Priority order: create_invoice > add_item > save_invoice > calculate_total > search_client
        """
        # Normalize text
        text = PatternMatcher.normalize_text(text)
        
        # Try patterns in priority order
        matchers = [
            PatternMatcher.match_create_invoice,
            PatternMatcher.match_add_item,
            PatternMatcher.match_save_invoice,
            PatternMatcher.match_calculate_total,
            PatternMatcher.match_search_client,
        ]
        
        for matcher in matchers:
            result = matcher(text)
            if result:
                return result
        
        # No match found
        return {
            'intent': 'unknown',
            'entities': {},
            'language': 'unknown',
            'confidence': 0.0,
            'original_text': text
        }


# =========================
# HELPER FUNCTIONS
# =========================

def get_command_suggestions() -> List[str]:
    """Get list of example commands for user guidance"""
    return [
        # English
        "Create invoice for Aravind",
        "Add pen quantity 2 price 10",
        "Add notebook 5 nos at 50",
        "Calculate total",
        "Save invoice",
        
        # Tamil/Tanglish
        "Aravind ku invoice podu",
        "Pen rendu ruba pathu",
        "Notebook anju nos rate aimpathu",
        "Total kandu pidu",
        "Save pannu",
    ]
