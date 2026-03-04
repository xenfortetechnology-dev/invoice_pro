import os
import json
import logging
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file, session, abort, Flask
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, and_, or_, extract, desc
from sqlalchemy.orm import joinedload

import os
from app import app, mail 
from models import *
from utils import *
from utils import safe_dict
from pdf_generator import generate_invoice_pdf, generate_challan_pdf, generate_triple_invoice_pdf, AnalyticsReportGenerator
from ai_services import ai_assistant, predictive_analytics, inventory_ai
from blockchain_service import blockchain_service, smart_contract_manager
from ocr_service import ocr_processor, receipt_processor
from voice_service import get_voice_processor, get_voice_session
from analytics_engine import AnalyticsEngine
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io
import csv
from flask import Response, request, render_template_string

from datetime import datetime
from sqlalchemy import func

from pdf_generator import generate_quotation_pdf
from flask import send_file
from models import BankDetails
from datetime import date
from sqlalchemy import func
from app import db
from models import Invoice, DeletedQuotation

import ai_services
import ai_client 
from types import SimpleNamespace
import requests
from flask import session

# Initialize analytics engine
analytics_engine = AnalyticsEngine(db.session)
from report_generator import AnalyticsReportGenerator
report_generator = AnalyticsReportGenerator()


CLOUD_API_BASE = os.environ.get("CLOUD_API_BASE", "http://44.208.164.236:5000/api")

def cloud_request(method, endpoint, **kwargs):
    """
    Centralized Cloud API request handler with JWT Authorization
    Keeps all existing routes unchanged, only fixes authentication.
    """
    headers = kwargs.pop("headers", {})

    # Attach JWT token if available
    token = session.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        logging.debug(f"Token found in session for {method} {endpoint}")
    else:
        logging.warning(f"No token in session for {method} {endpoint}")

    kwargs.setdefault("timeout", 10)
    try:
        response = requests.request(
            method,
            f"{CLOUD_API_BASE}{endpoint}",
            headers=headers,
            **kwargs
        )
        if response:
            logging.debug(f"API Response: {method} {endpoint} - Status: {response.status_code}")
        return response
    except Exception as e:
        logging.error(f"Cloud request error: {e}")
        return None



# ===== HELPER FOR DESKTOP DOWNLOADS =====
def save_pdf_to_downloads(buffer, filename):
    """Save PDF buffer to local Downloads folder (Reliable for Desktop EXE)"""
    try:
        downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.exists(downloads_path):
            os.makedirs(downloads_path)
        
        file_path = os.path.join(downloads_path, filename)
        with open(file_path, "wb") as f:
            f.write(buffer.getvalue())
        return file_path
    except Exception as e:
        logging.error(f"Error saving PDF to downloads: {e}")
        return None

# ===== CLOUD API HELPER FUNCTIONS =====
# CLOUD_API_BASE = os.environ.get("CLOUD_API_BASE", "http://44.208.164.236:5000/api")

def fetch_cloud_clients():
    try:
        response = cloud_request("GET", "/clients")
        if response and response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        logging.error(f"Cloud API error (clients): {e}")
        return []

def fetch_cloud_client_by_id(client_id):
    """Fetch single client from cloud database by ID"""
    try:
        # First fetch all clients, then filter by ID
        clients = fetch_cloud_clients()
        for client in clients:
            if client.get('id') == int(client_id):
                return client
        return None
    except Exception as e:
        logging.error(f"Cloud API error (client by ID): {e}")
        return None

def fetch_cloud_invoices():
    try:
        response = cloud_request("GET", "/invoices")
        if response and response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        logging.error(f"Cloud API error (invoices): {e}")
        return []


def fetch_cloud_invoice_by_id(invoice_id):
    """Fetch single invoice from cloud API by ID"""
    try:
        response = cloud_request("GET", f"/invoices/{invoice_id}")

        if response and response.status_code == 200:
            return response.json()

        logging.error(f"Failed to fetch invoice {invoice_id}: {response.status_code if response else 'No response'}")
        return None

    except Exception as e:
        logging.error(f"Cloud API error (invoice by ID): {e}")
        return None

def fetch_cloud_challans():
    """Fetch all delivery challans from cloud database"""
    try:
        response = cloud_request("GET", "/challans")
        if response and response.status_code == 200:
            return response.json()
        if response:
            logging.warning(f"Cloud API returned status {response.status_code}")
        else:
            logging.warning("Cloud API request returned None")
        return []
    except Exception as e:
        logging.error(f"Cloud API error (challans): {e}")
        return []

def fetch_cloud_challan_by_id(challan_id):
    """Fetch a single challan from cloud database by ID"""
    try:
        challans = fetch_cloud_challans()
        for challan in challans:
            if challan.get('id') == int(challan_id):
                return challan
        return None
    except Exception as e:
        logging.error(f"Cloud API error (challan by ID): {e}")
        return None

def fetch_cloud_quotations():
    """Fetch all quotations from cloud database"""
    try:
        response = cloud_request("GET", "/quotations")
        if response and response.status_code == 200:
            return response.json()
        if response:
            logging.warning(f"Cloud API returned status {response.status_code}")
        else:
            logging.warning("Cloud API request returned None")
        return []
    except Exception as e:
        logging.error(f"Cloud API error (quotations): {e}")
        return []

def fetch_cloud_quotation_by_id(qid):
    """Fetch single quotation from cloud database by ID — full detail endpoint"""
    try:
        response = cloud_request("GET", f"/quotations/{qid}")
        if response and response.status_code == 200:
            data = response.json()
            # API returns a single dict for the /quotations/<id> endpoint
            if isinstance(data, dict) and "id" in data:
                return data
            # Fallback: if list returned (shouldn't happen), find by id
            if isinstance(data, list):
                for item in data:
                    if str(item.get("id")) == str(qid):
                        return item

        logging.error(f"Failed to fetch quotation {qid}: {response.status_code if response else 'No response'}")
        return None
    except Exception as e:
        logging.error(f"Cloud API error (quotation by ID): {e}")
        return None
        return None

from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "token" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template("login.html")

    username = request.form.get("username")
    password = request.form.get("password")

    cloud_url = f"{CLOUD_API_BASE}/login"

    try:
        response = requests.post(
            cloud_url,
            json={
                "username": username,
                "password": password
            }
        )

        data = response.json()

        if data.get("success"):
            session["token"] = data["token"]

            # 🔥 FIX: Set user_id manually
            session["user_id"] = username   # just needs to be truthy

            # Optional
            session["username"] = username
            session["is_admin"] = False

            return redirect("/dashboard")
        else:
            flash("Invalid credentials")
            return redirect("/login")

    except Exception:
        flash("Cloud server not reachable")
        return redirect("/login")


@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/')
def index():
    """Redirect root to dashboard"""
    return redirect(url_for('dashboard_page'))

class CustomPagination:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        self.has_prev = page > 1
        self.has_next = page < self.pages
        self.prev_num = page - 1
        self.next_num = page + 1

    def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and \
                num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num


@app.route('/invoices')
@login_required
def invoice_management():
    try:
        response = cloud_request("GET", "/invoices")

        if response.status_code == 200:
            data = response.json()
        else:
            flash("Failed to load invoices from API", "error")
            data = []

    except Exception as e:
        flash(f"API connection error: {str(e)}", "error")
        data = []

    # =============================
    # PREPARE CLIENT MAPS
    # =============================

    client_ids = list(set(int(inv["client_id"]) for inv in data if inv.get("client_id")))

    cloud_clients_data = fetch_cloud_clients()
    cloud_clients = [SimpleNamespace(**c) for c in cloud_clients_data]

    local_clients = Client.query.filter(Client.id.in_(client_ids)).all()
    client_risk_map = {c.id: c.ai_risk_score for c in local_clients}

    client_name_map = {c.id: c.name for c in cloud_clients}

    # =============================
    # FILTERING
    # =============================

    search_query = request.args.get('search', '').lower().strip()
    status_filter = request.args.get('status') or 'All Status'
    client_filter = request.args.get('client_id') or 'All Clients'
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    filtered_data = []

    for inv in data:

        inv_number = str(inv.get('invoice_number', '')).lower()
        client_name = str(inv.get('client_name') or '').lower()

        # SEARCH FILTER
        if search_query:
            if search_query not in inv_number and search_query not in client_name:
                continue

        # STATUS FILTER
        if status_filter != 'All Status' and inv.get('payment_status') != status_filter:
            continue

        # CLIENT FILTER
        if client_filter != 'All Clients' and str(inv.get('client_id')) != client_filter:
            continue

        # DATE RANGE FILTER
        if date_from or date_to:
            inv_date_str = inv.get('invoice_date')
            if inv_date_str:
                try:
                    inv_date = datetime.strptime(inv_date_str, '%Y-%m-%d').date()

                    if date_from:
                        d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                        if inv_date < d_from:
                            continue

                    if date_to:
                        d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                        if inv_date > d_to:
                            continue

                except ValueError:
                    pass

        filtered_data.append(inv)

    # =============================
    # PAGINATION
    # =============================

    page = request.args.get('page', 1, type=int)
    per_page = 15
    total_invoices = len(filtered_data)

    start = (page - 1) * per_page
    end = start + per_page
    paginated_data = filtered_data[start:end]

    # =============================
    # BUILD INVOICE OBJECTS
    # =============================

    ai_insights = {}
    invoice_list = []

    for inv in paginated_data:

        # Risk logic
        risk_score = client_risk_map.get(int(inv.get("client_id", 0)), 0.0)
        risk_level = "High" if risk_score > 0.7 else "Medium" if risk_score > 0.3 else "Low"

        try:
            total_amount = float(inv.get("total_amount", 0))
        except (ValueError, TypeError):
            total_amount = 0.0

        is_high_value = total_amount > 100000

        # Overdue logic (NOW BASED ON DUE DATE)
        is_overdue_risk = False
        if inv.get("due_date") and inv.get("payment_status") != "Paid":
            try:
                due_date = datetime.strptime(inv["due_date"], "%Y-%m-%d").date()
                if datetime.now().date() > due_date:
                    is_overdue_risk = True
            except ValueError:
                pass

        if is_overdue_risk:
            risk_level = "High"

        ai_insights[inv["id"]] = {
            "payment_risk": risk_level,
            "high_value": is_high_value,
            "overdue_risk": is_overdue_risk,
            "predicted_payment_date": None
        }

        # SAFE DATE PARSING
        invoice_date_obj = None
        if inv.get("invoice_date"):
            try:
                invoice_date_obj = datetime.strptime(inv["invoice_date"], "%Y-%m-%d")
            except:
                pass

        due_date_obj = None
        if inv.get("due_date"):
            try:
                due_date_obj = datetime.strptime(inv["due_date"], "%Y-%m-%d")
            except:
                pass

        invoice_obj = SimpleNamespace(
            id=inv["id"],
            invoice_number=inv["invoice_number"],
            invoice_date=invoice_date_obj,
            due_date=due_date_obj,
            total_amount=total_amount,
            amount_paid=0,
            payment_status=inv["payment_status"],
            client=SimpleNamespace(
                name=inv.get("client_name")
            )
        )

        invoice_list.append(invoice_obj)

    invoices_obj = CustomPagination(invoice_list, page, per_page, total_invoices)

    return render_template(
        "invoice_management.html",
        invoices=invoices_obj,
        ai_enabled=True,
        ai_insights=ai_insights,
        search=search_query,
        status_filter=status_filter,
        client_filter=client_filter,
        clients=cloud_clients,
        date_from=date_from,
        date_to=date_to
    )


    try:
        response = cloud_request("GET", "/invoices")


        if response.status_code == 200:
            data = response.json()
        else:
            flash("Failed to load invoices from API", "error")
            data = []

    except Exception as e:
        flash(f"API connection error: {str(e)}", "error")
        data = []

    # Get list of unique client IDs from ALL invoice data (before filtering)
    client_ids = list(set(int(inv["client_id"]) for inv in data if inv.get("client_id")))
    
    # Fetch cloud client data for dropdown
    cloud_clients_data = fetch_cloud_clients()
    cloud_clients = [SimpleNamespace(**c) for c in cloud_clients_data]
    
    # Fetch local client data for risk scores only
    local_clients = Client.query.filter(Client.id.in_(client_ids)).all()
    client_risk_map = {c.id: c.ai_risk_score for c in local_clients}
    
    # Create client name map from cloud data
    client_name_map = {c.id: c.name for c in cloud_clients}

    # --- FILTERING LOGIC ---
    search_query = request.args.get('search', '').lower().strip()
    status_filter = request.args.get('status')
    if not status_filter:
        status_filter = 'All Status'

    client_filter = request.args.get('client_id')
    if not client_filter:
        client_filter = 'All Clients'

    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    # DEBUG LOGGING TO FILE
    try:
        with open('debug_log.txt', 'w') as f:
            f.write(f"TIMESTAMP: {datetime.now()}\n")
            f.write(f"FILTERS: Search='{search_query}', Status='{status_filter}', Client='{client_filter}', From='{date_from}', To='{date_to}'\n")
            f.write(f"TOTAL INVOICES FETCHED: {len(data)}\n")
            
            filtered_data = []
            
            for index, inv in enumerate(data):
                inv_number = str(inv.get('invoice_number', '')).lower()
                
                # Handle client_name safely
                raw_client_name = inv.get('client_name')
                if raw_client_name and str(raw_client_name).lower() != 'none':
                    client_name = str(raw_client_name).lower()
                else:
                     # Fallback to local map if Cloud data is missing name or is "None"
                    client_name = client_name_map.get(int(inv.get('client_id', 0)), '').lower()
                
                # Log first 5 invoices or if 'seenu' is involved
                should_log = index < 5 or 'seenu' in client_name or 'seenu' in inv_number or search_query == 'seenu'
                
                if should_log:
                    f.write(f"INV [{index}]: Num='{inv_number}', Client='{client_name}', ID='{inv.get('id')}'\n")

                # 1. Search Filter
                if search_query:
                    if search_query not in inv_number and search_query not in client_name:
                        if should_log: f.write(f"  -> SKIPPED by Search ('{search_query}' not in '{inv_number}' or '{client_name}')\n")
                        continue

                # 2. Status Filter
                if status_filter != 'All Status' and inv.get('payment_status') != status_filter:
                    if should_log: f.write("  -> SKIPPED by Status\n")
                    continue

                # 3. Client Filter
                if client_filter != 'All Clients' and str(inv.get('client_id')) != client_filter:
                    if should_log: f.write(f"  -> SKIPPED by Client ({inv.get('client_id')} != {client_filter})\n")
                    continue

                # 4. Date Range Filter
                if date_from or date_to:
                    inv_date_str = inv.get('invoice_date')
                    if inv_date_str:
                        try:
                            # Parse invoice date (assuming YYYY-MM-DD from API)
                            inv_date = datetime.strptime(inv_date_str, '%Y-%m-%d').date()
                            
                            if date_from:
                                d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                                if inv_date < d_from:
                                    if should_log: f.write(f"  -> SKIPPED by Date From ({inv_date} < {d_from})\n")
                                    continue
                            if date_to:
                                d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                                if inv_date > d_to:
                                    if should_log: f.write(f"  -> SKIPPED by Date To ({inv_date} > {d_to})\n")
                                    continue
                        except ValueError as e:
                            if should_log: f.write(f"  -> Date Parsing Error: {e}\n")
                            pass 

                if should_log: f.write("  -> MATCHED!\n")
                filtered_data.append(inv)
            
            f.write(f"FINAL RESULT COUNT: {len(filtered_data)}\n")
            
    except Exception as e:
        app.logger.error(f"Debug log error: {e}")
        # Fallback to original logic if logging fails, but we need to ensure flow continues
        pass
    
    app.logger.info(f"SEARCH DEBUG: Result count {len(filtered_data)}")

    ai_insights = {}
    invoice_list = []

    # --- PAGINATION ---
    page = request.args.get('page', 1, type=int)
    per_page = 15
    total_invoices = len(filtered_data)
    
    start = (page - 1) * per_page
    end = start + per_page
    paginated_data = filtered_data[start:end]

    for inv in paginated_data:
        # Determine risk level based on local data
        risk_score = client_risk_map.get(int(inv.get("client_id", 0)), 0.0)
        risk_level = "High" if risk_score > 0.7 else "Medium" if risk_score > 0.3 else "Low"
        
        # High Value & Overdue Calculations
        try:
            total_amount = float(inv.get("total_amount", 0))
        except (ValueError, TypeError):
            total_amount = 0.0
            
        is_high_value = total_amount > 100000
        
        is_overdue_risk = False
        if inv.get("invoice_date") and inv.get("payment_status") != "Paid":
            try:
                inv_date = datetime.strptime(inv["invoice_date"], "%Y-%m-%d").date()
                days_diff = (datetime.now().date() - inv_date).days
                if days_diff > 60:
                    is_overdue_risk = True
            except ValueError:
                pass

        # Override risk level if overdue
        if is_overdue_risk:
            risk_level = "High"

        # Populate ai_insights for the template
        ai_insights[inv["id"]] = {
            "payment_risk": risk_level,
            "high_value": is_high_value,
            "overdue_risk": is_overdue_risk,
            "predicted_payment_date": None
        }

        invoice_obj = SimpleNamespace(
            id=inv["id"],
            invoice_number=inv["invoice_number"],
            invoice_date=datetime.strptime(
                inv["invoice_date"], "%Y-%m-%d"
            ) if inv["invoice_date"] else None,
            due_date=None,
            total_amount=inv["total_amount"],
            amount_paid=0,
            payment_status=inv["payment_status"],
            ai_insights=None, # This is used in the loop but overridden by the separate dict passed to template
            # invoice_obj doesn't have the ai_insights dict attached directly in the template loop 
            # (template uses ai_insights[invoice.id]), so this is fine.
            client=SimpleNamespace(
                name=inv.get("client_name")
            )
        )
        invoice_list.append(invoice_obj)

    invoices_obj = CustomPagination(invoice_list, page, per_page, total_invoices)

    return render_template(
        "invoice_management.html",
        invoices=invoices_obj,
        ai_enabled=True,
        ai_insights=ai_insights,
        search=search_query,
        status_filter=status_filter,
        client_filter=client_filter,
        clients=cloud_clients, # Pass cloud clients for the dropdown
        date_from=date_from,
        date_to=date_to
    )

@app.route('/create_invoice', methods=['GET', 'POST'])
@login_required
def create_invoice():

    if request.method == 'POST':
        try:
            client_id = request.form.get('client_id')
            template_id = None

            # ✅ Convert to integer safely
            if template_id:
                template_id = int(template_id)

            invoice_date_str = request.form.get('invoice_date')
            due_date_str = request.form.get('due_date')

            invoice_number = generate_invoice_number()

            # Process line items — use pre-computed amounts from JS
            line_items_data = json.loads(request.form.get('line_items', '[]'))

            total_amount = sum(
                float(item.get("total_amount", 0)) for item in line_items_data
            )

            # 🔥 SEND TO CLOUD API
            response = cloud_request(
                "POST",
                "/invoices",
                json={
                    "invoice_number": invoice_number,
                    "client_id": client_id,
                    "invoice_date": invoice_date_str,
                    "due_date": due_date_str,
                    "total_amount": total_amount,
                    "payment_status": "Unpaid",
                    "line_items": line_items_data,
                    "template_id": template_id   # ✅ Using template_id
                }
            )

            # ✅ SUCCESS BLOCK
            if response and response.status_code in (200, 201):
                print("INVOICE SUCCESS BLOCK ENTERED")

                try:
                    from email_service import send_email

                    # Fetch Company
                    company_response = cloud_request("GET", "/company")

                    if not company_response or company_response.status_code != 200:
                        flash("Invoice created but company fetch failed", "warning")
                        return redirect(url_for("invoice_management"))

                    company_data = company_response.json()
                    company_name = company_data.get("name")
                    company_email = company_data.get("email")
                    company_phone = company_data.get("phone")

                    # Fetch Clients
                    client_response = cloud_request("GET", "/clients")

                    if not client_response or client_response.status_code != 200:
                        flash("Invoice created but client fetch failed", "warning")
                        return redirect(url_for("invoice_management"))

                    clients = client_response.json()

                    # Find specific client
                    client_data = next(
                        (c for c in clients if str(c.get("id")) == str(client_id)),
                        None
                    )

                    if not client_data:
                        flash("Invoice created but client not found", "warning")
                        return redirect(url_for("invoice_management"))

                    client_name = client_data.get("name")
                    client_email = client_data.get("email")

                    if not client_email:
                        flash("Invoice created but client email not found", "warning")
                        return redirect(url_for("invoice_management"))

                    # Prepare Email
                    subject = f"Invoice {invoice_number} from {company_name}"

                    body = f"""
                    <h2>Invoice Notification</h2>
                    <p>Dear {client_name},</p>

                    <p>Your invoice has been generated. Below are the details:</p>

                    <table border="1" cellpadding="8" cellspacing="0">
                        <tr>
                            <td><b>Invoice Number</b></td>
                            <td>{invoice_number}</td>
                        </tr>
                        <tr>
                            <td><b>Date</b></td>
                            <td>{invoice_date_str}</td>
                        </tr>
                        <tr>
                            <td><b>Total Amount</b></td>
                            <td>₹ {total_amount}</td>
                        </tr>
                    </table>

                    <br>

                    <h3>Company Details</h3>
                    <p>
                        <b>{company_name}</b><br>
                        Email: {company_email}<br>
                        Phone: {company_phone}
                    </p>

                    <br>
                    <p>Regards,<br>{company_name}</p>
                    """

                    print("Sending email to:", client_email)

                    email_status = send_email(client_email, subject, body)

                    if email_status:
                        flash("Invoice created and email sent to client ✅", "success")
                    else:
                        flash("Invoice created but email failed ❌", "danger")

                except Exception as e:
                    print("Notification error:", e)
                    flash("Invoice created but email error occurred", "danger")

                return redirect(url_for("invoice_management"))

            else:
                flash("Invoice creation failed", "danger")

        except Exception as e:
            print("MAIN ERROR:", e)
            flash(f"API connection error: {str(e)}", "danger")

    # GET request
    client_list = fetch_cloud_clients()
    clients = [SimpleNamespace(**c) for c in client_list]

    return render_template(
        'create_invoice.html',
        clients=clients,
        today=datetime.now()
    )

