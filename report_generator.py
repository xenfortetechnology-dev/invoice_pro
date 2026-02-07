import io
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfgen import canvas
from datetime import datetime

from utils import safe_dict

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
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []
        
        # Extract data
        revenue = safe_dict(analytics_data.get("revenue_trends", {}))
        profit = safe_dict(analytics_data.get("profitability_analysis", {}))
        payments = safe_dict(analytics_data.get("payment_analytics", {}))
        clients = safe_dict(analytics_data.get("client_performance", {}))
        
        # Title
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Title'],
            fontSize=24,
            spaceAfter=20
        )
        elements.append(Paragraph("Analytics Report", title_style))
        elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%d-%m-%Y %H:%M')}", styles['Normal']))
        elements.append(Spacer(1, 20))

        # Revenue Section
        elements.append(Paragraph("Revenue Trends", styles["Heading2"]))
        revenue_data = revenue.get("monthly_data", [])
        if revenue_data:
            table_data = [["Month", "Revenue", "Invoices"]]
            for r in revenue_data:
                table_data.append([
                    str(r.get("month", "")), 
                    f"₹{r.get('revenue', 0):,.2f}", 
                    str(r.get("invoice_count", 0))
                ])
            t = Table(table_data)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ]))
            elements.append(t)
        else:
            elements.append(Paragraph("No revenue data available.", styles["Normal"]))
        elements.append(Spacer(1, 15))

        # Profit Section
        elements.append(Paragraph("Profitability Analysis", styles["Heading2"]))
        profit_data = profit.get("monthly_trends", [])
        if profit_data:
            table_data = [["Month", "Revenue", "Cost", "Profit", "Margin %"]]
            for p in profit_data:
                table_data.append([
                    str(p.get("month", "")),
                    f"₹{p.get('revenue', 0):,.2f}",
                    f"₹{p.get('cost', 0):,.2f}",
                    f"₹{p.get('profit', 0):,.2f}",
                    f"{p.get('margin_percentage', 0)}%"
                ])
            t = Table(table_data)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ]))
            elements.append(t)
        else:
            elements.append(Paragraph("No profitability data available.", styles["Normal"]))
        elements.append(Spacer(1, 15))

        # Payment Status Section
        elements.append(Paragraph("Payment Status Distribution", styles["Heading2"]))
        payment_data = payments.get("payment_status_distribution", [])
        if payment_data:
            table_data = [["Status", "Count", "Amount"]]
            for pay in payment_data:
                table_data.append([
                    str(pay.get("status", "")),
                    str(pay.get("count", 0)),
                    f"₹{pay.get('amount', 0):,.2f}"
                ])
            t = Table(table_data)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ]))
            elements.append(t)
        else:
            elements.append(Paragraph("No payment data available.", styles["Normal"]))
        elements.append(Spacer(1, 15))

        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        return buffer
