import os
import json
import logging
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file, session, abort, Flask
from werkzeug.utils import secure_filename
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
from reportlab.lib.pagesizes import letter
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
import requests
from types import SimpleNamespace


# Initialize analytics engine
analytics_engine = AnalyticsEngine(db.session)
from report_generator import AnalyticsReportGenerator
report_generator = AnalyticsReportGenerator()

from functools import wraps
from flask import session, redirect, url_for, flash, jsonify

# -------------------------
# UI LOGIN DECORATOR
# -------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# -------------------------
# API LOGIN DECORATOR
# -------------------------
def api_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({
                "success": False,
                "message": "Unauthorized. Please login."
            }), 401
        return f(*args, **kwargs)
    return decorated



@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
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
    """Advanced invoice management with AI filtering"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    client_filter = request.args.get('client_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Build query
    query = Invoice.query.options(joinedload(Invoice.client))
    
    if search:
        query = query.join(Client).filter(
            or_(
                Invoice.invoice_number.contains(search),
                Client.name.contains(search),
                Client.phone.contains(search),
                Client.email.contains(search)
            )
        )
    
    if status_filter:
        query = query.filter(Invoice.payment_status == status_filter)
    
    if client_filter:
        query = query.filter(Invoice.client_id == client_filter)
    
    if date_from:
        query = query.filter(Invoice.invoice_date >= datetime.strptime(date_from, '%Y-%m-%d').date())
    
    if date_to:
        query = query.filter(Invoice.invoice_date <= datetime.strptime(date_to, '%Y-%m-%d').date())
    
    # Pagination
    invoices = query.order_by(Invoice.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get clients for filter dropdown
    clients = Client.query.order_by(Client.name).all()
    
    # AI insights for invoices
    ai_invoice_insights = {}
    if app.config.get("AI_FEATURES_ENABLED") and ai_services.ai_assistant:
        try:
            # Get payment delay predictions
            ai_invoice_insights = analytics_engine.get_ai_invoice_insights(
                [inv.id for inv in invoices.items]
            )
        except Exception as e:
            logging.error(f"AI invoice insights failed: {e}")
    
    return render_template('invoice_management.html',
                         invoices=invoices,
                         clients=clients,
                         search=search,
                         status_filter=status_filter,
                         client_filter=client_filter,
                         date_from=date_from,
                         date_to=date_to,
                         ai_insights=ai_invoice_insights)
@app.route('/create_invoice', methods=['GET', 'POST'])
@login_required
def create_invoice():
    """AI-enhanced invoice creation with voice commands"""
    if request.method == 'POST':
        try:
            # Extract form data
            client_id = request.form.get('client_id')
            invoice_date_str = request.form.get('invoice_date')
            due_date_str = request.form.get('due_date')
            notes = request.form.get('notes', '')
            terms_conditions = request.form.get('terms_conditions', '')
            invoice_format = request.form.get("invoice_format", "default")

            # Parse dates
            invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date() if invoice_date_str else datetime.now().date()
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None

            # Generate invoice number
            invoice_number = generate_invoice_number()

            # Create invoice
            invoice = Invoice(
                invoice_number=invoice_number,
                client_id=client_id,
                invoice_date=invoice_date,
                due_date=due_date,
                notes=notes,
                terms_conditions=terms_conditions,
                invoice_format=invoice_format,
                ai_generated=request.form.get('ai_generated') == 'true',
                voice_command_created=request.form.get('voice_created') == 'true'
            )

            db.session.add(invoice)
            db.session.commit()

            # Process line items
            print("RAW line_items:", request.form.get("line_items"))

            line_items_data = json.loads(request.form.get('line_items', '[]'))
            subtotal = 0
            total_cgst = 0
            total_sgst = 0
            total_igst = 0

            for i, item_data in enumerate(line_items_data, 1):
                quantity = float(item_data['quantity'])
                unit_price = float(item_data['unit_price'])
                
                # Get individual tax percentages
                cgst_percentage = float(item_data.get('cgst_percentage', 0.0))
                sgst_percentage = float(item_data.get('sgst_percentage', 0.0))
                igst_percentage = float(item_data.get('igst_percentage', 0.0))

                line_total = quantity * unit_price
                
                # Calculate individual tax amounts
                cgst_amount = (line_total * cgst_percentage) / 100
                sgst_amount = (line_total * sgst_percentage) / 100
                igst_amount = (line_total * igst_percentage) / 100
                
                # Total tax for this line
                tax_amount = cgst_amount + sgst_amount + igst_amount
                
                # For backward compatibility, use total tax percentage
                tax_percentage = cgst_percentage + sgst_percentage + igst_percentage

                line_item = InvoiceLineItem(
                    invoice_id=invoice.id,
                    sr_no=i,
                    hsn_code=item_data.get('hsn_code', ''),
                    description=item_data['description'],
                    quantity=quantity,
                    unit=item_data.get('unit', 'Nos'),
                    unit_price=unit_price,
                    tax_percentage=tax_percentage,
                    tax_amount=tax_amount,
                    cgst_percentage=cgst_percentage,
                    sgst_percentage=sgst_percentage,
                    igst_percentage=igst_percentage,
                    cgst_amount=cgst_amount,
                    sgst_amount=sgst_amount,
                    igst_amount=igst_amount,
                    total_amount=line_total + tax_amount,
                    cost_price=float(item_data.get('cost_price', 0)),
                    ai_suggested=item_data.get('ai_suggested', False)
                )

                db.session.add(line_item)
                subtotal += line_total
                total_cgst += cgst_amount
                total_sgst += sgst_amount
                total_igst += igst_amount
            db.session.commit()

            # Calculate invoice-level taxes
            client = Client.query.get(client_id)
            company = Company.query.first()

            # Set invoice totals based on what was calculated from line items
            invoice.cgst = total_cgst
            invoice.sgst = total_sgst
            invoice.igst = total_igst
            invoice.subtotal = subtotal
            invoice.total_amount = subtotal + total_cgst + total_sgst + total_igst

            # Generate QR code
            invoice.qr_payment_code = generate_payment_qr_code(invoice)

            # AI risk assessment
            if app.config.get("AI_FEATURES_ENABLED") and ai_services.ai_assistant:
                try:
                    risk_assessment = ai_services.ai_assistant.analyze_client_history(client_id)
                    invoice.ai_risk_assessment = risk_assessment
                    invoice.predicted_payment_date = predict_payment_date(invoice, risk_assessment)
                except Exception as e:
                    logging.error(f"AI risk assessment failed: {e}")

            # Blockchain
            if app.config.get("BLOCKCHAIN_ENABLED") and blockchain_service:
                try:
                    blockchain_hash = blockchain_service.add_invoice_to_blockchain(invoice)
                    if blockchain_hash:
                        logging.info(f"Invoice {invoice_number} added to blockchain")
                except Exception as e:
                    logging.error(f"Blockchain addition failed: {e}")

            db.session.commit()

            invoice_url = url_for('invoice_detail', id=invoice.id)

            # 🆕 Return JSON if AJAX
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(success=True, invoice_url=invoice_url)

            flash('AI-powered invoice created successfully!', 'success')
            return redirect(invoice_url)

        except Exception as e:
            db.session.rollback()
            logging.error(f"Invoice creation failed: {e}")
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(success=False, error=str(e))
            flash(f'Error creating invoice: {str(e)}', 'error')

    # GET request
    clients = Client.query.order_by(Client.name).all()
    ai_suggestions = {}
    client_id = request.args.get('client_id')

    if client_id and app.config.get("AI_FEATURES_ENABLED") and ai_services.ai_assistant:
        try:
            ai_suggestions = ai_services.ai_assistant.suggest_invoice_items(int(client_id))
        except Exception as e:
            logging.error(f"AI suggestions failed: {e}")

    return render_template('create_invoice.html',
                           clients=clients,
                           today=datetime.now())


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

        # Create ephemeral objects
        client = Client.query.get(client_id)
        if not client:
             return "Client not found", 404

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
            
            # Create transient object
            li = InvoiceLineItem(
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

        # Create transient invoice
        invoice = Invoice(
            invoice_number="PREVIEW",
            invoice_date=invoice_date,
            client=client,
            notes=notes,
            terms_conditions=terms_conditions,
            subtotal=subtotal,
            cgst=total_cgst,
            sgst=total_sgst,
            igst=total_igst,
            total_amount=subtotal + total_cgst + total_sgst + total_igst,
            invoice_format=invoice_format
        )
        # Manually attach line items for Jinja loop
        invoice.line_items = line_items 
        
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
    """Detailed invoice view with blockchain verification"""
    invoice = Invoice.query.get_or_404(id)
 
    # Blockchain verification
    blockchain_verification = {}
    if app.config.get("BLOCKCHAIN_ENABLED") and blockchain_service and invoice.blockchain_hash:
        try:
            blockchain_verification = blockchain_service.verify_invoice_integrity(id)
        except Exception as e:
            logging.error(f"Blockchain verification failed: {e}")
    
    # AI insights for this invoice
    ai_insights = {}
    if app.config.get("AI_FEATURES_ENABLED") and ai_services.ai_assistant:
        try:
            client_analysis = ai_services.ai_assistant.analyze_client_history(invoice.client_id)
            ai_insights = {
                'payment_prediction': client_analysis.get('risk_assessment', {}),
                'similar_invoices': analytics_engine.find_similar_invoices(id)
            }
        except Exception as e:
            logging.error(f"AI insights failed: {e}")

    # 🔹 FORMAT SWITCH LOGIC (THIS IS THE ONLY ADDITION)
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
    """Download PDF directly to user's Downloads folder"""
    try:
        invoice = Invoice.query.get_or_404(id)
        logging.info(f"Generating PDF for invoice {id}: {invoice.invoice_number}")
        
        pdf_buffer = generate_invoice_pdf(invoice)
        pdf_buffer.seek(0)
        
        # Get Downloads folder path
        from pathlib import Path
        downloads_folder = Path.home() / 'Downloads'
        downloads_folder.mkdir(exist_ok=True)
        
        # Create filename and save
        filename = f'Invoice_{invoice.invoice_number}.pdf'
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
    invoice = Invoice.query.get_or_404(id)
    db.session.delete(invoice)
    db.session.commit()
    flash('Invoice deleted successfully.', 'success')
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
    invoice = Invoice.query.get_or_404(id)
    try:
        db.session.delete(invoice)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500