@app.route('/invoice/preview', methods=['POST'])
@login_required
def preview_invoice():
    """Preview invoice without saving"""
    try:
        # Extract form data
        client_id = request.form.get('client_id')
        invoice_date_str = request.form.get('invoice_date')
        due_date_str = request.form.get('due_date')
        notes = request.form.get('notes', '')
        terms_conditions = request.form.get('terms_conditions', '')

        # ✅ Get template_id instead of invoice_format
        template_id = request.form.get("template_id")

        if template_id:
            template_id = int(template_id)

        print("Preview Template ID:", template_id)

        # Fetch client from cloud
        client_data = fetch_cloud_client_by_id(client_id)
        if not client_data:
            return "Client not found", 404

        client = SimpleNamespace(
            id=client_data.get('id'),
            name=client_data.get('name', 'N/A'),
            email=client_data.get('email', ''),
            phone=client_data.get('phone', ''),
            address='',
            gstin='',
            pan=''
        )

        invoice_date = datetime.strptime(
            invoice_date_str, '%Y-%m-%d'
        ).date() if invoice_date_str else datetime.now().date()

        # Parse line items
        line_items_data = json.loads(request.form.get('line_items', '[]'))

        line_items = []
        subtotal = 0
        total_cgst = 0
        total_sgst = 0
        total_igst = 0

        for i, item_data in enumerate(line_items_data, 1):
            quantity = float(item_data.get('quantity', 0))
            unit_price = float(item_data.get('unit_price', 0))

            cgst_percentage = float(item_data.get('cgst_percentage', 0.0))
            sgst_percentage = float(item_data.get('sgst_percentage', 0.0))

            line_total = quantity * unit_price

            cgst_amount = (line_total * cgst_percentage) / 100
            sgst_amount = (line_total * sgst_percentage) / 100
            igst_amount = cgst_amount + sgst_amount

            item_total = line_total + cgst_amount + sgst_amount

            li = SimpleNamespace(
                sr_no=i,
                hsn_code=item_data.get('hsn_code', ''),
                description=item_data.get('description', ''),
                quantity=quantity,
                unit=item_data.get('unit', 'Nos'),
                unit_price=unit_price,
                cgst_percentage=cgst_percentage,
                sgst_percentage=sgst_percentage,
                igst_percentage=cgst_percentage + sgst_percentage,
                cgst_amount=cgst_amount,
                sgst_amount=sgst_amount,
                igst_amount=igst_amount,
                total_amount=item_total
            )

            line_items.append(li)

            subtotal += line_total
            total_cgst += cgst_amount
            total_sgst += sgst_amount
            total_igst += igst_amount

        grand_total = subtotal + total_cgst + total_sgst

        invoice = SimpleNamespace(
            invoice_number="PREVIEW",
            invoice_date=invoice_date,
            due_date=None,
            client=client,
            notes=notes,
            terms_conditions=terms_conditions,
            subtotal=subtotal,
            cgst=total_cgst,
            sgst=total_sgst,
            igst=total_igst,
            total_amount=grand_total,
            line_items=line_items,
            payment_status='Unpaid'
        )

        # Fetch company
        company_res = cloud_request("GET", "/company")
        if company_res and company_res.status_code == 200:
            company = SimpleNamespace(**company_res.json())
        else:
            company = Company.query.first()
            
        bank_res = cloud_request("GET", "/bank-details")
        bank = SimpleNamespace(**bank_res.json()) if bank_res and bank_res.status_code == 200 else None

        print("TEMPLATE DEBUG:", template_id)
        
        # Add template_id to invoice namespace just in case the template needs it
        invoice.template_id = template_id

        template_map = {
            5: "invoice_detail.html",              
            6: "invoice_excel_customer_A.html"     
        }

        template_name = template_map.get(template_id, "invoice_detail.html")


        return render_template(
            template_name,
            invoice=invoice,
            company=company,
            bank=bank,
            blockchain_verification={},
            ai_insights={},
            is_preview=True
        )

    except Exception as e:
        logging.error(f"Preview failed: {e}")
        return f"Error creating preview: {str(e)}", 500
    
@app.route('/invoice/<int:id>')
@login_required
def invoice_detail(id):

    invoice_data = fetch_cloud_invoice_by_id(id)

    # 🔍 DEBUG TEMPLATE
    print("===== TEMPLATE DEBUG =====")
    print("Invoice ID:", id)
    print("template_id from cloud:", invoice_data.get("template_id") if invoice_data else None)
    print("==========================")

    if not invoice_data:
        flash('Invoice not found', 'error')
        return redirect(url_for('invoice_management'))

    client_data = fetch_cloud_client_by_id(invoice_data.get('client_id'))

    if not client_data:
        flash('Client not found', 'error')
        return redirect(url_for('invoice_management'))

    # 🔥 FETCH LINE ITEMS
    line_items_data = invoice_data.get("line_items", [])

    line_items = []
    subtotal = 0
    total_cgst = 0
    total_sgst = 0
    total_igst = 0

    for i, item in enumerate(line_items_data, 1):

        quantity = float(item.get("quantity", 0))
        unit_price = float(item.get("unit_price", 0))
        tax_amount = float(item.get("tax_amount", 0))
        total_amount = float(item.get("total_amount", 0))

        line_total = quantity * unit_price

        # If IGST exists
        if item.get("igst_percentage"):
            igst_amount = tax_amount
            cgst_amount = 0
            sgst_amount = 0
        else:
            cgst_amount = tax_amount / 2
            sgst_amount = tax_amount / 2
            igst_amount = 0

        subtotal += line_total
        total_cgst += cgst_amount
        total_sgst += sgst_amount
        total_igst += igst_amount

        line_items.append(SimpleNamespace(
            sr_no=i,
            hsn_code=item.get("hsn_code", ""),
            description=item.get("description"),
            quantity=quantity,
            unit=item.get("unit", "Nos"),
            unit_price=unit_price,
            tax_percentage=item.get("tax_percentage", 18),
            cgst_amount=cgst_amount,
            sgst_amount=sgst_amount,
            igst_amount=igst_amount,
            total_amount=total_amount
        ))

  
    company = Company.query.first()
    bank = BankDetails.query.first()
    template_id = invoice_data.get("template_id")
    print("TEMPLATE FROM CLOUD:", template_id)
    invoice = SimpleNamespace(
        id=invoice_data.get('id'),
        invoice_number=invoice_data.get('invoice_number'),
        invoice_date=datetime.strptime(invoice_data.get('invoice_date'), '%Y-%m-%d'),
        total_amount=subtotal + total_cgst + total_sgst,
        payment_status=invoice_data.get('payment_status'),
        line_items=line_items,
        subtotal=subtotal,
        cgst=total_cgst,
        sgst=total_sgst,
        igst=total_igst,
        template_id=template_id 
       
    )

    invoice.client = SimpleNamespace(
        name=client_data.get('name'),
        email=client_data.get('email'),
        phone=client_data.get('phone'),
        address=''
    )

    # Fetch company
    company_res = cloud_request("GET", "/company")
    if company_res and company_res.status_code == 200:
        company = SimpleNamespace(**company_res.json())
    else:
        company = Company.query.first()
        
    bank_res = cloud_request("GET", "/bank-details")
    bank = SimpleNamespace(**bank_res.json()) if bank_res and bank_res.status_code == 200 else None     

    # SELECT TEMPLATE BASED ON SAVED FORMAT
    invoice_format = invoice_data.get("invoice_format", "default")
    template_map = {
        1: "invoice_detail.html",
        2: "invoice_excel_customer_A.html"
    }

    template_name = template_map.get(template_id, "invoice_detail.html")

    print("Rendering Template:", template_name)

    return render_template(
        template_name,
        invoice=invoice,
        company=company,
        bank=bank,
        blockchain_verification={},
        ai_insights={}
    )

