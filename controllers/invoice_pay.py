import logging
import json
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class APIInvoicePaymentController(http.Controller):

    @http.route('/api/order/invoice_pay', type='http', auth='public', methods=['POST'], csrf=False, cors='*')
    def create_invoice_and_register_payment(self, **kwargs):
        try:
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except Exception:
                return request.make_json_response({
                    'status': 'error',
                    'message': 'Invalid JSON payload provided.'
                }, status=400)

            order_id = data.get('order_id')
            order_name = data.get('order_name')
            journal_code = data.get('journal_code', 'BNK1')
            payment_amount = data.get('amount')

            # 1. Locate the Sale Order using superuser
            SaleOrder = request.env['sale.order'].with_user(1)
            sale_order = False
            if order_id:
                sale_order = SaleOrder.browse(int(order_id))
            elif order_name:
                sale_order = SaleOrder.search([('name', '=', order_name)], limit=1)

            if not sale_order or not sale_order.exists():
                return request.make_json_response({
                    'status': 'error',
                    'message': 'Sale order not found.'
                }, status=404)

            if sale_order.state not in ['sale', 'done']:
                return request.make_json_response({
                    'status': 'error',
                    'message': f'Cannot invoice sale order in state "{sale_order.state}". Order must be confirmed first.'
                }, status=400)

            # 2. Create Invoice from Sale Order using superuser
            invoices = sale_order.with_user(1)._create_invoices()
            if not invoices:
                return request.make_json_response({
                    'status': 'error',
                    'message': 'No invoice could be created. Order may already be fully invoiced.'
                }, status=400)

            posted_invoices = []
            payment_results = []

            for invoice in invoices:
                # Post the draft invoice with superuser
                if invoice.state == 'draft':
                    invoice.with_user(1).action_post()

                posted_invoices.append({
                    'invoice_id': invoice.id,
                    'invoice_name': invoice.name,
                    'amount_total': invoice.amount_total,
                    'amount_residual': invoice.amount_residual,
                })

                # 3. Register Payment using Journal Code with superuser
                if invoice.amount_residual > 0:
                    journal = request.env['account.journal'].with_user(1).search([
                        ('code', '=', journal_code),
                        ('company_id', '=', invoice.company_id.id)
                    ], limit=1)

                    if not journal.exists():
                        journal = request.env['account.journal'].with_user(1).search([
                            ('type', 'in', ('bank', 'cash')),
                            ('company_id', '=', invoice.company_id.id)
                        ], limit=1)

                    if not journal.exists():
                        request.env.cr.rollback()
                        return request.make_json_response({
                            'status': 'error',
                            'message': f'Payment journal with code "{journal_code}" not found.'
                        }, status=400)

                    amount_to_pay = float(payment_amount) if payment_amount else invoice.amount_residual

                    payment_register = request.env['account.payment.register'].with_user(1).with_context(
                        active_model='account.move',
                        active_ids=invoice.ids
                    ).create({
                        'journal_id': journal.id,
                        'amount': amount_to_pay,
                        'payment_date': fields.Date.context_today(invoice),
                        'communication': invoice.payment_reference or invoice.name,
                    })

                    payment = payment_register.with_user(1)._create_payments()

                    payment_results.append({
                        'payment_id': payment.id,
                        'payment_name': payment.name,
                        'amount': payment.amount,
                        'journal': journal.name,
                    })

            return request.make_json_response({
                'status': 'success',
                'message': 'Invoice created, posted, and payment registered successfully.',
                'data': {
                    'order_id': sale_order.id,
                    'order_name': sale_order.name,
                    'invoice_status': sale_order.invoice_status,
                    'invoices': posted_invoices,
                    'payments': payments if 'payments' in locals() else payment_results,
                }
            })

        except Exception as e:
            request.env.cr.rollback()
            _logger.exception("Failed to invoice and pay sale order via API")
            return request.make_json_response({
                'status': 'error',
                'message': str(e)
            }, status=500)