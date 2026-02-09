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
from types import SimpleNamespace
import requests

# Initialize analytics engine
analytics_engine = AnalyticsEngine(db.session)
from report_generator import AnalyticsReportGenerator
report_generator = AnalyticsReportGenerator()

def login_required(f):
    """Decorator to require login for routes"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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

            if response.status_code == 201:
                flash("Invoice created successfully (Cloud DB)", "success")
                return redirect(url_for("invoice_management"))
            else:
                flash(f"API Error: {response.text}", "error")

        except Exception as e:
            flash(f"API connection error: {str(e)}", "error")

    # GET request (only fetch clients from cloud later if needed)
    clients = Client.query.order_by(Client.name).all()

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
    try:
        response = requests.get(
            "http://44.208.164.236:5000/api/clients",
            timeout=5
        )

        if response.status_code == 200:
            client_list = response.json()
        else:
            client_list = []
            flash("Failed to load clients from cloud API", "error")

    except Exception as e:
        client_list = []
        flash("Cloud API not reachable", "error")

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
                "http://44.208.164.236:5000/api/clients",
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
    
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    PAGE_MARGIN = 20

    def draw_page_border():
        p.setStrokeColorRGB(0, 0, 0)
        p.setLineWidth(1)
        p.rect(PAGE_MARGIN, PAGE_MARGIN, width - PAGE_MARGIN*2, height - PAGE_MARGIN*2)

    draw_page_border()
    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(width / 2, height - 50, "Client Directory Report")
    
    p.setStrokeColorRGB(0.7, 0.7, 0.7)
    p.line(40, height - 65, width - 40, height - 65)

    y = height - 100
    col_x = [60, width / 2 + 10]
    col = 0
    block_height = 130

    for c in clients:
        if y - block_height < 60:
            if col == 0:
                col = 1
                y = height - 100
            else:
                p.showPage()
                draw_page_border()
                col = 0
                y = height - 100

        x = col_x[col]
        box_width = width / 2 - 70

        p.setFillColorRGB(0.97, 0.98, 1)
        p.roundRect(x, y - block_height, box_width, block_height, 6, fill=1)
        
        p.setStrokeColorRGB(0.8, 0.8, 0.9)
        p.roundRect(x, y - block_height, box_width, block_height, 6, fill=0)

        p.setFillColorRGB(0, 0, 0)
        curr_y = y - 25
        
        p.setFont("Helvetica-Bold", 12)
        p.drawString(x + 15, curr_y, c.name or "N/A")
        curr_y -= 20
        
        p.setFont("Helvetica", 10)
        p.drawString(x + 15, curr_y, f"Email: {c.email or 'N/A'}")
        curr_y -= 15
        p.drawString(x + 15, curr_y, f"Phone: {c.phone or 'N/A'}")
        curr_y -= 15
        p.drawString(x + 15, curr_y, f"Type: {c.client_type or 'Regular'}")
        curr_y -= 15
        p.drawString(x + 15, curr_y, f"Business: ₹{c.total_business:,.2f}" if c.total_business else "Business: ₹0.00")
        curr_y -= 15
        p.drawString(x + 15, curr_y, f"GSTIN: {c.gstin or 'N/A'}")

        y -= block_height + 20

    p.setFont("Helvetica-Oblique", 8)
    p.drawCentredString(width/2, 35, f"Generated: {datetime.now().strftime('%d-%m-%Y %H:%M')}")
    
    p.save()
    buffer.seek(0)
    
    filename = f"client_directory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = _save_buffer_to_downloads(buffer, filename)
    
    if filepath:
        return jsonify({
            'success': True,
            'message': f'PDF report generated and saved to Downloads: {filename}',
            'filename': filename
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to save PDF to system Downloads folder.'
        }), 500


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
    
    clients = Client.query.order_by(Client.name).all()
    return render_template("create_challan.html", clients=clients, today=datetime.now())


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
            "quotation_date": request.form.get("quotation_date"),
            "status": request.form.get("status", "Draft"),
            "grand_total": request.form.get("grand_total", 0)
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
    q = Quotation.query.get_or_404(qid)
    return render_template("quotation_preview.html", q=q)


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



