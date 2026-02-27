import io
from io import BytesIO
from app import db
import os
from datetime import datetime
import pandas as pd
from flask import send_file
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfgen import canvas
import logging
 
from reportlab.pdfgen import canvas
from utils import number_to_words, safe_dict
from models import Company
from analytics_engine import AnalyticsEngine
import config

def generate_invoice_pdf(invoice, company=None, bank=None):
    #Generate a professional invoice PDF with modern styling""" 
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=0.5 * inch,
            bottomMargin=0.5 * inch,
            leftMargin=0.5 * inch,
            rightMargin=0.5 * inch
        )

        styles = getSampleStyleSheet()
        content = []

        # Custom styles
        title_style = ParagraphStyle(
            name='InvoiceTitle',
            fontSize=20,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#2563eb'),
            spaceAfter=20
        )
        
        header_style = ParagraphStyle(
            name='Header',
            fontSize=12,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#1f2937')
        )
        
        normal_style = ParagraphStyle(
            name='Normal',
            fontSize=10,
            fontName='Helvetica',
            textColor=colors.HexColor('#374151')
        )

        # Invoice title
        if getattr(invoice, 'invoice_type', 'Invoice') == 'Proforma':
            title_text = "PROFORMA INVOICE"
        else:
            title_text = "TAX INVOICE"
        
        content.append(Paragraph(title_text, title_style))
        content.append(Spacer(1, 20))

        # Company and invoice details header
        if not company:
            company = Company.query.first()
        
        if not company:
            company = type('Company', (), {
                'name': config.COMPANY_NAME,
                'address': config.COMPANY_ADDRESS,
                'city': config.COMPANY_CITY,
                'state': config.COMPANY_STATE,
                'pincode': config.COMPANY_PINCODE,
                'phone': config.COMPANY_PHONE,
                'email': config.COMPANY_EMAIL,
                'gstin': config.GSTIN,
                'pan': config.PAN,
                'tin': getattr(config, 'TIN', '')
            })()

        header_data = [
            [
                Paragraph(f"<b>Invoice No:</b> {invoice.invoice_number}<br/>"
                         f"<b>Date:</b> {invoice.invoice_date.strftime('%d-%m-%Y')}<br/>"
                         f"<b>Due Date:</b> {invoice.due_date.strftime('%d-%m-%Y') if invoice.due_date else 'N/A'}", 
                         normal_style),
                Paragraph(f"<b>{company.name}</b><br/>"
                         f"{company.address}<br/>"
                         f"{company.city}, {company.state} - {company.pincode}<br/>"
                         f"Phone: {company.phone}<br/>"
                         f"Email: {company.email}", 
                         normal_style)
            ]
        ]
        
        header_table = Table(header_data, colWidths=[3.5 * inch, 3.5 * inch])
        header_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f9fafb')),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        content.append(header_table)
        content.append(Spacer(1, 20))

        # Bill to and company GST details
        client = invoice.client
        bill_to_data = [
            [
                Paragraph("<b>Bill To</b>", header_style),
                Paragraph("<b>Company Details</b>", header_style)
            ],
            [
                Paragraph(f"<b>{client.name}</b><br/>"
                         f"{client.contact_person}<br/>" if client.contact_person else "" +
                         f"{client.address}<br/>"
                         f"{client.city}, {client.state} - {client.pincode}<br/>"
                         f"Phone: {client.phone}<br/>"
                         f"Email: {client.email}<br/>"
                         f"<b>GSTIN:</b> {client.gstin or 'N/A'}", 
                         normal_style),
                Paragraph(f"<b>GSTIN:</b> {company.gstin}<br/>"
                         f"<b>PAN:</b> {company.pan}<br/>"
                         f"<b>State:</b> {company.state}<br/>"
                         f"<b>State Code:</b> {company.gstin[:2] if company.gstin else 'N/A'}", 
                         normal_style)
            ]
        ]
        
        bill_to_table = Table(bill_to_data, colWidths=[3.5 * inch, 3.5 * inch])
        bill_to_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#3b82f6')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        content.append(bill_to_table)
        content.append(Spacer(1, 20))

        # Line items table
        items_data = [['S.No', 'HSN/SAC', 'Description', 'Qty', 'Unit', 'Rate', 'Tax%', 'Amount']]
        
        for item in invoice.line_items:
            items_data.append([
                str(item.sr_no),
                item.hsn_code or '',
                Paragraph(item.description.replace('\n', '<br/>'), normal_style),
                f"{item.quantity:g}",
                item.unit,
                f"Rs. {item.unit_price:,.2f}",
                f"{item.tax_percentage:g}%",
                f"Rs. {item.total_amount:,.2f}"
            ])

        # Add empty rows to maintain table structure
        while len(items_data) < 12:  # Minimum 10 rows for professional look
            items_data.append(['', '', '', '', '', '', '', ''])

        items_table = Table(items_data, colWidths=[
            0.5*inch, 0.8*inch, 2.8*inch, 0.6*inch, 0.6*inch, 0.8*inch, 0.5*inch, 1*inch
        ])
        
        items_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (2, 1), (2, -1), 'LEFT'),
            ('ALIGN', (5, 1), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        content.append(items_table)
        content.append(Spacer(1, 15))

        # Tax summary and totals
        tax_data = [
            ['', '', 'Subtotal:', f"Rs. {invoice.subtotal:,.2f}"],
            ['', '', 'CGST:', f"Rs. {invoice.cgst:,.2f}"],
            ['', '', 'SGST:', f"Rs. {invoice.sgst:,.2f}"],
            ['', '', 'IGST:', f"Rs. {invoice.igst:,.2f}"],
            ['', '', 'Round Off:', 'Rs. 0.00'],
            ['', '', Paragraph('<b>Total Amount:</b>', header_style), 
             Paragraph(f'<b>Rs. {invoice.total_amount:,.2f}</b>', header_style)]
        ]
        
        tax_table = Table(tax_data, colWidths=[2*inch, 2*inch, 1.5*inch, 1.5*inch])
        tax_table.setStyle(TableStyle([
            ('GRID', (2, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (2, -1), (-1, -1), colors.HexColor('#f3f4f6')),
            ('LEFTPADDING', (2, 0), (-1, -1), 8),
            ('RIGHTPADDING', (2, 0), (-1, -1), 8),
            ('TOPPADDING', (2, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (2, 0), (-1, -1), 4),
        ]))
        content.append(tax_table)
        content.append(Spacer(1, 15))

        # Amount in words
        amount_words = number_to_words(int(invoice.total_amount))
        words_text = f"Amount in Words: {amount_words.title()} Rupees Only"
        
        words_table = Table([[Paragraph(f'<b>{words_text}</b>', normal_style)]], 
                           colWidths=[7*inch])
        words_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f9fafb')),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        content.append(words_table)
        content.append(Spacer(1, 20))

        from flask import g

        # bank = BankDetails.query.filter_by(company_id=invoice.company_id).first()
        # Terms and bank details
        terms_data = [
            [
                Paragraph("<b>Terms & Conditions:</b><br/>" + 
                         (invoice.terms_conditions or 
                          "1. Payment due within 30 days of invoice date.<br/>"
                          "2. Interest @ 2% per month will be charged on overdue amounts.<br/>"
                          "3. Subject to local jurisdiction only."), 
                         normal_style),
                Paragraph(
                    f"<b>Bank Details:</b><br/>"
                    f"Bank: {bank.bank_name if bank else ''}<br/>"
                    f"A/c No: {bank.account_number if bank else ''}<br/>"
                    f"A/c Name: {bank.account_name if bank else ''}<br/>"
                    f"IFSC: {bank.ifsc_code if bank else ''}<br/>"
                    f"Branch: {bank.branch if bank else ''}",
                    normal_style
                )
            ]
        ]
        
        terms_table = Table(terms_data, colWidths=[3.5*inch, 3.5*inch])
        terms_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        content.append(terms_table)
        content.append(Spacer(1, 30))

        # Signature section
        signature_data = [
            ['', f"For {company.name}"],
            ['', ''],
            ['', ''],
            ['Customer Signature', 'Authorized Signatory']
        ]
        
        signature_table = Table(signature_data, colWidths=[3.5*inch, 3.5*inch])
        signature_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (0, -1), (-1, -1), 0.5, colors.HexColor('#6b7280')),
        ]))
        content.append(signature_table)

        # Add footer
        footer_text = f"This is a computer generated invoice | Generated on {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        if invoice.blockchain_hash:
            footer_text += f" | Blockchain Verified: {invoice.blockchain_hash[:16]}..."
        
        footer_para = Paragraph(footer_text, 
                               ParagraphStyle('Footer', fontSize=8, alignment=TA_CENTER, 
                                            textColor=colors.HexColor('#6b7280')))
        content.append(Spacer(1, 20))
        content.append(footer_para)

        # Build PDF
        doc.build(content)
        buffer.seek(0)
        
        return buffer

    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Watermark helpers for triple-copy download
