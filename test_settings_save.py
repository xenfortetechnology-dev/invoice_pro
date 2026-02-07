from app import app, db
from models import User, Company
import json

def test_settings_update():
    with app.app_context():
        # extensive setup to ensure we have data
        user = User.query.filter_by(username='admin').first()
        if not user:
            print("Admin user not found!")
            return

        with app.test_client() as client:
            # Login first (mock session or login route)
            # Assuming standard flask-login, we can access the session or just mock login_required if needed
            # But easier to just use test_request_context if we bypass login or use login helper
            
            # Let's try to simulate a logged-in session transaction
            with client.session_transaction() as sess:
                sess['user_id'] = user.id
                sess['_fresh'] = True

            # Data to update
            payload = {
                'company': {
                    'companyName': 'Updated Company Name Test',
                    'companyEmail': 'test@example.com'
                },
                'user': {
                    'themePreference': 'dark'
                },
                'invoice': {
                    'defaultTaxRate': 20
                }
            }

            print("Sending update request...")
            response = client.post('/settings/update', 
                                 data=json.dumps(payload),
                                 content_type='application/json')
            
            print(f"Response Status: {response.status_code}")
            print(f"Response Data: {response.get_json()}")
            
            if response.status_code == 200:
                # Verify DB update
                company = Company.query.first()
                print(f"Company Name in DB: {company.name}")
                if company.name == 'Updated Company Name Test':
                   print("SUCCESS: Company name updated correctly.")
                else:
                   print("FAILURE: Company name did not update.")
            else:
                print("FAILURE: Request failed.")

if __name__ == "__main__":
    test_settings_update()