@app.route('/invoice/<int:id>/download-pdf')
@login_required
def download_invoice_pdf(id):
    """Stream the invoice PDF directly to the browser as a file download."""
    try:
        # Fetch full invoice detail (with line_items) from cloud API
        invoice_data = fetch_cloud_invoice_by_id(id)
        if not invoice_data:
            return jsonify({'success': False, 'error': 'Invoice not found'}), 404

        # Fetch client data
        client_data = fetch_cloud_client_by_id(invoice_data.get('client_id'))
        if not client_data:
            return jsonify({'success': False, 'error': 'Client not found'}), 404

        # Build line_items with per-row cgst/sgst/igst amounts for the template
        raw_items = invoice_data.get('line_items', [])
        line_items = []
        subtotal = 0
        total_cgst = 0
        total_sgst = 0
        total_igst = 0
        for i, item in enumerate(raw_items):
            qty = item.get('quantity', 0)
            price = item.get('unit_price', 0)
            line_total = qty * price
            tax_amt = item.get('tax_amount', 0)  # total tax stored = cgst + sgst
            cgst_amt = round(tax_amt / 2, 2)
            sgst_amt = round(tax_amt / 2, 2)
            igst_amt = cgst_amt + sgst_amt
            item_total = line_total + cgst_amt + sgst_amt
            subtotal += line_total
            total_cgst += cgst_amt
            total_sgst += sgst_amt
            total_igst += igst_amt
            line_items.append(SimpleNamespace(
                sr_no=item.get('sr_no', i + 1),
                hsn_code=item.get('hsn_code', ''),
                description=item.get('description', ''),
                quantity=qty,
                unit=item.get('unit', 'Nos'),
                unit_price=price,
                tax_percentage=item.get('tax_percentage', 18), # Used by PDF generator
                cgst_amount=cgst_amt,
                sgst_amount=sgst_amt,
                igst_amount=igst_amt,
                total_amount=item_total,
                cost_price=item.get('cost_price', 0)
            ))

        invoice = SimpleNamespace(
            id=invoice_data.get('id'),
            invoice_number=invoice_data.get('invoice_number', 'N/A'),
            invoice_date=datetime.strptime(invoice_data.get('invoice_date'), '%Y-%m-%d').date() if invoice_data.get('invoice_date') else datetime.now().date(),
            due_date=None,
            total_amount=subtotal + total_cgst + total_sgst,   # grand total = sub + CGST + SGST
            payment_status=invoice_data.get('payment_status', 'Unpaid'),
            notes=invoice_data.get('notes', ''),
            terms_conditions=invoice_data.get('terms_conditions', ''),
            line_items=line_items,
            subtotal=subtotal,
            cgst=total_cgst,
            sgst=total_sgst,
            igst=total_igst,   # = CGST + SGST
            invoice_type='Invoice',
            blockchain_hash=None
        )

        invoice.client = SimpleNamespace(
            name=client_data.get('name', 'N/A'),
            email=client_data.get('email', ''),
            phone=client_data.get('phone', ''),
            address=client_data.get('address', ''),
            city=client_data.get('city', ''),
            state=client_data.get('state', ''),
            pincode=client_data.get('pincode', ''),
            gstin=client_data.get('gstin', ''),
            pan=client_data.get('pan', ''),
            contact_person=client_data.get('contact_person', '')
        )

        logging.info(f"Generating PDF for invoice {id}: {invoice_data.get('invoice_number')} with {len(line_items)} items")

        # Fetch company from cloud API
        company_res = cloud_request("GET", "/company")
        company = SimpleNamespace(**company_res.json()) if company_res and company_res.status_code == 200 else None
        # Fetch bank details from cloud API
        bank_res = cloud_request("GET", "/bank-details")
        bank = SimpleNamespace(**bank_res.json()) if bank_res and bank_res.status_code == 200 else None
        # 🔥 Fetch logo from cloud
        logo_res = cloud_request("GET", "/company/logo")
        logo_bytes = logo_res.content if logo_res and logo_res.status_code == 200 else None

        # 🔥 Fetch signature from cloud
        signature_res = cloud_request("GET", "/company/signature")
        signature_bytes = signature_res.content if signature_res and signature_res.status_code == 200 else None

        print("Logo bytes:", len(logo_bytes) if logo_bytes else "None")
        print("Signature bytes:", len(signature_bytes) if signature_bytes else "None")

        # Generate 3-copy PDF: 1 Original + 2 Duplicate (watermarked)
        pdf_buffer = generate_triple_invoice_pdf(
            invoice,
            company=company,
            bank=bank,
            logo_bytes=logo_bytes,
            signature_bytes=signature_bytes
        )
        pdf_buffer.seek(0)

        # The JS passes ?t=<timestamp> so each download gets a unique filename –
        # Chrome will never overwrite a previous download of the same invoice.
        ts = request.args.get('t', datetime.now().strftime('%Y%m%d%H%M%S'))
        invoice_number = invoice_data.get('invoice_number', str(id))
        filename = f'Invoice_{invoice_number}_{ts}_3copies.pdf'

        logging.info(f"Streaming PDF to browser as: {filename}")
        from urllib.parse import quote
        encoded_filename = quote(filename)
        return Response(
            pdf_buffer.getvalue(),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded_filename}',
                'Content-Type': 'application/pdf',
            }
        )

    except Exception as e:
        logging.error(f"PDF download failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'Failed to generate PDF: {str(e)}'}), 500


@app.route('/invoice/<int:id>/save-pdf', methods=['POST'])
@login_required
def save_invoice_pdf_to_disk(id):
    """Save invoice PDF directly to the OS Downloads folder.

    Called by the PyWebView desktop app via fetch() — no browser navigation
    needed so the session cookie is valid and there is no login redirect.
    Returns JSON {success, filename, path}.
    """
    try:
        invoice_data = fetch_cloud_invoice_by_id(id)
        if not invoice_data:
            return jsonify({'success': False, 'error': 'Invoice not found'}), 404

        client_data = fetch_cloud_client_by_id(invoice_data.get('client_id'))
        if not client_data:
            return jsonify({'success': False, 'error': 'Client not found'}), 404

        raw_items = invoice_data.get('line_items', [])
        line_items = []
        subtotal = total_cgst = total_sgst = total_igst = 0
        for i, item in enumerate(raw_items):
            qty   = item.get('quantity', 0)
            price = item.get('unit_price', 0)
            line_total = qty * price
            tax_amt  = item.get('tax_amount', 0)
            cgst_amt = round(tax_amt / 2, 2)
            sgst_amt = round(tax_amt / 2, 2)
            igst_amt = cgst_amt + sgst_amt
            subtotal    += line_total
            total_cgst  += cgst_amt
            total_sgst  += sgst_amt
            total_igst  += igst_amt
            line_items.append(SimpleNamespace(
                sr_no=item.get('sr_no', i + 1),
                hsn_code=item.get('hsn_code', ''),
                description=item.get('description', ''),
                quantity=qty,
                unit=item.get('unit', 'Nos'),
                unit_price=price,
                tax_percentage=item.get('tax_percentage', 18),
                cgst_amount=cgst_amt,
                sgst_amount=sgst_amt,
                igst_amount=igst_amt,
                total_amount=line_total + cgst_amt + sgst_amt,
                cost_price=item.get('cost_price', 0)
            ))

        invoice = SimpleNamespace(
            id=invoice_data.get('id'),
            invoice_number=invoice_data.get('invoice_number', 'N/A'),
            invoice_date=datetime.strptime(invoice_data.get('invoice_date'), '%Y-%m-%d').date()
                         if invoice_data.get('invoice_date') else datetime.now().date(),
            due_date=None,
            total_amount=subtotal + total_cgst + total_sgst,
            payment_status=invoice_data.get('payment_status', 'Unpaid'),
            notes=invoice_data.get('notes', ''),
            terms_conditions=invoice_data.get('terms_conditions', ''),
            line_items=line_items,
            subtotal=subtotal,
            cgst=total_cgst,
            sgst=total_sgst,
            igst=total_igst,
            invoice_type='Invoice',
            blockchain_hash=None
        )
        invoice.client = SimpleNamespace(
            name=client_data.get('name', 'N/A'),
            email=client_data.get('email', ''),
            phone=client_data.get('phone', ''),
            address=client_data.get('address', ''),
            city=client_data.get('city', ''),
            state=client_data.get('state', ''),
            pincode=client_data.get('pincode', ''),
            gstin=client_data.get('gstin', ''),
            pan=client_data.get('pan', ''),
            contact_person=client_data.get('contact_person', '')
        )

        company_res = cloud_request("GET", "/company")
        company = SimpleNamespace(**company_res.json()) if company_res and company_res.status_code == 200 else None

        # Fetch bank details
        bank_res = cloud_request("GET", "/bank-details")
        bank = SimpleNamespace(**bank_res.json()) if bank_res and bank_res.status_code == 200 else None

        # Fetch logo
        logo_res = cloud_request("GET", "/company/logo")
        logo_bytes = logo_res.content if logo_res and logo_res.status_code == 200 else None

        # Fetch signature
        signature_res = cloud_request("GET", "/company/signature")
        signature_bytes = signature_res.content if signature_res and signature_res.status_code == 200 else None

        # Generate 3-copy PDF: 1 Original + 2 Duplicate (watermarked)
        pdf_buffer = generate_triple_invoice_pdf(
            invoice,
            company=company,
            bank=bank,
            logo_bytes=logo_bytes,
            signature_bytes=signature_bytes
        )
        pdf_buffer.seek(0)

        ts = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f'Invoice_{invoice_data.get("invoice_number", id)}_{ts}_3copies.pdf'
        saved_path = save_pdf_to_downloads(pdf_buffer, filename)

        if saved_path:
            logging.info(f"PDF saved to Downloads: {saved_path}")
            return jsonify({'success': True, 'filename': filename, 'path': saved_path})
        else:
            return jsonify({'success': False, 'error': 'Could not save PDF to Downloads folder'}), 500

    except Exception as e:
        logging.error(f"save-pdf failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500




@app.route('/invoice/<int:id>/send', methods=['POST'])
@login_required
def send_invoice_to_client(id):
    """Generate invoice PDF and email it to the client (Multi-Tenant Secure)."""
    try:
        from email_service import send_email
        from types import SimpleNamespace
        

        # ─────────────────────────────────────────────
        # 1️⃣ Fetch Invoice
        # ─────────────────────────────────────────────
        invoice_data = fetch_cloud_invoice_by_id(id)

        if not invoice_data:
            return jsonify({'success': False, 'message': 'Invoice not found'}), 404

        # ─────────────────────────────────────────────
        # 2️⃣ Fetch Client
        # ─────────────────────────────────────────────
        client_data = fetch_cloud_client_by_id(invoice_data.get('client_id'))

        if not client_data:
            return jsonify({'success': False, 'message': 'Client not found'}), 404

        client_email = client_data.get('email')
        client_name  = client_data.get('name', 'Client')

        if not client_email:
            return jsonify({'success': False, 'message': 'Client email not found'}), 400

        # ─────────────────────────────────────────────
        # 3️⃣ Fetch Logged-In User (Sender)
        # ─────────────────────────────────────────────
        user_res = cloud_request("GET", "/user/profile")

        if not user_res or user_res.status_code != 200:
            return jsonify({'success': False, 'message': 'Unable to fetch user profile'}), 500

        user_data = user_res.json()

        sender_email = user_data.get("email")
        encrypted_password = user_data.get("email_app_password")

        if not sender_email or not encrypted_password:
            return jsonify({
                'success': False,
                'message': 'Email not configured. Please set your App Password in Settings.'
            }), 400

        sender_password = encrypted_password

        # ─────────────────────────────────────────────
        # 4️⃣ Build Invoice Object
        # ─────────────────────────────────────────────
        raw_items  = invoice_data.get('line_items', [])
        line_items = []
        subtotal = total_cgst = total_sgst = total_igst = 0

        for i, item in enumerate(raw_items):
            qty        = item.get('quantity', 0)
            price      = item.get('unit_price', 0)
            line_total = qty * price
            tax_amt    = item.get('tax_amount', 0)

            cgst_amt = round(tax_amt / 2, 2)
            sgst_amt = round(tax_amt / 2, 2)
            igst_amt = cgst_amt + sgst_amt

            subtotal   += line_total
            total_cgst += cgst_amt
            total_sgst += sgst_amt
            total_igst += igst_amt

            line_items.append(SimpleNamespace(
                sr_no=i + 1,
                hsn_code=item.get('hsn_code', ''),
                description=item.get('description', ''),
                quantity=qty,
                unit=item.get('unit', 'Nos'),
                unit_price=price,
                tax_percentage=item.get('tax_percentage', 0),
                total_amount=line_total + cgst_amt + sgst_amt
            ))

        invoice_number = invoice_data.get('invoice_number', str(id))

        invoice = SimpleNamespace(
            id=invoice_data.get('id'),
            invoice_number=invoice_number,
            invoice_date=datetime.strptime(
                invoice_data.get('invoice_date'), '%Y-%m-%d'
            ).date() if invoice_data.get('invoice_date') else datetime.now().date(),
            due_date=None,
            total_amount=subtotal + total_cgst + total_sgst,
            payment_status=invoice_data.get('payment_status', 'Unpaid'),
            notes=invoice_data.get('notes', ''),
            terms_conditions=invoice_data.get('terms_conditions', ''),
            line_items=line_items,
            subtotal=subtotal,
            cgst=total_cgst,
            sgst=total_sgst,
            igst=total_igst
        )

        # ✅ FULL CLIENT DETAILS (IMPORTANT FIX)
        invoice.client = SimpleNamespace(
            name=client_data.get('name') or "",
            address=client_data.get('address') or "",
            city=client_data.get('city') or "",
            state=client_data.get('state') or "",
            pincode=client_data.get('pincode') or "",
            gstin=client_data.get('gstin') or "",
            phone=client_data.get('phone') or "",
            email=client_data.get('email') or ""
        )

        # ─────────────────────────────────────────────
        # 5️⃣ Fetch Company + Bank + Logo + Signature
        # ─────────────────────────────────────────────
        company_res = cloud_request("GET", "/company")
        bank_res    = cloud_request("GET", "/bank-details")

        company = SimpleNamespace(**company_res.json()) if company_res and company_res.status_code == 200 else None
        bank    = SimpleNamespace(**bank_res.json()) if bank_res and bank_res.status_code == 200 else None

        # Fetch logo
        logo_bytes = None
        logo_res = cloud_request("GET", "/company/logo")
        if logo_res and logo_res.status_code == 200:
            logo_bytes = logo_res.content

        # Fetch signature
        signature_bytes = None
        sign_res = cloud_request("GET", "/company/signature")
        if sign_res and sign_res.status_code == 200:
            signature_bytes = sign_res.content

        # ─────────────────────────────────────────────
        # 6️⃣ Generate PDF
        # ─────────────────────────────────────────────
        pdf_buffer = generate_invoice_pdf(
            invoice,
            company=company,
            bank=bank,
            logo_bytes=logo_bytes,
            signature_bytes=signature_bytes
        )

        pdf_buffer.seek(0)
        pdf_bytes = pdf_buffer.read()
        pdf_filename = f'Invoice_{invoice_number}.pdf'

        # ─────────────────────────────────────────────
        # 7️⃣ Build Email
        # ─────────────────────────────────────────────
        subject = f"Invoice {invoice_number} from {company.name if company else ''}"

        body = f"""
        <h2>Invoice from {company.name if company else ''}</h2>
        <p>Dear {client_name},</p>
        <p>Please find your invoice attached.</p>
        <p><b>Total Amount:</b> ₹ {invoice.total_amount:,.2f}</p>
        <br>
        <p>Regards,<br>{company.name if company else ''}</p>
        """

        # ─────────────────────────────────────────────
        # 8️⃣ Send Email
        # ─────────────────────────────────────────────
        success = send_email(
            sender_email=sender_email,
            sender_password=sender_password,
            to_email=client_email,
            subject=subject,
            body=body,
            attachment_bytes=pdf_bytes,
            attachment_filename=pdf_filename
        )

        if success:
            return jsonify({'success': True, 'message': f'Invoice sent to {client_email} ✅'})
        else:
            return jsonify({'success': False, 'message': 'Email sending failed.'}), 500

    except Exception as e:
        logging.error(f"send_invoice_to_client error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@app.route('/invoice/<int:id>/pdf')
@login_required
def invoice_pdf(id):
    """Generate PDF for invoice - works with both web and desktop (PyWebView)"""
    try:
        invoice = Invoice.query.get_or_404(id)
        logging.info(f"Generating PDF for invoice {id}: {invoice.invoice_number}")
        
        # Fetch company from cloud API
        company_res = cloud_request("GET", "/company")
        company = SimpleNamespace(**company_res.json()) if company_res and company_res.status_code == 200 else None

        pdf_buffer = generate_invoice_pdf(invoice, company=company)
        pdf_buffer.seek(0)
        
        buffer_size = len(pdf_buffer.getvalue())
        logging.info(f"PDF buffer size: {buffer_size} bytes")
        
        filename = f'Invoice_{invoice.invoice_number}.pdf'
        
        # 🔥 Save to local Downloads for Desktop EXE support
        saved_path = save_pdf_to_downloads(pdf_buffer, filename)
        if saved_path:
            flash(f"PDF saved to: {saved_path}", "success")
        
        from urllib.parse import quote
        encoded_filename = quote(filename)
        response = Response(
            pdf_buffer.getvalue(),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded_filename}',
                'Content-Type': 'application/pdf',
                'Content-Length': buffer_size
            }
        )
        
        logging.info(f"PDF response headers: {dict(response.headers)}")
        return response
        
    except Exception as e:
        logging.error(f"PDF generation failed: {e}", exc_info=True)
        return jsonify({'error': f'PDF generation failed: {str(e)}'}), 500
    
@app.route('/invoice/<int:id>/delete', methods=['POST'])
@login_required
def delete_invoice(id):
    """Delete invoice from cloud database"""
    try:
        response = cloud_request("DELETE", f"/invoices/{id}")

        if response.status_code in (200, 204):
            flash('Invoice deleted successfully.', 'success')
        else:
            flash(f'Failed to delete invoice: {response.text}', 'error')
    except Exception as e:
        logging.error(f"Cloud API delete error: {e}")
        flash(f'API connection error: {str(e)}', 'error')
    
    return redirect(url_for('invoice_management'))

@app.route('/invoices/bulk_delete', methods=['POST'])
@login_required
def bulk_delete_invoices():
    data = request.get_json()
    ids = data.get('invoice_ids', [])
    if ids:
        Invoice.query.filter(Invoice.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
    return jsonify({'success': True})

@app.route('/invoices/<int:id>', methods=['DELETE'])
@login_required
def delete_invoice1(id):
    """Delete invoice from cloud database (REST endpoint)"""
    try:
        response = cloud_request("DELETE", f"/invoices/{id}")
        if response and response.status_code in (200, 204):
            return jsonify({'success': True})
        else:
            return jsonify({
                'success': False,
                'error': f'Cloud API error: {response.text if response else "No response"}'
            }), (response.status_code if response else 500)
    except Exception as e:
        logging.error(f"Delete error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500





@app.route('/invoice/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_invoice(id):

    # =========================
    # 🔥 POST (UPDATE)
    # =========================
    if request.method == 'POST':

        action = request.form.get('action', 'update')
        update_data = {}
        send_payment_email = False

        if action == 'mark_paid':
            update_data['payment_status'] = 'Paid'
            flash_msg = 'Invoice marked as Paid!'
            send_payment_email = True

        elif action == 'mark_unpaid':
            update_data['payment_status'] = 'Unpaid'
            flash_msg = 'Invoice marked as Unpaid!'

        else:
            update_data['notes'] = request.form.get('notes', '')
            update_data['terms_conditions'] = request.form.get('terms_conditions', '')
            update_data['due_date'] = request.form.get('due_date')  # 🔥 ADD THIS

            line_items_data = json.loads(request.form.get('line_items', '[]'))

            total_amount = sum(
                float(item.get("total_amount", 0))
                for item in line_items_data
            )

            update_data['total_amount'] = total_amount
            update_data['line_items'] = line_items_data

            flash_msg = 'Invoice updated successfully!'

        try:
            response = cloud_request(
                "PUT",
                f"/invoices/{id}",
                json=update_data
            )

            if response and response.status_code in (200, 204):
                flash(flash_msg, 'success')
            else:
                flash(f'Failed to update invoice: {response.text}', 'error')

        except Exception as e:
            flash(f'API error: {str(e)}', 'error')

        return redirect(url_for('invoice_management'))

    # =========================
    # 🔥 GET (LOAD EDIT PAGE)
    # =========================

    invoice_data = fetch_cloud_invoice_by_id(id)

    if not invoice_data:
        flash('Invoice not found', 'error')
        return redirect(url_for('invoice_management'))

    client_data = fetch_cloud_client_by_id(invoice_data.get('client_id'))

    client = SimpleNamespace(
        id=client_data.get('id'),
        name=client_data.get('name', 'N/A'),
        email=client_data.get('email', ''),
        phone=client_data.get('phone', '')
    )

    raw_items = invoice_data.get("line_items", [])
    line_items = []

    for item in raw_items:
        line_items.append(SimpleNamespace(
            hsn_code=item.get("hsn_code", ""),
            description=item.get("description", ""),
            quantity=item.get("quantity", 0),
            unit=item.get("unit", "Nos"),
            unit_price=item.get("unit_price", 0),
            cgst_percentage=item.get("cgst_percentage", 0),
            sgst_percentage=item.get("sgst_percentage", 0),
            igst_percentage=item.get("igst_percentage", 0),
            total_amount=item.get("total_amount", 0)
        ))

    invoice = SimpleNamespace(
        id=invoice_data.get('id'),
        invoice_number=invoice_data.get('invoice_number'),
        invoice_date=invoice_data.get('invoice_date'),
        due_date=invoice_data.get('due_date'),   # 🔥 CRITICAL FIX
        client_id=invoice_data.get('client_id'),
        client=client,
        total_amount=invoice_data.get('total_amount', 0),
        payment_status=invoice_data.get('payment_status', 'Unpaid'),
        notes=invoice_data.get('notes', ''),
        terms_conditions=invoice_data.get('terms_conditions', ''),
        line_items=line_items
    )

    client_list = fetch_cloud_clients()
    clients = [SimpleNamespace(**c) for c in client_list]

    return render_template(
        'edit_invoice.html',
        invoice=invoice,
        clients=clients
    )




@app.route('/invoice/<int:id>/duplicate', methods=['POST'])
@login_required
def duplicate_invoice(id):
    """Duplicate an invoice by fetching it from the cloud API and re-creating it."""
    try:
        # 1. Fetch the original invoice from cloud
        invoice_data = fetch_cloud_invoice_by_id(id)
        if not invoice_data:
            return jsonify({'message': 'Original invoice not found in cloud'}), 404

        # 2. Build the new invoice payload
        #    - New invoice number = original + "-COPY"
        #    - Reset payment status to Unpaid
        #    - Use today's date
        #    - Strip 'id' from each line item so the cloud creates new records
        original_number = invoice_data.get('invoice_number', str(id))
        new_number = f"{original_number}-COPY"

        raw_line_items = invoice_data.get('line_items', [])
        new_line_items = []
        for item in raw_line_items:
            new_item = {k: v for k, v in item.items() if k != 'id'}
            new_line_items.append(new_item)

        payload = {
            'invoice_number':    new_number,
            'client_id':         invoice_data.get('client_id'),
            'invoice_date':      datetime.now().strftime('%Y-%m-%d'),
            'total_amount':      invoice_data.get('total_amount', 0),
            'payment_status':    'Unpaid',
            'notes':             invoice_data.get('notes', ''),
            'terms_conditions':  invoice_data.get('terms_conditions', ''),
            'line_items':        new_line_items,
        }

        # 3. POST new invoice to cloud API
        response = cloud_request('POST', '/invoices', json=payload)

        if response and response.status_code in (200, 201):
            logging.info(f"Invoice {id} duplicated as {new_number} on cloud")
            return jsonify({'message': f'Invoice duplicated successfully as {new_number}!'}), 200
        else:
            err = response.text if response else 'No response from cloud'
            logging.error(f"Cloud duplicate failed: {err}")
            return jsonify({'message': f'Failed to duplicate invoice on cloud: {err}'}), 400

    except Exception as e:
        logging.error(f"duplicate_invoice error: {e}", exc_info=True)
        return jsonify({'message': f'Failed to duplicate invoice: {str(e)}'}), 400


@app.route('/invoice/<int:id>/send', methods=['POST'])
@login_required
def send_invoice(id):
    """Send invoice via email to client (fetch from cloud)"""
    try:
        invoice_data = fetch_cloud_invoice_by_id(id)
        if not invoice_data:
            return jsonify({"success": False, "message": "❌ Invoice not found."}), 404

        client_data = fetch_cloud_client_by_id(invoice_data.get('client_id'))
        if not client_data:
            return jsonify({"success": False, "message": "❌ Client not found."}), 404

        recipient_email = client_data.get('email')
        if not recipient_email:
            return jsonify({"success": False, "message": "❌ Client has no email address set."}), 400

        # Build line_items from cloud data
        raw_items = invoice_data.get('line_items', [])
        line_items = [
            SimpleNamespace(
                sr_no=item.get('sr_no', i + 1),
                hsn_code=item.get('hsn_code', ''),
                description=item.get('description', ''),
                quantity=item.get('quantity', 0),
                unit=item.get('unit', 'Nos'),
                unit_price=item.get('unit_price', 0),
                tax_percentage=item.get('tax_percentage', 0),
                tax_amount=item.get('tax_amount', 0),
                total_amount=item.get('total_amount', 0),
                cost_price=item.get('cost_price', 0)
            )
            for i, item in enumerate(raw_items)
        ]

        subtotal = sum(item.get('unit_price', 0) * item.get('quantity', 0) for item in raw_items)
        total_tax = sum(item.get('tax_amount', 0) for item in raw_items)

        invoice = SimpleNamespace(
            id=invoice_data.get('id'),
            invoice_number=invoice_data.get('invoice_number', 'N/A'),
            invoice_date=datetime.strptime(invoice_data.get('invoice_date'), '%Y-%m-%d').date() if invoice_data.get('invoice_date') else datetime.now().date(),
            due_date=None,
            total_amount=invoice_data.get('total_amount', 0),
            payment_status=invoice_data.get('payment_status', 'Unpaid'),
            notes=invoice_data.get('notes', ''),
            terms_conditions=invoice_data.get('terms_conditions', ''),
            line_items=line_items,
            subtotal=subtotal,
            cgst=round(total_tax / 2, 2),
            sgst=round(total_tax / 2, 2),
            igst=0,
            invoice_type='Invoice',
            blockchain_hash=None
        )

        invoice.client = SimpleNamespace(
            name=client_data.get('name', 'N/A'),
            email=client_data.get('email', ''),
            phone=client_data.get('phone', ''),
            address=client_data.get('address', ''),
            city=client_data.get('city', ''),
            state='',
            pincode='',
            gstin='',
            pan='',
            contact_person=''
        )

        send_invoice_email(invoice, recipient_email)
        logging.info(f"Invoice {invoice_data.get('invoice_number')} sent to {recipient_email}")

        return jsonify({"success": True, "message": f"✅ Invoice sent successfully to {recipient_email}!"})

    except Exception as e:
        logging.error(f"Failed to send invoice: {e}", exc_info=True)
        return jsonify({"success": False, "message": f"❌ Failed to send invoice: {str(e)}"}), 500





@app.route('/bulk_export', methods=['POST'])
@login_required
def bulk_export():
    data = request.get_json()
    invoice_ids = data.get('ids', [])
    invoices = Invoice.query.filter(Invoice.id.in_(invoice_ids)).all()

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Invoice Number', 'Client', 'Total Amount'])  # header
    for inv in invoices:
        writer.writerow([inv.invoice_number, inv.client.name, inv.total_amount])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-Disposition": "attachment;filename=invoices.csv"}
    )


@app.route('/clients')
@login_required
def client_management():
    search = request.args.get('search', '').lower()
    client_type = request.args.get('type', '')
    lead_stage = request.args.get('lead_stage', '')
    risk_level_filter = request.args.get('risk_level', '')
    
    # Handle View Mode Persistence
    if 'view' in request.args:
        view_mode = request.args.get('view')
        session['client_view_mode'] = view_mode
    else:
        view_mode = session.get('client_view_mode', 'grid')
    
    client_list = []
    client_insights = {}
    today = datetime.utcnow().date()

    # --- 1. Fetch Cloud Data Only ---
    try:
        # Fetch Clients
        cloud_clients = fetch_cloud_clients()
        
        # Fetch Invoices for metrics
        cloud_invoices = fetch_cloud_invoices()
            
    except Exception as e:
        print(f"Cloud fetch error: {e}")
        flash("Could not fetch cloud data.", "error")
        cloud_clients = []
        cloud_invoices = []

    # --- HYBRID MERGE ---
    # Fetch all local clients to enrich cloud data
    local_clients_map = {}
    local_clients_name_map = {} # Fallback
    try:
        all_local = Client.query.all()
        for lc in all_local:
            if lc.email:
                local_clients_map[lc.email.lower()] = lc
            if lc.name:
                local_clients_name_map[lc.name.lower()] = lc
    except Exception as e:
        print(f"Local fetch error: {e}")
    for c in cloud_clients:
        # Create a unified object
        # Metric Calculation
        c_invoices = [inv for inv in cloud_invoices if inv.get('client_id') == c['id']]
        total_business = sum(float(inv.get('total_amount', 0)) for inv in c_invoices)
        
        # Risk Logic
        is_high_risk = False
        for inv in c_invoices:
            if inv.get('payment_status') != 'Paid':
                inv_date_str = inv.get('invoice_date')
                if inv_date_str:
                    try:
                        inv_date = datetime.strptime(inv_date_str, '%Y-%m-%d').date()
                        if (today - inv_date).days > 60:
                            is_high_risk = True
                            break
                    except:
                        pass
        
        risk_level = "High" if is_high_risk else "Low"
        is_high_value = total_business > 100000

        # Override from Local DB if exists
        c_email = c.get('email', '').lower() if c.get('email') else None
        c_name = c.get('name', '').lower() if c.get('name') else None
        
        loc = None
        if c_email and c_email in local_clients_map:
            loc = local_clients_map[c_email]
        elif c_name and c_name in local_clients_name_map:
             loc = local_clients_name_map[c_name]
        
        c_type = c.get('client_type') or 'Regular'
        c_gstin = 'N/A'
        c_pan = 'N/A'
        c_contact = c.get('name')
        
        if loc:
            c_type = loc.client_type or c_type
            c_gstin = loc.gstin or 'N/A'
            c_pan = loc.pan or 'N/A'
            c_contact = loc.contact_person or c.get('name')
        c_lead_stage = c.get('lead_stage')

        if loc and loc.lead_stage:
            c_lead_stage = loc.lead_stage

        # Use simple ID (integer) as we are only using cloud now
        client_obj = SimpleNamespace(
            id=c['id'],
            real_id=c['id'],
            source='cloud',
            name=c.get('name'),
            email=c.get('email'),
            phone=c.get('phone'),
            contact_person=c_contact, # Enhanced
            client_type=c_type, # Enhanced
            lead_stage=c_lead_stage or 'New',
            total_business=total_business,
            gstin=c_gstin, # Enhanced
            pan=c_pan, # Enhanced
            risk_level=risk_level,
            high_value=is_high_value,
            created_at=datetime.utcnow() # Mock
        )
        
        client_insights[client_obj.id] = {
            'risk_level': risk_level,
            'predicted_ltv': total_business,
            'high_value': is_high_value
        }
        
        client_list.append(client_obj)

    # --- 2. Filtering ---
    filtered_list = []
    
    for c in client_list:
        # Search
        if search:
            s = search
            if not (s in (c.name or '').lower() or 
                    s in (c.email or '').lower() or 
                    s in (c.phone or '').lower()):
                continue
                
        # Type
        if client_type and c.client_type != client_type:
            continue
            
        # Lead Stage
        if lead_stage and c.lead_stage != lead_stage:
            continue
            
        # Risk Level
        if risk_level_filter:
            c_risk = client_insights[c.id]['risk_level']
            if risk_level_filter == 'High' and c_risk != 'High':
                continue
            if risk_level_filter == 'Low' and c_risk != 'Low':
                continue

        filtered_list.append(c)

    # Sort
    filtered_list.sort(key=lambda x: str(x.name))

    # --- 3. Pagination ---
    page = request.args.get('page', 1, type=int)
    per_page = 10
    total = len(filtered_list)
    start = (page - 1) * per_page
    end = start + per_page
    
    paginated_items = filtered_list[start:end]
    
    clients_obj = SimpleNamespace(
        items=paginated_items,
        total=total,
        pages=(total + per_page - 1) // per_page,
        has_prev=page > 1,
        has_next=end < total,
        page=page,
        prev_num=page - 1,
        next_num=page + 1,
        iter_pages=lambda **kwargs: range(1, (total + per_page - 1) // per_page + 1)
    )

    return render_template(
        'client_management.html',
        clients=clients_obj,
        client_list=paginated_items,
        search=search,
        client_type=client_type,
        client_insights=client_insights,
        view_mode=view_mode
    )

@app.route('/create_client', methods=['GET', 'POST'])
@login_required
def create_client():
    if request.method == 'POST':
        try:
            # Create Client in Cloud API
            client_data = {
                "name": request.form.get('name'),
                "email": request.form.get('email'),
                "phone": request.form.get('phone'),
                "client_type": request.form.get('client_type'),
                "lead_stage": request.form.get('lead_stage'),
                "address": request.form.get('address'),
                "city": request.form.get('city'),
                "state": request.form.get('state'),
                "pincode": request.form.get('pincode'),
                "gstin": request.form.get('gstin'),
                "pan": request.form.get('pan'),
                # Add other fields if Cloud API supports them, otherwise they are lost or need local storage map
                # For now assuming basic fields supported by the provided API
            }
            
            response = cloud_request(
                "POST",
                "/clients",
                json=client_data
            )


            if response.status_code in (200, 201):
                # --- HYBRID: Save details locally as well ---
                try:
                    email = request.form.get('email')
                    name = request.form.get('name')
                    local_client = None

                    # Try to find existing by Email
                    if email:
                        local_client = Client.query.filter_by(email=email).first()
                    
                    # Fallback: Try to find by Name if not found yet
                    if not local_client and name:
                        local_client = Client.query.filter_by(name=name).first()
                        
                    # Create new if still not found
                    if not local_client:
                        local_client = Client(name=name, email=email)
                        db.session.add(local_client)
                    
                    # Update fields not supported by cloud
                    local_client.client_type = request.form.get('client_type')
                    local_client.contact_person = request.form.get('contact_person')
                    local_client.address = request.form.get('address')
                    local_client.city = request.form.get('city')
                    local_client.state = request.form.get('state')
                    local_client.pincode = request.form.get('pincode')
                    local_client.gstin = request.form.get('gstin')
                    local_client.pan = request.form.get('pan')
                    local_client.lead_stage = request.form.get('lead_stage')
                    local_client.notes = request.form.get('notes')
                    local_client.phone = request.form.get('phone') # Sync phone too
                    
                    if email: local_client.email = email 
                    
                    db.session.commit()
                    logging.info(f"Hybrid: Synced client '{local_client.name}' to local DB.")
                except Exception as e:
                    logging.error(f"Hybrid Sync Error: {e}")

                flash('Client created successfully in Cloud (& Local)!', 'success')
                return redirect(url_for('client_management'))
            else:
                 flash(f'Error creating client: {response.text}', 'error')

        except Exception as e:
            logging.error(f"Client creation failed: {e}")
            flash(f'Error creating client: {str(e)}', 'error')

    return render_template('create_client.html')

@app.route('/api/client/<client_id>')
@login_required
def api_client_details(client_id):
    # Only support Cloud IDs (which come as simple integers now, or strings from template)
    try:
        # Strip 'c_' prefix if it still persists in some cache/url, though we removed it from listing
        if str(client_id).startswith('c_'):
            real_id = int(str(client_id).replace('c_', ''))
        else:
            real_id = int(client_id)
            
        # Fetch from Cloud
        found = fetch_cloud_client_by_id(real_id)
        
        if found:
            # Get invoices for stats
            invoices = fetch_cloud_invoices()
            c_invoices = [inv for inv in invoices if inv.get('client_id') == real_id]
            total_business = sum(float(inv.get('total_amount', 0)) for inv in c_invoices)
            pending_amount = sum(float(inv.get('total_amount', 0)) for inv in c_invoices if inv.get('payment_status') != 'Paid')
            
            # Format Activity
            recent_activity = []
            for inv in sorted(c_invoices, key=lambda x: x.get('invoice_date', ''), reverse=True)[:5]:
                recent_activity.append({
                    'description': f"Invoice #{inv.get('invoice_number')} ({inv.get('payment_status')})",
                    'date': inv.get('invoice_date') or 'Recent'
                })

            data = {
                'name': found.get('name'),
                'email': found.get('email'),
                'phone': found.get('phone'),
                'address': found.get('address'),
                'city': found.get('city'),
                'state': found.get('state'),
                'pincode': found.get('pincode'),
                'gstin': found.get('gstin'),
                'pan': found.get('pan'),
                'total_business': total_business,
                'pending_amount': pending_amount,
                'contact_person': found.get('name'),
                'recent_activity': recent_activity
            }
            return jsonify(data)
        else:
             return jsonify({'error': 'Cloud client not found'}), 404
             
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/clients/excel')
@login_required
def export_clients_excel():
    search = request.args.get('search', '')
    client_type = request.args.get('type', '')
    
    # Build query with filters
    # Build list from Cloud
    try:
        clients_list = fetch_cloud_clients()
        invoices_list = fetch_cloud_invoices()
    except Exception as e:
        logging.error(f"Cloud fetch error in excel export: {e}")
        return jsonify({'success': False, 'message': 'Failed to fetch cloud data'}), 500

    # Filter
    filtered_clients = []
    for c in clients_list:
        if search:
             if not (search in (c.get('name') or '').lower() or 
                     search in (c.get('email') or '').lower() or 
                     search in (c.get('phone') or '').lower()):
                continue
        # Client type filter - not in basic cloud model, so skip or assume 'Regular'
        if client_type and client_type != 'Regular':
             continue
        
        filtered_clients.append(c)

    filtered_clients.sort(key=lambda x: x.get('name', ''))

    client_data = []
    for c in filtered_clients:
         # Calculate business
         c_invs = [inv for inv in invoices_list if inv.get('client_id') == c.get('id')]
         total_business = sum(float(inv.get('total_amount', 0)) for inv in c_invs)
         
         client_data.append({
            'Name': c.get('name') or 'N/A',
            'Email': c.get('email') or 'N/A',
            'Phone': c.get('phone') or 'N/A',
            'Type': c.get('client_type') or 'Regular',
            'Lead Stage': c.get('lead_stage') or 'New',
            'Total Business': total_business,
            'Risk Score': 0, # Placeholder
            'GST No': c.get('gstin') or 'N/A',
            'PAN No': c.get('pan') or 'N/A',
            'Created Date': c.get('created_at') or 'N/A'
        })

    df = pd.DataFrame(client_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Clients')
    output.seek(0)

    # Use desktop integration
    filename = f"clients_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/api/export/clients/pdf')
@login_required
def export_clients_pdf():
    # --- 1. Fetch Hybrid Data (Copy logic from client_management) ---
    search = request.args.get('search', '').lower()
    client_type = request.args.get('type', '')
    
    client_list = []
    today = datetime.utcnow().date()

    # Cloud Fetch
    try:
        cloud_clients = fetch_cloud_clients()
        cloud_invoices = fetch_cloud_invoices()
        
        for c in cloud_clients:
            c_invs = [inv for inv in cloud_invoices if inv.get('client_id') == c['id']]
            total_biz = sum(float(inv.get('total_amount', 0)) for inv in c_invs)
            
            client_dict = {
                'name': c.get('name', ''),
                'email': c.get('email', ''),
                'phone': c.get('phone', ''),
                'type': c.get('client_type') or 'Regular',
                'gstin': 'N/A', # Cloud default
                'business_value': total_biz
            }
            client_list.append(client_dict)
            
    except Exception as e:
        print(f"Cloud fetch error in export: {e}")
        return jsonify({'success': False, 'message': 'Cloud fetch error'}), 500

    # Local Fetch - REMOVED

    # Filter
    filtered = []
    for c in client_list:
        if search:
            if not (search in c['name'].lower() or search in c['email'].lower() or search in c['phone'].lower()):
                continue
        if client_type and c['type'] != client_type:
            continue
        filtered.append(c)
        
    filtered.sort(key=lambda x: x['name'])

    # --- 2. Generate PDF ---
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=18,
                            title='Client Directory Report', author='Invoice Pro', subject='Client Directory')
    elements = []
    styles = getSampleStyleSheet()

    # Header
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=24,
        alignment=1, # Center
        spaceAfter=20,
        textColor=colors.black
    )
    elements.append(Paragraph("Client Directory Report", title_style))
    
    # Org Details (Hardcoded for now or fetch from settings if available)
    org_style = ParagraphStyle('Org', parent=styles['Normal'], fontSize=10, spaceAfter=20)
    user_org = "Revolutionary Invoice System" # Placeholder
    gen_date = datetime.now().strftime("%d-%b-%Y")
    
    elements.append(Paragraph(f"<b>Organization Name:</b> {user_org}", org_style))
    elements.append(Paragraph(f"<b>Generated On:</b> {gen_date}", org_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("<b>Client Information Structure</b>", styles['Heading3']))
    elements.append(Spacer(1, 10))

    # Table Info
    # Data structure for Table: Header row + Data rows
    table_data = [['Client Name', 'Email Address', 'Phone Number', 'Client Type', 'Business Value', 'GSTIN']]
    
    for c in filtered:
        row = [
            c['name'][:20], # Truncate long names
            c['email'][:25], 
            c['phone'], 
            c['type'], 
            f"Rs. {c['business_value']:,.2f}", 
            c['gstin']
        ]
        table_data.append(row)

    # Create Table
    # Column widths
    col_widths = [2.0*inch, 2.5*inch, 1.2*inch, 1.0*inch, 1.5*inch, 1.5*inch]
    t = Table(table_data, colWidths=col_widths)

    # Styling
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(t)
    doc.build(elements)
    
    buffer.seek(0)
    filename = f"Client_Directory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    from urllib.parse import quote
    encoded_filename = quote(filename)
    return Response(
        buffer.getvalue(),
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded_filename}',
            'Content-Type': 'application/pdf'
        }
    )


def _get_analytics_data_dict(time_range='12m'):
    """Helper to gather all analytics data as a dictionary"""
    # Fetch cloud data
    invoices_data = fetch_cloud_invoices()
    clients_data = fetch_cloud_clients()
    
    analytics_data = {
        'revenue_trends': analytics_engine.compute_revenue_trends(invoices_data, time_range),
        'client_performance': analytics_engine.compute_client_performance_metrics(invoices_data, clients_data, time_range),
        'payment_analytics': analytics_engine.compute_payment_analytics(invoices_data, time_range),
        'profitability_analysis': analytics_engine.compute_profitability_analysis(invoices_data, time_range),
        'ai_predictions': {},
        'blockchain_insights': {}
    }
    
    # AI-powered predictions
    if app.config.get("AI_FEATURES_ENABLED") and predictive_analytics:
        try:
            analytics_data['ai_predictions'] = {
                'cash_flow': predictive_analytics.predict_cash_flow(6),
                'payment_patterns': predictive_analytics.analyze_client_payment_patterns()
            }
        except Exception as e:
            logging.error(f"AI predictions failed: {e}")
    
    # Blockchain analytics
    if app.config.get("BLOCKCHAIN_ENABLED") and blockchain_service:
        try:
            analytics_data['blockchain_insights'] = blockchain_service.get_blockchain_stats()
        except Exception as e:
            logging.error(f"Blockchain analytics failed: {e}")
            
    return analytics_data

def _save_buffer_to_downloads(buffer, filename):
    """Helper to save a memory buffer to the system Downloads folder and open it"""
    try:
        downloads_path = os.path.join(os.path.expanduser('~'), 'Downloads')
        if not os.path.exists(downloads_path):
            try:
                os.makedirs(downloads_path)
            except Exception:
                # Fallback to current directory if Downloads is somehow unreachable
                downloads_path = os.getcwd()
                
        file_path = os.path.join(downloads_path, filename)
        
        # Ensure buffer is at start
        buffer.seek(0)
        
        with open(file_path, 'wb') as f:
            f.write(buffer.read())
            
        # Try to open the file automatically on Windows
        if os.name == 'nt':
            try:
                os.startfile(file_path)
            except Exception as e:
                logging.error(f"Could not open file: {e}")
                
        return file_path
    except Exception as e:
        logging.error(f"Failed to save file to downloads: {e}")
        return None

@app.route('/analytics')
@login_required
def analytics():
    """Advanced analytics dashboard with AI insights"""
    try:
        # Time range for analytics
        time_range = request.args.get('range', '12m')  # 12 months default
        
        # Generate comprehensive analytics using helper
        analytics_data = _get_analytics_data_dict(time_range)
        
        print("Client Performance Data:", analytics_data['client_performance'])
        print("Full Analytics Data:", analytics_data)


        return render_template('analytics.html', analytics_data=analytics_data)
    
    except Exception as e:
        logging.error(f"Analytics error: {e}")
        flash('Error loading analytics data.', 'error')
        
        return render_template('analytics.html', analytics_data={'revenue_trends': {},
        'client_performance': {},
        'payment_analytics': {},
        'profitability_analysis': {},
        'ai_predictions': {},
        'blockchain_insights': {}}, error=str(e))

@app.route('/analytics/export/excel')
@login_required
def export_analytics_excel():
    """Export analytics data to Excel and download it"""
    try:
        time_range = request.args.get('range', '12m')
        report_type = request.args.get('type', 'all')
        analytics_data = _get_analytics_data_dict(time_range)
        output = report_generator.generate_excel_report(analytics_data, report_type)
        
        prefix = report_type.title() if report_type != 'all' else 'Analytics'
        filename = f"{prefix}_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        output.seek(0)
        from urllib.parse import quote
        encoded_filename = quote(filename)
        return Response(
            output.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded_filename}',
                'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }
        )
            
    except Exception as e:
        logging.error(f"Excel export failed: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/analytics/export/pdf')
@login_required
def export_analytics_pdf():
    """Export analytics data to PDF and download it"""
    try:
        time_range = request.args.get('range', '12m')
        report_type = request.args.get('type', 'all')
        analytics_data = _get_analytics_data_dict(time_range)
        output = report_generator.generate_pdf_report(analytics_data, report_type)
        
        prefix = report_type.title() if report_type != 'all' else 'Analytics'
        filename = f"{prefix}_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        output.seek(0)
        from urllib.parse import quote
        encoded_filename = quote(filename)
        return Response(
            output.getvalue(),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded_filename}',
                'Content-Type': 'application/pdf'
            }
        )
            
    except Exception as e:
        logging.error(f"PDF export failed: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/ai_assistant')
@login_required
def ai_assistant_page():
    """AI Assistant interface"""
    return render_template('ai_assistant.html')

@app.route('/settings')
@login_required
def settings():

    print("SESSION TOKEN:", session.get("token"))
    try:
        # Fetch company from cloud (tenant scoped automatically)
        company_res = cloud_request("GET", "/company")
        company_data = company_res.json() if company_res and company_res.status_code == 200 else {}

        bank_res = cloud_request("GET", "/bank-details")
        bank_data = bank_res.json() if bank_res and bank_res.status_code == 200 else {}

        # Fetch invoice defaults
        defaults_res = cloud_request("GET", "/settings/default-prefix")
        defaults_data = defaults_res.json() if defaults_res and defaults_res.status_code == 200 else {}

        tax_res = cloud_request("GET", "/settings/default-tax")
        tax_data = tax_res.json() if tax_res and tax_res.status_code == 200 else {}

        user_res = cloud_request("GET", "/user/profile")

        if user_res.status_code == 200:
            user_data = user_res.json()
        else:
            user_data = {}

        settings_data = {
            "company": company_data,
            "bank": bank_data,
            "user": user_data
        }

        return render_template("settings.html", settings_data=settings_data)

    except Exception:
        company_data = {}
        bank_data = {}
        defaults_data = {}
        tax_data = {}

    settings_data = {
        "company": company_data,
        "bank": bank_data,
        "invoice_defaults": defaults_data,
        "tax_settings": tax_data,
        "user": {
            "username": session.get("username"),
        },
        "ai_enabled": True,
        "blockchain_enabled": True
    }

    return render_template("settings.html", settings_data=settings_data)


@app.route('/settings/update', methods=['POST'])
@login_required
def update_settings():
    try:
        # ---------------------------------------
        # HANDLE FORM DATA (supports file upload)
        # ---------------------------------------
        import json

        if request.content_type and "multipart/form-data" in request.content_type:
            logo_file = request.files.get("logo")
            signature_file = request.files.get("authorized_signature") 

            # 🔥 Parse JSON strings properly
            data = {
                "company": json.loads(request.form.get("company", "{}")),
                "bank": json.loads(request.form.get("bank", "{}")),
                "user": json.loads(request.form.get("user", "{}")),
                "invoice": json.loads(request.form.get("invoice", "{}")),
            }
        else:
            data = request.get_json()
            logo_file = None
            signature_file = None
        print("FULL DATA RECEIVED:", data)    
        # ---------------------------------------
        # 1️⃣ UPDATE COMPANY (WITH LOGO SUPPORT)
        # ---------------------------------------
        if data and (
            "companyName" in data or
            (isinstance(data, dict) and "company" in data)
        ):

            if isinstance(data, dict) and "company" in data:
                company_data = data["company"]
            else:
                company_data = data

            company_payload = {
                "name": company_data.get("companyName"),
                "email": company_data.get("companyEmail"),
                "phone": company_data.get("companyPhone"),
                "website": company_data.get("companyWebsite"),
                "address": company_data.get("companyAddress"),
                "city": company_data.get("companyCity"),
                "state": company_data.get("companyState"),
                "pincode": company_data.get("companyPincode"),
                "gstin": company_data.get("companyGstin"),
                "pan": company_data.get("companyPan")
            }

            files = {}

            # Add logo if present
            if logo_file and logo_file.filename != "":
                files["logo"] = (
                    logo_file.filename,
                    logo_file.stream,
                    logo_file.mimetype
                )

            # ✅ Add signature if present
            if signature_file and signature_file.filename != "":
                files["authorized_signature"] = (
                    signature_file.filename,
                    signature_file.stream,
                    signature_file.mimetype
                )

            response = cloud_request(
                "POST",
                "/company",
                data=company_payload,
                files=files
            )

            if not response or response.status_code != 200:
                return jsonify({
                    "success": False,
                    "message": "Company update failed"
                }), 400

        # ---------------------------------------
        # 2️⃣ UPDATE BANK
        # ---------------------------------------
        if isinstance(data, dict) and "bank" in data:
            bank_payload = {
                "bank_name": data["bank"].get("bankName"),
                "account_number": data["bank"].get("accountNumber"),
                "account_name": data["bank"].get("accountName"),
                "ifsc_code": data["bank"].get("ifscCode"),
                "branch": data["bank"].get("branchName")
            }

            response = cloud_request(
                "POST",
                "/bank-details",
                json=bank_payload
            )

            if not response or response.status_code not in (200, 201):
                return jsonify({
                    "success": False,
                    "message": "Bank update failed"
                }), 400

        # =============================
        # UPDATE USER PROFILE (CLOUD)
        # =============================
        if isinstance(data, dict) and "user" in data:

            user_data = data.get("user", {})

            user_payload = {
                "email": user_data.get("userEmail"),
                "preferred_language": user_data.get("preferredLanguage"),
                "theme_preference": user_data.get("themePreference"),
                "ai_features_enabled": user_data.get("aiFeatures"),
                "voice_commands_enabled": user_data.get("voiceCommands"),
                "collaboration_access": user_data.get("collaborationAccess"),
                "biometric_enabled": user_data.get("biometricEnabled")
            }

            if user_data.get("newPassword"):
                user_payload["new_password"] = user_data.get("newPassword")

            # 🔥 FIXED VERSION
            if "emailAppPassword" in user_data:
                user_payload["email_app_password"] = user_data.get("emailAppPassword")

            print("USER PAYLOAD:", user_payload)

            response = cloud_request("PUT", "/user/profile", json=user_payload)

            if not response or response.status_code != 200:
                return jsonify({
                    "success": False,
                    "message": "User profile update failed"
                }), 400
                
        # ---------------------------------------
        # 4️⃣ UPDATE INVOICE SETTINGS
        # ---------------------------------------
        if isinstance(data, dict) and "invoice" in data:
            inv = data["invoice"]

            cloud_request(
                "POST",
                "/settings/default-tax",
                json={"default_tax_rate": inv.get("defaultTaxRate")}
            )

            cloud_request(
                "POST",
                "/settings/default-prefix",
                json={
                    "invoice_prefix": inv.get("invoicePrefix"),
                    "default_currency": inv.get("defaultCurrency"),
                    "default_terms": inv.get("defaultTerms")
                }
            )

        return jsonify({
            "success": True,
            "message": "Settings saved successfully"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


from flask import Response

@app.route("/company/logo")
@login_required
def company_logo():
    response = cloud_request("GET", "/company/logo")

    if response and response.status_code == 200:
        return Response(
            response.content,
            content_type=response.headers.get("Content-Type")
        )

    return "", 404



@app.route("/company/signature")
@login_required
def company_signature():
    response = cloud_request("GET", "/company/signature")

    if response and response.status_code == 200:
        return Response(
            response.content,
            content_type=response.headers.get("Content-Type")
        )

    return "", 404

@app.route("/create-challan", methods=["GET", "POST"])
@login_required
def create_challan():

    if request.method == "POST":
        try:
            client_id = request.form.get("client_id")
            challan_date_str = request.form.get("challan_date")
            delivery_date_str = request.form.get("delivery_date")
            vehicle_number = request.form.get("vehicle_number")
            transport_mode = request.form.get("transport_mode")
            notes = request.form.get("notes", "")
            line_items_json = request.form.get("line_items")

            # 🔹 Append transport metadata into notes
            meta_notes = []
            if transport_mode:
                meta_notes.append(f"Mode: {transport_mode}")
            if vehicle_number:
                meta_notes.append(f"Vehicle: {vehicle_number}")

            if meta_notes:
                notes = (notes or "") + ("\n" if notes else "") + " | ".join(meta_notes)

            # 🔹 Build line items list
            line_items = []

            if line_items_json:
                try:
                    items = json.loads(line_items_json)
                except Exception:
                    items = []

                for idx, item in enumerate(items, start=1):

                    line_items.append({
                        "sr_no": item.get("sr_no", idx),
                        "hsn_code": item.get("hsn_code", ""),
                        "description": item.get("description", "") or "Item",
                        "quantity": float(item.get("quantity", 0) or 0),
                        "unit": item.get("unit", "Nos"),
                        "unit_price": float(item.get("unit_price", 0) or 0),

                        # 🔥 SEND TAX PERCENTAGES (Cloud will calculate totals)
                        "cgst_percentage": float(item.get("cgst_percentage", 0) or 0),
                        "sgst_percentage": float(item.get("sgst_percentage", 0) or 0),
                        "igst_percentage": float(item.get("igst_percentage", 0) or 0),
                    })

            # 🔹 Prepare payload for cloud API
            payload = {
                "client_id": client_id,
                "challan_date": challan_date_str,
                "delivery_date": delivery_date_str,
                "notes": notes,
                "status": "Open",
                "line_items": line_items
            }

            # 🔹 Send to cloud
            response = cloud_request(
                "POST",
                "/challans",
                json=payload,
                timeout=10
            )

            if response and response.status_code in (200, 201):
                resp_json = response.json()
                challan_number = resp_json.get("challan_number", "DC")
                flash(
                    f"Delivery Challan {challan_number} created successfully!",
                    "success"
                )
            else:
                error = response.text if response else "No response from server"
                flash(f"Error creating challan: {error}", "error")

            return redirect(url_for("delivery_challan"))

        except Exception as e:
            logging.error(f"Error creating challan: {e}")
            flash(f"Error creating challan: {e}", "error")
            return redirect(url_for("delivery_challan"))

    # 🔹 GET Request – Load Clients
    client_list = fetch_cloud_clients()
    clients = [SimpleNamespace(**c) for c in client_list]

    return render_template(
        "create_challan.html",
        clients=clients,
        today=datetime.now()
    )


@app.route('/challan/preview', methods=['POST'])
@login_required
def preview_challan():
    """Preview delivery challan without saving"""
    try:
        # 1. Collect Form Data
        client_id = request.form.get('client_id')
        challan_date_str = request.form.get('challan_date')
        delivery_date_str = request.form.get('delivery_date')
        vehicle_number = request.form.get('vehicle_number')
        transport_mode = request.form.get('transport_mode')
        notes = request.form.get('notes', '')
        line_items_json = request.form.get('line_items', '[]')

        # 2. validation (basic)
        if not client_id:
             return "Client is required for preview", 400

        # 3. Create Transient Client (or fetch)
        # We need client details for the PDF.
        client_data = fetch_cloud_client_by_id(client_id)
        if not client_data:
             return "Client not found", 404
        
        # SimpleNamespace to mimic object access in PDF generator
        client = SimpleNamespace(**client_data)

        # 4. Create Transient Challan Object
        # Use a dummy number or "PREVIEW"
        challan_number = "PREVIEW"
        
        # Parse dates
        challan_date = datetime.strptime(challan_date_str, '%Y-%m-%d').date() if challan_date_str else datetime.now().date()
        delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date() if delivery_date_str else None

        # Prepare notes with transport info
        meta_notes = []
        if transport_mode: meta_notes.append(f"Mode: {transport_mode}")
        if vehicle_number: meta_notes.append(f"Vehicle: {vehicle_number}")
        
        full_notes = notes
        if meta_notes:
            full_notes = (full_notes or "") + "\n" + " | ".join(meta_notes)

        # Create transient Challan object
        challan = DeliveryChallan(
            challan_number=challan_number,
            client_id=int(client_id),
            challan_date=challan_date,
            delivery_date=delivery_date,
            notes=full_notes,
            status='Draft' 
        )
        # Manually attach client object for PDF generator which expects challan.client
        # USE A DIFFERENT ATTRIBUTE NAME to avoid SQLAlchemy relationship validation error
        challan.preview_client = client 

        # 5. Parse Line Items
        line_items = []
        if line_items_json:
            try:
                items_data = json.loads(line_items_json)
                for item in items_data:
                     # Create Transient Line Item
                     li = ChallanLineItem(
                         sr_no=int(item.get('sr_no', 0)),
                         hsn_code=item.get('hsn_code', ''),
                         description=item.get('description', ''),
                         quantity=float(item.get('quantity', 0)),
                         unit=item.get('unit', ''),
                         unit_price=float(item.get('unit_price', 0)),
                         total_amount=float(item.get('quantity', 0)) * float(item.get('unit_price', 0))
                     )
                     line_items.append(li)
            except json.JSONDecodeError:
                logging.error("Failed to parse line items JSON")
        
        challan.line_items = line_items

        # Fetch company from cloud API
        company_res = cloud_request("GET", "/company")
        company = SimpleNamespace(**company_res.json()) if company_res and company_res.status_code == 200 else None

        # 6. Generate PDF
        # We use the existing function. 
        pdf_buffer = generate_challan_pdf(challan, company=company)
        pdf_buffer.seek(0)
        
        # 7. Return PDF Inline
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=False,
            download_name='challan_preview.pdf'
        )

    except Exception as e:
        logging.error(f"Challan preview failed: {e}")
        return f"Error creating preview: {str(e)}", 500


@app.route("/delivery-challan")
@login_required
def delivery_challan():
    try:
        response = cloud_request("GET", "/challans")
        print("STATUS:", response.status_code)
        print("RESPONSE TEXT:", response.text)



        if response.status_code == 200:
            data = response.json()
        else:
            flash("Failed to load delivery challans", "error")
            data = []

    except Exception as e:
        flash(f"API connection error: {str(e)}", "error")
        data = []

    # Fetch all clients from cloud API to get phone numbers
    clients_data = fetch_cloud_clients()
    # Create a mapping of client_id to client data for quick lookup
    client_map = {client.get('id'): client for client in clients_data}

    challan_list = []

    for c in data:
        # Get client details from the client_map
        client_id = c.get("client_id")
        client_info = client_map.get(client_id, {})
        
        challan_obj = SimpleNamespace(
            id=c["id"],
            challan_number=c["challan_number"],

            challan_date=datetime.strptime(
                c["challan_date"], "%Y-%m-%d"
            ) if c.get("challan_date") else None,

            delivery_date=datetime.strptime(
                c["delivery_date"], "%Y-%m-%d"
            ) if c.get("delivery_date") else None,

            created_at=datetime.fromisoformat(
                c["created_at"]
            ) if c.get("created_at") else None,

            client=SimpleNamespace(
                id=client_id,
                name=c.get("client_name") or client_info.get("name", "Unknown"),
                phone=client_info.get("phone", "")
            ),

            status=c["status"],
            notes=c["notes"],
            line_items=c.get("line_items", [])
        )

        challan_list.append(challan_obj)

    # Pagination logic
    page = request.args.get('page', 1, type=int)
    per_page = 15
    total_challans = len(challan_list)
    total_pages = (total_challans + per_page - 1) // per_page  # Ceiling division
    
    # Ensure page is within valid range
    if page < 1:
        page = 1
    elif page > total_pages and total_pages > 0:
        page = total_pages
    
    # Calculate start and end indices for slicing
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    # Slice the challan list for current page
    paginated_challans = challan_list[start_idx:end_idx]

    challans_obj = SimpleNamespace(
        items=paginated_challans,
        total=total_challans,
        pages=total_pages,
        has_prev=(page > 1),
        has_next=(page < total_pages),
        page=page,
        per_page=per_page
    )

    return render_template(
        "delivery_challan.html",
        challans=challans_obj
    )


@app.route("/challan/<int:id>/delete", methods=['POST'])
@login_required
def delete_challan(id):
    """Delete delivery challan from cloud database"""
    try:
        response = cloud_request("DELETE", f"/challans/{id}")
        if response and response.status_code in (200, 204):
            flash('Delivery Challan deleted successfully.', 'success')
        else:
            flash(f'Failed to delete challan: {response.text if response else "No response"}', 'error')
    except Exception as e:
        logging.error(f"Cloud API delete challan error: {e}")
        flash(f'API connection error: {str(e)}', 'error')
    return redirect(url_for('delivery_challan'))


@app.route("/challan/<int:id>/status", methods=['POST'])
@login_required
def update_challan_status(id):
    try:
        new_status = request.form.get('status')
        note = request.form.get('note')

        if new_status:

            # Build payload
            update_data = {'status': new_status}

            # Add note if provided
            if note:
                challan_data = fetch_cloud_challan_by_id(id)
                existing_notes = challan_data.get('notes', '') if challan_data else ''

                update_data['notes'] = (
                    (existing_notes or "") +
                    f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] "
                    f"Status updated to {new_status}: {note}"
                )

            # ⭐ CLOUD CALL WITH TOKEN (IMPORTANT)
            print("CLOUD URL:", f"{CLOUD_API_BASE}/challans/{id}")

            response = requests.put(
                f"{CLOUD_API_BASE}/challans/{id}",
                json=update_data,
                headers={
                    "Authorization": f"Bearer {session.get('token')}",
                    "Content-Type": "application/json"
                },
                timeout=5
            )

            print("STATUS:", response.status_code)
            print("RESPONSE:", response.text)

            if response.status_code in (200, 204):
                flash(f'Challan status updated to {new_status}', 'success')
            else:
                flash(f'Failed to update status: {response.text}', 'error')

        return redirect(url_for('delivery_challan'))

    except Exception as e:
        logging.error(f"Cloud API update error: {e}")
        flash(f'Error updating status: {str(e)}', 'error')
        return redirect(url_for('delivery_challan'))

@app.route('/crm')
@login_required
def crm():
    # 1. Fetch Stats
    lead_stats = analytics_engine.get_lead_stats()
    print(f"\n🔍 [CRM DEBUG] Lead Stats: {lead_stats}")
    
    # 2. Fetch Clients (Cloud)
    clients_data = fetch_cloud_clients()
    processed_clients = []
    
    # Process clients for template
    for c in clients_data:
        client = c.copy()
        
        # Parse dates (handle missing fields gracefully)
        client['created_at'] = None
        if c.get('created_at'):
             try:
                client['created_at'] = datetime.fromisoformat(c.get('created_at').replace('Z', '+00:00'))
             except: pass

        client['last_contact_date'] = None
        if c.get('last_contact_date'):
             try:
                client['last_contact_date'] = datetime.fromisoformat(c.get('last_contact_date').replace('Z', '+00:00'))
             except: pass
        
        # Ensure lead_stage exists
        if not client.get('lead_stage'):
            client['lead_stage'] = 'New'
            
        processed_clients.append(client)
        
    # 3. Recent Contacts
    # Fallback: Since cloud data might lack dates, if no contacts have dates, just show the last 5
    recents_with_dates = [c for c in processed_clients if c.get('last_contact_date')]
    if recents_with_dates:
        recent_contacts = sorted(recents_with_dates, key=lambda x: x['last_contact_date'], reverse=True)[:5]
    else:
        # Fallback: Show last 5 clients (assuming they are newest)
        recent_contacts = processed_clients[-5:][::-1]
    
    # 4. Overdue Invoices (Cloud)
    invoices_data = fetch_cloud_invoices()
    overdue_invoices = []
    
    today = datetime.now().date()
    
    for inv in invoices_data:
        inv_date = None
        if inv.get('invoice_date'):
            try:
                inv_date = datetime.strptime(inv.get('invoice_date'), '%Y-%m-%d').date()
            except: pass
            
        if inv.get('payment_status') != 'Paid' and inv_date:
            days_pending = (today - inv_date).days
            if days_pending > 44:
                # Find client
                client_match = next((c for c in processed_clients if c['id'] == inv.get('client_id')), None)
                if client_match:
                    inv['client'] = client_match
                    inv['created_at'] = datetime.combine(inv_date, datetime.min.time())
                    overdue_invoices.append(inv)
    
    # 5. Reminders (Local)
    reminders = []
    try:
        from models import Reminder
        from types import SimpleNamespace
        
        db_reminders = Reminder.query.filter(Reminder.status != 'Completed') \
            .order_by(Reminder.reminder_date.asc()) \
            .all()
            
        for r in db_reminders:
            client_dict = next((c for c in processed_clients if c['id'] == r.client_id), None)
            if client_dict:
                c_obj = SimpleNamespace(
                    id=client_dict['id'], 
                    name=client_dict['name'], 
                    email=client_dict.get('email', '')
                )
                rem = SimpleNamespace(
                    id=r.id,
                    client=c_obj,
                    reminder_date=r.reminder_date,
                    note=r.notes,
                    status=r.status,
                    reminder_type=r.reminder_type
                )
                reminders.append(rem)
                
    except Exception as e:
        app.logger.error(f"Error fetching local reminders: {e}")

    # 6. Follow-ups
    follow_ups = [r for r in reminders if r.reminder_type == 'Follow-up']
    


    # DEBUG: Print what we're passing to template
    print(f"\n🔍 [CRM DEBUG] Data being passed to template:")
    print(f"  - processed_clients: {len(processed_clients)} items")
    print(f"  - recent_contacts: {len(recent_contacts)} items")
    if recent_contacts:
        print(f"    First recent contact: {recent_contacts[0]}")
    print(f"  - follow_ups: {len(follow_ups)} items")
    if follow_ups:
        print(f"    First follow-up: {follow_ups[0]}")
        print(f"    First follow-up type: {type(follow_ups[0])}")

    return render_template(
        'crm.html', 
        title='CRM', 
        lead_stats=lead_stats,
        clients=processed_clients,
        recent_contacts=recent_contacts,
        overdue_invoices=overdue_invoices,
        reminders=reminders,
        follow_ups=follow_ups
    )

@app.route('/create-reminder')
@login_required
def create_reminder_page():
    return render_template('create_reminder.html', title='Create Reminder')

@app.route('/reminder/create', methods=['POST'])
@login_required
def create_reminder():
    try:
        client_id = request.form.get('client_id')
        reminder_date_str = request.form.get('reminder_date')
        reminder_type = request.form.get('reminder_type')
        notes = request.form.get('notes', '')
        
        reminder_date = datetime.strptime(reminder_date_str, '%Y-%m-%dT%H:%M') if reminder_date_str else None
        
        reminder = Reminder(
            client_id=client_id,
            reminder_date=reminder_date,
            reminder_type=reminder_type,
            notes=notes,
            status='Pending'
        )
        
        db.session.add(reminder)
        db.session.commit()
        flash('Reminder created successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating reminder: {str(e)}', 'error')
    
    return redirect(url_for('crm'))

@app.route('/reminder/<int:id>/complete', methods=['POST'])
@login_required
def complete_reminder(id):
    try:
        if id == 0:
            flash('System-generated follow-up acknowledged.', 'success')
            return redirect(url_for('crm'))
            
        reminder = Reminder.query.get_or_404(id)
        reminder.status = 'Completed'
        db.session.commit()
        flash('Reminder marked as completed.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating reminder: {str(e)}', 'error')
    return redirect(url_for('crm'))

@app.route('/api/contact_client_whatsapp', methods=['POST'])
@login_required
def contact_client_whatsapp():
    return jsonify({'success': False, 'error': 'WhatsApp integration pending client setup'}), 501

@app.route('/api/send_invoice_whatsapp', methods=['POST'])
@login_required
def send_invoice_whatsapp():
    return jsonify({'success': False, 'error': 'WhatsApp integration pending client setup'}), 501


from flask import send_file, request
import io
import pandas as pd

@app.route("/api/export/excel")
def export_excel():
    # Example: create a DataFrame (replace with your actual query)
    data = [
        {"Invoice": 1, "Client": "ABC Corp", "Amount": 500},
        {"Invoice": 2, "Client": "XYZ Ltd", "Amount": 750},
    ]
    df = pd.DataFrame(data)

    # Save Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Invoices")

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="invoices.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.route("/api/export/pdf")
def export_pdf():
    from io import BytesIO
    buffer = BytesIO()

    # Create a PDF with reportlab
    p = canvas.Canvas(buffer)
    p.drawString(100, 750, "Invoice Report")
    p.drawString(100, 730, "Client: ABC Corp")
    p.drawString(100, 710, "Amount: $500")
    p.showPage()
    p.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="invoices.pdf",
        mimetype="application/pdf"
    )




