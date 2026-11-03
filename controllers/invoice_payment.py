import logging
import json
import jwt
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class APIInvoicePaymentController(http.Controller):

    @http.route('/api/order/invoice-and-pay', type='http', auth='public', methods=['POST'], csrf=False, cors='*')
    def create_invoice_and_register_payment(self, **kwargs):
        # 1. Validate JWT Bearer Token
        auth_header = request.httprequest.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return request.make_json_response({
                'status': 'error',
                'message': 'Missing or invalid Authorization header.'
            }, status=401)

        token = auth_header.split(' ')[1]
        secret_key = request.env['ir.config_parameter'].sudo().get_param('auth_token.secret_key')

        try:
            payload = jwt.decode(token, secret_key, algorithms=['HS256'])
            user_id = payload.get('user_id')
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return request.make_json_response({
                'status': 'error',
                'message': 'Invalid or expired token.'
            }, status=401)

        user = request.env['res.users'].sudo().browse(user_id)
        if not user.exists() or not user.active:
            return request.make_json_response({
                'status': 'error',
                'message': 'User no longer exists or is inactive.'
            }, status=401)

        env_user = request.env(user=user.id)

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
            # Allow client to override journal code if needed, defaults to 'BNK1'
            journal_code = data.get('journal_code', 'BNK1')
            payment_amount = data.get('amount')  # Optional: defaults to total residual

            # 2. Locate the Sale Order
            SaleOrder = env_user['sale.order']
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

            # 3. Create Invoice from Sale Order
            invoices = sale_order._create_invoices()
            if not invoices:
                return request.make_json_response({
                    'status': 'error',
                    'message': 'No invoice could be created. Order may already be fully invoiced.'
                }, status=400)

            posted_invoices = []
            payment_results = []

            for invoice in invoices:
                # Post the draft invoice
                if invoice.state == 'draft':
                    invoice.action_post()

                posted_invoices.append({
                    'invoice_id': invoice.id,
                    'invoice_name': invoice.name,
                    'amount_total': invoice.amount_total,
                    'amount_residual': invoice.amount_residual,
                })

                # 4. Register Payment using Journal Code 'BNK1'
                if invoice.amount_residual > 0:
                    # Find journal by code 'BNK1'
                    journal = env_user['account.journal'].search([
                        ('code', '=', journal_code),
                        ('company_id', '=', invoice.company_id.id)
                    ], limit=1)

                    # Fallback to any bank/cash journal if 'BNK1' isn't found
                    if not journal.exists():
                        journal = env_user['account.journal'].search([
                            ('type', 'in', ('bank', 'cash')),
                            ('company_id', '=', invoice.company_id.id)
                        ], limit=1)

                    if not journal.exists():
                        return request.make_json_response({
                            'status': 'error',
                            'message': f'Payment journal with code "{journal_code}" not found.'
                        }, status=400)

                    amount_to_pay = float(payment_amount) if payment_amount else invoice.amount_residual

                    # Create and process payment wizard
                    payment_register = env_user['account.payment.register'].with_context(
                        active_model='account.move',
                        active_ids=invoice.id
                    ).create({
                        'journal_id': journal.id,
                        'amount': amount_to_pay,
                        'payment_date': fields.Date.context_today(invoice),
                        'communication': invoice.payment_reference or invoice.name,
                    })

                    payment = payment_register._create_payments()

                    payment_results.append({
                        'payment_id': payment.id,
                        'payment_name': payment.name,
                        'amount': payment.amount,
                        'journal': journal.name,
                    })

            return request.make_json_response({
                'status': 'success',
                'message': 'Invoice created, posted, and payment registered successfully with BNK1.',
                'data': {
                    'order_id': sale_order.id,
                    'order_name': sale_order.name,
                    'invoice_status': sale_order.invoice_status,
                    'invoices': posted_invoices,
                    'payments': payment_results,
                }
            })

        except Exception as e:
            _logger.exception("Failed to invoice and pay sale order via API")
            return request.make_json_response({
                'status': 'error',
                'message': str(e)
            }, status=500)