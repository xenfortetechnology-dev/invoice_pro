import io
from io import BytesIO
from app import db
import os
import requests
from datetime import datetime
import pandas as pd
from flask import send_file
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.pdfgen import canvas
import logging
 
from reportlab.pdfgen import canvas
from utils import number_to_words, safe_dict
from models import Company
from analytics_engine import AnalyticsEngine
import config

def generate_invoice_pdf(invoice, company=None, bank=None, logo_bytes=None, signature_bytes=None):
    """Generate invoice PDF with bottom-fixed references + totals + bank/signature area.
    Gap between items table and bottom block adjusts automatically."""
    try:
        if not company:
            company = Company.query.first() or type('Company', (), {
                'name': config.COMPANY_NAME, 'address': config.COMPANY_ADDRESS,
                'city': config.COMPANY_CITY, 'state': config.COMPANY_STATE,
                'pincode': config.COMPANY_PINCODE, 'phone': config.COMPANY_PHONE,
                'email': config.COMPANY_EMAIL, 'gstin': config.GSTIN, 'pan': config.PAN,
            })()

        client = invoice.client

        buffer = io.BytesIO()
        page_w, page_h = A4
        c = canvas.Canvas(buffer, pagesize=A4)
        c.setTitle(f"Invoice {invoice.invoice_number}")
        c.setAuthor(getattr(company, 'name', 'Invoice Pro') if company else 'Invoice Pro')
        c.setSubject("Invoice")

        ML = MR = MT = 36
        full_w = page_w - ML - MR
        col_split = ML + full_w * 0.58

        def hline(y, x0=ML, x1=page_w-MR, lw=0.5):
            c.setLineWidth(lw); c.setStrokeColor(colors.black); c.line(x0,y,x1,y)

        def vline(x, y0, y1, lw=0.5):
            c.setLineWidth(lw); c.setStrokeColor(colors.black); c.line(x,y0,x,y1)

        def rect(x, y, w, h, fill=0):
            c.setLineWidth(0.5); c.setStrokeColor(colors.black); c.rect(x,y,w,h,fill=fill)

        # ── 1. Draw top fixed parts ────────────────────────────────────────────
        y = page_h - MT

        # Row 1: INVOICE + logo (auto-scaled & centered)
        row1_h = 48
        rect(ML, y-row1_h, full_w, row1_h)
        c.setFont("Helvetica-Bold", 24)
        c.drawString(ML + 8, y - 30, "INVOICE")
        vline(col_split, y-row1_h, y)

        if logo_bytes:
            try:
                logo = ImageReader(io.BytesIO(logo_bytes))
                orig_w, orig_h = logo.getSize()
                max_logo_w = (page_w - MR - col_split) - 20
                max_logo_h = row1_h - 12
                scale = min(max_logo_w / orig_w, max_logo_h / orig_h, 1.0)
                draw_w = orig_w * scale
                draw_h = orig_h * scale
                logo_x = col_split + ((page_w - MR - col_split) - draw_w) / 2
                logo_y = (y - row1_h) + (row1_h - draw_h) / 2
                c.drawImage(logo, logo_x, logo_y, width=draw_w, height=draw_h,
                            preserveAspectRatio=True, mask='auto')
            except Exception as e:
                print("Logo rendering failed:", e)

        y -= row1_h + 4

        # Row 2: Invoice info | Company
        row2_h = 64
        rect(ML, y-row2_h, full_w, row2_h)
        vline(col_split, y-row2_h, y)

        c.setFont("Helvetica-Bold", 9)
        c.drawString(ML+6, y-16, "Invoice No :"); c.setFont("Helvetica",9); c.drawString(ML+78, y-16, str(invoice.invoice_number))
        c.setFont("Helvetica-Bold",9); c.drawString(ML+6, y-32, "Date       :"); c.setFont("Helvetica",9); c.drawString(ML+78, y-32, invoice.invoice_date.strftime('%d-%m-%Y'))
        if invoice.due_date:
            c.setFont("Helvetica-Bold",9); c.drawString(ML+6, y-48, "Due Date   :"); c.setFont("Helvetica",9); c.drawString(ML+78, y-48, invoice.due_date.strftime('%d-%m-%Y'))

        right_w = page_w - MR - col_split
        rcx = col_split + right_w / 2
        cname = (company.name or "").upper()
        c.setFont("Helvetica-Bold", 12)
        if c.stringWidth(cname, "Helvetica-Bold", 12) <= right_w - 20:
            c.drawCentredString(rcx, y-18, cname)
            name_h = 18
        else:
            words = cname.split(); l1 = l2 = ""
            for w in words:
                test = (l1 + " " + w).strip()
                if c.stringWidth(test, "Helvetica-Bold", 12) <= right_w - 20:
                    l1 = test
                else:
                    l2 = (l2 + " " + w).strip()
            c.drawCentredString(rcx, y-14, l1)
            c.drawCentredString(rcx, y-30, l2.strip())
            name_h = 34

        addr_str = f"{company.address or ''}, {company.city or ''} - {company.pincode or ''}, {company.state or ''}"
        pstyle = ParagraphStyle('addr', fontName='Helvetica', fontSize=8.5, leading=10, alignment=1, spaceAfter=4)
        para = Paragraph(addr_str, pstyle)
        pw, ph = para.wrap(right_w-16, 9999)
        para.drawOn(c, col_split+8, y - name_h - 8 - ph)

        y -= row2_h + 6

        # ── Row 3: To (with full client address) | Our Details ─────────────────
        row3_h = 110   # Increased to fit address comfortably
        rect(ML, y - row3_h, full_w, row3_h)
        vline(col_split, y - row3_h, y)

        # Left side – TO block (auto wrapped)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(ML + 6, y - 16, "To,")

        client_name = client.name or "—"

        client_address = f"""
        <b>{client_name}</b><br/>
        {client.address or ""}<br/>
        {client.city or ""}, {client.state or ""} - {client.pincode or ""}<br/>
        GSTIN: {getattr(client, 'gstin', '') or "—"}
        """

        client_style = ParagraphStyle(
            'client_addr',
            fontName='Helvetica',
            fontSize=9,
            leading=12,
        )

        client_para = Paragraph(client_address, client_style)

        available_width = col_split - ML - 14
        pw, ph = client_para.wrap(available_width, row3_h - 20)

        client_para.drawOn(
            c,
            ML + 6,
            y - 34 - ph
        )

        # Right side – Our Details
        c.setFillColor(colors.black)
        c.rect(col_split, y - 18, right_w, 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(rcx, y - 13, "Our Details")
        c.setFillColor(colors.black)

        c.setFont("Helvetica-Bold", 9)
        c.drawString(col_split + 8, y - 36, "GSTIN :")
        c.setFont("Helvetica", 9)
        c.drawString(col_split + 58, y - 36, company.gstin or "")

        c.setFont("Helvetica-Bold", 9)
        c.drawString(col_split + 8, y - 52, "PAN   :")
        c.setFont("Helvetica", 9)
        c.drawString(col_split + 58, y - 52, company.pan or "")

        y -= row3_h + 8

        # ── Items table ────────────────────────────────────────────────────────
        header_h = 22
        rect(ML, y-header_h, full_w, header_h)
        c.setFillColor(colors.black)
        c.rect(ML, y-header_h, full_w, header_h, fill=1, stroke=0)
        c.setFillColor(colors.white)

        col_w = [full_w*0.05, full_w*0.09, full_w*0.30, full_w*0.07, full_w*0.07, full_w*0.115, full_w*0.07, full_w*0.185]
        headers = ["Sl.\nNo", "HSN\nCode", "Product Name / Description", "Qty.", "Unit", "Rate", "Tax", "Amount"]

        c.setFont("Helvetica-Bold", 8)
        x = ML
        for w, txt in zip(col_w, headers):
            cx = x + w/2
            ps = txt.split('\n')
            if len(ps)==2:
                c.drawCentredString(cx, y-14, ps[0])
                c.drawCentredString(cx, y-7, ps[1])
            else:
                c.drawCentredString(cx, y-10, txt)
            x += w

        c.setFillColor(colors.black)
        y -= header_h

        item_h = 19
        items = list(invoice.line_items or [])

        for i, item in enumerate(items):
            top = y - i*item_h
            bot = top - item_h

            if i % 2 == 1:
                c.setFillColor(colors.HexColor("#f8f9fa"))
                c.rect(ML, bot, full_w, item_h, fill=1, stroke=0)
                c.setFillColor(colors.black)

            rect(ML, bot, full_w, item_h, fill=0)

            vals = [
                str(getattr(item,'sr_no',i+1)),
                getattr(item,'hsn_code','') or '',
                item.description or "",
                f"{item.quantity:g}",
                getattr(item,'unit','Nos'),
                f"{item.unit_price:,.2f}",
                f"{getattr(item,'tax_percentage',0):g}",
                f"{item.total_amount:,.2f}",
            ]

            c.setFont("Helvetica", 8)
            x = ML
            for j, (w, v) in enumerate(zip(col_w, vals)):
                if j < len(col_w)-1:
                    vline(x+w, bot, top, 0.4)
                if j == 2:
                    maxc = int(w / 4.0)
                    txt = v[:maxc-1]+"…" if len(v)>maxc else v
                    c.drawString(x+4, bot+6, txt)
                elif j in (5,7):
                    c.drawRightString(x+w-4, bot+6, v)
                else:
                    c.drawCentredString(x + w/2, bot+6, v)
                x += w

        items_bottom = y - len(items) * item_h if items else y - item_h

        # ── Bottom fixed block ─────────────────────────────────────────────────
        y_bottom = MT

        # Footer
        footer_h = 22
        rect(ML, y_bottom, full_w, footer_h)
        c.setFont("Helvetica", 8)
        foot = f"Ph. {company.phone or '—'} | Email: {company.email or '—'}"
        c.drawCentredString(ML + full_w/2, y_bottom + 8, foot)
        y_bottom += footer_h + 12

        # Bank + Signature (no box around signature)
        bank_h = 100
        rect(ML, y_bottom, full_w, bank_h)
        vline(col_split, y_bottom, y_bottom + bank_h)

        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(ML+6, y_bottom + bank_h - 18, "OUR BANK DETAILS")
        hline(y_bottom + bank_h - 20, ML+6, ML+160, 0.8)

        bdata = [
            ("Bank Name", bank.bank_name if bank else ""),
            ("A/C No", bank.account_number if bank else ""),
            ("A/C Name", bank.account_name if bank else ""),
            ("IFSC Code", bank.ifsc_code if bank else ""),
            ("Branch", bank.branch if bank else ""),
        ]

        yy = y_bottom + bank_h - 34
        for lbl, val in bdata:
            c.setFont("Helvetica-Bold", 8.5); c.drawString(ML+6, yy, lbl)
            c.setFont("Helvetica", 8.5); c.drawString(ML+64, yy, f" : {val}")
            yy -= 14

        c.setFont("Helvetica-Bold", 9.5)
        c.drawCentredString(col_split + right_w/2, y_bottom + bank_h - 18, f"For {company.name}")

        # Signature – centered & scaled, no border
        sx = col_split + 20
        sy = y_bottom + 20
        sw = right_w - 40
        sh = bank_h - 50

        if signature_bytes:
            try:
                sig = ImageReader(io.BytesIO(signature_bytes))
                orig_w, orig_h = sig.getSize()
                scale = min(sw / orig_w, sh / orig_h, 1.0)
                draw_w = orig_w * scale
                draw_h = orig_h * scale
                ix = sx + (sw - draw_w) / 2
                iy = sy + (sh - draw_h) / 2
                c.drawImage(sig, ix, iy, width=draw_w, height=draw_h,
                            preserveAspectRatio=True, mask='auto')
            except Exception as e:
                print("Signature rendering failed:", e)

        y_bottom += bank_h + 18

        # References + Totals (clean labels without %)
        ref_fields = [
            ("Party GST NO", getattr(invoice, 'party_gst_no', '') or getattr(invoice, 'parts_gst_no', '') or "—"),
            ("Ref Dc", getattr(invoice, 'ref_dc', '') or "—"),
            ("Ref Dc Date", getattr(invoice, 'ref_dc_date', '') or "—"),
            ("PO No", getattr(invoice, 'po_number', '') or "—"),
            ("PO Date", getattr(invoice, 'po_date', '') or "—"),
            ("Vehicle No.", getattr(invoice, 'vehicle_no', '') or "—"),
        ]

        totals = [
            ("Sub Total",     f"{invoice.subtotal:,.2f}"),
            ("SGST",          f"{getattr(invoice, 'sgst', 0):,.2f}"),
            ("CGST",          f"{getattr(invoice, 'cgst', 0):,.2f}"),
            ("IGST",          f"{getattr(invoice, 'igst', 0):,.2f}"),
            ("Grand Total",   f"{invoice.total_amount:,.2f}"),
        ]

        row_h = 15
        nrows = max(len(ref_fields), len(totals))
        refs_h = nrows * row_h + 10

        rect(ML, y_bottom, full_w, refs_h)
        vline(col_split, y_bottom, y_bottom + refs_h)

        for i, (lbl, val) in enumerate(ref_fields):
            yy = y_bottom + refs_h - (i+1)*row_h - 3
            c.setFont("Helvetica-Bold", 8.5); c.drawString(ML+6, yy, f"{lbl}:")
            c.setFont("Helvetica", 8.5); c.drawString(ML+78, yy, str(val))

        for i, (lbl, val) in enumerate(totals):
            yy = y_bottom + refs_h - (i+1)*row_h - 3
            bold = "Grand" in lbl
            c.setFont("Helvetica-Bold" if bold else "Helvetica", 10 if bold else 9)
            c.drawString(col_split+8, yy, f"{lbl}:")
            c.drawRightString(page_w-MR-6, yy, val)

        y_bottom += refs_h

        # ── Outer page border ──────────────────────────────────────────────────
        c.setStrokeColor(colors.black)
        c.setLineWidth(1.0)
        c.rect(ML, MT, full_w, page_h - MT - MT, fill=0)

        c.save()
        buffer.seek(0)
        return buffer

    except Exception as e:
        logging.error(f"PDF generation failed: {e}", exc_info=True)
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

    # Clone metadata from source so title is preserved after merge
    if src_reader.metadata:
        writer.add_metadata(dict(src_reader.metadata))

    for page in src_reader.pages:
        page.merge_page(wm_page)   # merge watermark on top of content
        writer.add_page(page)

    out_buffer = io.BytesIO()
    writer.write(out_buffer)
    out_buffer.seek(0)
    return out_buffer


def generate_triple_invoice_pdf(invoice, company=None, bank=None, logo_bytes=None, signature_bytes=None):
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
    base_buffer = generate_invoice_pdf(
        invoice,
        company=company,
        bank=bank,
        logo_bytes=logo_bytes,
        signature_bytes=signature_bytes
    )
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

    # Re-add metadata after merge (pypdf strips canvas metadata during merge)
    inv_number = getattr(invoice, 'invoice_number', '')
    writer.add_metadata({
        '/Title': f'Invoice {inv_number}',
        '/Author': 'Invoice Pro',
        '/Subject': 'Invoice'
    })

    merged = io.BytesIO()
    writer.write(merged)
    merged.seek(0)
    return merged

def generate_challan_pdf(challan, company=None):

    buffer = io.BytesIO()

    page_w, page_h = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    ML = MR = MT = 36
    full_w = page_w - ML - MR
    col_split = ML + full_w * 0.58
    BOTTOM_MARGIN = MT
    y = page_h - MT

    # ================= HEADER =================
    row1_h = 48
    c.rect(ML, y-row1_h, full_w, row1_h)

    c.setFont("Helvetica-Bold", 24)
    c.drawString(ML + 8, y - 30, "DELIVERY CHALLAN")

    y -= row1_h + 6


    # ================= CHALLAN INFO =================
    row2_h = 64
    c.rect(ML, y-row2_h, full_w, row2_h)

    c.setFont("Helvetica-Bold", 9)

    c.drawString(ML+6, y-16, "Challan No :")
    c.setFont("Helvetica",9)
    c.drawString(ML+90, y-16, str(challan.challan_number))

    c.setFont("Helvetica-Bold",9)
    c.drawString(ML+6, y-32, "Challan Date :")
    c.setFont("Helvetica",9)
    c.drawString(ML+90, y-32, challan.challan_date.strftime('%d-%m-%Y'))

    c.setFont("Helvetica-Bold",9)
    c.drawString(ML+6, y-48, "Delivery Date :")
    c.setFont("Helvetica",9)
    c.drawString(
        ML+90,
        y-48,
        challan.delivery_date.strftime('%d-%m-%Y') if challan.delivery_date else "N/A"
    )

    y -= row2_h + 10


    # ================= CLIENT / TRANSPORT =================
    row3_h = 100
    c.rect(ML, y-row3_h, full_w, row3_h)
    c.line(col_split, y-row3_h, col_split, y)

    client = getattr(challan, 'preview_client', None) or challan.client

    c.setFont("Helvetica-Bold", 10)
    c.drawString(ML+6, y-16, "Ship To")

    c.setFont("Helvetica", 9)

    style = ParagraphStyle(
        "client",
        fontName="Helvetica",
        fontSize=9,
        leading=12
    )

    client_text = f"""
    <b>{client.name}</b><br/>
    {getattr(client,'address','')}<br/>
    {getattr(client,'city','')}, {getattr(client,'state','')} - {getattr(client,'pincode','')}
    """

    para = Paragraph(client_text, style)

    pw, ph = para.wrap(col_split - ML - 12, row3_h)

    para.drawOn(c, ML + 6, y - 28 - ph)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(col_split+6, y-16, "Vehicle / Transport")

    c.setFont("Helvetica", 9)
    vehicle_para = Paragraph(
    challan.notes or "No instructions",
    style
    )

    pw, ph = vehicle_para.wrap(page_w - MR - col_split - 12, row3_h)

    vehicle_para.drawOn(c, col_split + 6, y - 30 - ph)

    y -= row3_h + 10


    # ================= ITEMS TABLE =================

    header_h = 22
    c.rect(ML, y-header_h, full_w, header_h)

    c.setFillColor(colors.black)
    c.rect(ML, y-header_h, full_w, header_h, fill=1)
    c.setFillColor(colors.white)

    headers = ["S.No", "HSN", "Description", "Qty", "Unit"]

    col_w = [
    40,   # S.No
    80,   # HSN
    full_w - 260,  # Description
    70,   # Qty
    70    # Unit
    ]

    c.setFont("Helvetica-Bold", 9)

    x = ML
    for w, h in zip(col_w, headers):
        c.drawCentredString(x + w/2, y-14, h)
        x += w

    c.setFillColor(colors.black)

    y -= header_h

    row_h = 20

    for i, item in enumerate(challan.line_items):

        top = y - i*row_h
        bottom = top - row_h

        c.rect(ML, bottom, full_w, row_h)

        values = [
            str(item.sr_no),
            item.hsn_code or "",
            item.description,
            f"{item.quantity:g}",
            item.unit
        ]

        x = ML

        for j,(w,val) in enumerate(zip(col_w, values)):

            if j < len(col_w)-1:
                c.line(x+w, bottom, x+w, top)

            if j == 2:
                c.drawString(x+4, bottom+6, val[:40])
            else:
                c.drawCentredString(x+w/2, bottom+6, val)

            x += w

    


    # ================= SIGNATURE =================

    sig_h = 80

    # place signature block at bottom
    sig_y = BOTTOM_MARGIN + sig_h

    c.rect(ML, sig_y - sig_h, full_w, sig_h)
    c.line(col_split, sig_y - sig_h, col_split, sig_y)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(col_split+10, sig_y - 20, f"For {company.name if company else ''}")

    c.setFont("Helvetica", 9)
    c.drawString(ML+10, sig_y - 60, "Receiver's Signature")
    c.drawString(col_split+10, sig_y - 60, "Authorized Signatory")

    y -= sig_h


    # ================= PAGE BORDER =================

    c.setLineWidth(1)
    c.rect(ML, MT, full_w, page_h - MT - MT)

    c.save()
    buffer.seek(0)

    return buffer

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


def generate_quotation_pdf(q, company=None, bank=None, logo_bytes=None, signature_bytes=None):
    """Generate quotation PDF matching the professional invoice layout.
    Same canvas-based drawing style as generate_invoice_pdf."""
    try:
        if not company:
            company = Company.query.first() or type('Company', (), {
                'name': config.COMPANY_NAME, 'address': config.COMPANY_ADDRESS,
                'city': config.COMPANY_CITY, 'state': config.COMPANY_STATE,
                'pincode': config.COMPANY_PINCODE, 'phone': config.COMPANY_PHONE,
                'email': config.COMPANY_EMAIL, 'gstin': config.GSTIN, 'pan': config.PAN,
            })()

        buffer = io.BytesIO()
        page_w, page_h = A4
        c = canvas.Canvas(buffer, pagesize=A4)
        c.setTitle(f"Quotation {q.quotation_number}")
        c.setAuthor(getattr(company, 'name', 'Invoice Pro') if company else 'Invoice Pro')
        c.setSubject("Quotation")

        ML = MR = MT = 36
        full_w = page_w - ML - MR
        col_split = ML + full_w * 0.58

        def hline(y, x0=ML, x1=page_w - MR, lw=0.5):
            c.setLineWidth(lw); c.setStrokeColor(colors.black); c.line(x0, y, x1, y)

        def vline(x, y0, y1, lw=0.5):
            c.setLineWidth(lw); c.setStrokeColor(colors.black); c.line(x, y0, x, y1)

        def rect(x, y, w, h, fill=0):
            c.setLineWidth(0.5); c.setStrokeColor(colors.black); c.rect(x, y, w, h, fill=fill)

        # ── 1. Draw top fixed parts ────────────────────────────────────────────
        y = page_h - MT

        # Row 1: QUOTATION + logo
        row1_h = 48
        rect(ML, y - row1_h, full_w, row1_h)
        c.setFont("Helvetica-Bold", 24)
        c.drawString(ML + 8, y - 30, "QUOTATION")
        vline(col_split, y - row1_h, y)

        if logo_bytes:
            try:
                logo = ImageReader(io.BytesIO(logo_bytes))
                orig_w, orig_h = logo.getSize()
                max_logo_w = (page_w - MR - col_split) - 20
                max_logo_h = row1_h - 12
                scale = min(max_logo_w / orig_w, max_logo_h / orig_h, 1.0)
                draw_w = orig_w * scale
                draw_h = orig_h * scale
                logo_x = col_split + ((page_w - MR - col_split) - draw_w) / 2
                logo_y = (y - row1_h) + (row1_h - draw_h) / 2
                c.drawImage(logo, logo_x, logo_y, width=draw_w, height=draw_h,
                            preserveAspectRatio=True, mask='auto')
            except Exception as e:
                print("Logo rendering failed:", e)

        y -= row1_h + 4

        # Row 2: Quotation info | Company name + address
        row2_h = 64
        rect(ML, y - row2_h, full_w, row2_h)
        vline(col_split, y - row2_h, y)

        c.setFont("Helvetica-Bold", 9)
        c.drawString(ML + 6, y - 16, "Quotation No :")
        c.setFont("Helvetica", 9)
        c.drawString(ML + 90, y - 16, str(q.quotation_number))

        c.setFont("Helvetica-Bold", 9)
        c.drawString(ML + 6, y - 32, "Date          :")
        c.setFont("Helvetica", 9)
        q_date_str = q.quotation_date.strftime('%d-%m-%Y') if q.quotation_date else "—"
        c.drawString(ML + 90, y - 32, q_date_str)

        if getattr(q, 'validity_days', None):
            c.setFont("Helvetica-Bold", 9)
            c.drawString(ML + 6, y - 48, "Valid (Days)  :")
            c.setFont("Helvetica", 9)
            c.drawString(ML + 90, y - 48, str(q.validity_days))

        right_w = page_w - MR - col_split
        rcx = col_split + right_w / 2
        cname = (getattr(company, 'name', '') or "").upper()
        c.setFont("Helvetica-Bold", 12)
        if c.stringWidth(cname, "Helvetica-Bold", 12) <= right_w - 20:
            c.drawCentredString(rcx, y - 18, cname)
            name_h = 18
        else:
            words = cname.split(); l1 = l2 = ""
            for w in words:
                test = (l1 + " " + w).strip()
                if c.stringWidth(test, "Helvetica-Bold", 12) <= right_w - 20:
                    l1 = test
                else:
                    l2 = (l2 + " " + w).strip()
            c.drawCentredString(rcx, y - 14, l1)
            c.drawCentredString(rcx, y - 30, l2.strip())
            name_h = 34

        addr_str = f"{getattr(company, 'address', '') or ''}, {getattr(company, 'city', '') or ''} - {getattr(company, 'pincode', '') or ''}, {getattr(company, 'state', '') or ''}"
        pstyle = ParagraphStyle('addr', fontName='Helvetica', fontSize=8.5, leading=10, alignment=1, spaceAfter=4)
        para = Paragraph(addr_str, pstyle)
        pw, ph = para.wrap(right_w - 16, 9999)
        para.drawOn(c, col_split + 8, y - name_h - 8 - ph)

        y -= row2_h + 6

        # ── Row 3: To (client info) | Our Details ─────────────────────────────
        row3_h = 110
        rect(ML, y - row3_h, full_w, row3_h)
        vline(col_split, y - row3_h, y)

        # Left side – TO block
        c.setFont("Helvetica-Bold", 10)
        c.drawString(ML + 6, y - 16, "To,")

        client = getattr(q, 'client', None)
        if client:
            client_name = getattr(client, 'name', '') or "—"
            client_addr = getattr(client, 'address', '') or ""
            client_city = getattr(client, 'city', '') or ""
            client_state = getattr(client, 'state', '') or ""
            client_pincode = getattr(client, 'pincode', '') or ""
            client_gstin = getattr(client, 'gstin', '') or "—"
        else:
            client_name = getattr(q, 'client_name', '') or "—"
            client_addr = getattr(q, 'client_address', '') or ""
            client_city = getattr(q, 'client_city', '') or ""
            client_state = getattr(q, 'client_state', '') or ""
            client_pincode = getattr(q, 'client_pincode', '') or ""
            client_gstin = getattr(q, 'client_gstin', '') or "—"

        client_address_html = f"""
        <b>{client_name}</b><br/>
        {client_addr}<br/>
        {client_city}, {client_state} - {client_pincode}<br/>
        GSTIN: {client_gstin}
        """

        client_style = ParagraphStyle(
            'client_addr',
            fontName='Helvetica',
            fontSize=9,
            leading=12,
        )
        client_para = Paragraph(client_address_html, client_style)
        available_width = col_split - ML - 14
        pw, ph = client_para.wrap(available_width, row3_h - 20)
        client_para.drawOn(c, ML + 6, y - 34 - ph)

        # Right side – Our Details
        c.setFillColor(colors.black)
        c.rect(col_split, y - 18, right_w, 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(rcx, y - 13, "Our Details")
        c.setFillColor(colors.black)

        c.setFont("Helvetica-Bold", 9)
        c.drawString(col_split + 8, y - 36, "GSTIN :")
        c.setFont("Helvetica", 9)
        c.drawString(col_split + 58, y - 36, getattr(company, 'gstin', '') or "")

        c.setFont("Helvetica-Bold", 9)
        c.drawString(col_split + 8, y - 52, "PAN   :")
        c.setFont("Helvetica", 9)
        c.drawString(col_split + 58, y - 52, getattr(company, 'pan', '') or "")

        y -= row3_h + 8

        # ── Items table ────────────────────────────────────────────────────────
        header_h = 22
        rect(ML, y - header_h, full_w, header_h)
        c.setFillColor(colors.black)
        c.rect(ML, y - header_h, full_w, header_h, fill=1, stroke=0)
        c.setFillColor(colors.white)

        col_w = [full_w * 0.05, full_w * 0.09, full_w * 0.30, full_w * 0.07, full_w * 0.07, full_w * 0.115, full_w * 0.07, full_w * 0.185]
        headers = ["Sl.\nNo", "HSN\nCode", "Product Name / Description", "Qty.", "Unit", "Rate", "Tax", "Amount"]

        c.setFont("Helvetica-Bold", 8)
        x = ML
        for w, txt in zip(col_w, headers):
            cx = x + w / 2
            ps = txt.split('\n')
            if len(ps) == 2:
                c.drawCentredString(cx, y - 14, ps[0])
                c.drawCentredString(cx, y - 7, ps[1])
            else:
                c.drawCentredString(cx, y - 10, txt)
            x += w

        c.setFillColor(colors.black)
        y -= header_h
        print("DEBUG quotation items:", q.line_items)
        item_h = 19
        items = list(getattr(q, 'line_items', []) or [])

        for i, item in enumerate(items):
            top = y - i * item_h
            bot = top - item_h

            if i % 2 == 1:
                c.setFillColor(colors.HexColor("#f8f9fa"))
                c.rect(ML, bot, full_w, item_h, fill=1, stroke=0)
                c.setFillColor(colors.black)

            rect(ML, bot, full_w, item_h, fill=0)

            vals = [
                str(getattr(item, 'sr_no', i + 1)),
                getattr(item, 'hsn_code', '') or '',
                item.description or "",
                f"{item.quantity:g}",
                getattr(item, 'unit', 'Nos'),
                f"{item.unit_price:,.2f}",
                f"{getattr(item, 'tax_percentage', 0):g}",
                f"{item.total_amount:,.2f}",
            ]

            c.setFont("Helvetica", 8)
            x = ML
            for j, (w, v) in enumerate(zip(col_w, vals)):
                if j < len(col_w) - 1:
                    vline(x + w, bot, top, 0.4)
                if j == 2:
                    maxc = int(w / 4.0)
                    txt = v[:maxc - 1] + "…" if len(v) > maxc else v
                    c.drawString(x + 4, bot + 6, txt)
                elif j in (5, 7):
                    c.drawRightString(x + w - 4, bot + 6, v)
                else:
                    c.drawCentredString(x + w / 2, bot + 6, v)
                x += w

        items_bottom = y - len(items) * item_h if items else y - item_h

        # ── Bottom fixed block ─────────────────────────────────────────────────
        y_bottom = MT

        # Footer
        footer_h = 22
        rect(ML, y_bottom, full_w, footer_h)
        c.setFont("Helvetica", 8)
        foot = f"Ph. {getattr(company, 'phone', '') or '—'} | Email: {getattr(company, 'email', '') or '—'}"
        c.drawCentredString(ML + full_w / 2, y_bottom + 8, foot)
        y_bottom += footer_h + 12

        # Bank + Signature
        bank_h = 100
        rect(ML, y_bottom, full_w, bank_h)
        vline(col_split, y_bottom, y_bottom + bank_h)

        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(ML + 6, y_bottom + bank_h - 18, "OUR BANK DETAILS")
        hline(y_bottom + bank_h - 20, ML + 6, ML + 160, 0.8)

        bdata = [
            ("Bank Name", bank.bank_name if bank else ""),
            ("A/C No", bank.account_number if bank else ""),
            ("A/C Name", bank.account_name if bank else ""),
            ("IFSC Code", bank.ifsc_code if bank else ""),
            ("Branch", bank.branch if bank else ""),
        ]

        yy = y_bottom + bank_h - 34
        for lbl, val in bdata:
            c.setFont("Helvetica-Bold", 8.5); c.drawString(ML + 6, yy, lbl)
            c.setFont("Helvetica", 8.5); c.drawString(ML + 64, yy, f" : {val}")
            yy -= 14

        c.setFont("Helvetica-Bold", 9.5)
        c.drawCentredString(col_split + right_w / 2, y_bottom + bank_h - 18, f"For {getattr(company, 'name', '')}")

        # Signature
        sx = col_split + 20
        sy = y_bottom + 20
        sw = right_w - 40
        sh = bank_h - 50

        if signature_bytes:
            try:
                sig = ImageReader(io.BytesIO(signature_bytes))
                orig_w, orig_h = sig.getSize()
                scale = min(sw / orig_w, sh / orig_h, 1.0)
                draw_w = orig_w * scale
                draw_h = orig_h * scale
                ix = sx + (sw - draw_w) / 2
                iy = sy + (sh - draw_h) / 2
                c.drawImage(sig, ix, iy, width=draw_w, height=draw_h,
                            preserveAspectRatio=True, mask='auto')
            except Exception as e:
                print("Signature rendering failed:", e)

        y_bottom += bank_h + 18

        # References + Totals
        ref_fields = [
            ("Sales Person", getattr(q, 'sales_person', '') or "—"),
            ("Reference ID", getattr(q, 'reference_id', '') or "—"),
            ("Validity (Days)", str(getattr(q, 'validity_days', '') or "—")),
            ("Expiry Date", q.expiry_date.strftime('%d-%m-%Y') if getattr(q, 'expiry_date', None) else "—"),
            ("Status", getattr(q, 'status', '') or "—"),
        ]

        totals = [
            ("Sub Total",   f"{getattr(q, 'subtotal', 0):,.2f}"),
            ("SGST",        f"{getattr(q, 'sgst', 0):,.2f}"),
            ("CGST",        f"{getattr(q, 'cgst', 0):,.2f}"),
            ("IGST",        f"{getattr(q, 'igst', 0):,.2f}"),
            ("Grand Total", f"{getattr(q, 'grand_total', 0):,.2f}"),
        ]

        row_h = 15
        nrows = max(len(ref_fields), len(totals))
        refs_h = nrows * row_h + 10

        rect(ML, y_bottom, full_w, refs_h)
        vline(col_split, y_bottom, y_bottom + refs_h)

        for i, (lbl, val) in enumerate(ref_fields):
            yy = y_bottom + refs_h - (i + 1) * row_h - 3
            c.setFont("Helvetica-Bold", 8.5); c.drawString(ML + 6, yy, f"{lbl}:")
            c.setFont("Helvetica", 8.5); c.drawString(ML + 90, yy, str(val))

        for i, (lbl, val) in enumerate(totals):
            yy = y_bottom + refs_h - (i + 1) * row_h - 3
            bold = "Grand" in lbl
            c.setFont("Helvetica-Bold" if bold else "Helvetica", 10 if bold else 9)
            c.drawString(col_split + 8, yy, f"{lbl}:")
            c.drawRightString(page_w - MR - 6, yy, val)

        y_bottom += refs_h

        # ── Outer page border ──────────────────────────────────────────────────
        c.setStrokeColor(colors.black)
        c.setLineWidth(1.0)
        c.rect(ML, MT, full_w, page_h - MT - MT, fill=0)

        c.save()
        buffer.seek(0)
        return buffer

    except Exception as e:
        logging.error(f"Quotation PDF generation failed: {e}", exc_info=True)
        raise
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
        pdf = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            title='Analytics Report',
            author='Invoice Pro',
            subject='Business Analytics Report'
        )
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