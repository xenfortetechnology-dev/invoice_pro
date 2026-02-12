import datetime

# Mock Data representing what we saw in diagnosis
mock_data = [
    {"id": 9, "client_name": "SEENU", "invoice_number": "AI-INV-20260211-001-949", "invoice_date": "2026-02-11", "payment_status": "Unpaid", "client_id": 9, "total_amount": 5000},
    {"id": 8, "client_name": "Seenu", "invoice_number": "AI-INV-20260211-001-757", "invoice_date": "2025-03-11", "payment_status": "Unpaid", "client_id": 9, "total_amount": 5000},
    {"id": 10, "client_name": "Other", "invoice_number": "INV-002", "invoice_date": "2026-02-10", "payment_status": "Paid", "client_id": 10, "total_amount": 1000}
]

# Mock Helper Maps (Empty for Seenu as per diagnosis)
client_name_map = {} 
client_risk_map = {}

def run_simulation(search_query, date_from_input, date_to_input):
    print(f"\n--- Simulation: Search='{search_query}', From='{date_from_input}' ---")
    
    # Logic from routes.py (Simplified for context but logic preserved)
    
    search_query = search_query.lower().strip()
    
    # Simulate the fix: Handle empty strings
    status_filter = 'All Status' # Default
    client_filter = 'All Clients' # Default

    date_from = date_from_input
    date_to = date_to_input

    filtered_data = []
    
    for inv in mock_data:
        inv_number = str(inv.get('invoice_number', '')).lower()
        
        # Handle client_name safely
        raw_client_name = inv.get('client_name')
        if raw_client_name and str(raw_client_name).lower() != 'none':
            client_name = str(raw_client_name).lower()
        else:
             # Fallback
            client_name = client_name_map.get(int(inv.get('client_id', 0)), '').lower()
        
        print(f"Checking Invoice {inv['id']}: Num='{inv_number}', Name='{client_name}'")

        # 1. Search Filter
        if search_query:
            if search_query not in inv_number and search_query not in client_name:
                print("  -> Skipped by Search")
                continue

        # 2. Status Filter
        if status_filter != 'All Status' and inv.get('payment_status') != status_filter:
            print("  -> Skipped by Status")
            continue

        # 3. Client Filter
        if client_filter != 'All Clients' and str(inv.get('client_id')) != client_filter:
            print("  -> Skipped by Client")
            continue

        # 4. Date Range Filter
        if date_from or date_to:
            inv_date_str = inv.get('invoice_date')
            if inv_date_str:
                try:
                    # Parse invoice date (assuming YYYY-MM-DD from API)
                    inv_date = datetime.datetime.strptime(inv_date_str, '%Y-%m-%d').date()
                    
                    if date_from:
                        d_from = datetime.datetime.strptime(date_from, '%Y-%m-%d').date()
                        if inv_date < d_from:
                            print(f"  -> Skipped by Date From ({inv_date} < {d_from})")
                            continue
                    if date_to:
                        d_to = datetime.datetime.strptime(date_to, '%Y-%m-%d').date()
                        if inv_date > d_to:
                            print("  -> Skipped by Date To")
                            continue
                except ValueError as e:
                    print(f"  -> Date Parsing Error: {e}")
                    pass 

        print("  -> MATCHED!")
        filtered_data.append(inv)

    print(f"Total Matches: {len(filtered_data)}")

# Test Case 1: "seenu" with NO date (Baseline)
run_simulation("seenu", "", "")

# Test Case 2: "seenu" with YYYY-MM-DD date (Correct format)
run_simulation("seenu", "2026-02-05", "")

# Test Case 3: "seenu" with DD-MM-YYYY date (Incorrect format - Simulate User Input from screenshot)
run_simulation("seenu", "05-02-2026", "")
