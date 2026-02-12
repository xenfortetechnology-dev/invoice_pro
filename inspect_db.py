
from app import app, db
from models import Client, Invoice

def inspect_data():
    with app.app_context():
        print("--- Inspecting Clients ---")
        clients = Client.query.all()
        print(f"Total Clients in DB: {len(clients)}")
        for c in clients:
            print(f"ID: {c.id} | Name: {c.name} | Type: {c.client_type} | Created: {c.created_at}")

        print("\n--- Inspecting Invoices ---")
        invoices = Invoice.query.all()
        print(f"Total Invoices in DB: {len(invoices)}")
        for inv in invoices:
            client_name = inv.client.name if inv.client else "ORPHAN"
            print(f"Invoice: {inv.invoice_number} | Client ID: {inv.client_id} | Client Name: {client_name}")

if __name__ == "__main__":
    inspect_data()