@app.route('/invoice/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_invoice(id):
    invoice = Invoice.query.get_or_404(id)

    if request.method == 'POST':
        action = request.form.get('action', 'update')

        # Update fields from the form
        invoice.notes = request.form.get('notes', invoice.notes)
        invoice.terms_conditions = request.form.get('terms_conditions', invoice.terms_conditions)
        
        # Update client if changed
        client_id = request.form.get('client_id')
        if client_id:
            invoice.client_id = int(client_id)
            
        # Handle specific actions
        if action == 'mark_paid':
            invoice.payment_status = 'Paid'
            flash('Invoice marked as Paid!', 'success')
        elif action == 'mark_unpaid':
            invoice.payment_status = 'Unpaid'
            flash('Invoice marked as Unpaid!', 'success')
        else:
            flash('Invoice updated successfully!', 'success')

        # You can update other invoice fields here as needed

        db.session.commit()
        
        # Always return a response after POST
        return redirect(url_for('invoice_management'))

    # GET request — show edit form
    clients = Client.query.order_by(Client.name).all()
    
    # Always return a response
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
    """Send invoice via email to client"""
    try:
        invoice = Invoice.query.get_or_404(id)
        recipient_email = invoice.client.email

        if not recipient_email:
            return jsonify({"success": False, "message": "❌ Client has no email address set."}), 400

        # Send the email
        send_invoice_email(invoice, recipient_email)
        
        # Log the activity
        logging.info(f"Invoice {invoice.invoice_number} sent to {recipient_email}")
        
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
    # TEMP: mock data to verify UI listing
    client_list = [
        {
            "id": 1,
            "name": "Test Client A",
            "phone": "9876543210",
            "email": "a@test.com",
            "city": "Chennai",
            "blockchain_verified": False
        },
        {
            "id": 2,
            "name": "Test Client B",
            "phone": "9999999999",
            "email": "b@test.com",
            "city": "Bangalore",
            "blockchain_verified": True
        }
    ]

    clients_obj = SimpleNamespace(
        items=client_list,
        total=len(client_list),
        pages=1,
        has_prev=False,
        has_next=False,
        page=1
    )

    return render_template(
        'client_management.html',
        clients=clients_obj,
        client_list=client_list,
        search="",
        client_type="",
        client_insights={}
    )



@app.route('/create_client', methods=['GET', 'POST'])
@login_required
def create_client():
    if request.method == 'POST':
        try:
            payload = request.form.to_dict()

            # Convert checkbox properly
            payload['blockchain_verified'] = payload.get('blockchain_verified') == 'on'

            # Send form data to CLOUD API (this replaces Postman)
            response = requests.post(
                "http://54.236.29.224:5000/api/clients",
                json=payload,
                timeout=5
            )

            if response.status_code in (200, 201):
                flash('Client created successfully!', 'success')
                return redirect(url_for('client_management'))
            else:
                flash(
                    f"API error: {response.status_code} - {response.text}",
                    'error'
                )

        except Exception as e:
            logging.error(f"API client creation failed: {e}")
            flash(f'API connection error: {str(e)}', 'error')

    return render_template('create_client.html')


@app.route('/api/export/clients/excel')
@login_required
def export_clients_excel():
    clients = Client.query.order_by(Client.name).all()

    client_data = [{
        'ID': c.id,
        'Name': c.name,
        'Email': c.email,
        'Phone': c.phone,
        'Type': c.client_type,
        'Lead Stage': c.lead_stage,
        'Total Business': c.total_business,
        'Risk Score': c.ai_risk_score,
        'Predicted LTV': c.predicted_ltv,
        'Verified': c.blockchain_verified,
        'Date': c.created_at.strftime('%d-%m-%Y') if c.created_at else 'N/A',
        'Name': c.name or 'N/A',
        'Amount': c.total_business if c.total_business else 0,
        'GST No': c.gstin or 'N/A',
        'PAN No': c.pan or 'N/A'
    } for c in clients]

    df = pd.DataFrame(client_data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Clients')
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name='clients.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/api/export/clients/pdf')
@login_required
def export_clients_pdf():
    clients = Client.query.all()
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    col_x = [50, width / 2 + 10]
    col = 0
    y = height - 70
 
    PAGE_MARGIN = 10   # 👈 moved border closer to page edge

    def draw_page_border():
        p.setStrokeColorRGB(0, 0, 0)   # black border
        p.setLineWidth(2)
        p.rect(
            PAGE_MARGIN,
            PAGE_MARGIN,
            width - PAGE_MARGIN * 2,
            height - PAGE_MARGIN * 2
        )

    # Draw border on first page
    draw_page_border()

    
    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(width / 2, height - 40, "Client Directory Report")

    # Light header line
    p.setStrokeColorRGB(0.7, 0.7, 0.7)
    p.line(40, height - 55, width - 40, height - 55)
 
    for c in clients:

        block_height = 150

        # Page & column handling
        if y - block_height < 80:
            if col == 0:
                col = 1
                y = height - 70
            else:
                p.showPage()
                draw_page_border()   # redraw border on new page
                col = 0
                y = height - 70

        x = col_x[col]
        box_width = width / 2 - 70

        # Light background color
        p.setFillColorRGB(0.95, 0.97, 1)
        p.roundRect(x, y - block_height, box_width, block_height, 8, fill=1)

        # Block border
        p.setStrokeColorRGB(0.75, 0.8, 0.9)
        p.roundRect(x, y - block_height, box_width, block_height, 8, fill=0)

        p.setFillColorRGB(0, 0, 0)
        text_y = y - 30

        # Client Name
        p.setFont("Helvetica-Bold", 14)
        p.drawString(x + 15, text_y, c.name or "N/A")
        text_y -= 24

        # Details
        p.setFont("Helvetica", 11)
        p.drawString(x + 15, text_y,
            f"Date      : {c.created_at.strftime('%d-%m-%Y') if c.created_at else 'N/A'}")
        text_y -= 18

        p.drawString(x + 15, text_y, f"Mail ID   : {c.email or 'N/A'}")
        text_y -= 18

        p.drawString(x + 15, text_y,
            f"Amount    : ₹{c.total_business:,.2f}" if c.total_business else "Amount    : ₹0.00")
        text_y -= 18

        p.drawString(x + 15, text_y, f"GST No    : {c.gstin or 'N/A'}")
        text_y -= 18

        p.drawString(x + 15, text_y, f"PAN No    : {c.pan or 'N/A'}")

        y -= block_height + 20

    
    p.setFont("Helvetica", 9)
    p.setFillColorRGB(0.4, 0.4, 0.4)
    p.drawCentredString(
        width / 2,
        25,
        f"Generated On : {datetime.now().strftime('%d-%m-%Y %H:%M')} | System Generated Report"
    )

    p.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="clients_styled.pdf",
        mimetype="application/pdf"
    )


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

