import sqlite3
import random
import json
from datetime import datetime, timedelta
from faker import Faker

DB = "./instance/revolutionary_invoice.db"
fake = Faker()

conn = sqlite3.connect(DB)
cur = conn.cursor()

def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

# -----------------------------
# USERS
# -----------------------------
cur.execute("""
INSERT OR IGNORE INTO user
(id, username, email, password_hash, is_admin,
 ai_features_enabled, voice_commands_enabled,
 preferred_language, theme_preference,
 biometric_enabled, collaboration_access,
 created_at, last_login)
VALUES
(1,'admin','admin@company.com','hash',1,1,1,'en','dark',0,1,?,?)
""", (now(), now()))

# -----------------------------
# COMPANY
# -----------------------------
cur.execute("""
INSERT OR IGNORE INTO company
(id, name, address, city, state, pincode,
 phone, email, gstin, pan, created_at)
VALUES
(1,'Revolutionary Tech Pvt Ltd',
'MG Road','Bengaluru','KA','560001',
'+91-9999999999','info@revtech.com',
'29ABCDE1234F1Z5','ABCDE1234F',?)
""", (now(),))

# -----------------------------
# CLIENTS
# -----------------------------
clients = []
for i in range(1, 11):
    total_business = random.randint(50000, 500000)
    cur.execute("""
    INSERT OR IGNORE INTO client
    (id, name, contact_person, address, city, state,
     phone, email, gstin, pan, client_type,
     lead_stage, total_business, ai_risk_score,
     predicted_ltv, sentiment_score, created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        i,
        fake.company(),
        fake.name(),
        fake.address(),
        fake.city(),
        fake.state(),
        fake.phone_number(),
        fake.company_email(),
        fake.bothify("##ABCDE####F#Z#"),
        fake.bothify("ABCDE####F"),
        random.choice(["Enterprise","SME"]),
        random.choice(["Lead","Active","Dormant"]),
        total_business,
        round(random.uniform(0.1, 0.9), 2),
        total_business * random.uniform(1.5, 3.5),
        round(random.uniform(0.3, 0.9), 2),
        now()
    ))
    clients.append(i)

# -----------------------------
# INVENTORY
# -----------------------------
for i in range(1, 8):
    cur.execute("""
    INSERT OR IGNORE INTO inventory_item
    (id, item_code, name, category, current_stock,
     unit, cost_price, selling_price,
     reorder_level, max_stock_level,
     abc_classification, created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        i,
        f"ITEM-{100+i}",
        fake.word().title(),
        random.choice(["Electronics","Office","Services"]),
        random.randint(20, 200),
        "pcs",
        random.randint(200, 1000),
        random.randint(1200, 3000),
        30,
        300,
        random.choice(["A","B","C"]),
        now()
    ))

# -----------------------------
# INVOICES + LINE ITEMS (SAFE)
# -----------------------------
for client_id in clients:
    for _ in range(random.randint(2, 6)):
        invoice_date = datetime.utcnow() - timedelta(days=random.randint(1, 90))
        due_date = invoice_date + timedelta(days=15)
        total = random.randint(5000, 50000)

        status = random.choice(["Paid","Unpaid","Overdue"])
        amount_paid = total if status == "Paid" else random.randint(0, total//2)

        cur.execute("""
        INSERT INTO invoice
        (invoice_number, client_id, invoice_date, due_date,
         subtotal, cgst, sgst, total_amount,
         payment_status, amount_paid,
         ai_generated, voice_command_created,
         predicted_payment_date, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            f"INV-{random.randint(1000,9999)}",
            client_id,
            invoice_date.date(),
            due_date.date(),
            total * 0.9,
            total * 0.05,
            total * 0.05,
            total,
            status,
            amount_paid,
            1,
            random.choice([0,1]),
            (invoice_date + timedelta(days=random.randint(10,20))).date(),
            now()
        ))

        invoice_id = cur.lastrowid  # ✅ CRITICAL FIX

        # Line items
        for line in range(1, random.randint(2,4)):
            qty = random.randint(1,5)
            price = random.randint(1000,5000)
            cur.execute("""
            INSERT INTO invoice_line_item
            (invoice_id, sr_no, description, quantity,
             unit, unit_price, tax_percentage, total_amount,
             ai_suggested, ai_confidence_score)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                invoice_id,
                line,
                fake.bs().title(),
                qty,
                "pcs",
                price,
                18,
                qty * price,
                random.choice([0,1]),
                round(random.uniform(0.6,0.95),2)
            ))

        # Payment reminders
        if amount_paid < total:
            cur.execute("""
            INSERT INTO payment_reminder
            (invoice_id, reminder_date, reminder_type,
             status, escalation_level, created_at)
            VALUES (?,?,?,?,?,?)
            """, (
                invoice_id,
                due_date + timedelta(days=3),
                "Email",
                "Sent",
                random.randint(0,2),
                now()
            ))

# -----------------------------
# EXPENSES
# -----------------------------
for _ in range(15):
    cur.execute("""
    INSERT INTO expense_tracking
    (user_id, expense_date, amount, category,
     vendor_name, ai_confidence_score, created_at)
    VALUES (?,?,?,?,?,?,?)
    """, (
        1,
        (datetime.utcnow() - timedelta(days=random.randint(1,60))).date(),
        random.randint(500,15000),
        random.choice(["Travel","Supplies","Marketing"]),
        fake.company(),
        round(random.uniform(0.7,0.95),2),
        now()
    ))

# -----------------------------
# AI INTERACTIONS
# -----------------------------
for _ in range(20):
    cur.execute("""
    INSERT INTO ai_interaction
    (user_id, interaction_type, input_data,
     ai_response, confidence_score,
     processing_time, created_at)
    VALUES (?,?,?,?,?,?,?)
    """, (
        1,
        random.choice(["chat","invoice","analysis"]),
        json.dumps({"query":"Analyze payment trends"}),
        json.dumps({"summary":"Payments stable"}),
        round(random.uniform(0.7,0.95),2),
        round(random.uniform(0.2,1.5),2),
        now()
    ))

conn.commit()
conn.close()

print("✅ Revolutionary Invoice DB fully populated with real-time dataset")
