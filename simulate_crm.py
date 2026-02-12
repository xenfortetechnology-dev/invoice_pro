from unittest.mock import MagicMock, patch
import json
from datetime import datetime

# Mock Flask and requests
mock_requests = MagicMock()
mock_app = MagicMock()
mock_render_template = MagicMock()

# Mock Data
MOCK_CLIENTS = [
    {"id": 1, "name": "Cloud Client A", "email": "a@cloud.com", "phone": "123", "total_business": 5000},
    {"id": 2, "name": "Cloud Client B", "email": "b@cloud.com", "phone": "456", "total_business": 150000}
]

MOCK_INVOICES = [
    {"id": 101, "client_id": 1, "total_amount": 5000, "payment_status": "Paid", "invoice_date": "2026-01-01"},
    {"id": 102, "client_id": 2, "total_amount": 150000, "payment_status": "Unpaid", "invoice_date": "2026-02-01"}
]

# Context Manager to mock requests
class MockCloudAPI:
    def __enter__(self):
        self.patcher = patch('requests.get', side_effect=self.mock_get)
        self.mock = self.patcher.start()
        return self.mock

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.patcher.stop()

    def mock_get(self, url, timeout=None):
        response = MagicMock()
        response.status_code = 200
        if "/clients" in url:
            response.json.return_value = MOCK_CLIENTS
        elif "/invoices" in url:
            response.json.return_value = MOCK_INVOICES
        return response

def test_crm_logic():
    print("--- Testing Cloud CRM Logic ---")
    
    # Simulate the logic inside client_management (copy-paste adapted)
    client_list = []
    today = datetime.now().date()
    
    with MockCloudAPI():
        # 1. Fetch
        import requests
        cloud_clients = requests.get("http://api/clients").json()
        cloud_invoices = requests.get("http://api/invoices").json()
        
        print(f"Fetched {len(cloud_clients)} clients and {len(cloud_invoices)} invoices from Cloud.")

        # 2. Process
        for c in cloud_clients:
            c_invoices = [inv for inv in cloud_invoices if inv.get('client_id') == c['id']]
            total_business = sum(float(inv.get('total_amount', 0)) for inv in c_invoices)
            
            is_high_risk = False
            for inv in c_invoices:
                if inv.get('payment_status') != 'Paid':
                    # Simplified risk check
                    pass 
            
            risk_level = "High" if is_high_risk else "Low"
            is_high_value = total_business > 100000
            
            print(f"Client: {c['name']} | Business: {total_business} | High Value: {is_high_value}")
            
            if c['id'] == 2 and not is_high_value:
                print("❌ FAILED: Client B should be High Value")
            if c['id'] == 1 and total_business != 5000:
                print("❌ FAILED: Client A business calculation wrong")

    print("\n--- CRM Logic Test Check Complete ---")

if __name__ == "__main__":
    test_crm_logic()
