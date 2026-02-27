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
    """Generate invoice PDF matching the reference image layout."""
    try:
        # ── Resolve company ────────────────────────────────────────────────
        if not company:
            company = Company.query.first()
        if not company:
            company = type('Company', (), {
                'name':    config.COMPANY_NAME,
                'address': config.COMPANY_ADDRESS,
                'city':    config.COMPANY_CITY,
                'state':   config.COMPANY_STATE,
                'pincode': config.COMPANY_PINCODE,
                'phone':   config.COMPANY_PHONE,
                'email':   config.COMPANY_EMAIL,
                'gstin':   config.GSTIN,
                'pan':     config.PAN,
            })()

        client = invoice.client

        # ── Canvas setup ───────────────────────────────────────────────────
        buffer = io.BytesIO()
        page_w, page_h = A4          # 595.27 x 841.89 pt
        c = canvas.Canvas(buffer, pagesize=A4)

        # Margins
        ML = 30   # left
        MR = 30   # right
        MT = 30   # top
        full_w = page_w - ML - MR    # usable width  ≈ 535 pt

        # Helper: thin black border line
        def hline(y, x0=ML, x1=page_w - MR, lw=0.5):
            c.setLineWidth(lw)
            c.setStrokeColor(colors.black)
            c.line(x0, y, x1, y)

        def vline(x, y0, y1, lw=0.5):
            c.setLineWidth(lw)
            c.setStrokeColor(colors.black)
            c.line(x, y0, x, y1)

        def rect(x, y, w, h, fill=0):
            c.setLineWidth(0.5)
            c.setStrokeColor(colors.black)
            c.rect(x, y, w, h, fill=fill)

        # ── ROW 1: INVOICE title (left) | blank logo area (right) ─────────
        row1_top  = page_h - MT
        row1_h    = 40
        row1_bot  = row1_top - row1_h

        # Outer border for row 1
        rect(ML, row1_bot, full_w, row1_h)

        # "INVOICE" text
        c.setFont("Helvetica-Bold", 22)
        c.setFillColor(colors.black)
        c.drawString(ML + 6, row1_bot + 12, "INVOICE")

        # Divider between title and logo area
        mid_x = ML + full_w * 0.6
        vline(mid_x, row1_bot, row1_top)

        # "Logo" label (blank space)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.grey)
        c.drawRightString(page_w - MR - 4, row1_bot + 4, "[Logo]")
        c.setFillColor(colors.black)

        # ── ROW 2: Invoice No/Date (left) | Company Name + Address (right) ─
        row2_top = row1_bot
        row2_h   = 50
        row2_bot = row2_top - row2_h
        col_split = mid_x   # align exactly with Row 1 divider

        rect(ML, row2_bot, full_w, row2_h)
        vline(col_split, row2_bot, row2_top)

        # Left: Invoice No / Date
        c.setFont("Helvetica-Bold", 8)
        c.drawString(ML + 4, row2_top - 13, "Invoice No :")
        c.setFont("Helvetica", 8)
        c.drawString(ML + 62, row2_top - 13, str(invoice.invoice_number))

        c.setFont("Helvetica-Bold", 8)
        c.drawString(ML + 4, row2_top - 27, "Date       :")
        c.setFont("Helvetica", 8)
        c.drawString(ML + 62, row2_top - 27, invoice.invoice_date.strftime('%d-%m-%Y'))

        if invoice.due_date:
            c.setFont("Helvetica-Bold", 8)
            c.drawString(ML + 4, row2_top - 41, "Due Date   :")
            c.setFont("Helvetica", 8)
            c.drawString(ML + 62, row2_top - 41, invoice.due_date.strftime('%d-%m-%Y'))

        # Right: Company Name centered, address right-aligned
        right_w   = page_w - MR - col_split
        right_cx  = col_split + right_w / 2

        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(right_cx, row2_top - 14, company.name.upper())

        addr_line = f"{company.address}, {company.city} - {company.pincode}"
        c.setFont("Helvetica", 7.5)
        c.drawCentredString(right_cx, row2_top - 26, addr_line)
        c.drawCentredString(right_cx, row2_top - 37, f"{company.state}")

        # ── ROW 3: To… (left) | Our Details (right) ───────────────────────
        row3_top = row2_bot
        row3_h   = 72
        row3_bot = row3_top - row3_h

        rect(ML, row3_bot, full_w, row3_h)
        vline(col_split, row3_bot, row3_top)

        # Left — "To:" header (bold, underline look via font)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(ML + 4, row3_top - 12, "To,")

        # Client name bold
        c.setFont("Helvetica-Bold", 9)
        client_name = getattr(client, 'name', '') or ''
        c.drawString(ML + 4, row3_top - 24, client_name)

        c.setFont("Helvetica", 8)
        y_cl = row3_top - 36
        for part in [
            getattr(client, 'address', '') or '',
            f"{getattr(client, 'city', '') or ''}, {getattr(client, 'state', '') or ''}",
            getattr(client, 'pincode', '') or '',
        ]:
            if part.strip().strip(','):
                c.drawString(ML + 4, y_cl, part)
                y_cl -= 11

        # Right — "Our Details" box with black header
        c.setFillColor(colors.black)
        c.rect(col_split, row3_top - 14, right_w, 14, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(right_cx, row3_top - 10, "Our Details")
        c.setFillColor(colors.black)

        # GSTIN
        c.setFont("Helvetica-Bold", 8)
        c.drawString(col_split + 4, row3_top - 26, "GSTIN :")
        c.setFont("Helvetica", 8)
        c.drawString(col_split + 48, row3_top - 26, company.gstin or '')

        # PAN
        c.setFont("Helvetica-Bold", 8)
        c.drawString(col_split + 4, row3_top - 38, "PAN   :")
        c.setFont("Helvetica", 8)
        c.drawString(col_split + 48, row3_top - 38, getattr(company, 'pan', '') or '')

        # ── ROW 4: Items table header ──────────────────────────────────────
        row4_top = row3_bot
        row4_h   = 20   # header row height
        row4_bot = row4_top - row4_h

        # Column widths (must sum to full_w) — 8 columns
        col_w = [
            full_w * 0.048,   # Sl No
            full_w * 0.08,    # HSM Code
            full_w * 0.30,    # Description
            full_w * 0.065,   # Qty
            full_w * 0.065,   # Unit
            full_w * 0.11,    # Rate
            full_w * 0.065,   # Tax%
            full_w * 0.167,   # Amount
        ]
        col_labels = ["Sl.\nNo.", "HSM\nCode", "Product Name / Description", "Qty.", "Unit", "Rate", "Tax\n%", "Amount"]
        col_aligns = ['C', 'C', 'C', 'C', 'C', 'C', 'C', 'C']

        # Draw header background
        c.setFillColor(colors.black)
        c.rect(ML, row4_bot, full_w, row4_h, fill=1, stroke=0)
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.5)
        c.rect(ML, row4_bot, full_w, row4_h, fill=0)

        # Header text + vertical dividers
        x_cur = ML
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 7)
        for i, (w, label) in enumerate(zip(col_w, col_labels)):
            cx = x_cur + w / 2
            # two-line labels: split on \n
            parts = label.split('\n')
            if len(parts) == 2:
                c.drawCentredString(cx, row4_bot + 11, parts[0])
                c.drawCentredString(cx, row4_bot + 3,  parts[1])
            else:
                c.drawCentredString(cx, row4_bot + 7, label)
            if i < len(col_w) - 1:
                c.setStrokeColor(colors.white)
                c.setLineWidth(0.3)
                vline(x_cur + w, row4_bot, row4_top, lw=0.3)
                c.setStrokeColor(colors.black)
            x_cur += w
        c.setFillColor(colors.black)

        # ── ROW 5: Item rows (only real items) ────────────────────────────
        item_row_h = 18
        line_items = list(invoice.line_items)
        items_top  = row4_bot
        items_bot  = items_top - item_row_h * len(line_items)

        for idx, item in enumerate(line_items):
            y_top = items_top - idx * item_row_h
            y_bot = y_top - item_row_h
            # alternating light background
            if idx % 2 == 1:
                c.setFillColor(colors.HexColor('#f5f5f5'))
                c.rect(ML, y_bot, full_w, item_row_h, fill=1, stroke=0)
                c.setFillColor(colors.black)

            # outer border for this row
            c.setStrokeColor(colors.black)
            c.setLineWidth(0.4)
            c.rect(ML, y_bot, full_w, item_row_h, fill=0)

            x_cur = ML
            row_vals = [
                str(item.sr_no),
                item.hsn_code or '',
                item.description or '',
                f"{item.quantity:g}",
                getattr(item, 'unit', '') or '',
                f"{item.unit_price:,.2f}",
                f"{getattr(item, 'tax_percentage', 0) or 0:g}%",
                f"{item.total_amount:,.2f}",
            ]
            c.setFont("Helvetica", 7)
            for i, (w, val) in enumerate(zip(col_w, row_vals)):
                # vertical divider
                if i < len(col_w) - 1:
                    vline(x_cur + w, y_bot, y_top, lw=0.4)
                # text align: description left, rate/amount right, others center
                if i == 2:
                    # Description — truncate if too long
                    max_chars = int(w / 3.8)
                    display = val if len(val) <= max_chars else val[:max_chars - 1] + '…'
                    c.drawString(x_cur + 3, y_bot + 5, display)
                elif i in (5, 7):  # Rate and Amount — right aligned
                    c.drawRightString(x_cur + w - 3, y_bot + 5, val)
                else:
                    c.drawCentredString(x_cur + w / 2, y_bot + 5, val)
                x_cur += w

        # ── If no items just draw an empty row placeholder ─────────────────
        if not line_items:
            items_bot = items_top - item_row_h
            c.setLineWidth(0.4)
            c.rect(ML, items_bot, full_w, item_row_h, fill=0)

        # ── Gap between items and totals section ────────────────────────
        gap = 10

        # ── ROW 6: Reference fields (left) | Totals (right) ───────────────
        ref_top = items_bot - gap

        # Collect ref fields
        ref_fields = [
            ("Party GST NO", getattr(invoice, 'parts_gst_no', '') or ''),
            ("Ref Dc",        getattr(invoice, 'ref_dc',       '') or ''),
            ("Ref Dc Date",   getattr(invoice, 'ref_dc_date',  '') or ''),
            ("PO No",         getattr(invoice, 'po_number',    '') or ''),
            ("Date",          getattr(invoice, 'po_date',      '') or ''),
            ("Vehicle No",    getattr(invoice, 'vehicle_no',   '') or ''),
        ]
        # Totals
        totals = [
            ("Sub Total",   f"{invoice.subtotal:,.2f}"),
            ("SGST 9%",     f"{invoice.sgst:,.2f}"),
            ("CGST 9%",     f"{invoice.cgst:,.2f}"),
            ("IGST 18%",    f"{invoice.igst:,.2f}"),
            ("Grand Total", f"{invoice.total_amount:,.2f}"),
        ]
        ref_row_h = 13
        n_rows    = max(len(ref_fields), len(totals))
        ref_bot   = ref_top - ref_row_h * n_rows

        # outer border
        rect(ML, ref_bot, full_w, ref_top - ref_bot)
        vline(col_split, ref_bot, ref_top)

        # Left: ref fields
        for i, (label, val) in enumerate(ref_fields):
            y = ref_top - (i + 1) * ref_row_h + 3
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString(ML + 4, y, f"{label}:")
            c.setFont("Helvetica", 7.5)
            c.drawString(ML + 72, y, str(val))
            if i < len(ref_fields) - 1:
                hline(ref_top - (i + 1) * ref_row_h, x0=ML, x1=col_split, lw=0.3)

        # Right: totals
        for i, (label, val) in enumerate(totals):
            y = ref_top - (i + 1) * ref_row_h + 3
            bold = (label == "Grand Total")
            c.setFont("Helvetica-Bold" if bold else "Helvetica", 7.5)
            c.drawString(col_split + 4, y, f"{label}:")
            c.drawRightString(page_w - MR - 4, y, val)
            if i < len(totals) - 1:
                hline(ref_top - (i + 1) * ref_row_h, x0=col_split, x1=page_w - MR, lw=0.3)

        # ── ROW 7: Bank Details (left) | Signature blank (right) ──────────
        bank_top = ref_bot
        bank_h   = 80
        bank_bot = bank_top - bank_h

        rect(ML, bank_bot, full_w, bank_h)
        vline(col_split, bank_bot, bank_top)

        # "OUR BANK DETAILS" header underlined style
        c.setFont("Helvetica-Bold", 8)
        c.drawString(ML + 4, bank_top - 12, "OUR BANK DETAILS")
        # underline
        txt_w = c.stringWidth("OUR BANK DETAILS", "Helvetica-Bold", 8)
        hline(bank_top - 13, x0=ML + 4, x1=ML + 4 + txt_w, lw=0.6)

        bank_fields = [
            ("Bank Name", bank.bank_name        if bank else ''),
            ("A/C No",    bank.account_number   if bank else ''),
            ("A/C Name",  bank.account_name     if bank else ''),
            ("IFSC Code", bank.ifsc_code        if bank else ''),
            ("Branch",    bank.branch           if bank else ''),
        ]
        c.setFont("Helvetica", 7.5)
        y_b = bank_top - 24
        for label, val in bank_fields:
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString(ML + 4, y_b, f"{label}")
            c.setFont("Helvetica", 7.5)
            c.drawString(ML + 52, y_b, f": {val}")
            y_b -= 11

        # Right: blank signature space + "For Company"
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(right_cx, bank_top - 12, f"For {company.name}")
        # blank signature box outline
        sig_box_x = col_split + 10
        sig_box_y = bank_bot + 10
        sig_box_w = right_w - 20
        sig_box_h = bank_h - 30
        c.setStrokeColor(colors.HexColor('#cccccc'))
        c.setLineWidth(0.4)
        c.rect(sig_box_x, sig_box_y, sig_box_w, sig_box_h, fill=0)
        c.setStrokeColor(colors.black)

        # ── ROW 8: Footer ─────────────────────────────────────────────────
        footer_top = bank_bot
        footer_h   = 18
        footer_bot = footer_top - footer_h

        rect(ML, footer_bot, full_w, footer_h)
        c.setFont("Helvetica", 7.5)
        footer_txt = f"Ph. {company.phone}   |   Email: {company.email}"
        c.drawCentredString(ML + full_w / 2, footer_bot + 5, footer_txt)

        # ── Outer page border ─────────────────────────────────────────────
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.rect(ML, footer_bot, full_w, page_h - MT - footer_bot, fill=0)

        c.save()
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