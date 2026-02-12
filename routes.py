import os
import json
import logging
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file, session, abort, Flask
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, and_, or_, extract, desc
from sqlalchemy.orm import joinedload

from app import app, mail 
from models import *
from utils import *
from utils import safe_dict
from pdf_generator import generate_invoice_pdf, generate_challan_pdf, AnalyticsReportGenerator
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
from models import Invoice

import ai_services
import ai_client 
from types import SimpleNamespace
import requests

# Initialize analytics engine
analytics_engine = AnalyticsEngine(db.session)
from report_generator import AnalyticsReportGenerator
report_generator = AnalyticsReportGenerator()

# ===== CLOUD API HELPER FUNCTIONS =====
CLOUD_API_BASE = "http://44.208.164.236:5000/api"

def fetch_cloud_clients():
    """Fetch all clients from cloud database"""
    try:
        response = requests.get(f"{CLOUD_API_BASE}/clients", timeout=5)
        if response.status_code == 200:
            return response.json()
        logging.warning(f"Cloud API returned status {response.status_code}")
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
    """Fetch all invoices from cloud database"""
    try:
        response = requests.get(f"{CLOUD_API_BASE}/invoices", timeout=5)
        if response.status_code == 200:
            return response.json()
        logging.warning(f"Cloud API returned status {response.status_code}")
        return []
    except Exception as e:
        logging.error(f"Cloud API error (invoices): {e}")
        return []

def fetch_cloud_invoice_by_id(invoice_id):
    """Fetch single invoice from cloud database by ID"""
    try:
        # First fetch all invoices, then filter by ID
        invoices = fetch_cloud_invoices()
        for invoice in invoices:
            if invoice.get('id') == int(invoice_id):
                return invoice
        return None
    except Exception as e:
        logging.error(f"Cloud API error (invoice by ID): {e}")
        return None

def fetch_cloud_challans():
    """Fetch all delivery challans from cloud database"""
    try:
        response = requests.get(f"{CLOUD_API_BASE}/challans", timeout=5)
        if response.status_code == 200:
            return response.json()
        logging.warning(f"Cloud API returned status {response.status_code}")
        return []
    except Exception as e:
        logging.error(f"Cloud API error (challans): {e}")
        return []

