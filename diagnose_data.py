import requests
import sys
import os
from flask import Flask
from models import db, Client

# Configure Flask app to access local DB
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///invoice.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

CLOUD_API_BASE = "http://44.208.164.236:5000/api"

def diagnose():
    print("--- DIAGNOSING 'SEENU' SEARCH ISSUE ---")

    # 1. Fetch Cloud Invoices
    print("\n[1] Fetching Cloud Invoices...")
    try:
        response = requests.get(f"{CLOUD_API_BASE}/invoices", timeout=5)
        invoices = response.json()
        print(f"Found {len(invoices)} invoices.")
    except Exception as e:
        print(f"Error fetching invoices: {e}")
        return

    # 2. Check for 'seenu' in invoice data (client_name)
    print("\n[2] Checking Invoice Data for 'seenu'...")
    seenu_invoices = []
    for inv in invoices:
        c_name = str(inv.get('client_name', '')).lower()
        if 'seenu' in c_name:
            seenu_invoices.append(inv)
            print(f"  -> Found: Name='{inv.get('client_name')}', Date='{inv.get('invoice_date')}', Num='{inv.get('invoice_number')}'")
    
    if not seenu_invoices:
        print("  -> 'seenu' NOT found in any invoice 'client_name'.")

    # 3. Check Local DB for 'seenu'
    print("\n[3] Checking Local DB for 'seenu'...")
    with app.app_context():
        # Ensure DB tables exist
        db.create_all()
        
        clients = Client.query.filter(Client.name.ilike('%seenu%')).all()
        if clients:
            for c in clients:
                print(f"  -> Found in Local DB: ID={c.id}, Name='{c.name}'")
                
                # Check if any invoices map to this client ID
                mapped_invoices = [inv for inv in invoices if str(inv.get('client_id')) == str(c.id)]
                if mapped_invoices:
                     print(f"     -> {len(mapped_invoices)} invoices map to this Client ID ({c.id}).")
                     for mi in mapped_invoices:
                         print(f"        - Invoice {mi.get('invoice_number')} (Client Name in API: '{mi.get('client_name')}')")
                else:
                     print(f"     -> NO invoices map to this Client ID ({c.id}).")
        else:
            print("  -> 'seenu' NOT found in Local DB.")

if __name__ == "__main__":
    diagnose()
