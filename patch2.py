import re

code_to_insert = '''        line_items=[
                    SimpleNamespace(
                        sr_no=item.get("sr_no", i+1),
                        hsn_code=item.get("hsn_code", ""),
                        description = item.get("description", item.get("item_name", "")),
                        quantity=item.get("quantity", 0),
                        unit=item.get("unit", "Nos"),
                        unit_price=item.get("unit_price", 0),
                        tax_percentage=item.get("tax_percentage", 0),
                        tax_amount=item.get("tax_amount", 0),
                        total_amount=item.get("total_amount", 0)
                    )
                    for i, item in enumerate(q_data.get("line_items", []))
                ]'''

with open(r'd:\Phone\download\ML\IP\routes.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = re.sub(r'line_items=\[\]\s*# Quotations currently don\'t.*', code_to_insert, text)

with open(r'd:\Phone\download\ML\IP\routes.py', 'w', encoding='utf-8') as f:
    f.write(text)

