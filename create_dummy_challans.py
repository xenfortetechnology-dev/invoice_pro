from app import app, db
from models import DeliveryChallan, Client, ChallanLineItem
from datetime import datetime, timedelta

def create_dummy_data():
    with app.app_context():
        # Check if any challans exist
        if DeliveryChallan.query.count() > 0:
            print("Challans already exist. Skipping dummy data creation.")
            return

        print("Creating dummy delivery challans...")
        
        # Get a client
        client = Client.query.first()
        if not client:
            print("No clients found! Please create a client first.")
            return

        # Create Challan 1 (Open)
        c1 = DeliveryChallan(
            challan_number=f"DC-{datetime.now().year}-0001",
            client_id=client.id,
            challan_date=datetime.now().date(),
            delivery_date=(datetime.now() + timedelta(days=2)).date(),
            status='Open',
            notes="Handle with care | Mode: By Road | Vehicle: TN-01-AB-1234"
        )
        db.session.add(c1)
        db.session.flush()
        
        item1 = ChallanLineItem(
            challan_id=c1.id,
            sr_no=1,
            description="Industrial Widget A",
            quantity=10,
            unit="Nos",
            unit_price=150.0,
            total_amount=1500.0
        )
        db.session.add(item1)
        
        # Create Challan 2 (Delivered)
        c2 = DeliveryChallan(
            challan_number=f"DC-{datetime.now().year}-0002",
            client_id=client.id,
            challan_date=(datetime.now() - timedelta(days=5)).date(),
            delivery_date=(datetime.now() - timedelta(days=1)).date(),
            status='Delivered',
            notes="Delivered to reception | Mode: Courier | Vehicle: DHL-Express"
        )
        db.session.add(c2)
        db.session.flush()
        
        item2 = ChallanLineItem(
            challan_id=c2.id,
            sr_no=1,
            description="Premium Bolt Set",
            quantity=50,
            unit="Box",
            unit_price=500.0,
            total_amount=25000.0
        )
        db.session.add(item2)

        db.session.commit()
        print("Dummy challans created successfully!")

if __name__ == "__main__":
    create_dummy_data()
