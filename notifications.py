import requests
from email_service import send_email

CLOUD_API_BASE = "http://44.208.164.236:5000/api"

# 🔥 Use system login to get token automatically
SYSTEM_EMAIL = "dharanimenaga229@gmail.com"
SYSTEM_PASSWORD = "wvpncmfqgvtflxqf"


def get_system_token():
    try:
        response = requests.post(
            f"{CLOUD_API_BASE}/login",
            json={
                "email": SYSTEM_EMAIL,
                "password": SYSTEM_PASSWORD
            },
            timeout=5
        )

        if response.status_code == 200:
            return response.json().get("token")

        print("Login failed ❌")
        return None

    except Exception as e:
        print("Token error:", e)
        return None


def background_cloud_request(method, endpoint, **kwargs):

    token = get_system_token()

    if not token:
        return None

    headers = {
        "Authorization": f"Bearer {token}"
    }

    url = f"{CLOUD_API_BASE}{endpoint}"

    return requests.request(method, url, headers=headers, timeout=5, **kwargs)


def send_weekly_business_report():

    print("Weekly report triggered ✅")

    invoices_response = background_cloud_request("GET", "/invoices")

    if not invoices_response or invoices_response.status_code != 200:
        print("Invoice fetch failed ❌")
        return

    invoices = invoices_response.json()

    total_revenue = sum(
        float(inv.get("total_amount", 0))
        for inv in invoices
        if inv.get("payment_status") == "Paid"
    )

    total_unpaid = sum(
        float(inv.get("total_amount", 0))
        for inv in invoices
        if inv.get("payment_status") == "Unpaid"
    )

    company_response = background_cloud_request("GET", "/company")

    if company_response and company_response.status_code == 200:

        company_data = company_response.json()

        print("Sending weekly report to:", company_data.get("email"))

        send_email(
            company_data.get("email"),
            "Weekly Business Report",
            f"""
            <h2>Weekly Business Summary</h2>
            <p>Total Revenue Collected: ₹{total_revenue}</p>
            <p>Total Pending Payments: ₹{total_unpaid}</p>
            <p>Total Invoices: {len(invoices)}</p>
            """
        )

        print("Weekly report sent ✅")
