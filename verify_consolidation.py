
def consolidate_items(challans, consolidation_option):
    consolidated_items = []
    item_map = {} # Used for 'merge' option

    for c in challans:
        c_num = c.get('challan_number', 'Unknown')
        for item in c.get('line_items', []):
            qty = float(item.get('quantity', 0))
            price = float(item.get('unit_price', 0))
            desc = item.get('description', '').strip()
            hsn = item.get('hsn_code', '').strip()
            unit = item.get('unit', '')

            if consolidation_option == 'merge':
                key = (desc, hsn, price)
                if key in item_map:
                    item_map[key]['quantity'] += qty
                    item_map[key]['total_amount'] += (qty * price)
                else:
                    item_map[key] = {
                        'hsn_code': hsn,
                        'description': desc,
                        'quantity': qty,
                        'unit': unit,
                        'unit_price': price,
                        'total_amount': qty * price
                    }
            else: # 'group' option
                consolidated_items.append({
                    'hsn_code': hsn,
                    'description': f"[{c_num}] {desc}",
                    'quantity': qty,
                    'unit': unit,
                    'unit_price': price,
                    'total_amount': qty * price
                })

    if consolidation_option == 'merge':
        for i, (key, item) in enumerate(item_map.items(), 1):
            item['sr_no'] = i
            consolidated_items.append(item)
    else:
        for i, item in enumerate(consolidated_items, 1):
            item['sr_no'] = i
    
    return consolidated_items

# Test Data
challans = [
    {
        'challan_number': 'CH-001',
        'line_items': [
            {'hsn_code': '123', 'description': 'Item A', 'quantity': 2, 'unit': 'Nos', 'unit_price': 100},
            {'hsn_code': '456', 'description': 'Item B', 'quantity': 1, 'unit': 'Nos', 'unit_price': 200}
        ]
    },
    {
        'challan_number': 'CH-002',
        'line_items': [
            {'hsn_code': '123', 'description': 'Item A', 'quantity': 3, 'unit': 'Nos', 'unit_price': 100},
            {'hsn_code': '789', 'description': 'Item C', 'quantity': 1, 'unit': 'Nos', 'unit_price': 300}
        ]
    }
]

print("--- MERGE OPTION ---")
merged = consolidate_items(challans, 'merge')
for item in merged:
    print(f"[{item['sr_no']}] {item['description']} ({item['hsn_code']}): Qty={item['quantity']}, Total={item['total_amount']}")

print("\n--- GROUP OPTION ---")
grouped = consolidate_items(challans, 'group')
for item in grouped:
    print(f"[{item['sr_no']}] {item['description']} ({item['hsn_code']}): Qty={item['quantity']}, Total={item['total_amount']}")