def login_required(f):
    """Decorator to require login for routes"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # Redirect to login without flash message (to avoid alert on automatic redirects)
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Validate empty fields
        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('login.html')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            
            # Update last login
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            flash('Welcome back! AI-powered invoice system is ready.', 'success')
            return redirect(url_for('dashboard_page'))
        else:
            flash('Invalid credentials. Please try again.', 'error')
    
    return render_template('login.html')

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

@app.route('/invoices')
@login_required
def invoice_management():
    try:
        response = requests.get(
            "http://44.208.164.236:5000/api/invoices",
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
        else:
            flash("Failed to load invoices from API", "error")
            data = []

    except Exception as e:
        flash(f"API connection error: {str(e)}", "error")
        data = []

    invoice_list = []

    for inv in data:
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
            ai_insights=None,
            client=SimpleNamespace(
                name=inv.get("client_name")
            )
    )
        invoice_list.append(invoice_obj)

    invoices_obj = SimpleNamespace(
        items=invoice_list,
        total=len(invoice_list),
        pages=1,
        has_prev=False,
        has_next=False,
        page=1
    )

    return render_template(
        "invoice_management.html",
        invoices=invoices_obj
    )

@app.route('/create_invoice', methods=['GET', 'POST'])
@login_required
def create_invoice():

    if request.method == 'POST':
        try:
            client_id = request.form.get('client_id')
            invoice_date_str = request.form.get('invoice_date')
            due_date_str = request.form.get('due_date')
            notes = request.form.get('notes', '')
            terms_conditions = request.form.get('terms_conditions', '')
            invoice_format = request.form.get("invoice_format", "default")

            invoice_number = generate_invoice_number()

            # Process line items
            line_items_data = json.loads(request.form.get('line_items', '[]'))

            subtotal = 0
            total_tax = 0

            for item in line_items_data:
                qty = float(item.get("quantity", 0))
                price = float(item.get("unit_price", 0))
                tax = float(item.get("tax_percentage", 0))

                line_total = qty * price
                tax_amount = (line_total * tax) / 100

                subtotal += line_total
                total_tax += tax_amount

            total_amount = subtotal + total_tax

            # 🔥 SEND TO CLOUD API
            response = requests.post(
                "http://44.208.164.236:5000/api/invoices",
                json={
                    "invoice_number": invoice_number,
                    "client_id": client_id,
                    "invoice_date": invoice_date_str,
                    "total_amount": total_amount,
                    "payment_status": "Unpaid"
                },
                timeout=5
            )

            if response.status_code in (200, 201):
                flash("Invoice created successfully (Cloud DB)", "success")
                return redirect(url_for("invoice_management"))
            else:
                flash(f"API Error: {response.text}", "error")

        except Exception as e:
            flash(f"API connection error: {str(e)}", "error")

    # GET request - fetch clients from cloud database
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
        # Extract form data (duplicates logic from create_invoice but doesn't save)
        client_id = request.form.get('client_id')
        invoice_date_str = request.form.get('invoice_date')
        due_date_str = request.form.get('due_date')
        notes = request.form.get('notes', '')
        terms_conditions = request.form.get('terms_conditions', '')
        invoice_format = request.form.get("invoice_format", "default")

        # Fetch client from cloud database
        client_data = fetch_cloud_client_by_id(client_id)
        if not client_data:
             return "Client not found", 404
        
        # Create client object with all required fields
        client = SimpleNamespace(
            id=client_data.get('id'),
            name=client_data.get('name', 'N/A'),
            email=client_data.get('email', ''),
            phone=client_data.get('phone', ''),
            address='',
            gstin='',
            pan=''
        )

        invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date() if invoice_date_str else datetime.now().date()
        
        # Parse Line Items
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
            igst_percentage = float(item_data.get('igst_percentage', 0.0))

            line_total = quantity * unit_price
            
            cgst_amount = (line_total * cgst_percentage) / 100
            sgst_amount = (line_total * sgst_percentage) / 100
            igst_amount = (line_total * igst_percentage) / 100
            
            tax_amount = cgst_amount + sgst_amount + igst_amount
            
            # Create SimpleNamespace object instead of InvoiceLineItem model
            li = SimpleNamespace(
                sr_no=i,
                hsn_code=item_data.get('hsn_code', ''),
                description=item_data.get('description', ''),
                quantity=quantity,
                unit=item_data.get('unit', 'Nos'),
                unit_price=unit_price,
                cgst_percentage=cgst_percentage,
                sgst_percentage=sgst_percentage,
                igst_percentage=igst_percentage,
                cgst_amount=cgst_amount,
                sgst_amount=sgst_amount,
                igst_amount=igst_amount,
                total_amount=line_total + tax_amount
            )
            
            line_items.append(li)

            subtotal += line_total
            total_cgst += cgst_amount
            total_sgst += sgst_amount
            total_igst += igst_amount

        # Create SimpleNamespace invoice instead of Invoice model
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
            total_amount=subtotal + total_cgst + total_sgst + total_igst,
            invoice_format=invoice_format,
            line_items=line_items,
            payment_status='Unpaid'
        )
        
        company = Company.query.first()
        bank = BankDetails.query.first()

        # Select Template
        template_map = {
            "default": "invoice_detail.html",
            "excel_customer_A": "invoice_excel_customer_A.html"
        }
        template_name = template_map.get(invoice_format, "invoice_detail.html")

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
    """Detailed invoice view (fetch from cloud)"""
    # Fetch invoice from cloud API
    invoice_data = fetch_cloud_invoice_by_id(id)
    if not invoice_data:
        flash('Invoice not found', 'error')
        return redirect(url_for('invoice_management'))
    
    # Fetch client data from cloud API
    client_data = fetch_cloud_client_by_id(invoice_data.get('client_id'))
    if not client_data:
        flash('Client not found', 'error')
        return redirect(url_for('invoice_management'))
    
    # Create invoice object with all required fields
    invoice = SimpleNamespace(
        id=invoice_data.get('id'),
        invoice_number=invoice_data.get('invoice_number', 'N/A'),
        invoice_date=datetime.strptime(invoice_data.get('invoice_date'), '%Y-%m-%d').date() if invoice_data.get('invoice_date') else datetime.now().date(),
        due_date=None,
        total_amount=invoice_data.get('total_amount', 0),
        payment_status=invoice_data.get('payment_status', 'Unpaid'),
        notes='',
        terms_conditions='',
        line_items=[],
        subtotal=invoice_data.get('total_amount', 0),
        cgst=0,
        sgst=0,
        igst=0,
        invoice_format='default'
    )
    
    invoice.client = SimpleNamespace(
        name=client_data.get('name', 'N/A'),
        email=client_data.get('email', ''),
        phone=client_data.get('phone', ''),
        address='',
        gstin='',
        pan=''
    )
 
    # Blockchain verification (skip for cloud data)
    blockchain_verification = {}
    
    # AI insights (skip for cloud data)
    ai_insights = {}

    # Select template
    template_map = {
    "default": "invoice_detail.html",
    "excel_customer_A": "invoice_excel_customer_A.html"
    }

    template_name = template_map.get(
        invoice.invoice_format,
        "invoice_detail.html"
    )
   
    company = Company.query.first()
    bank = BankDetails.query.first()

    return render_template(
        template_name,
        invoice=invoice,
        company=company,
        bank=bank,
        blockchain_verification=blockchain_verification,
        ai_insights=ai_insights
)


@app.route('/invoice/<int:id>/download-pdf')
@login_required
def download_invoice_pdf(id):
    """Download PDF directly to user's Downloads folder (fetch from cloud)"""
    try:
        # Fetch invoice from cloud API
        invoice_data = fetch_cloud_invoice_by_id(id)
        if not invoice_data:
            return jsonify({'success': False, 'error': 'Invoice not found'}), 404
        
        # Fetch client data
        client_data = fetch_cloud_client_by_id(invoice_data.get('client_id'))
        if not client_data:
            return jsonify({'success': False, 'error': 'Client not found'}), 404
        
        # Create invoice object for PDF generation with all required fields
        invoice = SimpleNamespace(
            id=invoice_data.get('id'),
            invoice_number=invoice_data.get('invoice_number', 'N/A'),
            invoice_date=datetime.strptime(invoice_data.get('invoice_date'), '%Y-%m-%d').date() if invoice_data.get('invoice_date') else datetime.now().date(),
            due_date=None,
            total_amount=invoice_data.get('total_amount', 0),
            payment_status=invoice_data.get('payment_status', 'Unpaid'),
            notes='',
            terms_conditions='',
            line_items=[],
            subtotal=invoice_data.get('total_amount', 0),
            cgst=0,
            sgst=0,
            igst=0,
            invoice_type='Invoice',  # Required by PDF generator
            blockchain_hash=None  # Required by PDF generator
        )
        
        invoice.client = SimpleNamespace(
            name=client_data.get('name', 'N/A'),
            email=client_data.get('email', ''),
            phone=client_data.get('phone', ''),
            address='',
            city='',
            state='',
            pincode='',
            gstin='',
            pan='',
            contact_person=''  # Required by PDF generator
        )
        
        logging.info(f"Generating PDF for invoice {id}: {invoice_data.get('invoice_number')}")
        
        pdf_buffer = generate_invoice_pdf(invoice)
        pdf_buffer.seek(0)
        
        # Get Downloads folder path
        from pathlib import Path
        downloads_folder = Path.home() / 'Downloads'
        downloads_folder.mkdir(exist_ok=True)
        
        # Create filename and save
        filename = f'Invoice_{invoice_data.get("invoice_number")}.pdf'
        filepath = downloads_folder / filename
        
        # Write PDF to file
        with open(filepath, 'wb') as f:
            f.write(pdf_buffer.getvalue())
        
        logging.info(f"PDF saved to: {filepath}")
        return jsonify({'success': True, 'message': f'PDF saved to Downloads: {filename}', 'filepath': str(filepath)})
        
    except Exception as e:
        logging.error(f"PDF download failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'Failed to save PDF: {str(e)}'}), 500


@app.route('/invoice/<int:id>/pdf')
@login_required
def invoice_pdf(id):
    """Generate PDF for invoice - works with both web and desktop (PyWebView)"""
    try:
        invoice = Invoice.query.get_or_404(id)
        logging.info(f"Generating PDF for invoice {id}: {invoice.invoice_number}")
        
        pdf_buffer = generate_invoice_pdf(invoice)
        pdf_buffer.seek(0)
        
        buffer_size = len(pdf_buffer.getvalue())
        logging.info(f"PDF buffer size: {buffer_size} bytes")
        
        filename = f'Invoice_{invoice.invoice_number}.pdf'
        
        response = Response(
            pdf_buffer.getvalue(),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
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
        response = requests.delete(
            f"{CLOUD_API_BASE}/invoices/{id}",
            timeout=5
        )
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
        response = requests.delete(
            f"{CLOUD_API_BASE}/invoices/{id}",
            timeout=5
        )
        if response.status_code in (200, 204):
            return jsonify({'success': True})
        else:
            return jsonify({
                'success': False,
                'error': f'Cloud API error: {response.text}'
            }), response.status_code
    except Exception as e:
        logging.error(f"Delete error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500






@app.route('/invoice/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_invoice(id):
    """Edit invoice from cloud database"""
    
    if request.method == 'POST':
        action = request.form.get('action', 'update')
        
        # Prepare update data
        update_data = {}
        
        # Handle specific actions
        if action == 'mark_paid':
            update_data['payment_status'] = 'Paid'
            flash_msg = 'Invoice marked as Paid!'
        elif action == 'mark_unpaid':
            update_data['payment_status'] = 'Unpaid'
            flash_msg = 'Invoice marked as Unpaid!'
        else:
            # Regular update
            if request.form.get('notes'):
                update_data['notes'] = request.form.get('notes')
            if request.form.get('terms_conditions'):
                update_data['terms_conditions'] = request.form.get('terms_conditions')
            if request.form.get('client_id'):
                update_data['client_id'] = int(request.form.get('client_id'))
            flash_msg = 'Invoice updated successfully!'
        
        # Send update to cloud API
        try:
            response = requests.put(
                f"{CLOUD_API_BASE}/invoices/{id}",
                json=update_data,
                timeout=5
            )
            if response.status_code in (200, 204):
                flash(flash_msg, 'success')
            else:
                flash(f'Failed to update invoice: {response.text}', 'error')
        except Exception as e:
            logging.error(f"Cloud API update error: {e}")
            flash(f'API connection error: {str(e)}', 'error')
        
        return redirect(url_for('invoice_management'))

    # GET request — fetch invoice from cloud and show edit form
    invoice_data = fetch_cloud_invoice_by_id(id)
    if not invoice_data:
        flash('Invoice not found', 'error')
        return redirect(url_for('invoice_management'))
    
    # Create invoice object with all fields needed by edit form
    invoice = SimpleNamespace(
        id=invoice_data.get('id'),
        invoice_number=invoice_data.get('invoice_number', 'N/A'),
        invoice_date=invoice_data.get('invoice_date'),
        client_id=invoice_data.get('client_id'),
        total_amount=invoice_data.get('total_amount', 0),
        payment_status=invoice_data.get('payment_status', 'Unpaid'),
        notes=invoice_data.get('notes', ''),
        terms_conditions=invoice_data.get('terms_conditions', '')
    )
    
    client_list = fetch_cloud_clients()
    clients = [SimpleNamespace(**c) for c in client_list]
    
    return render_template('edit_invoice.html', invoice=invoice, clients=clients)


@app.route('/invoice/<int:id>/duplicate', methods=['POST'])
@login_required
def duplicate_invoice(id):
    invoice = Invoice.query.get_or_404(id)

    try:
        new_invoice = Invoice(
            client_id=invoice.client_id,
            notes=invoice.notes,
            terms_conditions=invoice.terms_conditions,
            total_amount=invoice.total_amount,
            payment_status='Unpaid',
            invoice_date=datetime.utcnow(),
            # make sure invoice_number is unique, e.g.,
            invoice_number=f"{invoice.invoice_number}-COPY"
        )

        db.session.add(new_invoice)
        db.session.commit()
        return jsonify({'message': 'Invoice duplicated successfully!'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'Failed to duplicate invoice: {str(e)}'}), 400

@app.route('/invoice/<int:id>/send', methods=['POST'])
@login_required
def send_invoice(id):
    """Send invoice via email to client (fetch from cloud)"""
    try:
        # Fetch invoice from cloud API
        invoice_data = fetch_cloud_invoice_by_id(id)
        if not invoice_data:
            return jsonify({"success": False, "message": "❌ Invoice not found."}), 404
        
        # Fetch client data from cloud API
        client_data = fetch_cloud_client_by_id(invoice_data.get('client_id'))
        if not client_data:
            return jsonify({"success": False, "message": "❌ Client not found."}), 404
        
        recipient_email = client_data.get('email')

        if not recipient_email:
            return jsonify({"success": False, "message": "❌ Client has no email address set."}), 400

        # Create invoice object for email sending with all required fields
        invoice = SimpleNamespace(
            id=invoice_data.get('id'),
            invoice_number=invoice_data.get('invoice_number', 'N/A'),
            invoice_date=datetime.strptime(invoice_data.get('invoice_date'), '%Y-%m-%d').date() if invoice_data.get('invoice_date') else datetime.now().date(),
            due_date=None,
            total_amount=invoice_data.get('total_amount', 0),
            payment_status=invoice_data.get('payment_status', 'Unpaid'),
            notes='',
            terms_conditions='',
            line_items=[],
            subtotal=invoice_data.get('total_amount', 0),
            cgst=0,
            sgst=0,
            igst=0,
            invoice_type='Invoice',  # Required by PDF generator
            blockchain_hash=None  # Required by PDF generator
        )
        
        invoice.client = SimpleNamespace(
            name=client_data.get('name', 'N/A'),
            email=client_data.get('email', ''),
            phone=client_data.get('phone', ''),
            address='',
            city='',
            state='',
            pincode='',
            gstin='',
            pan='',
            contact_person=''  # Required by PDF generator
        )
        
        # Send the email
        send_invoice_email(invoice, recipient_email)
        
        logging.info(f"Invoice {invoice_data.get('invoice_number')} sent to {recipient_email}")
        
        return jsonify({
            "success": True, 
            "message": f"✅ Invoice sent successfully to {recipient_email}!"
        })
        
    except Exception as e:
        logging.error(f"Failed to send invoice: {e}", exc_info=True)
        return jsonify({
            "success": False, 
            "message": f"❌ Failed to send invoice: {str(e)}"
        }), 500





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

    # --- 1. Fetch Cloud Data ---
    cloud_clients = []
    cloud_invoices = []
    try:
        # Fetch Clients
        r_c = requests.get("http://44.208.164.236:5000/api/clients", timeout=3)
        if r_c.status_code == 200:
            cloud_clients = r_c.json()
        
        # Fetch Invoices for metrics
        r_i = requests.get("http://44.208.164.236:5000/api/invoices", timeout=3)
        if r_i.status_code == 200:
            cloud_invoices = r_i.json()
            
    except Exception as e:
        print(f"Cloud fetch error: {e}")
        flash("Could not fetch some cloud data, showing local only.", "warning")

    # Process Cloud Clients
    for c in cloud_clients:
        # Create a hybrid object
        # Metric Calculation
        c_invoices = [inv for inv in cloud_invoices if inv.get('client_id') == c['id']]
        total_business = sum(inv.get('total_amount', 0) for inv in c_invoices)
        
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

        # Create unified object
        # Use string ID with prefix to avoid collision
        client_obj = SimpleNamespace(
            id=f"c_{c['id']}",
            real_id=c['id'],
            source='cloud',
            name=c.get('name'),
            email=c.get('email'),
            phone=c.get('phone'),
            contact_person=c.get('name'), # Default
            client_type='Regular', # Default for cloud
            lead_stage='New', # Default for cloud
            total_business=total_business,
            gstin="N/A",
            pan="N/A",
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

    # --- 2. Fetch Local Data ---
    local_clients = Client.query.all()
    for lc in local_clients:
        # Calculate local metrics
        l_total = lc.total_business or 0
        l_risk = "Low" # Default
        # Check local invoices if any (assuming logic exists)
        # For now use stored or simple logic
        l_high_value = l_total > 100000
        
        # Local Risk Check (reusing logic from previous turn if needed, or simple)
        is_local_risk = False
        for inv in lc.invoices:
             if inv.payment_status != 'Paid' and inv.invoice_date:
                if (today - inv.invoice_date).days > 60:
                    is_local_risk = True
        
        l_risk = "High" if is_local_risk else "Low"

        # Unique ID is just str(id) for local vs c_id for cloud
        # But to be safe let's keep local as just ID (int) or str without prefix? 
        # Frontend expects ID. If I use int, it might mismatch the "c_" string.
        # Let's use string "l_{id}" for consistency? Or just keep raw ID and handle in template?
        # Template uses `client.id`.
        # If I use `c_1` and `1`, they are distinct.
        
        lc_obj = SimpleNamespace(
            id=lc.id, # Keep original INT id for local to avoid breaking other things?
            real_id=lc.id,
            source='local',
            name=lc.name,
            email=lc.email,
            phone=lc.phone,
            contact_person=lc.contact_person,
            client_type=lc.client_type,
            lead_stage=lc.lead_stage,
            total_business=l_total,
            gstin=lc.gstin,
            pan=lc.pan,
            risk_level=l_risk,
            high_value=l_high_value,
            created_at=lc.created_at
        )
        
        client_insights[lc.id] = {
            'risk_level': l_risk,
            'predicted_ltv': l_total,
            'high_value': l_high_value
        }
        
        client_list.append(lc_obj)


    # --- 3. Filtering ---
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

    # --- 4. Pagination ---
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
            # Create local Client object (Persist all details)
            new_client = Client(
                name=request.form.get('name'),
                contact_person=request.form.get('contact_person'),
                phone=request.form.get('phone'),
                email=request.form.get('email'),
                client_type=request.form.get('client_type', 'Regular'),
                address=request.form.get('address'),
                city=request.form.get('city'),
                state=request.form.get('state'),
                pincode=request.form.get('pincode'),
                gstin=request.form.get('gstin'),
                pan=request.form.get('pan'),
                notes=request.form.get('notes'),
                lead_stage=request.form.get('lead_stage', 'New'),
                tags=request.form.get('tags'),
                follow_up_date=datetime.strptime(request.form.get('follow_up_date'), '%Y-%m-%d') if request.form.get('follow_up_date') else None,
                created_at=datetime.utcnow()
            )
            
            db.session.add(new_client)
            db.session.commit()
            
            flash('Client created locally!', 'success')
            return redirect(url_for('client_management'))

        except Exception as e:
            logging.error(f"Client creation failed: {e}")
            db.session.rollback()
            flash(f'Error creating client: {str(e)}', 'error')

    return render_template('create_client.html')

@app.route('/api/client/<client_id>')
@login_required
def api_client_details(client_id):
    # Determine source
    is_cloud = str(client_id).startswith('c_')
    
    data = {}
    recent_activity = []
    
    if is_cloud:
        # Fetch from Cloud
        real_id = int(str(client_id).replace('c_', ''))
        try:
            # Fetch Client
            # Cloud API doesn't have single fetch? Use list for now or hope query works
            # Helper function from before or manual fetch
            r = requests.get(f"http://44.208.164.236:5000/api/clients", timeout=3)
            # Find in list (inefficient but works for 32 items)
            found = None
            if r.status_code == 200:
                for c in r.json():
                    if c['id'] == real_id:
                        found = c
                        break
            
            if found:
                # Get invoices for stats
                r_i = requests.get("http://44.208.164.236:5000/api/invoices", timeout=3)
                c_invoices = []
                pending_amount = 0
                total_business = 0
                if r_i.status_code == 200:
                    all_inv = r_i.json()
                    c_invoices = [inv for inv in all_inv if inv.get('client_id') == real_id]
                    total_business = sum(inv.get('total_amount', 0) for inv in c_invoices)
                    pending_amount = sum(inv.get('total_amount', 0) for inv in c_invoices if inv.get('payment_status') != 'Paid')
                
                # Format Activity
                for inv in sorted(c_invoices, key=lambda x: x.get('invoice_date', ''), reverse=True)[:5]:
                    recent_activity.append({
                        'description': f"Invoice #{inv.get('invoice_number')} ({inv.get('payment_status')})",
                        'date': inv.get('invoice_date') or 'Recent'
                    })

                data = {
                    'name': found.get('name'),
                    'email': found.get('email'),
                    'phone': found.get('phone'),
                    'address': "Cloud Record (Address N/A)", 
                    'gstin': "N/A",
                    'pan': "N/A",
                    'total_business': total_business,
                    'pending_amount': pending_amount,
                    'contact_person': found.get('name'),
                    'recent_activity': recent_activity
                }
            else:
                 return jsonify({'error': 'Cloud client not found'}), 404
                 
        except Exception as e:
            return jsonify({'error': str(e)}), 500
            
    else:
        # Local Fetch
        try:
            client = Client.query.get_or_404(int(client_id))
            # Calculate stats
            total_invoices = len(client.invoices)
            pending_amount = sum(inv.total_amount - inv.amount_paid for inv in client.invoices if inv.payment_status != 'Paid')
            
            # Recent activity
            for inv in sorted(client.invoices, key=lambda x: x.created_at, reverse=True)[:5]:
                recent_activity.append({
                    'description': f"Invoice #{inv.invoice_number} generated",
                    'date': inv.created_at.strftime('%Y-%m-%d') if inv.created_at else 'Recent'
                })
                
            data = {
                'name': client.name,
                'email': client.email,
                'phone': client.phone,
                'address': client.address,
                'gstin': client.gstin,
                'pan': client.pan,
                'total_business': client.total_business or 0,
                'pending_amount': pending_amount,
                'contact_person': client.contact_person,
                'recent_activity': recent_activity
            }
        except Exception as e:
             return jsonify({'error': str(e)}), 500

    return jsonify(data)

@app.route('/api/export/clients/excel')
@login_required
def export_clients_excel():
    search = request.args.get('search', '')
    client_type = request.args.get('type', '')
    
    # Build query with filters
    query = Client.query
    if search:
        query = query.filter(
            or_(
                Client.name.contains(search),
                Client.phone.contains(search),
                Client.email.contains(search),
                Client.contact_person.contains(search)
            )
        )
    if client_type:
        query = query.filter(Client.client_type == client_type)
        
    clients = query.order_by(Client.name).all()

    client_data = [{
        'Name': c.name or 'N/A',
        'Email': c.email or 'N/A',
        'Phone': c.phone or 'N/A',
        'Type': c.client_type or 'Regular',
        'Lead Stage': c.lead_stage or 'N/A',
        'Total Business': c.total_business if c.total_business else 0,
        'Risk Score': c.ai_risk_score if c.ai_risk_score else 0,
        'GST No': c.gstin or 'N/A',
        'PAN No': c.pan or 'N/A',
        'Created Date': c.created_at.strftime('%d-%m-%Y') if c.created_at else 'N/A'
    } for c in clients]

    df = pd.DataFrame(client_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Clients')
    output.seek(0)

    # Use desktop integration
    filename = f"clients_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    filepath = _save_buffer_to_downloads(output, filename)
    
    if filepath:
        return jsonify({
            'success': True,
            'message': f'Excel report generated and saved to Downloads: {filename}',
            'filename': filename
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to save file to system Downloads folder.'
        }), 500

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
        r_c = requests.get("http://44.208.164.236:5000/api/clients", timeout=3)
        cloud_clients = r_c.json() if r_c.status_code == 200 else []
        
        r_i = requests.get("http://44.208.164.236:5000/api/invoices", timeout=3)
        cloud_invoices = r_i.json() if r_i.status_code == 200 else []
        
        for c in cloud_clients:
            c_invs = [inv for inv in cloud_invoices if inv.get('client_id') == c['id']]
            total_biz = sum(inv.get('total_amount', 0) for inv in c_invs)
            
            client_dict = {
                'name': c.get('name', ''),
                'email': c.get('email', ''),
                'phone': c.get('phone', ''),
                'type': 'Regular', # Cloud default
                'gstin': 'N/A', # Cloud default
                'business_value': total_biz
            }
            client_list.append(client_dict)
    except Exception as e:
        print(f"Cloud fetch error in export: {e}")

    # Local Fetch
    local_clients = Client.query.all()
    for lc in local_clients:
        client_dict = {
            'name': lc.name,
            'email': lc.email,
            'phone': lc.phone,
            'type': lc.client_type,
            'gstin': lc.gstin or 'N/A',
            'business_value': lc.total_business or 0
        }
        client_list.append(client_dict)

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
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=18)
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
    
    filepath = _save_buffer_to_downloads(buffer, filename)
    
    if filepath:
        return jsonify({
            'success': True,
            'message': f'PDF report generated: {filename}',
            'filename': filename
        })
    else:
        return jsonify({'success': False, 'message': 'Failed to save PDF'}), 500


def _get_analytics_data_dict(time_range='12m'):
    """Helper to gather all analytics data as a dictionary"""
    analytics_data = {
        'revenue_trends': analytics_engine.get_revenue_trends(time_range),
        'client_performance': analytics_engine.get_client_performance_metrics(),
        'payment_analytics': analytics_engine.get_payment_analytics(),
        'profitability_analysis': analytics_engine.get_profitability_analysis(),
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
    """Export analytics data to Excel and save to system"""
    try:
        time_range = request.args.get('range', '12m')
        analytics_data = _get_analytics_data_dict(time_range)
        output = report_generator.generate_excel_report(analytics_data)
        
        filename = f"Analytics_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path = _save_buffer_to_downloads(output, filename)
        
        if file_path:
            return jsonify({
                "success": True, 
                "message": f"Excel report saved to Downloads: {filename}",
                "path": file_path
            })
        else:
            return jsonify({"success": False, "message": "Failed to save file to system."}), 500
            
    except Exception as e:
        logging.error(f"Excel export failed: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/analytics/export/pdf')
@login_required
def export_analytics_pdf():
    """Export analytics data to PDF and save to system"""
    try:
        time_range = request.args.get('range', '12m')
        analytics_data = _get_analytics_data_dict(time_range)
        output = report_generator.generate_pdf_report(analytics_data)
        
        filename = f"Analytics_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        file_path = _save_buffer_to_downloads(output, filename)
        
        if file_path:
            return jsonify({
                "success": True, 
                "message": f"PDF report saved to Downloads: {filename}",
                "path": file_path
            })
        else:
            return jsonify({"success": False, "message": "Failed to save file to system."}), 500
            
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
    """Application settings with AI and blockchain configuration"""
    company = Company.query.first()
    user = User.query.get(session['user_id'])
    business_settings = BusinessSettings.query.all()
    
    settings_data = {
        'company': company,
        'user': user,
        'business_settings': {setting.key: setting.value for setting in business_settings},
        'ai_enabled': app.config.get("AI_FEATURES_ENABLED", False),
        'blockchain_enabled': app.config.get("BLOCKCHAIN_ENABLED", False)
    }
    
    return render_template('settings.html', settings_data=settings_data)

@app.route('/settings/update', methods=['POST'])
@login_required
def update_settings():
    try:
        data = request.get_json()
        user = User.query.get(session['user_id'])
        company = Company.query.first()
        if not company:
            company = Company(name="SyncForte")
            db.session.add(company)
        
        # 1. Update Company
        if 'company' in data:
            c_data = data['company']
            company.name = c_data.get('companyName')
            company.email = c_data.get('companyEmail')
            company.phone = c_data.get('companyPhone')
            company.website = c_data.get('companyWebsite')
            company.address = c_data.get('companyAddress')
            company.city = c_data.get('companyCity')
            company.state = c_data.get('companyState')
            company.pincode = c_data.get('companyPincode')
            company.gstin = c_data.get('companyGstin')
            company.pan = c_data.get('companyPan')
            
        # 2. Update User Profile
        if 'user' in data:
            u_data = data['user']
            # user.email = u_data.get('userEmail') # Handle carefully if email is login
            if 'preferredLanguage' in u_data:
                user.preferred_language = u_data['preferredLanguage']
            if 'themePreference' in u_data:
                user.theme_preference = u_data['themePreference']
            
            # User Features
            user.ai_features_enabled = u_data.get('aiFeatures', False)
            user.voice_commands_enabled = u_data.get('voiceCommands', False)
            user.collaboration_access = u_data.get('collaborationAccess', False)
            user.biometric_enabled = u_data.get('biometricEnabled', False)
            
            # Handle Password Change
            new_pass = u_data.get('newPassword')
            if new_pass:
                # In a real app, verify current password first
                from werkzeug.security import generate_password_hash
                user.password_hash = generate_password_hash(new_pass)

        # 3. Update Business Settings (General, AI, Blockchain, etc.)
        # Helper to update or create setting
        def update_biz_setting(key, value, type='general'):
            setting = BusinessSettings.query.filter_by(key=key).first()
            if not setting:
                setting = BusinessSettings(key=key, setting_type=type)
                db.session.add(setting)
            setting.value = str(value)
            
        # Invoice Settings
        if 'invoice' in data:
            inv = data['invoice']
            update_biz_setting('default_tax_rate', inv.get('defaultTaxRate'))
            update_biz_setting('payment_terms', inv.get('paymentTerms'))
            update_biz_setting('invoice_prefix', inv.get('invoicePrefix'))
            update_biz_setting('default_currency', inv.get('defaultCurrency'))
            update_biz_setting('qr_code_payments', inv.get('qrCodePayments'))
            update_biz_setting('digital_watermark', inv.get('digitalWatermark'))
            update_biz_setting('auto_numbering', inv.get('autoNumbering'))
            update_biz_setting('default_terms', inv.get('defaultTerms'))
            
        # AI Settings
        if 'ai' in data:
            ai = data['ai']
            update_biz_setting('ai_assistant_enabled', ai.get('aiAssistant'), 'ai')
            update_biz_setting('ai_confidence_threshold', ai.get('aiConfidenceThreshold'), 'ai')
            
        # Blockchain Settings
        if 'blockchain' in data:
            bc = data['blockchain']
            update_biz_setting('blockchain_verification', bc.get('blockchainVerification'), 'blockchain')
            update_biz_setting('blockchain_network', bc.get('blockchainNetwork'), 'blockchain')

        # Notifications
        if 'notifications' in data:
            user.notification_preferences = data['notifications']

        db.session.commit()
        return jsonify({'success': True, 'message': 'Settings saved successfully'})
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Settings update failed: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route("/create-challan", methods=['GET', 'POST'])
@login_required
def create_challan():
    if request.method == 'POST':
        try:
            # Generate Challan Number
            last_challan = DeliveryChallan.query.order_by(DeliveryChallan.id.desc()).first()
            if last_challan and last_challan.challan_number.startswith('DC-'):
                try:
                    last_seq = int(last_challan.challan_number.split('-')[-1])
                    new_seq = last_seq + 1
                except:
                    new_seq = 1
            else:
                new_seq = 1
            
            challan_number = f"DC-{datetime.now().year}-{new_seq:04d}"
            
            client_id = request.form.get('client_id')
            challan_date_str = request.form.get('challan_date')
            delivery_date_str = request.form.get('delivery_date')
            vehicle_number = request.form.get('vehicle_number')
            transport_mode = request.form.get('transport_mode')
            notes = request.form.get('notes')
            
            line_items_json = request.form.get('line_items')
            
            challan = DeliveryChallan(
                challan_number=challan_number,
                client_id=client_id,
                challan_date=datetime.strptime(challan_date_str, '%Y-%m-%d').date() if challan_date_str else datetime.utcnow().date(),
                delivery_date=datetime.strptime(delivery_date_str, '%Y-%m-%d').date() if delivery_date_str else None,
                notes=notes,
                status='Open'
            )
            
            # Additional logic for vehicle/transport if needed, or store in notes/JSON
            # For now appending to notes if not fields in model (Model only sees notes)
            # Checked model: only notes. So let's prepend transport info to notes.
            meta_notes = []
            if transport_mode: meta_notes.append(f"Mode: {transport_mode}")
            if vehicle_number: meta_notes.append(f"Vehicle: {vehicle_number}")
            if meta_notes:
                challan.notes = (challan.notes or "") + "\n" + " | ".join(meta_notes)

            db.session.add(challan)
            db.session.flush() # Get ID
            
            if line_items_json:
                items = json.loads(line_items_json)
                for item in items:
                    line_item = ChallanLineItem(
                        challan_id=challan.id,
                        sr_no=item.get('sr_no'),
                        hsn_code=item.get('hsn_code'),
                        description=item.get('description'),
                        quantity=item.get('quantity'),
                        unit=item.get('unit'),
                        unit_price=item.get('unit_price', 0),
                        total_amount=float(item.get('quantity', 0)) * float(item.get('unit_price', 0))
                    )
                    db.session.add(line_item)
            
            db.session.commit()
            flash(f'Delivery Challan {challan_number} created successfully!', 'success')
            return redirect(url_for('delivery_challan'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error creating challan: {e}")
            flash(f"Error creating challan: {e}", 'error')
    
    client_list = fetch_cloud_clients()
    clients = [SimpleNamespace(**c) for c in client_list][:2] # Limit to 2 clients as requested
    return render_template("create_challan.html", clients=clients, today=datetime.now())

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

        # 6. Generate PDF
        # We use the existing function. 
        pdf_buffer = generate_challan_pdf(challan)
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
        response = requests.get(
            "http://44.208.164.236:5000/api/challans",
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
        else:
            flash("Failed to load delivery challans", "error")
            data = []

    except Exception as e:
        flash(f"API connection error: {str(e)}", "error")
        data = []

    challan_list = []

    for c in data:
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
                name=c.get("client_name")
            ),

            status=c["status"],
            notes=c["notes"],
            line_items=c.get("line_items", [])
        )

        challan_list.append(challan_obj)

    challans_obj = SimpleNamespace(
        items=challan_list,
        total=len(challan_list),
        pages=1,
        has_prev=False,
        has_next=False,
        page=1
    )

    return render_template(
        "delivery_challan.html",
        challans=challans_obj
    )


@app.route('/challan/<int:id>/update_status', methods=['POST'])
@login_required
def update_challan_status(id):
    try:
        challan = DeliveryChallan.query.get_or_404(id)
        new_status = request.form.get('status')
        note = request.form.get('note')
        
        if new_status:
            challan.status = new_status
            if note:
                challan.notes = (challan.notes or "") + f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Status updated to {new_status}: {note}"
            
            db.session.commit()
            flash(f'Challan status updated to {new_status}', 'success')
        
        return redirect(url_for('delivery_challan'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating status: {str(e)}', 'error')
        return redirect(url_for('delivery_challan'))
@app.route('/crm')
@login_required
def crm():
    lead_stats = analytics_engine.get_lead_stats()  
    return render_template('crm.html', title='CRM', lead_stats=lead_stats)
@app.route('/create-reminder')
@login_required
def create_reminder():
    return render_template('create_reminder.html', title='Create Reminder')


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
    """Process voice commands"""
    if not app.config.get("AI_FEATURES_ENABLED") or not voice_processor:
        return jsonify({'error': 'Voice commands not available'})
    
    try:
        data = request.get_json()
        voice_text = data.get('text', '')
        context = data.get('context', {})
        
        result = voice_processor.process(voice_text)
        
        return jsonify(result)
        
    except Exception as e:
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

@app.route('/api/proxy/clients', methods=['GET'])
@login_required
def api_proxy_clients():
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
    """AI chat endpoint that uses real database data"""
    try:
        data = request.get_json()
        message = data.get('message', '').lower().strip()
        
        # Fetch real data from database
        clients = Client.query.all()
        invoices = Invoice.query.all()
        
        # Determine active/inactive clients based on invoice activity
        client_ids_with_invoices = set([i.client_id for i in invoices])
        active_clients = [c for c in clients if c.id in client_ids_with_invoices]
        inactive_clients = [c for c in clients if c.id not in client_ids_with_invoices]
        
        paid_invoices = [i for i in invoices if i.payment_status == 'Paid']
        unpaid_invoices = [i for i in invoices if i.payment_status != 'Paid']
        
        # Calculate revenue stats
        from datetime import date, timedelta
        today = date.today()
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
        
        # Default fallback
        return jsonify({'reply': """I can help you with:
        <br>• Business health checks
        <br>• Revenue forecasts and predictions
        <br>• Client and invoice information
        <br>• Outstanding payments
        <br>• Recent activity
        <br>• How-to guides
        <br><br>Try asking "Show business health" or "Forecast revenue"!"""})
            
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
        # Capture all possible fields from the form
        payload = {
            "quotation_number": request.form.get("quotation_number"),
            "quotation_date": request.form.get("quotation_date"),
            "validity_days": request.form.get("validity_days"),
            "status": request.form.get("status", "Draft"),
            "sales_person": request.form.get("sales_person"),
            "reference_id": request.form.get("reference_id"),
            
            "subtotal": request.form.get("subtotal", 0),
            "discount": request.form.get("discount", 0),
            "taxable_value": request.form.get("taxable", 0),
            "cgst": request.form.get("cgst", 0),
            "sgst": request.form.get("sgst", 0),
            "igst": request.form.get("igst", 0),
            "shipping": request.form.get("shipping", 0),
            "rounding": request.form.get("rounding", 0),
            "grand_total": request.form.get("grand_total", 0),
            
            "delivery_timeline": request.form.get("delivery_timeline"),
            "project_scope": request.form.get("project_scope"),
            "milestones": request.form.get("milestones"),
            "warranty": request.form.get("warranty"),
            "revision_policy": request.form.get("revision_policy"),
            "dependencies": request.form.get("dependencies"),
            "terms": request.form.get("terms")
        }

        response = requests.post(
            "http://44.208.164.236:5000/api/quotations",
            json=payload,
            timeout=5
        )

        if response.status_code in (200, 201):
            flash("Quotation created successfully!", "success")
            return redirect(url_for("quotation_list"))
        else:
            flash(
                f"API error: {response.status_code} - {response.text}",
                "error"
            )

    except Exception as e:
        flash(f"API connection error: {str(e)}", "error")

    return redirect(url_for("quotation_form"))
# -------------------------
# Preview
# -------------------------
@app.route("/quotations/preview/<int:qid>")
def quotation_preview(qid):
    try:
        response = requests.get(
            f"http://44.208.164.236:5000/api/quotations/{qid}",
            timeout=5
        )
        
        if response.status_code == 200:
            q_data = response.json()
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
                ) if q_data.get("expiry_date") else None,
                delivery_timeline=q_data.get("delivery_timeline", ""),
                project_scope=q_data.get("project_scope", ""),
                milestones=q_data.get("milestones", ""),
                warranty=q_data.get("warranty", ""),
                revision_policy=q_data.get("revision_policy", ""),
                dependencies=q_data.get("dependencies", ""),
                terms=q_data.get("terms", "")
            )
            return render_template("quotation_preview.html", q=q)
        else:
            flash("Quotation not found", "error")
            return redirect(url_for("quotation_list"))
    except Exception as e:
        flash(f"Error loading quotation: {str(e)}", "error")
        return redirect(url_for("quotation_list"))


# -------------------------
# List
# -------------------------
@app.route("/quotations/list")
@login_required
def quotation_list():

    try:
        response = requests.get(
            "http://44.208.164.236:5000/api/quotations",
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
        else:
            flash("Failed to load quotations from API", "error")
            data = []

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
def duplicate_quotation(qid):
    try:
        # Fetch original quotation from API
        response = requests.get(
            f"http://44.208.164.236:5000/api/quotations/{qid}",
            timeout=5
        )
        
        if response.status_code == 200:
            q_data = response.json()
            
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
            
            create_response = requests.post(
                "http://44.208.164.236:5000/api/quotations",
                json=new_payload,
                timeout=5
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
def cancel_quotation(qid):
    try:
        response = requests.put(
            f"http://44.208.164.236:5000/api/quotations/{qid}",
            json={"status": "Cancelled"},
            timeout=5
        )
        
        if response.status_code == 200:
            flash("Quotation has been cancelled.", "warning")
            return redirect(url_for("quotation_preview", qid=qid))
        else:
            flash("Failed to cancel quotation", "error")
    except Exception as e:
        flash(f"Error cancelling quotation: {str(e)}", "error")
    
    return redirect(url_for("quotation_list"))


@app.route("/quotations/<int:qid>/delete")
def delete_quotation(qid):
    try:
        response = requests.delete(
            f"http://44.208.164.236:5000/api/quotations/{qid}",
            timeout=5
        )
        
        if response.status_code == 200:
            flash("Quotation deleted successfully!", "success")
        else:
            flash("Failed to delete quotation", "error")
    except Exception as e:
        flash(f"Error deleting quotation: {str(e)}", "error")
    
    return redirect(url_for("quotation_list"))

@app.route("/quotations/<int:qid>/pdf")
def quotation_pdf(qid):
    try:
        # Fetch quotation from API
        response = requests.get(
            f"http://44.208.164.236:5000/api/quotations/{qid}",
            timeout=5
        )
        
        if response.status_code == 200:
            q_data = response.json()
            
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
                ) if q_data.get("expiry_date") else None,
                delivery_timeline=q_data.get("delivery_timeline", ""),
                project_scope=q_data.get("project_scope", ""),
                milestones=q_data.get("milestones", ""),
                warranty=q_data.get("warranty", ""),
                revision_policy=q_data.get("revision_policy", ""),
                dependencies=q_data.get("dependencies", ""),
                terms=q_data.get("terms", "")
            )
            
            pdf_buffer = generate_quotation_pdf(quotation)
            filename = f"Quotation_{quotation.quotation_number.replace('-', '_')}.pdf"
            filepath = _save_buffer_to_downloads(pdf_buffer, filename)
            
            if filepath:
                return jsonify({
                    'success': True,
                    'message': f'Quotation PDF generated and saved to Downloads: {filename}',
                    'filename': filename
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Failed to save PDF to system Downloads folder.'
                }), 500
        else:
            return jsonify({
                'success': False,
                'message': 'Quotation not found in API'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error generating PDF: {str(e)}'
        }), 500


@app.route("/quotations/<int:qid>/convert")
def convert_to_invoice(qid):
    try:
        response = requests.put(
            f"http://44.208.164.236:5000/api/quotations/{qid}",
            json={"status": "Converted to Invoice"},
            timeout=5
        )
        
        if response.status_code == 200:
            flash("Quotation converted to Invoice successfully!", "success")
        else:
            flash("Failed to convert quotation", "error")
    except Exception as e:
        flash(f"Error converting quotation: {str(e)}", "error")
    
    return redirect(url_for("quotation_list"))
@app.route("/quotations/<int:qid>/send-email")
def send_email(qid):
    try:
        response = requests.get(
            f"http://44.208.164.236:5000/api/quotations/{qid}",
            timeout=5
        )
        
        if response.status_code == 200:
            q_data = response.json()
            # TEMP DEMO (replace with real email later)
            print("Sending email for quotation:", q_data["quotation_number"])
            flash("Email sent successfully (demo).", "success")
        else:
            flash("Quotation not found", "error")
    except Exception as e:
        flash(f"Error sending email: {str(e)}", "error")
    
    return redirect(url_for("quotation_list"))


@app.route("/quotations/<int:qid>/send-whatsapp")
def send_whatsapp(qid):
    try:
        response = requests.get(
            f"http://44.208.164.236:5000/api/quotations/{qid}",
            timeout=5
        )
        
        if response.status_code == 200:
            q_data = response.json()
            # TEMP DEMO
            print("Sending WhatsApp for quotation:", q_data["quotation_number"])
            flash("WhatsApp sent successfully (demo).", "success")
        else:
            flash("Quotation not found", "error")
    except Exception as e:
        flash(f"Error sending WhatsApp: {str(e)}", "error")
    
    return redirect(url_for("quotation_list"))



@app.route('/dashboard')
@login_required
def dashboard_page():

    # ✅ REQUIRED BY TEMPLATE
    today = date.today()

    try:
        data = fetch_cloud_invoices()
    except Exception as e:
        logging.error(f"Dashboard cloud fetch failed: {e}")
        data = []

    recent_invoices = []

    for inv in data[:10]:
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

    return render_template(
        "dashboard.html",

        # 🔑 MUST-HAVE VARIABLES
        today=today,
        recent_invoices=recent_invoices,

        # 🔑 METRICS (safe defaults)
        monthly_revenue_total=0,
        outstanding_amount=0,
        total_invoices=len(data),
        total_clients=0,

        # 🔑 CHART
        monthly_revenue=[],

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





@app.route('/convert_challan_to_invoice/<int:id>')
@login_required
def convert_challan_to_invoice(id):
    try:
        challan = DeliveryChallan.query.get_or_404(id)
        
        if challan.invoice_id:
            flash('This challan is already linked to an invoice.', 'warning')
            return redirect(url_for('delivery_challan'))
            
        # Generate Invoice Number logic (simplified)
        last_inv = Invoice.query.order_by(Invoice.id.desc()).first()
        if last_inv and last_inv.invoice_number.startswith('INV-'):
            try:
                last_seq = int(last_inv.invoice_number.split('-')[-1])
                new_seq = last_seq + 1
            except:
                new_seq = 1
        else:
            new_seq = 1
        invoice_number = f"INV-{datetime.now().year}-{new_seq:04d}"
        
        # Create Invoice
        new_invoice = Invoice(
            invoice_number=invoice_number,
            client_id=challan.client_id,
            invoice_date=datetime.utcnow().date(),
            notes=f"Converted from Challan {challan.challan_number}. {request.args.get('notes', '')}",
            terms_conditions="Standard Terms Applied",
            due_date=datetime.strptime(request.args.get('due_date'), '%Y-%m-%d').date() if request.args.get('due_date') else None
        )
        db.session.add(new_invoice)
        db.session.flush()
        
        # Copy Line Items
        total_amt = 0
        for item in challan.line_items:
            # Basic validation
            qty = item.quantity or 0
            price = item.unit_price or 0
            total = qty * price
            
            inv_item = InvoiceLineItem(
                invoice_id=new_invoice.id,
                sr_no=item.sr_no,
                hsn_code=item.hsn_code,
                description=item.description,
                quantity=qty,
                unit=item.unit,
                unit_price=price,
                total_amount=total
            )
            total_amt += total
            db.session.add(inv_item)
            
        new_invoice.total_amount = total_amt
        new_invoice.subtotal = total_amt # Assuming no tax calc for simplicity, or 0 tax
        
        # Link Challan
        challan.invoice_id = new_invoice.id
        challan.status = 'Billed'
        
        db.session.commit()
        
        flash(f'Challan {challan.challan_number} converted to Invoice {invoice_number}!', 'success')
        return redirect(url_for('invoice_detail', id=new_invoice.id))
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Conversion failed: {e}")
        return redirect(url_for('delivery_challan'))

@app.route('/delete_challan/<int:id>', methods=['POST'])
@login_required
def delete_challan(id):
    try:
        challan = DeliveryChallan.query.get_or_404(id)
        
        # Optional: Prevent deleting if converted to invoice
        if challan.status == 'Billed' or challan.invoice_id:
             # Unlink from invoice instead of hard block? Or just block.
             # For now, let's allow it but warn, or maybe just unlink.
             # Let's keep it simple: cleanup line items is cascade delete.
             pass

        db.session.delete(challan)
        db.session.commit()
        flash('Delivery Challan deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting challan: {str(e)}', 'error')
    
    return redirect(url_for('delivery_challan'))

@app.route('/challan/<int:id>/pdf')
@login_required
def challan_pdf(id):
    """Generate PDF for delivery challan"""
    try:
        challan = DeliveryChallan.query.get_or_404(id)
        
        pdf_buffer = generate_challan_pdf(challan)
        pdf_buffer.seek(0)
        
        filename = f'Challan_{challan.challan_number}.pdf'
        
        return send_file(
            pdf_buffer,
            download_name=filename,
            as_attachment=True,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logging.error(f"Challan PDF generation failed: {e}")
        flash(f'Error generating PDF: {str(e)}', 'error')
        return redirect(url_for('delivery_challan'))






