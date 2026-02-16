import requests
import json

CLOUD_API_BASE = "http://44.208.164.236:5000/api"

def main():
    try:
        r = requests.get(f"{CLOUD_API_BASE}/quotations", timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data:
                print(f"Total quotations: {len(data)}")
                print("\nFirst quotation structure:")
                print(json.dumps(data[0], indent=2))
                
                print("\n\nField types:")
                for key, value in data[0].items():
                    print(f"{key}: {type(value).__name__} = {repr(value)}")
            else:
                print("No quotations found")
        else:
            print(f"Failed to fetch: {r.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