# ─────────────────────────────────────────────────────────────────────────────

def add_watermark_to_pdf(source_buffer, watermark_text="DUPLICATE"):
    """Overlay a diagonal watermark on every page of *source_buffer*.

    Args:
        source_buffer : io.BytesIO containing a valid PDF.
        watermark_text: text to stamp diagonally across each page.

    Returns:
        io.BytesIO with the watermarked PDF.
    """
    from pypdf import PdfReader, PdfWriter
    import math

    # 1. Build a single-page watermark PDF in memory using reportlab canvas
    wm_buffer = io.BytesIO()
    page_width, page_height = A4  # (595.27, 841.89) in points

    c = canvas.Canvas(wm_buffer, pagesize=A4)

    # Semi-transparent red diagonal text
    c.saveState()
    c.setFont("Helvetica-Bold", 72)
    c.setFillColorRGB(0.85, 0.1, 0.1, alpha=0.18)   # light-red, near-transparent
    c.translate(page_width / 2, page_height / 2)
    c.rotate(45)
    text_width = c.stringWidth(watermark_text, "Helvetica-Bold", 72)
    c.drawString(-text_width / 2, 0, watermark_text)
    c.restoreState()
    c.save()
    wm_buffer.seek(0)

    # 2. Read the watermark page and the source PDF
    wm_reader = PdfReader(wm_buffer)
    wm_page   = wm_reader.pages[0]

    source_buffer.seek(0)
    src_reader = PdfReader(source_buffer)
    writer = PdfWriter()

    for page in src_reader.pages:
        page.merge_page(wm_page)   # merge watermark on top of content
        writer.add_page(page)

    out_buffer = io.BytesIO()
    writer.write(out_buffer)
    out_buffer.seek(0)
    return out_buffer


