import re

with open(r'd:\Phone\download\ML\IP\pdf_generator.py', 'r', encoding='utf-8') as f:
    data = f.read()

code_to_insert = '''def generate_quotation_pdf(invoice, company=None, bank=None, logo_bytes=None, signature_bytes=None):
    \"\"\"Generate quotation PDF matching the generated invoice format.\"\"\"
    try:
        if not company:
            company = Company.query.first() or type('Company', (), {
                'name': config.COMPANY_NAME, 'address': config.COMPANY_ADDRESS,
                'city': config.COMPANY_CITY, 'state': config.COMPANY_STATE,
                'pincode': config.COMPANY_PINCODE, 'phone': config.COMPANY_PHONE,
                'email': config.COMPANY_EMAIL, 'gstin': config.GSTIN, 'pan': config.PAN,
            })()

        client = getattr(invoice, 'client', None)

        buffer = io.BytesIO()
        page_w, page_h = A4
        c = canvas.Canvas(buffer, pagesize=A4)
        c.setTitle(f"Quotation {invoice.quotation_number}")
        c.setAuthor(getattr(company, 'name', 'Invoice Pro') if company else 'Invoice Pro')
        c.setSubject("Quotation")

        ML = MR = MT = 36
        full_w = page_w - ML - MR
        col_split = ML + full_w * 0.58

        def hline(y, x0=ML, x1=page_w-MR, lw=0.5):
            c.setLineWidth(lw); c.setStrokeColor(colors.black); c.line(x0,y,x1,y)

        def vline(x, y0, y1, lw=0.5):
            c.setLineWidth(lw); c.setStrokeColor(colors.black); c.line(x,y0,x,y1)

        def rect(x, y, w, h, fill=0):
            c.setLineWidth(0.5); c.setStrokeColor(colors.black); c.rect(x,y,w,h,fill=fill)

        y = page_h - MT

        row1_h = 48
        rect(ML, y-row1_h, full_w, row1_h)
        c.setFont("Helvetica-Bold", 24)
        c.drawString(ML + 8, y - 30, "QUOTATION")
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
                c.drawImage(logo, logo_x, logo_y, width=draw_w, height=draw_h, preserveAspectRatio=True, mask='auto')
            except Exception as e:
                print("Logo rendering failed:", e)

        y -= row1_h + 4

        row2_h = 64
        rect(ML, y-row2_h, full_w, row2_h)
        vline(col_split, y-row2_h, y)

        c.setFont("Helvetica-Bold", 9)
        c.drawString(ML+6, y-16, "Quotation No :"); c.setFont("Helvetica",9); c.drawString(ML+78, y-16, str(invoice.quotation_number))
        
        q_date_str = invoice.quotation_date.strftime('%d-%m-%Y') if hasattr(invoice.quotation_date, 'strftime') else ""
        c.setFont("Helvetica-Bold",9); c.drawString(ML+6, y-32, "Date       :"); c.setFont("Helvetica",9); c.drawString(ML+78, y-32, q_date_str)
        
        if invoice.expiry_date:
            e_date_str = invoice.expiry_date.strftime('%d-%m-%Y') if hasattr(invoice.expiry_date, 'strftime') else ""
            c.setFont("Helvetica-Bold",9); c.drawString(ML+6, y-48, "Expiry Date:"); c.setFont("Helvetica",9); c.drawString(ML+78, y-48, e_date_str)

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

        row3_h = 110
        rect(ML, y - row3_h, full_w, row3_h)
        vline(col_split, y - row3_h, y)

        c.setFont("Helvetica-Bold", 10)
        c.drawString(ML + 6, y - 16, "To,")

        client_name = client.name if client else "—"

        client_address = f"""
        <b>{client_name}</b><br/>
        {client.address if client else ""}<br/>
        {client.city if client else ""}, {client.state if client else ""} - {client.pincode if client else ""}<br/>
        GSTIN: {getattr(client, 'gstin', '') if client else "—"}
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
        client_para.drawOn(c, ML + 6, y - 34 - ph)

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

        header_h = 22
        rect(ML, y-header_h, full_w, header_h)
        c.setFillColor(colors.black)
        c.rect(ML, y-header_h, full_w, header_h, fill=1, stroke=0)
        c.setFillColor(colors.white)

        col_w = [full_w*0.05, full_w*0.09, full_w*0.30, full_w*0.07, full_w*0.07, full_w*0.115, full_w*0.07, full_w*0.185]
        headers = ["Sl.\\nNo", "HSN\\nCode", "Product Name / Description", "Qty.", "Unit", "Rate", "Tax", "Amount"]

        c.setFont("Helvetica-Bold", 8)
        x = ML
        for w, txt in zip(col_w, headers):
            cx = x + w/2
            ps = txt.split('\\n')
            if len(ps)==2:
                c.drawCentredString(cx, y-14, ps[0])
                c.drawCentredString(cx, y-7, ps[1])
            else:
                c.drawCentredString(cx, y-10, txt)
            x += w

        c.setFillColor(colors.black)
        y -= header_h

        item_h = 19
        items = list(getattr(invoice, 'line_items', []))

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
                getattr(item, 'description', '') or "",
                f"{getattr(item, 'quantity', 0):g}",
                getattr(item,'unit','Nos'),
                f"{getattr(item, 'unit_price', 0):,.2f}",
                f"{getattr(item,'tax_percentage',0):g}",
                f"{getattr(item, 'total_amount', 0):,.2f}",
            ]

            c.setFont("Helvetica", 8)
            x = ML
            for j, (w, v) in enumerate(zip(col_w, vals)):
                if j < len(col_w)-1:
                    vline(x+w, bot, top, 0.4)
                if j == 2:
                    maxc = int(w / 4.0)
                    txt = v[:maxc-1]+"" if len(v)>maxc else v
                    c.drawString(x+4, bot+6, txt)
                elif j in (5,7):
                    c.drawRightString(x+w-4, bot+6, v)
                else:
                    c.drawCentredString(x + w/2, bot+6, v)
                x += w

        items_bottom = y - len(items) * item_h if items else y - item_h

        y_bottom = MT

        footer_h = 22
        rect(ML, y_bottom, full_w, footer_h)
        c.setFont("Helvetica", 8)
        foot = f"Ph. {company.phone or '—'} | Email: {company.email or '—'}"
        c.drawCentredString(ML + full_w/2, y_bottom + 8, foot)
        y_bottom += footer_h + 12

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
                c.drawImage(sig, ix, iy, width=draw_w, height=draw_h, preserveAspectRatio=True, mask='auto')
            except Exception as e:
                print("Signature rendering failed:", e)

        y_bottom += bank_h + 18

        ref_fields = [
            ("Ref ID", getattr(invoice, 'reference_id', '') or "—"),
            ("Valid Days", getattr(invoice, 'validity_days', '') or "—"),
            ("Status", getattr(invoice, 'status', '') or "—"),
            ("Sales Person", getattr(invoice, 'sales_person', '') or "—"),
        ]

        totals = [
            ("Sub Total",     f"{getattr(invoice, 'subtotal', 0):,.2f}"),
            ("SGST",          f"{getattr(invoice, 'sgst', 0):,.2f}"),
            ("CGST",          f"{getattr(invoice, 'cgst', 0):,.2f}"),
            ("IGST",          f"{getattr(invoice, 'igst', 0):,.2f}"),
            ("Grand Total",   f"{getattr(invoice, 'grand_total', 0):,.2f}"),
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

        c.setStrokeColor(colors.black)
        c.setLineWidth(1.0)
        c.rect(ML, MT, full_w, page_h - MT - MT, fill=0)

        c.save()
        buffer.seek(0)
        return buffer

    except Exception as e:
        logging.error(f"PDF generation failed: {e}", exc_info=True)
        raise
'''

out_data = re.sub(r'def generate_quotation_pdf\(q\):.*?return buffer', code_to_insert, data, flags=re.DOTALL)

with open(r'd:\Phone\download\ML\IP\pdf_generator.py', 'w', encoding='utf-8') as f:
    f.write(out_data)

print("PDF generator patched successfully.")

