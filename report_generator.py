import io
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
from datetime import datetime


def safe_dict(value):
    return value if isinstance(value, dict) else {}


class AnalyticsReportGenerator:
    def __init__(self):
        pass
        
    def generate_excel_report(self, analytics_data):
        """Generate Excel report from analytics data dictionary"""
        output = io.BytesIO()
        
        # safely extract data with defaults
        revenue = safe_dict(analytics_data.get("revenue_trends", {}))
        profit = safe_dict(analytics_data.get("profitability_analysis", {}))
        payments = safe_dict(analytics_data.get("payment_analytics", {}))
        clients = safe_dict(analytics_data.get("client_performance", {}))

        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            
            # Revenue Sheet
            revenue_data = revenue.get("monthly_data", [])
            if revenue_data:
                pd.DataFrame(revenue_data).to_excel(writer, sheet_name="Revenue Trends", index=False)
            else:
                pd.DataFrame({"Message": ["No revenue data available"]}).to_excel(writer, sheet_name="Revenue Trends", index=False)

            # Profit Sheet
            profit_data = profit.get("monthly_trends", [])
            if profit_data:
                pd.DataFrame(profit_data).to_excel(writer, sheet_name="Profitability", index=False)
            else:
                 pd.DataFrame({"Message": ["No profitability data available"]}).to_excel(writer, sheet_name="Profitability", index=False)

            # Payments Sheet
            payment_data = payments.get("payment_status_distribution", [])
            if payment_data:
                pd.DataFrame(payment_data).to_excel(writer, sheet_name="Payments", index=False)
            else:
                pd.DataFrame({"Message": ["No payment data available"]}).to_excel(writer, sheet_name="Payments", index=False)

            # Client Performance Sheet
            client_data = clients.get("top_clients", [])
            if client_data:
                pd.DataFrame(client_data).to_excel(writer, sheet_name="Client Performance", index=False)
            else:
                pd.DataFrame({"Message": ["No client data available"]}).to_excel(writer, sheet_name="Client Performance", index=False)
                
        output.seek(0)
        return output

    def generate_pdf_report(self, analytics_data):
        """Generate PDF report from analytics data dictionary"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
        
        # Register Arial font for Rupee symbol support
        try:
            arial_path = "C:\\Windows\\Fonts\\arial.ttf"
            arial_bold_path = "C:\\Windows\\Fonts\\arialbd.ttf"
            if os.path.exists(arial_path) and os.path.exists(arial_bold_path):
                pdfmetrics.registerFont(TTFont('Arial', arial_path))
                pdfmetrics.registerFont(TTFont('Arial-Bold', arial_bold_path))
                pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold', italic='Arial', boldItalic='Arial-Bold')
                font_normal = 'Arial'
                font_bold = 'Arial-Bold'
            else:
                font_normal = 'Helvetica'
                font_bold = 'Helvetica-Bold'
        except Exception as e:
            print(f"Font registration failed: {e}")
            font_normal = 'Helvetica'
            font_bold = 'Helvetica-Bold'

        styles = getSampleStyleSheet()
        elements = []
        
        # Calculate available width (A4 width = 595.27 points)
        available_width = A4[0] - 80  # 40 margin on each side
        
        # --- Header Section ---
        
        # Title (Center) - MOVED TO TOP
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Title'],
            fontSize=24,
            spaceAfter=20,
            alignment=1, # Center
            textColor=colors.black,
            fontName=font_bold
        )
        elements.append(Paragraph("Analytics Report", title_style))
        elements.append(Spacer(1, 10))

        # Organization Name (Top Left)
        org_style = ParagraphStyle(
            'OrgHeader',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.dimgrey,
            alignment=0,  # Left
            fontName=font_normal
        )
        # Try to get organization name from config if possible, else "Xenforte"
        try:
            import config
            org_name = getattr(config, 'COMPANY_NAME', 'Xenforte')
        except:
            org_name = 'Xenforte'
            
        elements.append(Paragraph(f"Organization: {org_name}", org_style))
        elements.append(Paragraph(f"Generated On: {datetime.now().strftime('%d-%m-%Y %H:%M')}", org_style))
        time_range = "Last 12 Months" # Placeholder or passed arg? inferred for now
        elements.append(Paragraph(f"Reporting Period: {time_range}", org_style))
        elements.append(Spacer(1, 20))
        
        # Define Table Style
        # Header: Grey background, Bold text
        # Body: Grid lines, aligned numbers
        common_table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)), # Light grey header
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'), # Default left alignment
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'), # Numbers usually right aligned (adjust per table)
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'), # Numbers usually right aligned (adjust per table)
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTNAME', (0, 1), (-1, -1), font_normal),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ])

        # --- Section 1: Revenue Trends ---
        elements.append(Paragraph("1. Revenue Trends", styles["Heading2"]))
        revenue = safe_dict(analytics_data.get("revenue_trends", {}))
        revenue_data = revenue.get("monthly_data", [])
        
        # Columns: Month, Revenue, No. of Invoices
        # Widths: 40%, 40%, 20%
        col_widths = [available_width * 0.4, available_width * 0.4, available_width * 0.2]
        
        table_data = [["Month", "Revenue (₹)", "Number of Invoices"]]
        if revenue_data:
            for r in revenue_data:
                table_data.append([
                    str(r.get("month", "")), 
                    f"₹{r.get('revenue', 0):,.2f}", 
                    str(r.get("invoice_count", 0))
                ])
        else:
            # Empty row to maintain structure if needed, or just headers
            # User asked for "empty table with structures", so headers are sufficient, 
            # but let's add one empty row for better visual if chart is empty
            table_data.append(["-", "-", "-"])

        t = Table(table_data, colWidths=col_widths)
        t.setStyle(common_table_style)
        elements.append(t)
        elements.append(Spacer(1, 20))

        # --- Section 2: Profitability Analysis ---
        elements.append(Paragraph("2. Profitability Analysis", styles["Heading2"]))
        profit = safe_dict(analytics_data.get("profitability_analysis", {}))
        profit_data = profit.get("monthly_trends", [])
        
        # Columns: Month, Revenue, Cost, Profit, Margin %
        # Widths: 20% each
        col_w = available_width / 5
        col_widths = [col_w] * 5
        
        table_data = [["Month", "Revenue (₹)", "Cost (₹)", "Profit (₹)", "Margin (%)"]]
        if profit_data:
            for p in profit_data:
                table_data.append([
                    str(p.get("month", "")),
                    f"₹{p.get('revenue', 0):,.2f}",
                    f"₹{p.get('cost', 0):,.2f}",
                    f"₹{p.get('profit', 0):,.2f}",
                    f"{p.get('margin_percentage', 0)}%"
                ])
        else:
             table_data.append(["-", "-", "-", "-", "-"])
                
        t = Table(table_data, colWidths=col_widths)
        t.setStyle(common_table_style)
        elements.append(t)
        elements.append(Spacer(1, 20))

        # --- Section 3: Payment Status Distribution ---
        elements.append(Paragraph("3. Payment Status Distribution", styles["Heading2"]))
        payments = safe_dict(analytics_data.get("payment_analytics", {}))
        payment_data = payments.get("payment_status_distribution", [])
        
        # Columns: Payment Status, Invoice Count, Amount
        # Widths: 40%, 30%, 30%
        col_widths = [available_width * 0.4, available_width * 0.3, available_width * 0.3]
        
        table_data = [["Payment Status", "Invoice Count", "Amount (₹)"]]
        if payment_data:
            for pay in payment_data:
                table_data.append([
                    str(pay.get("status", "")),
                    str(pay.get("count", 0)),
                    f"₹{pay.get('amount', 0):,.2f}"
                ])
        else:
             table_data.append(["-", "-", "-"])
                
        t = Table(table_data, colWidths=col_widths)
        t.setStyle(common_table_style)
        elements.append(t)
        elements.append(Spacer(1, 30))

        # --- Summary Section ---
        elements.append(Paragraph("Summary", styles["Heading2"]))
        
        # Calculate totals
        overall_profit = profit.get("overall", {})
        total_revenue = overall_profit.get("total_revenue", 0)
        total_profit = overall_profit.get("total_profit", 0)
        total_cost = overall_profit.get("total_cost", 0)
        
        # Calculate outstanding from payment data
        outstanding_amount = sum(
            p.get('amount', 0) for p in payment_data 
            if p.get('status') in ['Unpaid', 'Partially Paid']
        )

        summary_style = ParagraphStyle(
            'SummaryText',
            parent=styles['Normal'],
            fontSize=11,
            leading=14,
            fontName=font_normal
        )
        
        elements.append(Paragraph(f"<b>Total Revenue:</b> ₹{total_revenue:,.2f}", summary_style))
        elements.append(Paragraph(f"<b>Total Profit:</b> ₹{total_profit:,.2f}", summary_style))
        elements.append(Paragraph(f"<b>Total Cost:</b> ₹{total_cost:,.2f}", summary_style))
        elements.append(Paragraph(f"<b>Outstanding Amount:</b> ₹{outstanding_amount:,.2f}", summary_style))
        
        # --- Footer ---
        # (Auto-handled by SimpleDocTemplate roughly, but we can add an end line)
        elements.append(Spacer(1, 20))

        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        return buffer
