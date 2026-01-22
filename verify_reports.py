from report_generator import AnalyticsReportGenerator
import os

def test_report_generation():
    print("Testing Report Generation...")
    
    # Mock Data
    mock_data = {
        'revenue_trends': {
            'monthly_data': [{'month': 'Jan 2024', 'revenue': 10000, 'invoice_count': 5}]
        },
        'profitability_analysis': {
            'monthly_trends': [{'month': 'Jan 2024', 'revenue': 10000, 'cost': 5000, 'profit': 5000, 'margin_percentage': 50}]
        },
        'payment_analytics': {
            'payment_status_distribution': [{'status': 'Paid', 'count': 5, 'amount': 10000}]
        },
        'client_performance': {
            'top_clients': [{'name': 'Test Client', 'total_revenue': 10000, 'invoice_count': 5}]
        }
    }
    
    generator = AnalyticsReportGenerator()
    
    # Test PDF
    try:
        pdf_buffer = generator.generate_pdf_report(mock_data)
        if pdf_buffer.getbuffer().nbytes > 0:
            print("PDF generation successful.")
        else:
            print("PDF generation failed (empty buffer).")
    except Exception as e:
        print(f"PDF generation failed: {e}")
        
    # Test Excel
    try:
        excel_buffer = generator.generate_excel_report(mock_data)
        if excel_buffer.getbuffer().nbytes > 0:
            print("Excel generation successful.")
        else:
            print("Excel generation failed (empty buffer).")
    except Exception as e:
        print(f"Excel generation failed: {e}")

if __name__ == "__main__":
    test_report_generation()
