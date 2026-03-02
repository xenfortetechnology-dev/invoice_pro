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
        
    def generate_excel_report(self, analytics_data, report_type='all'):
        """
        Generate Excel report from analytics data dictionary based on report_type.
        Matches PDF structure: Header -> Revenue -> Profit -> Payments -> Summary
        """
        output = io.BytesIO()
        
        # safely extract data with defaults
        revenue = safe_dict(analytics_data.get("revenue_trends", {}))
        profit = safe_dict(analytics_data.get("profitability_analysis", {}))
        payments = safe_dict(analytics_data.get("payment_analytics", {}))
        # Client performance removed to match PDF

        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            workbook = writer.book
            
            # --- Formats ---
            header_format = workbook.add_format({'bold': True, 'align': 'center', 'font_size': 14})
            sub_header_format = workbook.add_format({'bold': True, 'font_size': 12, 'underline': True})
            table_header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
            currency_format = workbook.add_format({'num_format': '₹#,##0.00'})
            bold_format = workbook.add_format({'bold': True})
            
            # --- Main Sheet: Analytics Report ---
            worksheet = workbook.add_worksheet("Analytics Report")
            writer.sheets["Analytics Report"] = worksheet
            
            row = 0
            
            # 1. Report Header
            # Check config or default
            try:
                import config
                org_name = getattr(config, 'COMPANY_NAME', 'Xenforte')
            except:
                org_name = 'Xenforte'

            worksheet.merge_range(row, 0, row, 4, "Analytics Report", header_format)
            row += 2
            worksheet.write(row, 0, f"Organization: {org_name}")
            row += 1
            worksheet.write(row, 0, f"Generated On: {datetime.now().strftime('%d-%m-%Y %H:%M')}")
            row += 1
            
            # Map type to string
            type_label_map = {
                'all': 'Comprehensive Business Summary',
                'monthly': 'Monthly Business Report',
                'financial': 'Financial/Tax Analysis',
                'clients': 'Client Performance Report'
            }
            report_title = type_label_map.get(report_type, 'Analytics Report')
            
            worksheet.write(row, 0, f"Report Type: {report_title}")
            row += 1
            worksheet.write(row, 0, "Reporting Period: Selected Range")
            row += 2
            
            # 2. Revenue Trends (All except clients)
            if report_type in ['all', 'monthly', 'financial']:
                worksheet.write(row, 0, "1. Revenue Trends", sub_header_format)
                row += 2
                
                revenue_data = revenue.get("monthly_data", [])
                df_revenue = pd.DataFrame(revenue_data)
                if not df_revenue.empty:
                    # Rename cols for display
                    df_revenue = df_revenue.rename(columns={
                        "month": "Month", 
                        "revenue": "Revenue (₹)", 
                        "invoice_count": "Number of Invoices"
                    })
                    # Select specific columns to match PDF
                    cols_to_show = ["Month", "Revenue (₹)", "Number of Invoices"]
                    # Ensure cols exist
                    valid_cols = [c for c in cols_to_show if c in df_revenue.columns]
                    df_revenue = df_revenue[valid_cols] if valid_cols else df_revenue
                    
                    df_revenue.to_excel(writer, sheet_name="Analytics Report", startrow=row, index=False)
                    
                    # Apply format to Revenue column (approximate check)
                    for i in range(len(df_revenue)):
                        worksheet.write_number(row + 1 + i, 1, df_revenue.iloc[i]["Revenue (₹)"], currency_format)
                    
                    row += len(df_revenue) + 3
                else:
                    worksheet.write(row, 0, "-")
                    row += 3

            # 3. Profitability Analysis (Only financial or all)
            if report_type in ['all', 'financial']:
                worksheet.write(row, 0, "2. Profitability Analysis", sub_header_format)
                row += 2
                
                profit_data = profit.get("monthly_trends", [])
                df_profit = pd.DataFrame(profit_data)
                if not df_profit.empty:
                    df_profit = df_profit.rename(columns={
                        "month": "Month",
                        "revenue": "Revenue (₹)", 
                        "cost": "Cost (₹)", 
                        "profit": "Profit (₹)",
                        "margin_percentage": "Margin (%)"
                    })
                    cols_to_show = ["Month", "Revenue (₹)", "Cost (₹)", "Profit (₹)", "Margin (%)"]
                    valid_cols = [c for c in cols_to_show if c in df_profit.columns]
                    df_profit = df_profit[valid_cols] if valid_cols else df_profit
                    
                    df_profit.to_excel(writer, sheet_name="Analytics Report", startrow=row, index=False)
                    
                    # Apply currency formats
                    # Revenue (B), Cost (C), Profit (D)
                    for i in range(len(df_profit)):
                        if "Revenue (₹)" in df_profit.columns:
                            worksheet.write_number(row + 1 + i, 1, df_profit.iloc[i].get("Revenue (₹)", 0), currency_format)
                        if "Cost (₹)" in df_profit.columns:
                            worksheet.write_number(row + 1 + i, 2, df_profit.iloc[i].get("Cost (₹)", 0), currency_format)
                        if "Profit (₹)" in df_profit.columns:
                            worksheet.write_number(row + 1 + i, 3, df_profit.iloc[i].get("Profit (₹)", 0), currency_format)

                    row += len(df_profit) + 3
                else:
                    worksheet.write(row, 0, "-")
                    row += 3

            # 4. Payment Status Distribution (Not relevant for client report)
            if report_type in ['all', 'monthly', 'financial']:
                worksheet.write(row, 0, "3. Payment Status Distribution", sub_header_format)
                row += 2
                
                payment_data = payments.get("payment_status_distribution", [])
                df_payments = pd.DataFrame(payment_data)
                if not df_payments.empty:
                    df_payments = df_payments.rename(columns={
                        "status": "Payment Status",
                        "count": "Invoice Count", 
                        "amount": "Amount (₹)"
                    })
                    cols_to_show = ["Payment Status", "Invoice Count", "Amount (₹)"]
                    valid_cols = [c for c in cols_to_show if c in df_payments.columns]
                    df_payments = df_payments[valid_cols] if valid_cols else df_payments
                    
                    df_payments.to_excel(writer, sheet_name="Analytics Report", startrow=row, index=False)
                    
                    # Apply currency format to Amount (C)
                    for i in range(len(df_payments)):
                        worksheet.write_number(row + 1 + i, 2, df_payments.iloc[i]["Amount (₹)"], currency_format)

                    row += len(df_payments) + 4
                else:
                    worksheet.write(row, 0, "-")
                    row += 4

            # 5. Summary Section (Only on all or financial)
            if report_type in ['all', 'financial']:
                worksheet.write(row, 0, "Summary", sub_header_format)
                row += 2
                
                overall_profit = profit.get("overall", {})
                total_revenue = overall_profit.get("total_revenue", 0)
                total_profit = overall_profit.get("total_profit", 0)
                total_cost = overall_profit.get("total_cost", 0)
                
                outstanding_amount = sum(
                    p.get('amount', 0) for p in payments.get("payment_status_distribution", [])
                    if p.get('status') in ['Unpaid', 'Partially Paid']
                )
                
                worksheet.write(row, 0, "Total Revenue:", bold_format)
                worksheet.write_number(row, 1, total_revenue, currency_format)
                row += 1
                
                worksheet.write(row, 0, "Total Profit:", bold_format)
                worksheet.write_number(row, 1, total_profit, currency_format)
                row += 1
                
                worksheet.write(row, 0, "Total Cost:", bold_format)
                worksheet.write_number(row, 1, total_cost, currency_format)
                row += 1
                
                worksheet.write(row, 0, "Outstanding Amount:", bold_format)
                worksheet.write_number(row, 1, outstanding_amount, currency_format)
                row += 1

            # Adjust column widths
            worksheet.set_column(0, 0, 25) # Month/Label
            worksheet.set_column(1, 4, 18) # Metrics
            
        output.seek(0)
        return output

    def generate_pdf_report(self, analytics_data, report_type='all'):
        """Generate PDF report from analytics data dictionary based on report_type"""
        buffer = io.BytesIO()
        type_label_map_title = {
            'all': 'Analytics Report',
            'monthly': 'Monthly Business Report',
            'financial': 'Financial Analysis Report',
            'clients': 'Client Performance Report'
        }
        pdf_title = type_label_map_title.get(report_type, 'Analytics Report')
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40,
            title=pdf_title,
            author='Invoice Pro',
            subject='Business Analytics Report'
        )
        
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
        
        type_label_map = {
            'all': 'Comprehensive Business Summary',
            'monthly': 'Monthly Business Report',
            'financial': 'Financial/Tax Analysis',
            'clients': 'Client Performance Report'
        }
        report_title = type_label_map.get(report_type, 'Analytics Report')
        elements.append(Paragraph(f"Report Type: {report_title}", org_style))
        elements.append(Paragraph(f"Reporting Period: Selected Range", org_style))
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
        if report_type in ['all', 'monthly', 'financial']:
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
                table_data.append(["-", "-", "-"])

            t = Table(table_data, colWidths=col_widths)
            t.setStyle(common_table_style)
            elements.append(t)
            elements.append(Spacer(1, 20))

        # --- Section 2: Profitability Analysis ---
        if report_type in ['all', 'financial']:
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
        if report_type in ['all', 'monthly', 'financial']:
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

        # --- Section 4: Client Performance ---
        if report_type in ['all', 'clients']:
            elements.append(Paragraph("Client Performance Analysis", styles["Heading2"]))
            clients = safe_dict(analytics_data.get("client_performance", {}))
            top_clients = clients.get("top_clients", [])
            
            col_w = available_width / 5
            col_widths = [col_w] * 5
            
            table_data = [["Client Name", "Type", "Revenue (₹)", "Invoices", "Avg Invoice (₹)"]]
            if top_clients:
                for cl in top_clients:
                    table_data.append([
                        str(cl.get("name", "")),
                        str(cl.get("type", "")),
                        f"₹{cl.get('total_revenue', 0):,.2f}",
                        str(cl.get("invoice_count", 0)),
                        f"₹{cl.get('avg_invoice_value', 0):,.2f}"
                    ])
            else:
                 table_data.append(["-", "-", "-", "-", "-"])
                    
            t = Table(table_data, colWidths=col_widths)
            t.setStyle(common_table_style)
            elements.append(t)
            elements.append(Spacer(1, 30))

        # --- Summary Section ---
        if report_type in ['all', 'financial']:
            elements.append(Paragraph("Summary", styles["Heading2"]))
            
            # Calculate totals
            profit = safe_dict(analytics_data.get("profitability_analysis", {}))
            overall_profit = profit.get("overall", {})
            total_revenue = overall_profit.get("total_revenue", 0)
            total_profit = overall_profit.get("total_profit", 0)
            total_cost = overall_profit.get("total_cost", 0)
            
            payments = safe_dict(analytics_data.get("payment_analytics", {}))
            payment_data = payments.get("payment_status_distribution", [])
            
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