# API Routes for AJAX and Advanced Features

@app.route('/api/voice_command', methods=['POST'])
@login_required
def api_voice_command():
    print(f"\n🎤 [VOICE API] hit: /api/voice_command")
    """Process voice commands"""
    # Force enable for debugging if needed, or rely on config
    if not app.config.get("AI_FEATURES_ENABLED") and not os.environ.get("FORCE_VOICE_DEBUG"):
        # Log this failure case
        app.logger.warning("Voice command rejected: AI_FEATURES_ENABLED is False")
        if not voice_processor:
             app.logger.error("Voice command rejected: voice_processor is None")
        return jsonify({'error': 'Voice commands not available'})
    
    try:
        data = request.get_json()
        app.logger.info(f"🎤 API RECEIVED VOICE REQUEST: {data}")
        
        voice_text = data.get('text', '')
        context = data.get('context', {})
        
        if not voice_text:
            app.logger.warning("🎤 Voice request missing 'text' field")
            return jsonify({'success': False, 'message': 'No voice text provided'})

        result = voice_processor.process(voice_text)
        app.logger.info(f"🎤 VOICE PROCESSOR RESULT: {result}")
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"❌ API VOICE ERROR: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Internal Server Error processing voice command', 'error': str(e)}), 500
        logging.error(f"Voice command API failed: {e}")
        return jsonify({'error': str(e)})