@app.route("/create-challan")
@login_required
def create_challan():
    clients = Client.query.order_by(Client.name).all()

    for c in clients:
        print("CLIENT:", c.name, "| Address:", c.address, "| City:", c.city, "| Phone:", c.phone)

    return render_template("create_challan.html", clients=clients)


@app.route("/delivery-challan")
@login_required
def delivery_challan():
    return render_template("delivery_challan.html")
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
        clients = Client.query.all()
        
        clients_data = {
            'total': len(clients),
            'active': len([c for c in clients if c.total_business and c.total_business > 0]),
            'inactive': len([c for c in clients if not c.total_business or c.total_business == 0]),
            'clients': [{
                'id': c.id,
                'name': c.name,
                'email': c.email,
                'phone': c.phone,
                'total_business': float(c.total_business) if c.total_business else 0,
                'created_at': c.created_at.strftime('%Y-%m-%d') if c.created_at else None,
                'gstin': c.gstin,
                'pan': c.pan
            } for c in clients]
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
        invoices = Invoice.query.all()
        
        invoices_data = {
            'total': len(invoices),
            'paid': len([i for i in invoices if i.payment_status == 'Paid']),
            'unpaid': len([i for i in invoices if i.payment_status == 'Unpaid']),
            'partial': len([i for i in invoices if i.payment_status == 'Partially Paid']),
            'invoices': [{
                'id': i.id,
                'invoice_number': i.invoice_number,
                'client_name': i.client.name if i.client else 'Unknown',
                'total_amount': float(i.total_amount) if i.total_amount else 0,
                'amount_paid': float(i.amount_paid) if i.amount_paid else 0,
                'payment_status': i.payment_status,
                'invoice_date': i.invoice_date.strftime('%Y-%m-%d') if i.invoice_date else None,
                'due_date': i.due_date.strftime('%Y-%m-%d') if i.due_date else None
            } for i in invoices]
        }
        
        return jsonify(invoices_data)
    except Exception as e:
        logging.error(f"Error fetching invoices data: {e}")
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


# Voice command routes are now defined above (lines ~1808-1890)
# Using get_voice_processor() and get_voice_session() functions


 

from flask import render_template, request, redirect, url_for
from datetime import datetime, timedelta
from app import app, db
from models import Quotation

# -------------------------
# Auto Quotation Number
# -------------------------
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
def create_quotation():
    f = request.form

    quotation_date = datetime.strptime(f["quotation_date"], "%Y-%m-%d")
    validity_days = int(f["validity_days"])
    expiry_date = quotation_date + timedelta(days=validity_days)

    quotation = Quotation(
    quotation_number=f.get("quotation_number"),
    quotation_date=quotation_date,
    validity_days=validity_days,
    expiry_date=expiry_date,
    status=f.get("status"),

    sales_person = f.get("sales_person"),
    reference_id=f.get("reference_id"),

    subtotal=safe_float(f.get("subtotal")),
    discount=safe_float(f.get("discount")),
    taxable_value=safe_float(f.get("taxable")),
    cgst=safe_float(f.get("cgst")),
    sgst=safe_float(f.get("sgst")),
    igst=safe_float(f.get("igst")),
    shipping=safe_float(f.get("shipping")),
    rounding=safe_float(f.get("rounding")),
    grand_total=safe_float(f.get("grand_total")),

    delivery_timeline=f.get("delivery_timeline"),
    project_scope=f.get("project_scope"),
    milestones=f.get("milestones"),
    warranty=f.get("warranty"),
    revision_policy=f.get("revision_policy"),
    dependencies=f.get("dependencies"),
    terms=f.get("terms")
)

    db.session.add(quotation)
    db.session.commit()

    return redirect(url_for("quotation_preview", qid=quotation.id))


# -------------------------
# Preview
# -------------------------
@app.route("/quotations/preview/<int:qid>")
def quotation_preview(qid):
    q = Quotation.query.get_or_404(qid)
    return render_template("quotation_preview.html", q=q)


# -------------------------
# List
# -------------------------
@app.route("/quotations/list")
def quotation_list():
    quotations = Quotation.query.order_by(Quotation.id.desc()).all()
    return render_template("quotation_list.html", quotations=quotations)


# -------------------------
# Duplicate
# -------------------------
@app.route("/quotations/duplicate/<int:qid>")
def duplicate_quotation(qid):
    q = Quotation.query.get_or_404(qid)

    new = Quotation(
        quotation_number=generate_quotation_number(),
        quotation_date=q.quotation_date,
        validity_days=q.validity_days,
        expiry_date=q.expiry_date,
        status="Draft",
        sales_person=q.sales_person,
        reference_id=q.reference_id,

        subtotal=q.subtotal,
        discount=q.discount,
        taxable_value=q.taxable_value,
        cgst=q.cgst,
        sgst=q.sgst,
        igst=q.igst,
        shipping=q.shipping,
        rounding=q.rounding,
        grand_total=q.grand_total,

        delivery_timeline=q.delivery_timeline,
        project_scope=q.project_scope,
        milestones=q.milestones,
        warranty=q.warranty,
        revision_policy=q.revision_policy,
        dependencies=q.dependencies,
        terms=q.terms
    )

    db.session.add(new)
    db.session.commit()
    return redirect(url_for("quotation_preview", qid=new.id))


# -------------------------
# Cancel / Reject
# -------------------------
@app.route("/quotations/cancel/<int:qid>")
def cancel_quotation(qid):
    q = Quotation.query.get_or_404(qid)
    q.status = "Cancelled"
    db.session.commit()
    flash("Quotation has been cancelled.", "warning")
    return redirect(url_for("quotation_preview", qid=q.id))


@app.route("/quotations/<int:qid>/delete")
def delete_quotation(qid):
    q = Quotation.query.get_or_404(qid)
    db.session.delete(q)
    db.session.commit()
    flash("Quotation deleted successfully!", "success")
    return redirect(url_for("quotation_list"))

@app.route("/quotations/<int:qid>/pdf")
def quotation_pdf(qid):
    quotation = Quotation.query.get_or_404(qid)
    pdf_file = generate_quotation_pdf(quotation)

    return send_file(
        pdf_file,
        download_name=f"{quotation.quotation_number}.pdf",
        as_attachment=True
    )


@app.route("/quotations/<int:qid>/convert")
def convert_to_invoice(qid):
    quotation = Quotation.query.get_or_404(qid)

    quotation.status = "Converted to Invoice"
    db.session.commit()

    flash("Quotation converted to Invoice successfully!", "success")
    return redirect(url_for("quotation_list"))
@app.route("/quotations/<int:qid>/send-email")
def send_email(qid):
    q = Quotation.query.get_or_404(qid)

    # TEMP DEMO (replace with real email later)
    print("Sending email for quotation:", q.quotation_number)

    flash("Email sent successfully (demo).")
    return redirect(url_for("quotation_list"))


@app.route("/quotations/<int:qid>/send-whatsapp")
def send_whatsapp(qid):
    q = Quotation.query.get_or_404(qid)

    # TEMP DEMO
    print("Sending WhatsApp for quotation:", q.quotation_number)

    flash("WhatsApp sent successfully (demo).")
    return redirect(url_for("quotation_list"))



@app.route('/dashboard')
@login_required
def dashboard_page():

    # Get today's date
    today = date.today()

    #  First day of current month
    start_of_month = date(today.year, today.month, 1)

    #  Current Month Revenue (Only PAID invoices)
    monthly_revenue_total = (
        db.session.query(func.sum(Invoice.total_amount))
        .filter(
            Invoice.payment_status == 'Paid',
            Invoice.invoice_date >= start_of_month,
            Invoice.invoice_date <= today
        )
        .scalar()
    ) or 0

    #  Outstanding Amount (Pending money only)
    outstanding_amount = (
        db.session.query(
            func.sum(Invoice.total_amount - Invoice.amount_paid)
        )
        .filter(
            Invoice.payment_status.in_(['Unpaid', 'Partially Paid'])
        )
        .scalar()
    ) or 0

    #  Recent Invoices (ALL: Paid, Unpaid, Partial)
    recent_invoices = (
        Invoice.query
        .order_by(Invoice.invoice_date.desc())
        .limit(10)
        .all()
    )

    #  Monthly revenue for last 12 months (Paid invoices only)
    monthly_revenue_rows = (
        db.session.query(
            func.strftime('%Y-%m', Invoice.invoice_date).label("month"),
            func.sum(Invoice.total_amount).label("revenue")
        )
        .filter(Invoice.payment_status == 'Paid')
        .group_by("month")
        .order_by("month")
        .all()
    )

    monthly_revenue = [
        {
            "month": row.month,
            "revenue": float(row.revenue)
        }
        for row in monthly_revenue_rows
    ]

    print(" Current Month Revenue:", monthly_revenue_total)
    print(" Outstanding Amount:", outstanding_amount)
    print(" Recent Invoices Count:", len(recent_invoices))
    print(" Monthly Revenue Data:", monthly_revenue)

    return render_template(
        "dashboard.html",
        monthly_revenue_total=monthly_revenue_total,
        outstanding_amount=outstanding_amount,
        recent_invoices=recent_invoices,
        monthly_revenue=monthly_revenue   # ✅ NEW
    )


@app.route('/analytics/export/excel')
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


@app.route('/analytics/export/excel')
@login_required
def export_analytics_excel():
    """Export analytics to Excel (Saves to Downloads)"""
    try:
        import pandas as pd
        time_range = request.args.get('range', '12m')
        analytics_data = _get_analytics_data_dict(time_range)

        # Generate filename and path
        filename = f'Analytics_Report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
        file_path = os.path.join(downloads_path, filename)

        with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
            # Sheet 1: Revenue Trends
            if analytics_data.get('revenue_trends') and analytics_data['revenue_trends'].get('monthly_data'):
                df_rev = pd.DataFrame(analytics_data['revenue_trends']['monthly_data'])
                df_rev.to_excel(writer, sheet_name='Revenue', index=False)

            # Sheet 2: Client Performance
            if analytics_data.get('client_performance') and analytics_data['client_performance'].get('top_clients'):
                # Flatten client object to dict
                client_data = []
                for client in analytics_data['client_performance']['top_clients']:
                    client_data.append({
                        'Name': client.name,
                        'Revenue': client.total_revenue,
                        'Invoices': client.invoice_count,
                        'Avg Value': client.avg_invoice_value
                    })
                df_clients = pd.DataFrame(client_data)
                df_clients.to_excel(writer, sheet_name='Clients', index=False)

            # Sheet 3: Payment Status
            if analytics_data.get('payment_analytics') and analytics_data['payment_analytics'].get('payment_status_distribution'):
                df_payment = pd.DataFrame(analytics_data['payment_analytics']['payment_status_distribution'])
                df_payment.to_excel(writer, sheet_name='Payments', index=False)

        # Open file automatically
        try:
            os.startfile(file_path)
        except Exception:
            pass

        return jsonify({"success": True, "message": f"Excel report saved to {file_path}", "path": file_path})

    except Exception as e:
        logging.error(f"Excel export failed: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/analytics/export/pdf')
@login_required
def export_analytics_pdf():
    """Export analytics to PDF (Saves to Downloads)"""
    try:
        time_range = request.args.get('range', '12m')
        analytics_data = _get_analytics_data_dict(time_range)

        # Generate filename and path
        filename = f'Analytics_Report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
        file_path = os.path.join(downloads_path, filename)

        c = canvas.Canvas(file_path, pagesize=letter)
        width, height = letter

        # Header
        c.setFont("Helvetica-Bold", 20)
        c.drawString(50, height - 50, "Business Analytics Report")
        c.setFont("Helvetica", 12)
        c.drawString(50, height - 70, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        y = height - 120

        # Revenue Summary
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, "Revenue Summary")
        y -= 20
        c.setFont("Helvetica", 12)
        if analytics_data.get('revenue_trends') and analytics_data['revenue_trends'].get('summary'):
            summary = analytics_data['revenue_trends']['summary']
            c.drawString(50, y, f"Total Revenue: {summary.get('total_revenue', 0)}")
        else:
            c.drawString(50, y, "No revenue data available.")
        y -= 40

        # Top Clients
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, "Top Clients")
        y -= 25
        c.setFont("Helvetica", 10)
        if analytics_data.get('client_performance') and analytics_data['client_performance'].get('top_clients'):
            for i, client in enumerate(analytics_data['client_performance']['top_clients'][:5]):
                c.drawString(50, y, f"{i+1}. {client.name} - Revenue: {client.total_revenue}")
                y -= 15
        else:
             c.drawString(50, y, "No client data available.")

        c.save()

        # Open file automatically
        try:
            os.startfile(file_path)
        except Exception:
            pass
            
        return jsonify({"success": True, "message": f"PDF report saved to {file_path}", "path": file_path})

    except Exception as e:
        logging.error(f"PDF export failed: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


### API for core features
'''----------------------------
    Client
--------------------------------'''
@app.route("/api/clients", methods=["GET"])
@api_login_required
def api_get_clients():
    clients = Client.query.order_by(Client.name).all()
    return jsonify([safe_dict(c) for c in clients])


@app.route("/api/clients", methods=["POST"])
@api_login_required
def api_create_client():
    data = request.get_json()

    try:
        client = Client(
            name=data.get("name"),
            phone=data.get("phone"),
            email=data.get("email"),
            city=data.get("city")
        )
        db.session.add(client)
        db.session.commit()
        return jsonify({"success": True, "client_id": client.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/clients/<int:id>", methods=["PUT"])
@api_login_required
def api_update_client(id):
    client = Client.query.get_or_404(id)
    data = request.get_json()

    try:
        client.name = data.get("name", client.name)
        client.phone = data.get("phone", client.phone)
        client.email = data.get("email", client.email)
        client.city = data.get("city", client.city)

        db.session.commit()

        return jsonify({
            "success": True,
            "client": safe_dict(client)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/clients/<int:id>", methods=["DELETE"])
@api_login_required
def api_delete_client(id):
    client = Client.query.get_or_404(id)

    try:
        db.session.delete(client)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Client deleted successfully"
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

'''----------------------------
    Invoice
--------------------------------'''
@app.route("/api/invoices", methods=["GET"])
@api_login_required
def api_get_invoices():
    invoices = Invoice.query.order_by(Invoice.invoice_date.desc()).all()

    result = []
    for i in invoices:
        result.append({
            "id": i.id,
            "invoice_number": i.invoice_number,
            "client_id": i.client_id,
            "invoice_date": i.invoice_date.isoformat() if i.invoice_date else None,
            "total_amount": i.total_amount,
            "payment_status": i.payment_status
        })

    return jsonify(result)


@app.route("/api/invoices", methods=["POST"])
@api_login_required
def api_create_invoice():
    data = request.get_json()

    try:
        invoice = Invoice(
            invoice_number=generate_invoice_number(),
            client_id=data["client_id"],
            invoice_date=datetime.strptime(data["invoice_date"], "%Y-%m-%d").date(),
            notes=data.get("notes", "")
        )

        db.session.add(invoice)
        db.session.commit()

        subtotal = 0
        total_tax = 0

        for i, item in enumerate(data["items"], 1):
            qty = float(item["quantity"])
            price = float(item["unit_price"])
            tax = float(item.get("tax_percentage", 18))

            line_total = qty * price
            tax_amt = (line_total * tax) / 100

            line = InvoiceLineItem(
                invoice_id=invoice.id,
                sr_no=i,
                description=item["description"],
                quantity=qty,
                unit_price=price,
                tax_percentage=tax,
                tax_amount=tax_amt,
                total_amount=line_total + tax_amt
            )

            db.session.add(line)
            subtotal += line_total
            total_tax += tax_amt

        invoice.subtotal = subtotal
        invoice.total_amount = subtotal + total_tax
        db.session.commit()

        return jsonify({"success": True, "invoice_id": invoice.id})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/invoices/<int:id>", methods=["PUT"])
@api_login_required
def api_update_invoice(id):
    invoice = Invoice.query.get_or_404(id)
    data = request.get_json()

    invoice.notes = data.get("notes", invoice.notes)
    invoice.payment_status = data.get("payment_status", invoice.payment_status)

    db.session.commit()

    return jsonify({"success": True, "message": "Invoice updated"})


@app.route("/api/invoices/<int:id>/delete", methods=["DELETE"])
@api_login_required
def api_delete_invoice(id):
    invoice = Invoice.query.get_or_404(id)
    db.session.delete(invoice)
    db.session.commit()

    return jsonify({"success": True})

'''----------------------------
   quotation 
--------------------------------'''
@app.route("/api/quotations", methods=["GET"])
@api_login_required
def api_get_quotations():
    quotations = Quotation.query.order_by(Quotation.id.desc()).all()
    return jsonify([q.to_dict() for q in quotations])


@app.route("/api/quotations", methods=["POST"])
@api_login_required
def api_create_quotation():
    data = request.get_json()

    try:
        quotation = Quotation(
            quotation_number=generate_quotation_number(),
            quotation_date=datetime.strptime(data["quotation_date"], "%Y-%m-%d"),
            validity_days=data.get("validity_days", 30),
            status="Draft",
            sales_person=data.get("sales_person"),
            reference_id=data.get("reference_id"),
            subtotal=data.get("subtotal", 0),
            discount=data.get("discount", 0),
            taxable_value=data.get("taxable_value", 0),
            cgst=data.get("cgst", 0),
            sgst=data.get("sgst", 0),
            igst=data.get("igst", 0),
            grand_total=data.get("grand_total", 0)
        )

        db.session.add(quotation)
        db.session.commit()

        return jsonify({"success": True, "quotation_id": quotation.id})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/quotations/<int:id>", methods=["PUT"])
@api_login_required
def api_update_quotation(id):
    quotation = Quotation.query.get_or_404(id)
    data = request.get_json()

    for key, value in data.items():
        if hasattr(quotation, key):
            setattr(quotation, key, value)

    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/quotations/<int:id>", methods=["DELETE"])
@api_login_required
def api_delete_quotation(id):
    quotation = Quotation.query.get_or_404(id)
    db.session.delete(quotation)
    db.session.commit()
    return jsonify({"success": True})

'''----------------------------
   Challan
--------------------------------'''

@app.route("/api/challans", methods=["GET"])
@api_login_required
def api_get_challans():
    challans = DeliveryChallan.query.order_by(DeliveryChallan.created_at.desc()).all()
    return jsonify([safe_dict(c) for c in challans])


@app.route("/api/challans", methods=["POST"])
@api_login_required
def api_create_challan():
    data = request.get_json()

    try:
        challan = DeliveryChallan(
            challan_number=data["challan_number"],
            client_id=data["client_id"],
            challan_date=datetime.strptime(
                data.get("challan_date"), "%Y-%m-%d"
            ).date() if data.get("challan_date") else datetime.utcnow().date(),
            delivery_date=datetime.strptime(
                data.get("delivery_date"), "%Y-%m-%d"
            ).date() if data.get("delivery_date") else None,
            status=data.get("status", "Open"),
            notes=data.get("notes")
        )

        db.session.add(challan)
        db.session.commit()

        return jsonify({
            "success": True,
            "challan_id": challan.id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/challans/<int:id>", methods=["PUT"])
@api_login_required
def api_update_challan(id):
    data = request.get_json()
    challan = DeliveryChallan.query.get_or_404(id)

    try:
        challan.status = data.get("status", challan.status)
        challan.notes = data.get("notes", challan.notes)
        challan.delivery_date = (
            datetime.strptime(data["delivery_date"], "%Y-%m-%d").date()
            if data.get("delivery_date") else challan.delivery_date
        )

        db.session.commit()
        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/challans/<int:id>", methods=["DELETE"])
@api_login_required
def api_delete_challan(id):
    challan = DeliveryChallan.query.get_or_404(id)

    try:
        db.session.delete(challan)
        db.session.commit()
        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

'''----------------------------
   Company profile
--------------------------------'''

@app.route("/api/company", methods=["GET"])
@api_login_required
def api_get_company():
    company = Company.query.first()

    if not company:
        return jsonify({"message": "Company profile not set"}), 404

    return jsonify(company_to_dict(company))

@app.route("/api/company", methods=["PUT"])
@api_login_required
def api_update_company():
    data = request.get_json()

    company = Company.query.first()

    # If company not exists, create first time
    if not company:
        company = Company()
        db.session.add(company)

    try:
        company.name = data.get("name", company.name)
        company.address = data.get("address", company.address)
        company.city = data.get("city", company.city)
        company.state = data.get("state", company.state)
        company.pincode = data.get("pincode", company.pincode)
        company.phone = data.get("phone", company.phone)
        company.email = data.get("email", company.email)
        company.website = data.get("website", company.website)
        company.gstin = data.get("gstin", company.gstin)
        company.pan = data.get("pan", company.pan)
        company.logo_path = data.get("logo_path", company.logo_path)

        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Company profile updated successfully"
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

'''----------------------------
   login profile
--------------------------------'''
@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json()

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({
            "success": False,
            "message": "Username and password required"
        }), 400

    user = User.query.filter_by(username=username).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({
            "success": False,
            "message": "Invalid credentials"
        }), 401

    # create session
    session["user_id"] = user.id
    session["username"] = user.username
    session["is_admin"] = user.is_admin

    return jsonify({
        "success": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "is_admin": user.is_admin
        }
    })


@app.route("/api/auth/me", methods=["GET"])
@api_login_required
def api_me():
    if "user_id" not in session:
        return jsonify({
            "authenticated": False
        }), 401

    return jsonify({
        "authenticated": True,
        "user": {
            "id": session["user_id"],
            "username": session["username"],
            "is_admin": session.get("is_admin", False)
        }
    })



@app.route("/api/auth/logout", methods=["POST"])
@api_login_required
def api_logout():
    session.clear()
    return jsonify({
        "success": True,
        "message": "Logged out successfully"
    })