def generate_triple_invoice_pdf(invoice, company=None, bank=None):
    """Generate a single PDF containing 3 copies of the invoice.

    Page layout:
      • Copy 1 – ORIGINAL  (no watermark)
      • Copy 2 – DUPLICATE (diagonal watermark)
      • Copy 3 – DUPLICATE (diagonal watermark)

    Returns:
        io.BytesIO  — merged PDF with all 3 copies.
    """
    from pypdf import PdfReader, PdfWriter

    # Generate the base invoice once
    base_buffer = generate_invoice_pdf(invoice, company=company, bank=bank)
    base_buffer.seek(0)
    base_bytes = base_buffer.read()

    # Copy 1 – original (no watermark)
    copy1 = io.BytesIO(base_bytes)

    # Copy 2 – duplicate watermark
    copy2 = add_watermark_to_pdf(io.BytesIO(base_bytes), "DUPLICATE")

    # Copy 3 – duplicate watermark
    copy3 = add_watermark_to_pdf(io.BytesIO(base_bytes), "DUPLICATE")

    # Merge all 3 copies into one PDF
    writer = PdfWriter()
    for buf in (copy1, copy2, copy3):
        buf.seek(0)
        reader = PdfReader(buf)
        for page in reader.pages:
            writer.add_page(page)

    merged = io.BytesIO()
    writer.write(merged)
    merged.seek(0)
    return merged


