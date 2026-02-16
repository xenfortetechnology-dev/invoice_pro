import requests
import json

CLOUD_API_BASE = "http://44.208.164.236:5000/api"

def main():
    try:
        r = requests.get(f"{CLOUD_API_BASE}/quotations", timeout=10)
        if r.status_code == 200:
            data = r.json()
            statuses = set()
            for q in data:
                statuses.add(q.get('status'))
            
            print(f"Total quotations: {len(data)}")
            print(f"All statuses found: {statuses}")
            
            # Find example of Cancelled if exists
            cancelled = [q for q in data if q.get('status') == 'Cancelled']
            if cancelled:
                print(f"Found {len(cancelled)} Cancelled quotations. Example ID: {cancelled[0].get('id')}")
            else:
                print("No Cancelled quotations found.")
                
        else:
            print(f"Failed to fetch: {r.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
