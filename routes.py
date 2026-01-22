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
from pdf_generator import generate_invoice_pdf, generate_challan_pdf
import ai_services
from extensions import db

from blockchain_service import blockchain_service, smart_contract_manager
from ocr_service import ocr_processor, receipt_processor
from voice_service import voice_processor, voice_invoice_builder
from analytics_engine import AnalyticsEngine
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io
import csv
from flask import Response, request

from datetime import datetime
from sqlalchemy import func

from voice_service import VoiceCommandProcessor, VoiceInvoiceBuilder

from pdf_generator import generate_quotation_pdf
from flask import send_file
from models import BankDetails
from datetime import date
from sqlalchemy import func
from app import db
from models import Invoice

import ai_services
import ai_client 

# Initialize analytics engine
analytics_engine = AnalyticsEngine(db.session)

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
            total_tax = 0

            for i, item_data in enumerate(line_items_data, 1):
                quantity = float(item_data['quantity'])
                unit_price = float(item_data['unit_price'])
                tax_percentage = float(item_data.get('tax_percentage', 18.0))

                line_total = quantity * unit_price
                tax_amount = (line_total * tax_percentage) / 100

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
                    total_amount=line_total + tax_amount,
                    cost_price=float(item_data.get('cost_price', 0)),
                    ai_suggested=item_data.get('ai_suggested', False)
                )

                db.session.add(line_item)
                subtotal += line_total
                total_tax += tax_amount
            db.session.commit()

            # Calculate taxes based on client location
            client = Client.query.get(client_id)
            company = Company.query.first()

            if client and company and client.state == company.state:
                invoice.cgst = total_tax / 2
                invoice.sgst = total_tax / 2
                invoice.igst = 0
            else:
                invoice.igst = total_tax
                invoice.cgst = 0
                invoice.sgst = 0

            invoice.subtotal = subtotal
            invoice.total_amount = subtotal + total_tax

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


@app.route('/invoice/<int:id>/pdf')
@login_required
def invoice_pdf(id):
    """Generate PDF for invoice"""
    invoice = Invoice.query.get_or_404(id)
    try:
        pdf_buffer = generate_invoice_pdf(invoice)
        return send_file(pdf_buffer,
                        as_attachment=True,
                        download_name=f'Invoice_{invoice.invoice_number}.pdf',
                        mimetype='application/pdf')
    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        flash('Error generating PDF', 'error')
        return redirect(url_for('invoice_detail', id=id))
    
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
        return redirect(url_for('invoice_detail', id=invoice.id))

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
    invoice = Invoice.query.get_or_404(id)
    recipient_email = invoice.client.email

    if not recipient_email:
        return {"success": False, "message": "Client has no email set."}, 400

    try:
        send_invoice_email(invoice, recipient_email)
        return {"success": True, "message": f"Invoice sent to {recipient_email} successfully!"}
    except Exception as e:
        return {"success": False, "message": f"Failed to send invoice: {str(e)}"}, 500





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
    """Advanced client management with AI insights"""
    search = request.args.get('search', '')
    client_type = request.args.get('type', '')
    page = request.args.get('page', 1, type=int)
    
    # Build query
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
    
    # Pagination
    clients = query.order_by(Client.name).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Prepare iterable for template
    client_list = clients.items if hasattr(clients, 'items') else clients

    # AI insights for clients
    client_insights = {}
    if app.config.get("AI_FEATURES_ENABLED") and ai_services.ai_assistant:
        try:
            for client in client_list:
                if client.ai_risk_score > 0:
                    client_insights[client.id] = {
                        'risk_level': 'High' if client.ai_risk_score > 0.7 else 'Medium' if client.ai_risk_score > 0.3 else 'Low',
                        'predicted_ltv': client.predicted_ltv,
                        'payment_behavior': client.payment_behavior_pattern
                    }
        except Exception as e:
            logging.error(f"Client insights failed: {e}")
    
    return render_template(
        'client_management.html',
        clients=clients,
        client_list=client_list,
        search=search,
        client_type=client_type,
        client_insights=client_insights
    )