@app.route('/api/ai_suggestions/<int:client_id>')
@login_required
def api_ai_suggestions(client_id):
    """Get AI suggestions for invoice items"""
    if not app.config.get("AI_FEATURES_ENABLED") or not ai_services.ai_assistant:
        return jsonify({'error': 'AI features not available'})
    
    try:
        context = request.args.get('context', '')
        suggestions = ai_services.ai_assistant.suggest_invoice_items(client_id, context)
        return jsonify({'suggestions': suggestions})
        
    except Exception as e:
        logging.error(f"AI suggestions API failed: {e}")
        return jsonify({'error': str(e)})

@app.route('/api/document_scan', methods=['POST'])
@login_required
def api_document_scan():
    """OCR document scanning API"""
    if not app.config.get("AI_FEATURES_ENABLED") or not ocr_processor:
        return jsonify({'error': 'OCR features not available'})
    
    try:
        if 'document' not in request.files:
            return jsonify({'error': 'No document provided'})
        
        file = request.files['document']
        if file.filename == '':
            return jsonify({'error': 'No file selected'})
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        
        # Process with OCR
        scan_type = request.form.get('type', 'invoice')
        
        if scan_type == 'receipt':
            result = receipt_processor.extract_receipt_data(filepath)
        else:
            result = ocr_processor.extract_invoice_data(filepath)
        
        # Clean up uploaded file
        os.remove(filepath)
        
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"Document scan API failed: {e}")
        return jsonify({'error': str(e)})

@app.route('/api/blockchain_verify/<int:invoice_id>')
@login_required
def api_blockchain_verify(invoice_id):
    """Blockchain verification API"""
    if not app.config.get("BLOCKCHAIN_ENABLED") or not blockchain_service:
        return jsonify({'error': 'Blockchain features not available'})
    
    try:
        verification = blockchain_service.verify_invoice_integrity(invoice_id)
        return jsonify(verification)
        
    except Exception as e:
        logging.error(f"Blockchain verification API failed: {e}")
        return jsonify({'error': str(e)})

@app.route('/api/inventory_forecast/<int:item_id>')
@login_required
def api_inventory_forecast(item_id):
    """Inventory demand forecasting API"""
    if not app.config.get("AI_FEATURES_ENABLED") or not ai_services.inventory_ai:
        return jsonify({'error': 'AI inventory features not available'})
    
    try:
        days_ahead = request.args.get('days', 30, type=int)
        forecast = ai_services.inventory_ai.forecast_demand(item_id, days_ahead)
        return jsonify(forecast)
        
    except Exception as e:
        logging.error(f"Inventory forecast API failed: {e}")
        return jsonify({'error': str(e)})

@app.route('/api/analytics_data')
@login_required
def api_analytics_data():
    """Real-time analytics data API"""
    try:
        data_type = request.args.get('type', 'revenue')
        time_range = request.args.get('range', '12m')
        
        if data_type == 'revenue':
            data = analytics_engine.get_revenue_trends(time_range)
        elif data_type == 'clients':
            data = analytics_engine.get_client_performance_metrics()
        elif data_type == 'payments':
            data = analytics_engine.get_payment_analytics()
        else:
            data = {'error': 'Invalid data type'}
        
        return jsonify(data)
        
    except Exception as e:
        logging.error(f"Analytics API failed: {e}")
        return jsonify({'error': str(e)})



