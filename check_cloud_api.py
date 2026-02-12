
import requests
import json

def check_api():
    try:
        print("Fetching Clients...")
        r_clients = requests.get("http://44.208.164.236:5000/api/clients", timeout=5)
        if r_clients.status_code == 200:
            clients = r_clients.json()
            print(f"Total Clients: {len(clients)}")
            if clients:
                print("Sample Client:", json.dumps(clients[0], indent=2))
        else:
            print(f"Failed to fetch clients: {r_clients.status_code}")

        print("\nFetching Invoices...")
        r_invoices = requests.get("http://44.208.164.236:5000/api/invoices", timeout=5)
        if r_invoices.status_code == 200:
            invoices = r_invoices.json()
            print(f"Total Invoices: {len(invoices)}")
            if invoices:
                 print("Sample Invoice:", json.dumps(invoices[0], indent=2))
        else:
            print(f"Failed to fetch invoices: {r_invoices.status_code}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_api()