@app.route('/create_client', methods=['GET', 'POST'])
@login_required
def create_client():
    """Create new client with AI enhancements"""
    if request.method == 'POST':
        try:
            client = Client(
                name=request.form.get('name'),
                contact_person=request.form.get('contact_person'),
                address=request.form.get('address'),
                city=request.form.get('city'),
                state=request.form.get('state'),
                pincode=request.form.get('pincode'),
                phone=request.form.get('phone'),
                email=request.form.get('email'),
                gstin=request.form.get('gstin'),
                pan=request.form.get('pan'),
                client_type=request.form.get('client_type', 'Regular'),
                lead_stage=request.form.get('lead_stage', 'New'),
                notes=request.form.get('notes', ''),
                tags=request.form.get('tags', ''),
                blockchain_verified=request.form.get('blockchain_verified') == 'on'
            )
            
            # Set follow-up date if provided
            follow_up_date = request.form.get('follow_up_date')
            if follow_up_date:
                client.follow_up_date = datetime.strptime(follow_up_date, '%Y-%m-%d').date()
            
            db.session.add(client)
            db.session.commit()
            
            flash('Client created successfully!', 'success')
            return redirect(url_for('client_management'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Client creation failed: {e}")
            flash(f'Error creating client: {str(e)}', 'error')
    
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

@app.route('/analytics')
@login_required
def analytics():
    """Advanced analytics dashboard with AI insights"""
    try:
        # Time range for analytics
        time_range = request.args.get('range', '12m')  # 12 months default
        
        # Generate comprehensive analytics
        analytics_data = {
            'revenue_trends': analytics_engine.get_revenue_trends(time_range),
            'client_performance': analytics_engine.get_client_performance_metrics(),
            'payment_analytics': analytics_engine.get_payment_analytics(),
            'profitability_analysis': analytics_engine.get_profitability_analysis(),
            'ai_predictions': {},
            'blockchain_insights': {}
        }
        
        # AI-powered predictions
        if app.config.get("AI_FEATURES_ENABLED") and ai_services.predictive_analytics:
            try:
                analytics_data['ai_predictions'] = {
                    'cash_flow': ai_services.predictive_analytics.predict_cash_flow(6),
                    'payment_patterns': ai_services.predictive_analytics.analyze_client_payment_patterns()
                }
            except Exception as e:
                logging.error(f"AI predictions failed: {e}")
        
        # Blockchain analytics
        if app.config.get("BLOCKCHAIN_ENABLED") and blockchain_service:
            try:
                analytics_data['blockchain_insights'] = blockchain_service.get_blockchain_stats()
            except Exception as e:
                logging.error(f"Blockchain analytics failed: {e}")
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
      

@app.route('/analytics/export/pdf')
@login_required
def export_analytics_pdf():

    output = io.BytesIO()
    p = canvas.Canvas(output, pagesize=letter)
    width, height = letter

   
    PAGE_MARGIN = 10

    def draw_page_border():
        p.setStrokeColorRGB(0, 0, 0)
        p.setLineWidth(2)
        p.rect(
            PAGE_MARGIN,
            PAGE_MARGIN,
            width - PAGE_MARGIN * 2,
            height - PAGE_MARGIN * 2
        )

    draw_page_border()


    total_revenue = db.session.query(func.sum(Invoice.total_amount)).scalar() or 0
    total_clients = Client.query.count()
    total_invoices = Invoice.query.count()
    generated_on = datetime.now().strftime('%d-%m-%Y %H:%M')

    y = height - 80

    
    p.setFont("Helvetica-Bold", 20)
    p.drawCentredString(width / 2, y, "ANALYTICS REPORT")
    y -= 30

    p.setFont("Helvetica", 11)
    p.drawCentredString(width / 2, y, f"Generated On : {generated_on}")
    y -= 30

    # Divider
    p.setLineWidth(1)
    p.line(50, y, width - 50, y)
    y -= 40

   
    metrics = [
        ("Total Revenue", f"₹{total_revenue:,.2f}"),
        ("Total Clients", str(total_clients)),
        ("Total Invoices", str(total_invoices)),
    ]

    card_width = width - 140
    card_height = 50
    x = 70

    for label, value in metrics:

        if y - card_height < 80:
            p.showPage()
            draw_page_border()
            y = height - 120

        # Card background
        p.setFillColorRGB(0.95, 0.97, 1)
        p.roundRect(x, y - card_height, card_width, card_height, 10, fill=1)

        # Card border
        p.setStrokeColorRGB(0, 0, 0)
        p.roundRect(x, y - card_height, card_width, card_height, 10, fill=0)

        p.setFillColorRGB(0, 0, 0)

        # Text
        p.setFont("Helvetica-Bold", 14)
        p.drawString(x + 25, y - 30, label)

        p.setFont("Helvetica", 13)
        p.drawRightString(x + card_width - 25, y - 30, value)

        y -= card_height + 30

   
    p.setFont("Helvetica", 10)
    p.drawCentredString(
        width / 2,
        30,
        "System Generated Business Analytics Report"
    )

    p.save()
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="analytics_report.pdf",
        mimetype="application/pdf"
    )

@app.route('/analytics/export/excel')

@login_required
def export_analytics_excel():

    total_revenue = db.session.query(func.sum(Invoice.total_amount)).scalar() or 0
    total_clients = Client.query.count()
    total_invoices = Invoice.query.count()
    generated_on = datetime.now().strftime('%d-%m-%Y %H:%M')

    data = [
        ["Generated On", generated_on],
        ["Total Revenue", total_revenue],
        ["Total Clients", total_clients],
        ["Total Invoices", total_invoices],
    ]

    df = pd.DataFrame(data, columns=["Metric", "Value"])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Analytics")

        workbook = writer.book
        worksheet = writer.sheets["Analytics"]

        # Formatting
        header_format = workbook.add_format({
            "bold": True,
            "font_size": 12,
            "align": "center",
            "border": 1
        })

        cell_format = workbook.add_format({
            "font_size": 11,
            "border": 1
        })

        currency_format = workbook.add_format({
            "num_format": "₹#,##0.00",
            "border": 1
        })

        # Apply formatting
        worksheet.set_column("A:A", 25)
        worksheet.set_column("B:B", 25)

        worksheet.write_row("A1", ["Metric", "Value"], header_format)

        for row in range(1, len(data) + 1):
            worksheet.write(row, 0, df.iloc[row - 1, 0], cell_format)

            if df.iloc[row - 1, 0] == "Total Revenue":
                worksheet.write(row, 1, df.iloc[row - 1, 1], currency_format)
            else:
                worksheet.write(row, 1, df.iloc[row - 1, 1], cell_format)

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="analytics_report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


voice_processor = VoiceCommandProcessor()

@app.route("/api/voice-command", methods=["POST"])
def handle_voice_command():
    try:
        data = request.get_json(force=True)

        voice_text = data.get("text", "").strip()
        language = data.get("language", "en-IN")
        user_id = data.get("user_id", 1)  # default for now

        if not voice_text:
            return jsonify({
                "success": False,
                "message": "No voice text received"
            }), 400

        result = voice_processor.process(voice_text, language=language)

        return jsonify(result)

    except Exception as e:
        # 🔴 THIS IS THE MOST IMPORTANT PART
        import traceback
        traceback.print_exc()

        return jsonify({
            "success": False,
            "message": "Internal server error in voice command",
            "error": str(e)
        }), 500

    

 

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


# AI Chat API
@app.route("/api/ai/chat", methods=["POST"])
@login_required
def ai_chat():
    data = request.get_json()
    message = (data.get("message") or "").lower()

    try:
        # -------------------------
        # CREATE INVOICE (AI)
        # -------------------------
        if "create" in message and "invoice" in message:
            top_client = (
                db.session.query(Client)
                .join(Invoice)
                .group_by(Client.id)
                .order_by(func.sum(Invoice.total_amount).desc())
                .first()
            )

            if not top_client:
                return jsonify(reply="❌ No clients found to create an invoice.")

            return jsonify(reply=(
                f"🧾 Creating invoice for <b>{top_client.name}</b>.<br>"
                f"<a href='{url_for('create_invoice', client_id=top_client.id)}'>"
                f"👉 Click here to continue</a>"
            ))
        
        # -------------------------
        # CLIENT FOLLOW-UP
        # -------------------------
        if "follow" in message:
            clients = (
                db.session.query(Client.name)
                .join(Invoice)
                .filter(Invoice.payment_status.in_(["Unpaid", "Overdue"]))
                .distinct()
                .all()
            )

            if not clients:
                return jsonify(reply="🎉 No clients currently need follow-up.")

            names = ", ".join(c.name for c in clients)
            return jsonify(reply=f"📋 Clients needing follow-up:<br><b>{names}</b>")

        # -------------------------
        # PAYMENT ANALYSIS (AI)
        # -------------------------
        if "payment" in message and "analy" in message:
            if not ai_services.predictive_analytics:
                return jsonify(error="AI unavailable")

            analysis = ai_services.predictive_analytics.analyze_client_payment_patterns()
            return jsonify(reply=format_payment_analysis(analysis))

        # -------------------------
        # REVENUE
        # -------------------------
        if "revenue" in message:
            total = (
                db.session.query(func.sum(Invoice.total_amount))
                .filter(Invoice.payment_status == "Paid")
                .scalar() or 0
            )
            return jsonify(reply=f"💰 Total revenue collected: ₹{int(total):,}")

        # -------------------------
        # CLIENT COUNT
        # -------------------------
        if "how many" in message and "client" in message:
            count = Client.query.count()
            return jsonify(reply=f"👥 You have <b>{count}</b> clients.")

        # -------------------------
        # FALLBACK → AI CHAT
        # -------------------------
        if ai_services.ai_assistant:
            reply = ai_services.ai_assistant.general_chat(message)
            return jsonify(reply=reply)

        return jsonify(error="AI unavailable")

    except Exception as e:
        return jsonify(error=str(e))


def format_payment_analysis(data):
    segments = data.get("payment_behavior_segments", [])
    output = ["📊 <b>Payment Analysis</b><br>"]

    for s in segments:
        output.append(
            f"• <b>{s['segment_name']}</b>: "
            f"{s['client_count']} clients "
            f"(avg delay {round(s['avg_delay_days'],1)} days)"
        )

    return "<br>".join(output)

# For OpenAI service status check
# @app.route("/api/ai/status")
# def ai_status():
#     return {
#         "ai_assistant": ai_services.ai_assistant is not None,
#         "predictive_analytics": ai_services.predictive_analytics is not None,
#         "inventory_ai": ai_services.inventory_ai is not None
#     }

# For Openrouter service status check
@app.route("/api/ai/status")
def ai_status():
    return {
        "provider": ai_client.PROVIDER,
        "available": ai_client.AI_AVAILABLE,
        "model": ai_client.MODEL,
        "ai_assistant": ai_services.ai_assistant is not None,
        "predictive_analytics": ai_services.predictive_analytics is not None,
        "inventory_ai": ai_services.inventory_ai is not None
    }