def generate_challan_pdf(challan, company=None):
    #Generate delivery challan PDF
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=0.5 * inch,
            bottomMargin=0.5 * inch,
            leftMargin=0.5 * inch,
            rightMargin=0.5 * inch
        )

        styles = getSampleStyleSheet()
        content = []

        # Custom styles (reused/adapted)
        title_style = ParagraphStyle(
            name='ChallanTitle',
            fontSize=18,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#dc2626'),
            spaceAfter=20
        )
        
        header_style = ParagraphStyle(
            name='Header',
            fontSize=12,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#1f2937')
        )
        
        normal_style = ParagraphStyle(
            name='Normal',
            fontSize=10,
            fontName='Helvetica',
            textColor=colors.HexColor('#374151')
        )

        content.append(Paragraph("DELIVERY CHALLAN", title_style))
        content.append(Spacer(1, 10))

        # Company Header (similar to invoice)
        if not company:
            company = Company.query.first()
            
        if not company:
            company = type('Company', (), {
                'name': config.COMPANY_NAME,
                'address': config.COMPANY_ADDRESS,
                'city': config.COMPANY_CITY,
                'state': config.COMPANY_STATE,
                'pincode': config.COMPANY_PINCODE,
                'phone': config.COMPANY_PHONE,
                'email': config.COMPANY_EMAIL,
                'gstin': config.GSTIN
            })()

        # Challan Details
        # Try to get client from preview_client (transient) or standard relationship
        client = getattr(challan, 'preview_client', None) or challan.client
        
        # Fallback if client is missing (should not happen in preview flow)
        if not client:
             client = type('Client', (), {
                'name': 'Unknown Client',
                'address': '',
                'city': '', 
                'state': '',
                'pincode': '',
                'phone': '',
                'email': ''
            })()

        header_data = [
            [
                Paragraph(f"<b>Challan No:</b> {challan.challan_number}<br/>"
                          f"<b>Date:</b> {challan.challan_date.strftime('%d-%m-%Y')}<br/>"
                          f"<b>Delivery Date:</b> {challan.delivery_date.strftime('%d-%m-%Y') if challan.delivery_date else 'N/A'}", 
                          normal_style),
                Paragraph(f"<b>{company.name}</b><br/>"
                          f"{company.address}<br/>"
                          f"{company.city}, {company.state} - {company.pincode}<br/>"
                          f"Phone: {company.phone}", 
                          normal_style)
            ]
        ]
        
        header_table = Table(header_data, colWidths=[3.5 * inch, 3.5 * inch])
        header_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f9fafb')),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        content.append(header_table)
        content.append(Spacer(1, 20))

        # Ship To / Bill To
        client_details = (
            f"<b>{getattr(client, 'name', 'Unknown Client')}</b><br/>"
            f"{getattr(client, 'contact_person', '')}<br/>"
            f"{getattr(client, 'address', '')}<br/>"
            f"{getattr(client, 'city', '')}, {getattr(client, 'state', '')} - {getattr(client, 'pincode', '')}<br/>"
            f"Phone: {getattr(client, 'phone', '')}"
        )

        ship_data = [
            [
                Paragraph("<b>Ship To</b>", header_style),
                Paragraph("<b>Vehicle / Transport Details</b>", header_style)
            ],
            [
                Paragraph(client_details, normal_style),
                Paragraph(challan.notes or "No specific instructions", normal_style)
            ]
        ]
        
        ship_table = Table(ship_data, colWidths=[3.5 * inch, 3.5 * inch])
        ship_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#dc2626')), # Red theme for challan
            ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        content.append(ship_table)
        content.append(Spacer(1, 20))

        # Items Table
        items_data = [['S.No', 'HSN', 'Description', 'Qty', 'Unit']]
        
        for item in challan.line_items:
            items_data.append([
                str(item.sr_no),
                item.hsn_code or '',
                Paragraph(item.description, normal_style),
                f"{item.quantity:g}",
                item.unit
            ])

        # Fill empty rows
        while len(items_data) < 10:
            items_data.append(['', '', '', '', ''])

        items_table = Table(items_data, colWidths=[
            0.5*inch, 1*inch, 4*inch, 0.8*inch, 0.7*inch
        ])
        
        items_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (2, 1), (2, -1), 'LEFT'), # Description left align
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        content.append(items_table)
        content.append(Spacer(1, 30))

        # Footer / Signatures
        signature_data = [
            ['', f"For {company.name}"],
            ['', ''],
            ['', ''],
            ['Receiver\'s Signature', 'Authorized Signatory']
        ]
        
        signature_table = Table(signature_data, colWidths=[3.5*inch, 3.5*inch])
        signature_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (0, -1), (-1, -1), 0.5, colors.HexColor('#6b7280')),
        ]))
        content.append(signature_table)

        doc.build(content)
        buffer.seek(0)
        
        return buffer

    except Exception as e:
        logging.error(f"Challan PDF generation failed: {e}")
        raise

