"""
Database Migration Script - Add Tax Fields to InvoiceLineItem
Run this script to add CGST, SGST, and IGST fields to invoice_line_item table
"""

from app import app, db
from sqlalchemy import text

def migrate_database():
    """Add new tax columns to invoice_line_item table"""
    
    with app.app_context():
        try:
            # Check if columns already exist
            inspector = db.inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('invoice_line_item')]
            
            new_columns = [
                'cgst_percentage',
                'sgst_percentage', 
                'igst_percentage',
                'cgst_amount',
                'sgst_amount',
                'igst_amount'
            ]
            
            columns_to_add = [col for col in new_columns if col not in columns]
            
            if not columns_to_add:
                print("[SUCCESS] All tax columns already exist. No migration needed.")
                return
            
            print(f"[INFO] Adding {len(columns_to_add)} new columns to invoice_line_item table...")
            
            # Add columns one by one
            for column in columns_to_add:
                sql = f"ALTER TABLE invoice_line_item ADD COLUMN {column} FLOAT DEFAULT 0.0"
                db.session.execute(text(sql))
                print(f"  [OK] Added column: {column}")
            
            db.session.commit()
            print("[SUCCESS] Migration completed successfully!")
            
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Migration failed: {e}")
            raise

if __name__ == "__main__":
    migrate_database()
