
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
            inv_item = InvoiceLineItem(
                invoice_id=new_invoice.id,
                sr_no=item.sr_no,
                hsn_code=item.hsn_code,
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=item.unit_price,
                total_amount=item.total_amount
            )
            total_amt += inv_item.total_amount
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
        flash(f'Error converting to invoice: {str(e)}', 'error')
        return redirect(url_for('delivery_challan'))
