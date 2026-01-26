import requests
import sys

try:
    response = requests.get('http://127.0.0.1:5000/analytics')
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("Analytics page loaded successfully.")
    else:
        print("Failed to load analytics page.")
        print(response.text[:500])
except Exception as e:
    print(f"Error connecting to server: {e}")