def export_excel(invoices, filename="invoices_export.xlsx"):
    """Export invoices to Excel format"""
    try:
        import xlsxwriter
        
        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer)
        worksheet = workbook.add_worksheet('Invoices')
        
        # Headers
        headers = ['Invoice No', 'Date', 'Client', 'Amount', 'Status', 'Due Date']
        for col, header in enumerate(headers):
            worksheet.write(0, col, header)
        
        # Data
        for row, invoice in enumerate(invoices, 1):
            worksheet.write(row, 0, invoice.invoice_number)
            worksheet.write(row, 1, invoice.invoice_date.strftime('%Y-%m-%d'))
            worksheet.write(row, 2, invoice.client.name)
            worksheet.write(row, 3, invoice.total_amount)
            worksheet.write(row, 4, invoice.payment_status)
            worksheet.write(row, 5, invoice.due_date.strftime('%Y-%m-%d') if invoice.due_date else '')
        
        workbook.close()
        buffer.seek(0)
        
        return buffer

    except Exception as e:
        logging.error(f"Excel export failed: {e}")
        raise


def generate_quotation_pdf(q):
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=40,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title",
        fontSize=20,
        alignment=TA_CENTER,
        spaceAfter=10,
        textColor=colors.HexColor("#2c3e50")
    )

    label_style = ParagraphStyle(
        "label",
        fontSize=10,
        textColor=colors.grey
    )

    value_style = ParagraphStyle(
        "value",
        fontSize=11
    )

    elements = []

    # ================= TITLE =================
    elements.append(Paragraph("QUOTATION", title_style))
    elements.append(Spacer(1, 10))

    # ================= QUOTATION INFO =================
    info_data = [
        ["Quotation No", q.quotation_number, "Status", q.status],
        ["Quotation Date", str(q.quotation_date), "Sales Person", q.sales_person],
        ["Validity (Days)", str(q.validity_days), "Grand Total", f"Rs. {q.grand_total:,.2f}"],
    ]

    info_table = Table(info_data, colWidths=[90, 180, 90, 150])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("FONT", (0,0), (-1,-1), "Helvetica"),
        ("ALIGN", (-1,0), (-1,-1), "RIGHT"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 8),
    ]))

    elements.append(info_table)
    elements.append(Spacer(1, 20))

    # ================= PRICING SUMMARY =================
    pricing_data = [
        ["Subtotal", f"Rs. {q.subtotal:,.2f}"],
        ["Discount", f"Rs. {q.discount:,.2f}"],
        ["Taxable Value", f"Rs. {q.taxable_value:,.2f}"],
        ["CGST", f"Rs. {q.cgst:,.2f}"],
        ["SGST", f"Rs. {q.sgst:,.2f}"],
        ["Shipping", f"Rs. {q.shipping:,.2f}"],
        ["Rounding", f"Rs. {q.rounding:,.2f}"],
        ["Grand Total", f"Rs. {q.grand_total:,.2f}"],
    ]

    pricing_table = Table(pricing_data, colWidths=[200, 150])
    pricing_table.setStyle(TableStyle([
        ("BACKGROUND", (0,-1), (-1,-1), colors.lightgrey),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("FONT", (0,-1), (-1,-1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
    ]))

    elements.append(Paragraph("Pricing Summary", styles["Heading3"]))
    elements.append(pricing_table)
    elements.append(Spacer(1, 20))

    # ================= DELIVERY TERMS =================
    terms_text = f"""
    <b>Delivery Timeline:</b> {q.delivery_timeline}<br/>
    <b>Project Scope:</b> {q.project_scope}<br/>
    <b>Milestones:</b> {q.milestones}<br/>
    <b>Warranty:</b> {q.warranty}<br/>
    <b>Revision Policy:</b> {q.revision_policy}<br/>
    <b>Dependencies:</b> {q.dependencies}<br/>
    """

    elements.append(Paragraph("Delivery & Project Terms", styles["Heading3"]))
    elements.append(Paragraph(terms_text, styles["Normal"]))
    elements.append(Spacer(1, 15))

    # ================= TERMS & CONDITIONS =================
    elements.append(Paragraph("Terms & Conditions", styles["Heading3"]))
    elements.append(Paragraph(q.terms or "-", styles["Normal"]))

    # ================= PAGE BORDER =================
    def draw_border(canvas, doc):
        canvas.setStrokeColor(colors.grey)
        canvas.setLineWidth(1)
        canvas.rect(20, 20, A4[0]-40, A4[1]-40)

    doc.build(elements, onFirstPage=draw_border, onLaterPages=draw_border)

    buffer.seek(0)
    return buffer
class AnalyticsReportGenerator:
    def __init__(self):
        self.engine = AnalyticsEngine(db.session)
        
    def generate_excel_report(self, analytics_data):
        revenue_trends = safe_dict(analytics_data.get("revenue_trends", {}))
    # build excel

        output = io.BytesIO()

        revenue = self.engine.get_revenue_trends()
        profit = self.engine.get_profitability_analysis()
        payments = self.engine.get_payment_analytics()
        clients = self.engine.get_client_performance_metrics()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:

            pd.DataFrame(revenue["monthly_data"]) \
                .to_excel(writer, sheet_name="Revenue Trends", index=False)

            pd.DataFrame(profit["monthly_trends"]) \
                .to_excel(writer, sheet_name="Profitability", index=False)

            pd.DataFrame(payments["payment_status_distribution"]) \
                .to_excel(writer, sheet_name="Payments", index=False)

            pd.DataFrame(clients["top_clients"]) \
                .to_excel(writer, sheet_name="Client Performance", index=False)

        output.seek(0)
        return output

    def generate_pdf_report(self, analytics_data):
        revenue_trends = safe_dict(analytics_data.get("revenue_trends", {}))
        # build pdf

        buffer = BytesIO()
        pdf = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        revenue = self.engine.get_revenue_trends()
        profit = self.engine.get_profitability_analysis()
        payments = self.engine.get_payment_analytics()
        clients = self.engine.get_client_performance_metrics()

        elements.append(Paragraph("Analytics Report", styles["Title"]))
        elements.append(Spacer(1, 12))

        # Revenue
        elements.append(Paragraph("Revenue Trends", styles["Heading2"]))
        revenue_table = [["Month", "Revenue"]]
        for r in revenue["monthly_data"]:
            revenue_table.append([r["month"], f"Rs. {r['revenue']}"])
        elements.append(Table(revenue_table))
        elements.append(Spacer(1, 10))

        # Profit
        elements.append(Paragraph("Profitability Analysis", styles["Heading2"]))
        profit_table = [["Month", "Profit"]]
        for p in profit["monthly_trends"]:
            profit_table.append([p["month"], f"Rs. {p['profit']}"])
        elements.append(Table(profit_table))
        elements.append(Spacer(1, 10))

        # Payments
        elements.append(Paragraph("Payment Status", styles["Heading2"]))
        payment_table = [["Status", "Amount"]]
        for pay in payments["payment_status_distribution"]:
            payment_table.append([pay["status"], f"Rs. {pay['amount']}"])
        elements.append(Table(payment_table))
        elements.append(Spacer(1, 10))

        # Clients
        elements.append(Paragraph("Top Clients", styles["Heading2"]))
        client_table = [["Client", "Revenue", "Invoices"]]
        for c in clients["top_clients"]:
            client_table.append([c["name"], f"Rs. {c['total_revenue']}", c["invoice_count"]])
        elements.append(Table(client_table))

        pdf.build(elements)
        buffer.seek(0)
        return buffer