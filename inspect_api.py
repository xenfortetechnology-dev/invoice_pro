import requests
import json

try:
    # Try fetching a specific client ID (e.g., 110 from the previous dump)
    print("Probing /clients/110...")
    resp = requests.get("http://44.208.164.236:5000/api/clients/110", timeout=5)
    print(f"Detail Status: {resp.status_code}")
    if resp.status_code == 200:
        client = resp.json()
        print("Client Detail:", json.dumps(client, indent=2))
    else:
        print("Detail Response:", resp.text)

except Exception as e:
    print(f"Error: {e}")