# Error Handlers

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# Context Processors

@app.context_processor
def inject_globals():
    """Inject global template variables"""
    return {
        'ai_enabled': app.config.get("AI_FEATURES_ENABLED", False),
        'blockchain_enabled': app.config.get("BLOCKCHAIN_ENABLED", False),
        'current_user_id': session.get('user_id'),
        'is_admin': session.get('is_admin', False)
    }
      





# ===== API ENDPOINTS FOR CLIENT-SIDE AI (REAL DATA) =====

@app.route('/api/data/clients', methods=['GET'])
@login_required
def api_get_clients_data():
    """Get real client data for client-side AI processing"""
    try:
        # Fetch from cloud database
        clients_list = fetch_cloud_clients()
        
        clients_data = {
            'total': len(clients_list),
            'active': len([c for c in clients_list if c.get('total_business') and c.get('total_business') > 0]),
            'inactive': len([c for c in clients_list if not c.get('total_business') or c.get('total_business') == 0]),
            'clients': [{
                'id': c.get('id'),
                'name': c.get('name'),
                'email': c.get('email'),
                'phone': c.get('phone'),
                'total_business': float(c.get('total_business', 0)),
                'created_at': c.get('created_at'),
                'gstin': c.get('gstin'),
                'pan': c.get('pan')
            } for c in clients_list]
        }
        
        return jsonify(clients_data)
    except Exception as e:
        logging.error(f"Error fetching clients data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/data/invoices', methods=['GET'])
@login_required
def api_get_invoices_data():
    """Get real invoice data for client-side AI processing"""
    try:
        # Fetch from cloud database
        invoices_list = fetch_cloud_invoices()
        
        invoices_data = {
            'total': len(invoices_list),
            'paid': len([i for i in invoices_list if i.get('payment_status') == 'Paid']),
            'unpaid': len([i for i in invoices_list if i.get('payment_status') == 'Unpaid']),
            'partial': len([i for i in invoices_list if i.get('payment_status') == 'Partially Paid']),
            'invoices': [{
                'id': i.get('id'),
                'invoice_number': i.get('invoice_number'),
                'client_name': i.get('client_name', 'Unknown'),
                'total_amount': float(i.get('total_amount', 0)),
                'amount_paid': float(i.get('amount_paid', 0)),
                'payment_status': i.get('payment_status'),
                'invoice_date': i.get('invoice_date'),
                'due_date': i.get('due_date')
            } for i in invoices_list]
        }
        
        return jsonify(invoices_data)
    except Exception as e:
        logging.error(f"Error fetching invoices data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/invoices/by-client/<int:client_id>', methods=['GET'])
@login_required
def api_invoices_by_client(client_id):
    """Return invoices for a specific client — used by the challan import modal."""
    try:
        all_invoices = fetch_cloud_invoices()
        client_invoices = [
            {
                'id': inv.get('id'),
                'invoice_number': inv.get('invoice_number'),
                'invoice_date': inv.get('invoice_date'),
                'total_amount': float(inv.get('total_amount', 0)),
                'payment_status': inv.get('payment_status'),
            }
            for inv in all_invoices
            if str(inv.get('client_id')) == str(client_id)
        ]
        return jsonify({'invoices': client_invoices})
    except Exception as e:
        logging.error(f"Error fetching invoices for client {client_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/invoices/<int:invoice_id>/items', methods=['GET'])
@login_required
def api_invoice_items(invoice_id):
    """Return line items for a specific invoice — used by the challan import modal."""
    try:
        inv = fetch_cloud_invoice_by_id(invoice_id)
        if not inv:
            return jsonify({'items': []})
        items = inv.get('line_items') or inv.get('items') or inv.get('invoice_items') or []
        return jsonify({'items': items})
    except Exception as e:
        logging.error(f"Error fetching items for invoice {invoice_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/proxy/clients', methods=['GET'])
@login_required
def api_proxy_clients():
    print(f"\n🎤 [VOICE API] hit: /api/proxy/clients")
    """Proxy endpoint for voice commands to fetch clients (avoids CORS)"""
    try:
        clients_list = fetch_cloud_clients()
        return jsonify(clients_list)
    except Exception as e:
        logging.error(f"Error proxying clients: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/data/stats', methods=['GET'])
@login_required
def api_get_stats_data():
    """Get real statistics for client-side AI processing"""
    try:
        from datetime import date, timedelta
        from sqlalchemy import func
        
        today = date.today()
        start_of_month = date(today.year, today.month, 1)
        start_of_week = today - timedelta(days=today.weekday())
        
        # Today's revenue
        today_revenue = db.session.query(func.sum(Invoice.total_amount)).filter(
            Invoice.payment_status == 'Paid',
            Invoice.invoice_date == today
        ).scalar() or 0
        
        # Week's revenue
        week_revenue = db.session.query(func.sum(Invoice.total_amount)).filter(
            Invoice.payment_status == 'Paid',
            Invoice.invoice_date >= start_of_week,
            Invoice.invoice_date <= today
        ).scalar() or 0
        
        # Month's revenue
        month_revenue = db.session.query(func.sum(Invoice.total_amount)).filter(
            Invoice.payment_status == 'Paid',
            Invoice.invoice_date >= start_of_month,
            Invoice.invoice_date <= today
        ).scalar() or 0
        
        # Outstanding amount
        outstanding = db.session.query(
            func.sum(Invoice.total_amount - Invoice.amount_paid)
        ).filter(
            Invoice.payment_status.in_(['Unpaid', 'Partially Paid'])
        ).scalar() or 0
        
        stats_data = {
            'revenue': {
                'today': float(today_revenue),
                'week': float(week_revenue),
                'month': float(month_revenue)
            },
            'outstanding': float(outstanding)
        }
        
        return jsonify(stats_data)
    except Exception as e:
        logging.error(f"Error fetching stats data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai/chat', methods=['POST'])
@login_required
def api_ai_chat():
    print(f"\n🎤 [VOICE API] hit: /api/ai/chat")
    """AI chat endpoint that uses real database data"""
    try:
        data = request.get_json()
        message = data.get('message', '').lower().strip()

        # Try to use cloud data first (if available), otherwise fall back to local DB
        use_cloud = False
        clients = []
        invoices = []

        try:
            cloud_clients = fetch_cloud_clients()
            cloud_invoices = fetch_cloud_invoices()
            if cloud_clients is not None and isinstance(cloud_clients, list) and len(cloud_clients) > 0:
                clients = cloud_clients
                invoices = cloud_invoices or []
                use_cloud = True
        except Exception:
            use_cloud = False

        if not use_cloud:
            clients = Client.query.all()
            invoices = Invoice.query.all()

        # Compute helpful groupings depending on source
        from datetime import date, timedelta
        today = date.today()

        if use_cloud:
            client_ids_with_invoices = set([int(i.get('client_id')) for i in invoices if i.get('client_id') is not None])
            active_clients = [c for c in clients if c.get('id') in client_ids_with_invoices]
            inactive_clients = [c for c in clients if c.get('id') not in client_ids_with_invoices]

            paid_invoices = [i for i in invoices if i.get('payment_status') == 'Paid']
            unpaid_invoices = [i for i in invoices if i.get('payment_status') != 'Paid']

            # Parse dates as strings 'YYYY-MM-DD' expected from cloud
            def parse_date(s):
                try:
                    return date.fromisoformat(s)
                except Exception:
                    return None

            today_revenue = 0
            week_revenue = 0
            month_revenue = 0
            outstanding = 0

            week_ago = today - timedelta(days=7)
            month_start = today.replace(day=1)

            for inv in invoices:
                amt = float(inv.get('total_amount', 0) or 0)
                status = inv.get('payment_status')
                inv_date = parse_date(inv.get('invoice_date'))
                if status == 'Paid' and inv_date:
                    if inv_date == today:
                        today_revenue += amt
                    if inv_date >= week_ago:
                        week_revenue += amt
                    if inv_date >= month_start:
                        month_revenue += amt
                if status != 'Paid':
                    outstanding += amt

        else:
            client_ids_with_invoices = set([i.client_id for i in invoices])
            active_clients = [c for c in clients if c.id in client_ids_with_invoices]
            inactive_clients = [c for c in clients if c.id not in client_ids_with_invoices]

            paid_invoices = [i for i in invoices if i.payment_status == 'Paid']
            unpaid_invoices = [i for i in invoices if i.payment_status != 'Paid']

            week_ago = today - timedelta(days=7)
            month_start = today.replace(day=1)

            today_revenue = db.session.query(func.sum(Invoice.total_amount)).filter(
                Invoice.payment_status == 'Paid',
                Invoice.invoice_date == today
            ).scalar() or 0

            week_revenue = db.session.query(func.sum(Invoice.total_amount)).filter(
                Invoice.payment_status == 'Paid',
                Invoice.invoice_date >= week_ago
            ).scalar() or 0

            month_revenue = db.session.query(func.sum(Invoice.total_amount)).filter(
                Invoice.payment_status == 'Paid',
                Invoice.invoice_date >= month_start
            ).scalar() or 0

            outstanding = db.session.query(func.sum(Invoice.total_amount)).filter(
                Invoice.payment_status != 'Paid'
            ).scalar() or 0
        
        # ===== GREETING AND HELP PATTERNS =====
        
        # Follow-up queries (check FIRST before greetings to avoid conflicts)
        if ('follow' in message and ('up' in message or 'client' in message or 'need' in message)) or ('which' in message and 'client' in message and 'need' in message):
            if len(unpaid_invoices) > 0:
                # Support both cloud (dicts) and local ORM objects
                if use_cloud:
                    client_ids = set([int(i.get('client_id')) for i in unpaid_invoices if i.get('client_id') is not None])
                    clients_needing_followup = [c.get('name') or c.get('email') for c in clients if c.get('id') in client_ids][:5]
                else:
                    client_ids = set([i.client_id for i in unpaid_invoices])
                    clients_needing_followup = [c.name for c in clients if c.id in client_ids][:5]

                return jsonify({'reply': f"📋 Clients needing follow-up: {', '.join(clients_needing_followup)}"})
            else:
                return jsonify({'reply': "🎉 No clients currently need follow-up for delayed payments."})
        
        # Greetings
        if any(word in message for word in ['hi', 'hello', 'hey', 'hai', 'good morning', 'good afternoon', 'good evening']):
            return jsonify({'reply': """👋 Hello! I'm your AI-powered business assistant. I can help you with:
            <br>• Creating invoices through voice commands
            <br>• Analyzing business performance and trends
            <br>• Predicting client payment behavior
            <br>• Generating insights and recommendations
            <br>• Automating routine tasks
            <br><br>How can I assist you today? 😊"""})
        
        # Help or capabilities
        if 'help' in message or 'what can you do' in message or 'capabilities' in message:
            return jsonify({'reply': """🤖 Here's what I can assist you with:
            <br><br>📊 Analytics & Insights:
            <br>• Revenue forecasting and trend analysis
            <br>• Client payment behavior predictions
            <br>• Business performance metrics
            <br><br>📄 Invoice Management:
            <br>• Create invoices via voice or text
            <br>• Smart item suggestions based on client history
            <br>• Automated pricing optimization
            <br><br>👥 Client Management:
            <br>• Risk assessment and scoring
            <br>• Follow-up recommendations
            <br>• Communication insights
            <br><br>Just ask me anything about your business!"""})
        
        # Thank you
        if 'thank' in message:
            return jsonify({'reply': "🙏 You're welcome! If you need anything else, just ask."})
        
        # Goodbye
        if any(word in message for word in ['bye', 'goodbye', 'exit', 'quit']):
            return jsonify({'reply': "👋 Goodbye! Have a productive day ahead."})
        
        # ===== NAVIGATION PATTERNS =====
        
        # Analytics Dashboard
        if ('analytics' in message or 'dashboard' in message) and ('show' in message or 'open' in message or 'go' in message or 'analytics' in message):
            return jsonify({
                'reply': "📊 Opening Analytics Dashboard... You'll see detailed insights about your business performance, revenue trends, and client analytics.",
                'action': 'navigate',
                'url': '/analytics'
            })
        
        # Create Invoice
        if ('create' in message or 'new' in message or 'make' in message) and 'invoice' in message:
            return jsonify({
                'reply': "📄 Opening Invoice Creation... You can create a new invoice for your clients.",
                'action': 'navigate',
                'url': '/create_invoice'
            })
        
        # Client Management
        if ('client' in message and 'management' in message) or ('show' in message and 'client' in message and 'management' in message):
            return jsonify({
                'reply': "👥 Opening Client Management... You can view and manage all your clients here.",
                'action': 'navigate',
                'url': '/clients'
            })
        
        # ===== NEW CONVERSATION PATTERNS =====
        
        # 1. Business Health Check
        if 'business health' in message or 'health check' in message or 'how is business' in message:
            health = '🟢 Healthy' if month_revenue > 0 else '🟡 Needs Attention'
            return jsonify({'reply': f"""❤️ <strong>Business Health Report:</strong>
            <br><br>• Status: {health}
            <br>• Active Clients: {len(active_clients)}
            <br>• Monthly Revenue: ₹{float(month_revenue):,.2f}
            <br>• Outstanding: ₹{float(outstanding):,.2f}
            <br>• Unpaid Invoices: {len(unpaid_invoices)}
            <br><br>💡 <em>Tip: Focus on following up with clients who have unpaid invoices to improve cash flow.</em>"""})
        
        # 2. Payment Predictions
        if 'predict' in message or 'forecast' in message:
            if 'revenue' in message or 'income' in message:
                projected = float(month_revenue) * 1.15
                return jsonify({'reply': f"""📈 <strong>Revenue Forecast:</strong>
                <br><br>• Current Month: ₹{float(month_revenue):,.2f}
                <br>• Projected Next Month: ₹{projected:,.2f}
                <br>• Growth Estimate: +15%
                <br><br>💡 Based on current trends and historical patterns."""})
            else:
                return jsonify({'reply': """🔮 <strong>Payment Predictions:</strong>
                <br><br>Based on historical data:
                <br>• Most clients pay within 7-14 days
                <br>• Early payers: Usually within 3-5 days
                <br>• Late payers: May take 20-30 days
                <br><br>💡 For specific client predictions, ask "When will [Client Name] pay?\""""})
        
        # 3. Comparative Analysis
        if 'compare' in message or 'comparison' in message or 'vs' in message or 'versus' in message:
            return jsonify({'reply': f"""📊 <strong>Comparative Analysis:</strong>
            <br><br><strong>This Week vs Last Week:</strong>
            <br>• Revenue: ₹{float(week_revenue):,.2f}
            <br><br><strong>This Month Performance:</strong>
            <br>• Total Revenue: ₹{float(month_revenue):,.2f}
            <br>• Active Clients: {len(active_clients)}
            <br>• Invoices Created: {len(invoices)}
            <br><br>💡 Visit the Analytics Dashboard for detailed comparisons."""})
        
        # 4. Top Clients Query
        if 'top client' in message or 'best client' in message or 'biggest client' in message:
            top_clients = clients[:5]
            if use_cloud:
                client_list = '<br>'.join([f"{i+1}. {c.get('name') or c.get('email') or ('Client '+str(c.get('id')))}" for i, c in enumerate(top_clients)])
            else:
                client_list = '<br>'.join([f"{i+1}. {c.name}" for i, c in enumerate(top_clients)])
            return jsonify({'reply': f"""🌟 <strong>Top Clients:</strong>
            <br><br>{client_list}
            <br><br>💡 These are your most active clients. Consider offering them loyalty benefits!"""})
        
        # 5. Outstanding Payments
        if 'outstanding' in message or ('pending' in message and 'payment' in message) or 'due' in message:
            return jsonify({'reply': f"""💳 <strong>Outstanding Payments:</strong>
            <br><br>• Total Outstanding: ₹{float(outstanding):,.2f}
            <br>• Unpaid Invoices: {len(unpaid_invoices)}
            <br><br>💡 <strong>Recommendation:</strong> Send payment reminders to clients with overdue invoices to improve cash flow."""})
        
        # 6. Reminder and Notification Queries
        if 'reminder' in message or 'notification' in message or 'alert' in message:
            return jsonify({'reply': f"""🔔 <strong>Active Reminders:</strong>
            <br><br>• {len(unpaid_invoices)} unpaid invoices need follow-up
            <br>• Outstanding amount: ₹{float(outstanding):,.2f}
            <br><br>💡 I recommend sending payment reminders to clients with overdue invoices."""})
        
        # 7. Recent Activity
        if 'recent' in message or 'latest' in message or 'last' in message:
            if 'payment' in message:
                return jsonify({'reply': f"""💰 <strong>Recent Payment Activity:</strong>
                <br><br>• Paid Invoices: {len(paid_invoices)}
                <br>• Pending Payments: {len(unpaid_invoices)}
                <br>• Today's Revenue: ₹{float(today_revenue):,.2f}
                <br><br>💡 Check the Analytics page for detailed payment trends."""})
            else:
                return jsonify({'reply': """📅 I can show you recent invoices, payments, or client activity. What would you like to see?"""})
        
        # 8. Export Data Requests
        if 'export' in message or 'download' in message:
            if 'invoice' in message:
                return jsonify({'reply': """📥 To export invoices:
                <br>1. Go to Invoice Management
                <br>2. Select the invoices you want to export
                <br>3. Click the "Export" button
                <br><br>You can export to PDF, Excel, or CSV formats."""})
            elif 'client' in message:
                return jsonify({'reply': """📥 To export client data:
                <br>1. Navigate to Client Management
                <br>2. Use the "Export Clients" option
                <br>3. Choose your preferred format (Excel/CSV)
                <br><br>All client information will be included in the export."""})
            else:
                return jsonify({'reply': """📥 You can export invoices, client data, and reports. What would you like to export?"""})
        
        # 9. How-to Guides
        if 'how to' in message or 'how do i' in message or 'how can i' in message:
            if 'create' in message and 'invoice' in message:
                return jsonify({'reply': """📝 <strong>How to Create an Invoice:</strong>
                <br><br>1. Click "Create Invoice" or say "Create new invoice"
                <br>2. Select the client
                <br>3. Add items/services
                <br>4. Set quantities and prices
                <br>5. Review and save
                <br><br>💡 You can also use voice commands to create invoices!"""})
            elif 'add' in message and 'client' in message:
                return jsonify({'reply': """👤 <strong>How to Add a Client:</strong>
                <br><br>1. Go to Client Management
                <br>2. Click "Add New Client"
                <br>3. Fill in client details (name, email, phone, address)
                <br>4. Save the client
                <br><br>💡 You can also import clients from a CSV file!"""})
            else:
                return jsonify({'reply': """🤔 I can guide you through various tasks. What would you like to learn how to do?"""})
        
        # ===== EXISTING PATTERNS =====
        
        # Client queries
        if 'client' in message:
            if 'how many' in message or 'total' in message or 'count' in message:
                return jsonify({'reply': f"👥 You have {len(clients)} clients in total."})
            elif 'active' in message:
                return jsonify({'reply': f"✅ Currently, you have {len(active_clients)} active clients."})
            elif 'inactive' in message:
                return jsonify({'reply': f"⚠️ You have {len(inactive_clients)} inactive clients."})
            elif 'list' in message or 'name' in message:
                if use_cloud:
                    client_names = ', '.join([c.get('name') or c.get('email') or f"Client {c.get('id')}" for c in clients[:10]])
                else:
                    client_names = ', '.join([c.name for c in clients[:10]])
                more = '...' if len(clients) > 10 else ''
                return jsonify({'reply': f"👥 Here are your clients: {client_names}{more}"})
        
        # Invoice queries
        if 'invoice' in message:
            if 'how many' in message or 'total' in message or 'count' in message:
                return jsonify({'reply': f"📄 You have {len(invoices)} invoices in total."})
            elif 'paid' in message:
                return jsonify({'reply': f"✅ {len(paid_invoices)} invoices have been paid."})
            elif 'unpaid' in message or 'pending' in message:
                return jsonify({'reply': f"⏳ There are {len(unpaid_invoices)} unpaid invoices."})
        
        # Revenue queries
        if 'revenue' in message or 'income' in message:
            if 'today' in message:
                return jsonify({'reply': f"💵 Today's revenue is ₹{float(today_revenue):,.2f}"})
            elif 'week' in message:
                return jsonify({'reply': f"📅 This week's revenue is ₹{float(week_revenue):,.2f}"})
            elif 'month' in message:
                return jsonify({'reply': f"📈 This month's revenue is ₹{float(month_revenue):,.2f}"})
        
        # AI Fallback for unhandled queries
        try:
            # Prepare context for AI
            business_context = f"""
            Current Business Status:
            - Monthly Revenue: ₹{float(month_revenue):,.2f}
            - Weekly Revenue: ₹{float(week_revenue):,.2f}
            - Today's Revenue: ₹{float(today_revenue):,.2f}
            - Outstanding Amount: ₹{float(outstanding):,.2f}
            - Active Clients: {len(active_clients)}
            - Total Invoices: {len(invoices)}
            - Paid Invoices: {len(paid_invoices)}
            - Unpaid Invoices: {len(unpaid_invoices)}
            """
            
            system_prompt = "You are a helpful business assistant for an invoice management system. " \
                            "Use the provided business context to answer the user's question accurately. " \
                            "Be concise, professional, and helpful. " \
                            "If the user asks to perform an action (Create Invoice, etc.), guide them."
            
            full_prompt = f"{system_prompt}\n\nContext:{business_context}\n\nUser Question: {message}\nAssistant:"
            
            reply = ai_client.generate_response(full_prompt)
            return jsonify({'reply': reply})
            
        except Exception as ai_error:
             app.logger.error(f"AI generation failed: {ai_error}")
             return jsonify({'reply': "I didn't understand that command. Try asking about revenue, clients, or specific invoices."})
            
    except Exception as e:
        logging.error(f"AI chat error: {e}")
        return jsonify({'reply': f"Sorry, I encountered an error: {str(e)}"})


def generate_quotation_number():
    last = Quotation.query.order_by(Quotation.id.desc()).first()
    next_id = 1 if not last else last.id + 1
    return f"QT-2026-{str(next_id).zfill(4)}"


# -------------------------
# Create Form
# -------------------------
@app.route("/quotations")
def quotation_form():
    return render_template(
        "quotation_form.html",
        quotation_no=generate_quotation_number()
    )

def safe_float(value):
    try:
        return float(value)
    except:
        return 0.0

# -------------------------
# Save Quotation
# -------------------------
@app.route("/quotations/create", methods=["POST"])
@login_required
def create_quotation():
    try:
        payload = {
            "quotation_number": request.form.get("quotation_number"),
            "quotation_date": request.form.get("quotation_date"),
            "status": request.form.get("status", "Draft"),
            "grand_total": float(request.form.get("grand_total", 0) or 0),
            "subtotal": float(request.form.get("subtotal", 0) or 0),
            "discount": float(request.form.get("discount", 0) or 0),
            "taxable_value": float(request.form.get("taxable_value", 0) or 0),
            "cgst": float(request.form.get("cgst", 0) or 0),
            "sgst": float(request.form.get("sgst", 0) or 0),
            "igst": float(request.form.get("igst", 0) or 0),
            "shipping": float(request.form.get("shipping", 0) or 0),
            "rounding": float(request.form.get("rounding", 0) or 0),
            "sales_person": request.form.get("sales_person"),
            "reference_id": request.form.get("reference_id"),
            "terms": request.form.get("terms"),
            "delivery_timeline": request.form.get("delivery_timeline"),
            "project_scope": request.form.get("project_scope"),
            "milestones": request.form.get("milestones"),
            "warranty": request.form.get("warranty"),
            "revision_policy": request.form.get("revision_policy"),
            "dependencies": request.form.get("dependencies"),
        }

        validity_days = request.form.get("validity_days")
        if validity_days:
            payload["validity_days"] = int(validity_days)

        expiry_date = request.form.get("expiry_date")
        if expiry_date:
            payload["expiry_date"] = expiry_date

        # Include line items if sent as JSON
        line_items_json = request.form.get("line_items")
        if line_items_json:
            try:
                payload["line_items"] = json.loads(line_items_json)
            except Exception:
                pass

        logging.debug(f"Quotation payload: {json.dumps(payload, indent=2, default=str)}")

        response = cloud_request(
            "POST",
            "/quotations",
            json=payload
        )

        if response is None:
            flash("API connection error: Unable to reach server", "error")
        elif response.status_code in (200, 201):
            flash("Quotation created successfully!", "success")
            return redirect(url_for("quotation_list"))
        else:
            error_msg = f"API error: {response.status_code} - {response.text}"
            logging.error(f"Quotation creation failed: {error_msg}")
            flash(error_msg, "error")

    except Exception as e:
        flash(f"API connection error: {str(e)}", "error")

    return redirect(url_for("quotation_form"))

@app.route("/quotations/<int:qid>/delete", methods=["POST"])
@login_required
def delete_quotation(qid):
    try:
        response = cloud_request("DELETE", f"/quotations/{qid}")
        if response and response.status_code in (200, 204):
            flash("Quotation deleted successfully!", "success")
        else:
            flash(f"Failed to delete quotation: {response.text if response else 'No response'}", "error")
    except Exception as e:
        flash(f"Cloud API error: {str(e)}", "error")
    return redirect(url_for("quotation_list"))


# -------------------------
# Preview
# -------------------------
@app.route("/quotations/preview/<int:qid>")
@login_required
def quotation_preview(qid):
    q_data = fetch_cloud_quotation_by_id(qid)
    if q_data:
        try:
            q = SimpleNamespace(
                id=q_data["id"],
                quotation_number=q_data["quotation_number"],
                quotation_date=datetime.strptime(
                    q_data["quotation_date"], "%Y-%m-%d"
                ) if q_data.get("quotation_date") else None,
                status=q_data.get("status"),
                grand_total=q_data.get("grand_total", 0),
                sales_person=q_data.get("sales_person", ""),
                reference_id=q_data.get("reference_id", ""),
                subtotal=q_data.get("subtotal", 0),
                discount=q_data.get("discount", 0),
                taxable_value=q_data.get("taxable_value", 0),
                cgst=q_data.get("cgst", 0),
                sgst=q_data.get("sgst", 0),
                igst=q_data.get("igst", 0),
                shipping=q_data.get("shipping", 0),
                rounding=q_data.get("rounding", 0),
                validity_days=q_data.get("validity_days"),
                expiry_date=datetime.strptime(
                    q_data["expiry_date"], "%Y-%m-%d"
                ) if q_data.get("expiry_date") and q_data["expiry_date"] != "None" else None,
                delivery_timeline=q_data.get("delivery_timeline", ""),
                project_scope=q_data.get("project_scope", ""),
                milestones=q_data.get("milestones", ""),
                warranty=q_data.get("warranty", ""),
                revision_policy=q_data.get("revision_policy", ""),
                dependencies=q_data.get("dependencies", ""),
                terms=q_data.get("terms", ""),
                line_items=[
                    SimpleNamespace(
                        sr_no=item.get("sr_no", i+1),
                        hsn_code=item.get("hsn_code", ""),
                        description=item.get("description", ""),
                        quantity=item.get("quantity", 0),
                        unit=item.get("unit", "Nos"),
                        unit_price=item.get("unit_price", 0),
                        tax_percentage=item.get("tax_percentage", 0),
                        tax_amount=item.get("tax_amount", 0),
                        total_amount=item.get("total_amount", 0)
                    )
                    for i, item in enumerate(q_data.get("line_items", []))
                ]
            )
            return render_template("quotation_preview.html", q=q)
        except Exception as e:
            logging.error(f"Error parsing quotation details: {e}")
            flash(f"Error parsing quotation: {str(e)}", "error")
            return redirect(url_for("quotation_list"))
    else:
        flash("Quotation not found", "error")
        return redirect(url_for("quotation_list"))


# -------------------------
# List
# -------------------------
@app.route("/quotations/list")
@login_required
def quotation_list():

    try:
        data = fetch_cloud_quotations()
        if not data:
            flash("No quotations found or API unavailable", "info")
            data = []

        # local tracking workaround for blocked Cloud API
        try:
            deleted_ids = [dq.quotation_id for dq in DeletedQuotation.query.all()]
            data = [q for q in data if q["id"] not in deleted_ids]
        except Exception as db_err:
            logging.error(f"Error filtering deleted quotations: {db_err}")

    except Exception as e:
        flash(f"API connection error: {str(e)}", "error")
        data = []

    quotation_list = []

    for q in data:
        quotation_obj = SimpleNamespace(
            id=q["id"],
            quotation_number=q["quotation_number"],
            quotation_date=datetime.strptime(
                q["quotation_date"], "%Y-%m-%d"
            ) if q.get("quotation_date") else None,
            status=q.get("status"),
            grand_total=q.get("grand_total", 0)
        )

        quotation_list.append(quotation_obj)

    quotations_obj = SimpleNamespace(
        items=quotation_list,
        total=len(quotation_list),
        pages=1,
        has_prev=False,
        has_next=False,
        page=1
    )

    return render_template(
        "quotation_list.html",
        quotations=quotations_obj
    )


# -------------------------
# Duplicate
# -------------------------
@app.route("/quotations/duplicate/<int:qid>")
@login_required
def duplicate_quotation(qid):
    try:
        # Fetch original quotation from API
        q_data = fetch_cloud_quotation_by_id(qid)
        
        if q_data:
            
            # Create duplicate via API
            new_payload = {
                "quotation_date": q_data.get("quotation_date"),
                "validity_days": q_data.get("validity_days"),
                "expiry_date": q_data.get("expiry_date"),
                "status": "Draft",
                "sales_person": q_data.get("sales_person"),
                "reference_id": q_data.get("reference_id"),
                "subtotal": q_data.get("subtotal"),
                "discount": q_data.get("discount"),
                "taxable_value": q_data.get("taxable_value"),
                "cgst": q_data.get("cgst"),
                "sgst": q_data.get("sgst"),
                "igst": q_data.get("igst"),
                "shipping": q_data.get("shipping"),
                "rounding": q_data.get("rounding"),
                "grand_total": q_data.get("grand_total"),
                "delivery_timeline": q_data.get("delivery_timeline"),
                "project_scope": q_data.get("project_scope"),
                "milestones": q_data.get("milestones"),
                "warranty": q_data.get("warranty"),
                "revision_policy": q_data.get("revision_policy"),
                "dependencies": q_data.get("dependencies"),
                "terms": q_data.get("terms")
            }
            
            create_response = cloud_request(
                "POST",
                "/quotations",
                json=new_payload
            )
            
            if create_response.status_code in (200, 201):
                new_q = create_response.json()
                flash("Quotation duplicated successfully!", "success")
                return redirect(url_for("quotation_preview", qid=new_q["id"]))
            else:
                flash("Failed to duplicate quotation", "error")
        else:
            flash("Original quotation not found", "error")
    except Exception as e:
        flash(f"Error duplicating quotation: {str(e)}", "error")
    
    return redirect(url_for("quotation_list"))


# -------------------------
# Cancel / Reject
# -------------------------
@app.route("/quotations/cancel/<int:qid>")
@login_required
def cancel_quotation(qid):
    try:
        response = cloud_request(
            "PUT",
            f"/quotations/{qid}",
            json={"status": "Cancelled"}
        )
        
        if response.status_code == 200:
            flash("Quotation has been cancelled.", "warning")
            return redirect(url_for("quotation_preview", qid=qid))
        # Fallback to query param if needed
        response = cloud_request(
            "PUT",
            f"/quotations?id={qid}",
            json={"status": "Cancelled"}
        )
        if response.status_code == 200:
            flash("Quotation has been cancelled.", "warning")
            return redirect(url_for("quotation_preview", qid=qid))
            
        flash("Failed to cancel quotation", "error")
    except Exception as e:
        flash(f"Error cancelling quotation: {str(e)}", "error")
    
    return redirect(url_for("quotation_list"))

'''
@app.route("/quotations/<int:qid>/delete")
@login_required
def delete_quotation(qid):
    """Delete quotation via Local tracking (Workaround for blocked Cloud API)"""
    try:
        # 1. Attempt Cloud API call for future-proofing
        # Using short timeout to not hang UI
        response = requests.delete(
            f"{CLOUD_API_BASE}/quotations?id={qid}",
            timeout=2
        )
        
        if response.status_code in (200, 204):
            flash("Quotation deleted successfully!", "success")
        else:
            # 2. If Cloud API fails (as expected), add to local DeletedQuotation table
            logging.warning(f"Cloud Deletion unavailable (Status {response.status_code}). Using local workaround for ID {qid}.")
            
            existing = DeletedQuotation.query.filter_by(quotation_id=qid).first()
            if not existing:
                new_deleted = DeletedQuotation(quotation_id=qid)
                db.session.add(new_deleted)
                db.session.commit()
            
            flash("Quotation marked as deleted.", "success")
            
    except Exception as e:
        logging.error(f"Error handling deletion, falling back to local: {e}")
        # Even on connection error, track it locally
        try:
            existing = DeletedQuotation.query.filter_by(quotation_id=qid).first()
            if not existing:
                new_deleted = DeletedQuotation(quotation_id=qid)
                db.session.add(new_deleted)
                db.session.commit()
            flash("Quotation marked as deleted (Local workaround).", "success")
        except Exception as db_err:
            flash(f"Error marking quotation as deleted: {str(db_err)}", "error")
    
    return redirect(url_for("quotation_list"))'''

@app.route("/quotations/<int:qid>/pdf")
@login_required
def quotation_pdf(qid):
    """Generate PDF for quotation - returns direct download response"""
    try:
        # Fetch quotation from API
        q_data = fetch_cloud_quotation_by_id(qid)
        
        if q_data:
            # Build client object from quotation API data
            client_obj = SimpleNamespace(
                name=q_data.get("client_name") or q_data.get("party_name") or "—",
                address=q_data.get("client_address") or q_data.get("party_address") or "",
                city=q_data.get("client_city") or q_data.get("party_city") or "",
                state=q_data.get("client_state") or q_data.get("party_state") or "",
                pincode=q_data.get("client_pincode") or q_data.get("party_pincode") or "",
                gstin=q_data.get("client_gstin") or q_data.get("party_gstin") or "—",
            )
            # If quotation has a client_id, fetch full client details
            client_id = q_data.get("client_id")
            if client_id:
                try:
                    client_res = cloud_request("GET", f"/clients/{client_id}")
                    if client_res and client_res.status_code == 200:
                        cd = client_res.json()
                        client_obj = SimpleNamespace(
                            name=cd.get("name") or "—",
                            address=cd.get("address") or "",
                            city=cd.get("city") or "",
                            state=cd.get("state") or "",
                            pincode=cd.get("pincode") or "",
                            gstin=cd.get("gstin") or "—",
                        )
                except Exception as ce:
                    logging.warning(f"Could not fetch client details for quotation PDF: {ce}")

            # Convert API data to SimpleNamespace for PDF generator
            quotation = SimpleNamespace(
                id=q_data["id"],
                quotation_number=q_data["quotation_number"],
                quotation_date=datetime.strptime(
                    q_data["quotation_date"], "%Y-%m-%d"
                ) if q_data.get("quotation_date") else None,
                status=q_data.get("status"),
                grand_total=q_data.get("grand_total", 0),
                sales_person=q_data.get("sales_person", ""),
                reference_id=q_data.get("reference_id", ""),
                subtotal=q_data.get("subtotal", 0),
                discount=q_data.get("discount", 0),
                taxable_value=q_data.get("taxable_value", 0),
                cgst=q_data.get("cgst", 0),
                sgst=q_data.get("sgst", 0),
                igst=q_data.get("igst", 0),
                shipping=q_data.get("shipping", 0),
                rounding=q_data.get("rounding", 0),
                validity_days=q_data.get("validity_days"),
                expiry_date=datetime.strptime(
                    q_data["expiry_date"], "%Y-%m-%d"
                ) if q_data.get("expiry_date") and q_data["expiry_date"] != "None" else None,
                delivery_timeline=q_data.get("delivery_timeline", ""),
                project_scope=q_data.get("project_scope", ""),
                milestones=q_data.get("milestones", ""),
                warranty=q_data.get("warranty", ""),
                revision_policy=q_data.get("revision_policy", ""),
                dependencies=q_data.get("dependencies", ""),
                terms=q_data.get("terms", ""),
                client=client_obj,
                line_items=[
                    SimpleNamespace(
                        sr_no=item.get("sr_no", i+1),
                        hsn_code=item.get("hsn_code", ""),
                        description=item.get("description", item.get("item_name", "")),
                        quantity=item.get("quantity", 0),
                        unit=item.get("unit", "Nos"),
                        unit_price=item.get("unit_price", 0),
                        tax_percentage=item.get("tax_percentage", 0),
                        tax_amount=item.get("tax_amount", 0),
                        total_amount=item.get("total_amount", 0)
                    )
                    for i, item in enumerate(q_data.get("line_items", []))
                ]
            )

            # Fetch company, bank, logo and signature (same as invoice PDF route)
            company_res = cloud_request("GET", "/company")
            company = SimpleNamespace(**company_res.json()) if company_res and company_res.status_code == 200 else None

            bank_res = cloud_request("GET", "/bank-details")
            bank = SimpleNamespace(**bank_res.json()) if bank_res and bank_res.status_code == 200 else None

            logo_res = cloud_request("GET", "/company/logo")
            logo_bytes = logo_res.content if logo_res and logo_res.status_code == 200 else None

            signature_res = cloud_request("GET", "/company/signature")
            signature_bytes = signature_res.content if signature_res and signature_res.status_code == 200 else None

            # Generate quotation PDF with invoice-style layout
            pdf_buffer = generate_quotation_pdf(quotation, company=company, bank=bank,
                                                logo_bytes=logo_bytes, signature_bytes=signature_bytes)
            pdf_buffer.seek(0)
            
            filename = f'Quotation_{quotation.quotation_number}.pdf'
            
            # Save to local Downloads for Desktop EXE support
            saved_path = save_pdf_to_downloads(pdf_buffer, filename)
            if saved_path:
                flash(f"PDF saved to: {saved_path}", "success")
            
            # Return as attachment for direct browser download
            from urllib.parse import quote
            encoded_filename = quote(filename)
            return Response(
                pdf_buffer.getvalue(),
                mimetype='application/pdf',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded_filename}',
                    'Content-Type': 'application/pdf'
                }
            )
        else:
            flash("Quotation not found on Cloud API", "error")
            return redirect(url_for("quotation_list"))
            
    except Exception as e:
        logging.error(f"Quotation PDF generation failed: {e}", exc_info=True)
        flash(f"Failed to generate PDF: {str(e)}", "error")
        return redirect(url_for("quotation_list"))


@app.route("/quotations/<int:qid>/convert")
@login_required
def convert_to_invoice(qid):
    try:
        response = cloud_request(
            "PUT",
            f"/quotations/{qid}",
            json={"status": "Converted to Invoice"}
        )
        
        if response.status_code == 200:
            flash("Quotation converted to Invoice successfully!", "success")
        else:
            # Fallback to query param
            response = cloud_request(
                "PUT",
                f"/quotations?id={qid}",
                json={"status": "Converted to Invoice"}
            )
            if response.status_code == 200:
                flash("Quotation converted to Invoice successfully!", "success")
            else:
                flash("Failed to convert quotation", "error")
    except Exception as e:
        flash(f"Error converting quotation: {str(e)}", "error")
    
    return redirect(url_for("quotation_list"))
@app.route("/quotations/<int:qid>/send-email")
@login_required
def send_email(qid):
    try:
        response = cloud_request(
            "GET",
            f"/quotations?id={qid}"
        )
        
        if response.status_code == 200:
            q_data = response.json()
            if isinstance(q_data, list) and q_data:
                q_data = next((item for item in q_data if str(item.get('id')) == str(qid)), None)
            
            if q_data:
                # TEMP DEMO (replace with real email later)
                print("Sending email for quotation:", q_data.get("quotation_number"))
                flash("Email sent successfully (demo).", "success")
            else:
                flash("Quotation not found", "error")
        else:
            flash("Quotation not found", "error")
    except Exception as e:
        flash(f"Error sending email: {str(e)}", "error")
    
    return redirect(url_for("quotation_list"))


@app.route("/quotations/<int:qid>/send-whatsapp")
@login_required
def send_whatsapp(qid):
    try:
        response = cloud_request(
            "GET",
            f"/quotations?id={qid}"
        )
        
        if response.status_code == 200:
            q_data = response.json()
            if isinstance(q_data, list) and q_data:
                q_data = next((item for item in q_data if str(item.get('id')) == str(qid)), None)
            
            if q_data:
                # TEMP DEMO
                print("Sending WhatsApp for quotation:", q_data.get("quotation_number"))
                flash("WhatsApp sent successfully (demo).", "success")
            else:
                flash("Quotation not found", "error")
        else:
            flash("Quotation not found", "error")
    except Exception as e:
        flash(f"Error sending WhatsApp: {str(e)}", "error")
    
    return redirect(url_for("quotation_list"))

@app.route("/quotations/<int:qid>/edit", methods=["GET", "POST"])
@login_required
def edit_quotation(qid):
    if request.method == "POST":
        try:
            payload = {
                "quotation_date": request.form.get("quotation_date"),
                "status": request.form.get("status"),
                "validity_days": int(request.form.get("validity_days", 15) or 15),
                "sales_person": request.form.get("sales_person"),
                "reference_id": request.form.get("reference_id"),
                "terms": request.form.get("terms"),
                "delivery_timeline": request.form.get("delivery_timeline"),
                "project_scope": request.form.get("project_scope"),
                "milestones": request.form.get("milestones"),
                "warranty": request.form.get("warranty"),
                "revision_policy": request.form.get("revision_policy"),
                "dependencies": request.form.get("dependencies"),
                "subtotal": float(request.form.get("subtotal", 0) or 0),
                "discount": float(request.form.get("discount", 0) or 0),
                "taxable_value": float(request.form.get("taxable_value", 0) or 0),
                "cgst": float(request.form.get("cgst", 0) or 0),
                "sgst": float(request.form.get("sgst", 0) or 0),
                "igst": float(request.form.get("igst", 0) or 0),
                "shipping": float(request.form.get("shipping", 0) or 0),
                "rounding": float(request.form.get("rounding", 0) or 0),
                "grand_total": float(request.form.get("grand_total", 0) or 0),
            }

            response = cloud_request(
                "PUT",
                f"/quotations/{qid}",
                json=payload
            )

            if response is None:
                flash("API connection error", "error")
            elif response.status_code == 200:
                flash("Quotation updated successfully!", "success")
                return redirect(url_for("quotation_list"))
            else:
                flash(f"Failed to update quotation: {response.status_code} - {response.text}", "error")
        except Exception as e:
            flash(f"Error updating quotation: {str(e)}", "error")
            
    q_data = fetch_cloud_quotation_by_id(qid)
    if not q_data:
        flash("Quotation not found", "error")
        return redirect(url_for("quotation_list"))
    
    # Convert to SimpleNamespace for consistency in template
    q = SimpleNamespace(
        id=q_data["id"],
        quotation_number=q_data["quotation_number"],
        quotation_date=datetime.strptime(q_data["quotation_date"], "%Y-%m-%d") if q_data.get("quotation_date") else None,
        validity_days=q_data.get("validity_days", 15),
        expiry_date=datetime.strptime(q_data["expiry_date"], "%Y-%m-%d") if q_data.get("expiry_date") else None,
        status=q_data.get("status"),
        sales_person=q_data.get("sales_person", ""),
        reference_id=q_data.get("reference_id", ""),
        subtotal=q_data.get("subtotal", 0),
        discount=q_data.get("discount", 0),
        taxable_value=q_data.get("taxable_value", 0),
        cgst=q_data.get("cgst", 0),
        sgst=q_data.get("sgst", 0),
        igst=q_data.get("igst", 0),
        shipping=q_data.get("shipping", 0),
        rounding=q_data.get("rounding", 0),
        grand_total=q_data.get("grand_total", 0),
        delivery_timeline=q_data.get("delivery_timeline", ""),
        project_scope=q_data.get("project_scope", ""),
        milestones=q_data.get("milestones", ""),
        warranty=q_data.get("warranty", ""),
        revision_policy=q_data.get("revision_policy", ""),
        dependencies=q_data.get("dependencies", ""),
        terms=q_data.get("terms", "")
    )
    
    return render_template("quotation_form.html", q=q, is_edit=True)



@app.route('/dashboard')
@login_required
def dashboard_page():

    # ✅ REQUIRED BY TEMPLATE
    today = date.today()

    try:
        invoices = fetch_cloud_invoices()
        clients = fetch_cloud_clients()
    except Exception as e:
        logging.error(f"Dashboard cloud fetch failed: {e}")
        invoices = []
        clients = []

    recent_invoices = []

    for inv in invoices[:10]:
        invoice_obj = SimpleNamespace(
            id=inv.get("id"),
            invoice_number=inv.get("invoice_number"),
            total_amount=inv.get("total_amount", 0),
            amount_paid=inv.get("amount_paid", 0),
            payment_status=inv.get("payment_status"),
            client=SimpleNamespace(
                name=inv.get("client_name", "Unknown")
            )
        )
        recent_invoices.append(invoice_obj)

    # 📊 Compute Metrics from Cloud Data
    rev_trends = analytics_engine.compute_revenue_trends(invoices)
    monthly_revenue = rev_trends.get('monthly_data', [])
    
    # Calculate totals
    monthly_revenue_total = sum(item['revenue'] for item in monthly_revenue)
    
    # Calculate growth (latest month vs previous)
    revenue_growth = 0
    if monthly_revenue:
        revenue_growth = monthly_revenue[-1].get('growth_rate', 0)

    outstanding_amount = sum(
        float(inv.get('total_amount', 0)) - float(inv.get('amount_paid', 0))
        for inv in invoices 
        if inv.get('payment_status') != 'Paid'
    )

    # Calculate recent invoices count (last 30 days)
    thirty_days_ago = today - timedelta(days=30)
    new_invoices_count = 0
    for inv in invoices:
        inv_date_str = inv.get('invoice_date')
        if inv_date_str:
            try:
                inv_date = datetime.strptime(inv_date_str, '%Y-%m-%d').date()
                if inv_date >= thirty_days_ago:
                    new_invoices_count += 1
            except ValueError:
                pass

    return render_template(
        "dashboard.html",

        # 🔑 MUST-HAVE VARIABLES
        today=today,
        recent_invoices=recent_invoices,

        # 🔑 METRICS (Calculated)
        monthly_revenue_total=monthly_revenue_total,
        revenue_growth=revenue_growth,
        outstanding_amount=outstanding_amount,
        total_invoices=len(invoices),
        new_invoices_count=new_invoices_count,
        total_clients=len(clients),

        # 🔑 CHART
        monthly_revenue=monthly_revenue,

        # 🔑 OPTIONAL SECTIONS (prevent crashes)
        ai_insights={},
        upcoming_payments=[],
        blockchain_stats=None
    )



@app.route('/api/voice_command_regex', methods=['POST'])
@login_required
def voice_command_api():
    """
    Process voice commands using script-based pattern matching
    No AI/API dependencies - Pure regex matching
    """
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        language = data.get('language', 'en-IN')
        
        if not text:
            return jsonify({
                'success': False,
                'message': 'No voice input received',
                'intent': 'error'
            }), 400
        
        logging.info(f"🎤 Voice command received: '{text}' (Language: {language})")
        
        # Get voice processor
        voice_processor = get_voice_processor()
        
        # Process command
        result = voice_processor.process(text, language)
        
        logging.info(f"✅ Voice command processed: {result.get('intent')}")
        
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"❌ Voice command API error: {e}")
        return jsonify({
            'success': False,
            'message': 'Error processing voice command',
            'error': str(e),
            'intent': 'error'
        }), 500


@app.route('/api/voice-session/status', methods=['GET'])
@login_required
def voice_session_status():
    """Get current voice session status"""
    try:
        voice_session = get_voice_session()
        
        return jsonify({
            'success': True,
            'has_active_invoice': voice_session.has_active_invoice(),
            'client_name': voice_session.active_invoice['client'].name if voice_session.active_invoice['client'] else None,
            'item_count': len(voice_session.active_invoice['items']),
            'total_amount': voice_session.get_total()
        })
        
    except Exception as e:
        logging.error(f"Voice session status error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/voice-session/clear', methods=['POST'])
@login_required
def voice_session_clear():
    """Clear voice session"""
    try:
        voice_session = get_voice_session()
        voice_session.clear()
        
        return jsonify({
            'success': True,
            'message': 'Voice session cleared'
        })
        
    except Exception as e:
        logging.error(f"Voice session clear error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500




@app.route("/challan/<int:id>/details")
@login_required
def challan_details(id):
    try:
        response = cloud_request("GET", f"/challans/{id}")

        if not response or response.status_code != 200:
            return "<div class='text-danger'>Failed to fetch challan details.</div>"

        challan = response.json()
        line_items = challan.get("line_items", [])

        total = 0
        items_html = ""

        for item in line_items:
            qty = float(item.get("quantity", 0))
            price = float(item.get("unit_price", 0))
            cgst = float(item.get("cgst_percentage", 0))
            sgst = float(item.get("sgst_percentage", 0))
            igst = float(item.get("igst_percentage", 0))
            tax_amt = float(item.get("tax_amount", 0))
            total_amt = float(item.get("total_amount", 0))

            total += total_amt

            items_html += f"""
            <tr>
                <td>{item.get('sr_no', '')}</td>
                <td>{item.get('description', '')}</td>
                <td>{item.get('hsn_code', '')}</td>
                <td>{qty}</td>
                <td>{item.get('unit', '')}</td>
                <td>₹{price:,.2f}</td>
                <td>{cgst:.2f}%</td>
                <td>{sgst:.2f}%</td>
                <td>{igst:.2f}%</td>
                <td>₹{tax_amt:,.2f}</td>
                <td>₹{total_amt:,.2f}</td>
            </tr>
            """

        return f"""
        <div class="row">
            <div class="col-md-6">
                <h6><strong>Challan Info</strong></h6>
                <p><strong>Number:</strong> {challan.get('challan_number')}</p>
                <p><strong>Date:</strong> {challan.get('challan_date')}</p>
                <p><strong>Delivery Date:</strong> {challan.get('delivery_date')}</p>
                <p><strong>Status:</strong> {challan.get('status')}</p>
            </div>
            <div class="col-md-6">
                <h6><strong>Client Info</strong></h6>
                <p><strong>Name:</strong> {challan.get('client', {}).get('name')}</p>
                <p><strong>Phone:</strong> {challan.get('client', {}).get('phone')}</p>
                <p><strong>Email:</strong> {challan.get('client', {}).get('email')}</p>
                <p><strong>Address:</strong> {challan.get('client', {}).get('address')}</p>
            </div>
        </div>

        <hr>

        <h6><strong>Line Items</strong></h6>
        <div class="table-responsive">
            <table class="table table-bordered">
                <thead class="table-light">
                    <tr>
                        <th>Sr</th>
                        <th>Description</th>
                        <th>HSN</th>
                        <th>Qty</th>
                        <th>Unit</th>
                        <th>Price</th>
                        <th>CGST %</th>
                        <th>SGST %</th>
                        <th>IGST %</th>
                        <th>Tax</th>
                        <th>Total</th>
                    </tr>
                </thead>
                <tbody>
                    {items_html}
                </tbody>
                <tfoot>
                    <tr>
                        <td colspan="10" class="text-end"><strong>Grand Total:</strong></td>
                        <td><strong>₹{total:,.2f}</strong></td>
                    </tr>
                </tfoot>
            </table>
        </div>

        <p><strong>Notes:</strong> {challan.get('notes', '')}</p>
        """

    except Exception as e:
        return f"<div class='text-danger'>Error loading challan details: {str(e)}</div>"



@app.route('/convert_challan_to_invoice/<int:id>')
@login_required
def convert_challan_to_invoice(id):
    try:
        # 🔹 Fetch challan from cloud
        challan_data = fetch_cloud_challan_by_id(id)

        if not challan_data:
            flash('Challan not found in cloud database.', 'error')
            return redirect(url_for('delivery_challan'))

        if challan_data.get('status') == 'Billed':
            flash('This challan has already been converted to an invoice.', 'warning')
            return redirect(url_for('delivery_challan'))

        client_id = challan_data.get('client_id')
        line_items = challan_data.get('line_items', [])

        if not line_items:
            flash('Challan has no line items.', 'error')
            return redirect(url_for('delivery_challan'))

        # 🔹 Generate Invoice Number
        cloud_invoices = fetch_cloud_invoices()
        current_year = datetime.now().year
        max_seq = 0

        if cloud_invoices:
            for inv in cloud_invoices:
                inv_num = inv.get('invoice_number', '')
                if inv_num and inv_num.startswith(f'INV-{current_year}-'):
                    try:
                        seq = int(inv_num.split('-')[-1])
                        if seq > max_seq:
                            max_seq = seq
                    except:
                        pass

        new_seq = max_seq + 1
        invoice_number = f"INV-{current_year}-{new_seq:04d}"

        # 🔹 Build invoice line items
        invoice_items = []

        for item in line_items:

            invoice_items.append({
                'sr_no': item.get('sr_no', 0),
                'hsn_code': item.get('hsn_code', ''),
                'description': item.get('description', ''),
                'quantity': float(item.get('quantity', 0) or 0),
                'unit': item.get('unit', 'Nos'),
                'unit_price': float(item.get('unit_price', 0) or 0),

                # ✅ SEND GST % ONLY (invoice API will calculate totals)
                'cgst_percentage': float(item.get('cgst_percentage', 0) or 0),
                'sgst_percentage': float(item.get('sgst_percentage', 0) or 0),
                'igst_percentage': float(item.get('igst_percentage', 0) or 0)
            })

        # 🔹 Optional fields
        due_date = request.args.get('due_date', '')
        notes = request.args.get('notes', '')

        invoice_data = {
            'invoice_number': invoice_number,
            'client_id': client_id,
            'invoice_date': datetime.now().strftime('%Y-%m-%d'),
            'due_date': due_date if due_date else None,
            'notes': f"Converted from Challan {challan_data.get('challan_number', '')}. {notes}".strip(),
            'terms_conditions': 'Standard Terms Applied',
            'payment_status': 'Unpaid',
            'line_items': invoice_items
        }

        # 🔹 Create Invoice via Cloud API
        response = cloud_request(
            "POST",
            "/invoices",
            json=invoice_data,
            timeout=10
        )

        if response and response.status_code in (200, 201):

            # 🔹 Update Challan Status to Billed
            cloud_request(
                "PUT",
                f"/challans/{id}",
                json={'status': 'Billed'},
                timeout=5
            )

            flash(
                f'Challan {challan_data.get("challan_number", "")} converted to invoice successfully!',
                'success'
            )
            return redirect(url_for('invoice_management'))

        else:
            error_msg = response.text if response else "Cloud server not reachable"
            flash(f'Failed to create invoice: {error_msg}', 'error')
            return redirect(url_for('delivery_challan'))

    except Exception as e:
        logging.error(f"Conversion failed: {e}")
        flash(f'Error converting challan: {str(e)}', 'error')
        return redirect(url_for('delivery_challan'))




@app.route('/convert_multiple_challans_to_invoice')
@login_required
def convert_multiple_challans_to_invoice():
    try:
        challan_ids_str = request.args.get('challan_ids', '')
        consolidation_option = request.args.get('consolidation_option', 'merge')
        due_date = request.args.get('due_date', '')
        notes = request.args.get('notes', '')

        if not challan_ids_str:
            flash('No challans selected.', 'error')
            return redirect(url_for('delivery_challan'))

        challan_ids = [int(id_str.strip()) for id_str in challan_ids_str.split(',') if id_str.strip()]
        
        challans = []
        for cid in challan_ids:
            c_data = fetch_cloud_challan_by_id(cid)
            if c_data:
                challans.append(c_data)
            else:
                flash(f'Challan ID {cid} not found.', 'error')
                return redirect(url_for('delivery_challan'))

        if not challans:
            flash('No valid challans found.', 'error')
            return redirect(url_for('delivery_challan'))

        # Verify all challans belong to the same client
        client_id = challans[0].get('client_id')
        for c in challans:
            if c.get('client_id') != client_id:
                flash('All selected challans must belong to the same client.', 'error')
                return redirect(url_for('delivery_challan'))

        # Consolidate line items
        consolidated_items = []
        item_map = {} # Used for 'merge' option

        for c in challans:
            c_num = c.get('challan_number', 'Unknown')
            for item in c.get('line_items', []):
                qty = float(item.get('quantity', 0))
                price = float(item.get('unit_price', 0))
                desc = item.get('description', '').strip()
                hsn = item.get('hsn_code', '').strip()
                unit = item.get('unit', '')

                if consolidation_option == 'merge':
                    key = (desc, hsn, price)
                    if key in item_map:
                        item_map[key]['quantity'] += qty
                        item_map[key]['total_amount'] += (qty * price)
                    else:
                        item_map[key] = {
                            'hsn_code': hsn,
                            'description': desc,
                            'quantity': qty,
                            'unit': unit,
                            'unit_price': price,
                            'total_amount': qty * price
                        }
                else: # 'group' option
                    consolidated_items.append({
                        'hsn_code': hsn,
                        'description': f"[{c_num}] {desc}",
                        'quantity': qty,
                        'unit': unit,
                        'unit_price': price,
                        'total_amount': qty * price
                    })

        if consolidation_option == 'merge':
            for i, (key, item) in enumerate(item_map.items(), 1):
                item['sr_no'] = i
                consolidated_items.append(item)
        else:
            for i, item in enumerate(consolidated_items, 1):
                item['sr_no'] = i

        total_amt = sum(item['total_amount'] for item in consolidated_items)

        # Determine next invoice number
        cloud_invoices = fetch_cloud_invoices()
        current_year = datetime.now().year
        max_seq = 0
        if cloud_invoices:
            for inv in cloud_invoices:
                inv_num = inv.get('invoice_number', '')
                if inv_num and inv_num.startswith(f'INV-{current_year}-'):
                    try:
                        seq = int(inv_num.split('-')[-1])
                        if seq > max_seq:
                            max_seq = seq
                    except:
                        pass
        
        new_seq = max_seq + 1
        invoice_number = f"INV-{current_year}-{new_seq:04d}"

        source_challans = ", ".join([c.get('challan_number', '') for c in challans])
        invoice_data = {
            'invoice_number': invoice_number,
            'client_id': client_id,
            'invoice_date': datetime.now().strftime('%Y-%m-%d'),
            'due_date': due_date if due_date else None,
            'notes': f"Consolidated from Challans: {source_challans}. {notes}".strip(),
            'terms_conditions': 'Standard Terms Applied',
            'total_amount': total_amt,
            'subtotal': total_amt,
            'payment_status': 'Unpaid',
            'line_items': consolidated_items
        }

        response = cloud_request(
            "POST",
            "/invoices",
            json=invoice_data,
            timeout=10
        )

        if response and response.status_code in (200, 201):
            # Update all challans' status to Billed
            for cid in challan_ids:
                cloud_request(
                    "PUT",
                    f"/challans/{cid}",
                    json={'status': 'Billed'},
                    timeout=5
                )
            flash(f'Consolidated Challan {invoice_number} generated successfully!', 'success')
            return redirect(url_for('invoice_management'))
        else:
            error_msg = response.text if response else "Cloud server not reachable"
            flash(f'Failed to generate consolidated challan: {error_msg}', 'error')
            return redirect(url_for('delivery_challan'))

    except Exception as e:
        logging.error(f"Consolidated conversion failed: {e}")
        flash(f'Error generating consolidated challan: {str(e)}', 'error')
        return redirect(url_for('delivery_challan'))



@app.route('/challan/<int:id>/pdf')
@login_required
def challan_pdf(id):
    """Generate PDF for delivery challan from cloud data"""
    try:
        # Fetch challan from cloud
        challan_data = fetch_cloud_challan_by_id(id)
        if not challan_data:
            flash('Challan not found in cloud database.', 'error')
            return redirect(url_for('delivery_challan'))
        
        # Fetch client data
        client_id = challan_data.get('client_id')
        client_data = fetch_cloud_client_by_id(client_id) if client_id else {}
        if not client_data:
            client_data = {'name': challan_data.get('client_name', 'Unknown'), 'id': client_id}
        
        # Build SimpleNamespace client object
        client = SimpleNamespace(**client_data)
        
        # Parse dates
        challan_date = datetime.strptime(challan_data['challan_date'], '%Y-%m-%d').date() if challan_data.get('challan_date') else datetime.now().date()
        delivery_date = datetime.strptime(challan_data['delivery_date'], '%Y-%m-%d').date() if challan_data.get('delivery_date') else None
        
        # Create challan object for PDF generator
        challan = DeliveryChallan(
            challan_number=challan_data.get('challan_number', ''),
            client_id=client_id,
            challan_date=challan_date,
            delivery_date=delivery_date,
            notes=challan_data.get('notes', ''),
            status=challan_data.get('status', '')
        )
        challan.id = challan_data.get('id')
        challan.preview_client = client
        
        # Build line items
        line_items = []
        for item in challan_data.get('line_items', []):
            li = ChallanLineItem(
                sr_no=int(item.get('sr_no', 0)),
                hsn_code=item.get('hsn_code', ''),
                description=item.get('description', ''),
                quantity=float(item.get('quantity', 0)),
                unit=item.get('unit', ''),
                unit_price=float(item.get('unit_price', 0)),
                total_amount=float(item.get('quantity', 0)) * float(item.get('unit_price', 0))
            )
            line_items.append(li)
        
        challan.line_items = line_items
        
        # Fetch company from cloud API
        company_res = cloud_request("GET", "/company")
        company = SimpleNamespace(**company_res.json()) if company_res and company_res.status_code == 200 else None

        # Generate PDF
        pdf_buffer = generate_challan_pdf(challan, company=company)
        pdf_buffer.seek(0)
        
        filename = f'Challan_{challan.challan_number}.pdf'
        
        # Save to local Downloads for Desktop EXE support
        saved_path = save_pdf_to_downloads(pdf_buffer, filename)
        if saved_path:
            flash(f"PDF saved to: {saved_path}", "success")
        
        from urllib.parse import quote
        encoded_filename = quote(filename)
        return Response(
            pdf_buffer.getvalue(),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded_filename}',
                'Content-Type': 'application/pdf'
            }
        )
        
    except Exception as e:
        logging.error(f"Challan PDF generation failed: {e}")
        flash(f'Error generating PDF: {str(e)}', 'error')
        return redirect(url_for('delivery_challan'))


@app.route("/test_email")
def test_email():
    from email_service import send_email
    send_email(
        "dharanimenaga229@gmail.com",
        "Test Invoice Email",
        "<h3>This is a test email.</h3>"
    )
    return "Test Email Sent"






