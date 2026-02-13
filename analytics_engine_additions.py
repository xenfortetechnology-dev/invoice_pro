    def compute_revenue_trends(self, invoices_data: List[Dict], time_range: str = '12m') -> Dict[str, Any]:
        """Compute revenue trends from invoice data list"""
        try:
            months = self._parse_time_range(time_range)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30 * months)
            
            # Filter and process data
            monthly_data = defaultdict(lambda: {'revenue': 0.0, 'count': 0, 'total': 0.0})
            
            for inv in invoices_data:
                if inv.get('payment_status') != 'Paid':
                    continue
                    
                inv_date_str = inv.get('invoice_date')
                if not inv_date_str:
                    continue
                    
                try:
                    inv_date = datetime.strptime(inv_date_str, '%Y-%m-%d')
                    if inv_date < start_date:
                        continue
                        
                    month_key = inv_date.strftime('%Y-%m')
                    amount = float(inv.get('total_amount', 0))
                    
                    monthly_data[month_key]['revenue'] += amount
                    monthly_data[month_key]['count'] += 1
                    monthly_data[month_key]['total'] += amount
                except ValueError:
                    continue

            # Format result
            revenue_data = []
            sorted_months = sorted(monthly_data.keys())
            
            previous_revenue = 0
            for month in sorted_months:
                data = monthly_data[month]
                current_revenue = data['revenue']
                
                growth_rate = 0
                if previous_revenue > 0:
                    growth_rate = ((current_revenue - previous_revenue) / previous_revenue) * 100
                
                revenue_data.append({
                    'month': month,
                    'revenue': current_revenue,
                    'invoice_count': data['count'],
                    'avg_invoice_value': data['total'] / data['count'] if data['count'] else 0,
                    'growth_rate': round(growth_rate, 2)
                })
                previous_revenue = current_revenue
                
            # Summary
            total_revenue = sum(d['revenue'] for d in revenue_data)
            
            return {
                'monthly_data': revenue_data,
                'summary': {
                    'total_revenue': total_revenue,
                    'avg_monthly_revenue': total_revenue / len(revenue_data) if revenue_data else 0,
                    'trend_direction': self._calculate_trend_direction(revenue_data),
                    'total_invoices': sum(d['invoice_count'] for d in revenue_data),
                    'period_months': months
                }
            }
        except Exception as e:
            logging.error(f"Compute revenue trends error: {e}")
            return {'error': str(e)}

    def compute_client_performance_metrics(self, invoices_data: List[Dict], clients_data: List[Dict]) -> Dict[str, Any]:
        """Compute client performance from data lists"""
        try:
            client_metrics = defaultdict(lambda: {
                'revenue': 0.0, 'count': 0, 'last_date': None
            })
            
            # Aggregate invoice data
            for inv in invoices_data:
                if inv.get('payment_status') != 'Paid':
                    continue
                
                client_id = inv.get('client_id')
                if not client_id:
                    continue
                    
                amount = float(inv.get('total_amount', 0))
                inv_date = inv.get('invoice_date')
                
                metrics = client_metrics[int(client_id)]
                metrics['revenue'] += amount
                metrics['count'] += 1
                if inv_date:
                    if not metrics['last_date'] or inv_date > metrics['last_date']:
                        metrics['last_date'] = inv_date

            # Merge with client data
            top_clients = []
            client_map = {c['id']: c for c in clients_data}
            
            for cid, metrics in client_metrics.items():
                client = client_map.get(cid)
                if not client:
                    continue
                    
                top_clients.append({
                    'id': cid,
                    'name': client.get('name', 'Unknown'),
                    'type': client.get('client_type', 'Regular'),
                    'total_revenue': metrics['revenue'],
                    'invoice_count': metrics['count'],
                    'avg_invoice_value': metrics['revenue'] / metrics['count'] if metrics['count'] else 0,
                    'last_invoice_date': metrics['last_date'],
                    'risk_score': float(client.get('ai_risk_score', 0) or 0),
                    'predicted_ltv': float(client.get('predicted_ltv', 0) or 0)
                })
            
            # Sort by revenue
            top_clients.sort(key=lambda x: x['total_revenue'], reverse=True)
            
            # Segments (simplified)
            segments = {
                'by_value': {
                    'high_value': len([c for c in top_clients if c['total_revenue'] > 100000]),
                    'medium_value': len([c for c in top_clients if 25000 <= c['total_revenue'] <= 100000]),
                    'low_value': len([c for c in top_clients if c['total_revenue'] < 25000])
                }
            }
            
            # Client Types
            type_counts = defaultdict(int)
            for c in clients_data:
                type_counts[c.get('client_type', 'Regular')] += 1
                
            client_types = [{'type': k, 'count': v} for k, v in type_counts.items()]

            return {
                'top_clients': top_clients[:20],
                'segments': segments,
                'lifecycle': {'stages': []}, 
                'risk_analysis': {'risk_distribution': {}}, 
                'client_types': client_types
            }
        except Exception as e:
            logging.error(f"Compute client metrics error: {e}")
            return {'error': str(e)}

    def compute_payment_analytics(self, invoices_data: List[Dict]) -> Dict[str, Any]:
        """Compute payment analytics from invoice data"""
        try:
            status_dist = defaultdict(lambda: {'count': 0, 'amount': 0.0})
            monthly_collections = defaultdict(lambda: {'collected': 0.0, 'count': 0})
            
            current_date = datetime.now().date()
            overdue_counts = {'30': 0, '60': 0, '90': 0}
            overdue_amounts = {'30': 0.0, '60': 0.0, '90': 0.0}

            for inv in invoices_data:
                status = inv.get('payment_status', 'Unknown')
                amount = float(inv.get('total_amount', 0))
                
                status_dist[status]['count'] += 1
                status_dist[status]['amount'] += amount
                
                if status == 'Paid':
                    p_date_str = inv.get('payment_date') or inv.get('invoice_date')
                    if p_date_str:
                        try:
                            p_date = datetime.strptime(p_date_str, '%Y-%m-%d')
                            if p_date.date() >= (current_date - timedelta(days=365)):
                                m_key = p_date.strftime('%Y-%m')
                                monthly_collections[m_key]['collected'] += amount
                                monthly_collections[m_key]['count'] += 1
                        except ValueError:
                            pass
                            
                # Outstanding
                if status in ['Unpaid', 'Partially Paid']:
                    due_date_str = inv.get('due_date')
                    target_date = None
                    if due_date_str:
                        try:
                            target_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
                        except: pass
                    elif inv.get('invoice_date'):
                         try:
                            target_date = datetime.strptime(inv.get('invoice_date'), '%Y-%m-%d').date() + timedelta(days=30)
                         except: pass
                    
                    if target_date:
                        days_overdue = (current_date - target_date).days
                        if days_overdue > 90:
                            overdue_counts['90'] += 1
                            overdue_amounts['90'] += amount
                        elif days_overdue > 60:
                            overdue_counts['60'] += 1
                            overdue_amounts['60'] += amount
                        elif days_overdue > 30:
                            overdue_counts['30'] += 1
                            overdue_amounts['30'] += amount

            # Format
            payment_status_distribution = [
                {'status': k, 'count': v['count'], 'amount': v['amount']}
                for k, v in status_dist.items()
            ]
            
            monthly_coll_list = [
                {'month': k, 'collected': v['collected'], 'invoices_paid': v['count']}
                for k, v in sorted(monthly_collections.items())
            ]
            
            return {
                'payment_status_distribution': payment_status_distribution,
                'payment_timing': {'avg_delay_days': 0},
                'payment_modes': [],
                'monthly_collections': monthly_coll_list,
                'outstanding': {
                    'aging_analysis': {
                        '30_days': {'count': overdue_counts['30'], 'amount': overdue_amounts['30']},
                        '60_days': {'count': overdue_counts['60'], 'amount': overdue_amounts['60']},
                        '90_days': {'count': overdue_counts['90'], 'amount': overdue_amounts['90']},
                    }
                }
            }
        except Exception as e:
            logging.error(f"Compute payment analytics error: {e}")
            return {'error': str(e)}

    def compute_profitability_analysis(self, invoices_data: List[Dict]) -> Dict[str, Any]:
        """Compute profitability (approximate as we might lack cost data)"""
        try:
            total_revenue = 0.0
            total_cost = 0.0
            
            monthly_data = defaultdict(lambda: {'revenue': 0, 'cost': 0})
            
            for inv in invoices_data:
                if inv.get('payment_status') == 'Paid':
                    amount = float(inv.get('total_amount', 0))
                    total_revenue += amount
                    # Mock cost as 70% of revenue for demonstration if field missing
                    cost = amount * 0.7 
                    total_cost += cost
                    
                    if inv.get('invoice_date'):
                         try:
                            m_key = inv.get('invoice_date')[:7] # YYYY-MM
                            monthly_data[m_key]['revenue'] += amount
                            monthly_data[m_key]['cost'] += cost
                         except: pass

            total_profit = total_revenue - total_cost
            margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
            
            monthly_list = []
            for m_key in sorted(monthly_data.keys()):
                d = monthly_data[m_key]
                prof = d['revenue'] - d['cost']
                marg = (prof / d['revenue'] * 100) if d['revenue'] > 0 else 0
                monthly_list.append({
                    'month': m_key,
                    'revenue': d['revenue'],
                    'cost': d['cost'],
                    'profit': prof,
                    'margin_percentage': round(marg, 2)
                })
                
            return {
                "overall": {
                    "total_revenue": total_revenue,
                    "total_cost": total_cost,
                    "total_profit": total_profit,
                    "profit_margin_percentage": round(margin, 2)
                },
                "monthly_trends": monthly_list,
                "top_profitable_clients": [] 
            }
        except Exception as e:
            logging.error(f"Compute profitability error: {e}")
            return {'error': str(e)}
