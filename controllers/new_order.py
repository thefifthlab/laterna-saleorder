import logging
import json
import jwt
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class APIOrderController(http.Controller):

    @http.route('/api/create/saleorder', type='http', auth='public', methods=['POST'], csrf=False, cors='*')
    def create_sale_order_from_json(self, **kwargs):
        # 1. Extract and Validate Bearer Token from Authorization Header
        auth_header = request.httprequest.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return request.make_json_response({
                'status': 'error',
                'message': 'Missing or invalid Authorization header. Expected "Bearer <token>"'
            }, status=401)

        token = auth_header.split(' ')[1]

        # 2. Load JWT secret key
        secret_key = request.env['ir.config_parameter'].sudo().get_param('auth_token.secret_key')
        if not secret_key:
            _logger.error("Missing 'auth_token.secret_key' in ir.config_parameter")
            return request.make_json_response({
                'status': 'error',
                'message': 'Server configuration error'
            }, status=500)

        # 3. Decode and Verify JWT Token
        try:
            payload = jwt.decode(token, secret_key, algorithms=['HS256'])
            user_id = payload.get('user_id')
        except jwt.ExpiredSignatureError:
            return request.make_json_response({
                'status': 'error',
                'message': 'Token has expired'
            }, status=401)
        except jwt.InvalidTokenError:
            return request.make_json_response({
                'status': 'error',
                'message': 'Invalid token'
            }, status=401)

        # Verify user still exists and is active
        user = request.env['res.users'].sudo().browse(user_id)
        if not user.exists() or not user.active:
            return request.make_json_response({
                'status': 'error',
                'message': 'User no longer exists or is inactive'
            }, status=401)

        try:
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except Exception:
                return request.make_json_response({
                    'status': 'error',
                    'message': 'Invalid JSON payload provided in the request body.'
                }, status=400)

            if not data:
                return request.make_json_response({
                    'status': 'error',
                    'message': 'No data provided.'
                }, status=400)

            billing = data.get('billing_address', {})
            shipping = data.get('shipping_address', {})
            shipping_same = data.get('shipping_same_as_billing', True)
            cart = data.get('cart', {})

            # Use environment scoped to the authenticated user for business logic
            # (or use sudo() if partners/countries require elevated creation rights)
            env_user = request.env(user=user.id)
            Partner = env_user['res.partner']

            country_id = int(billing.get('country_id', 0)) if billing.get('country_id') else False
            if not country_id and billing.get('country_code'):
                country = env_user['res.country'].search([('code', '=', billing.get('country_code'))], limit=1)
                country_id = country.id if country else False

            partner_email = billing.get('email')
            if not partner_email:
                return request.make_json_response({
                    'status': 'error',
                    'message': 'Billing email is required.'
                }, status=400)

            partner = Partner.search([('email', '=', partner_email)], limit=1)
            partner_vals = {
                'name': billing.get('name'),
                'email': partner_email,
                'phone': billing.get('phone'),
                'street': billing.get('street'),
                'city': billing.get('city'),
                'zip': billing.get('zip'),
                'country_id': country_id,
            }

            if not partner:
                partner = Partner.create(partner_vals)
            else:
                partner.write(partner_vals)

            shipping_partner = partner
            if not shipping_same and shipping:
                ship_country_id = int(shipping.get('country_id', 0)) if shipping.get('country_id') else False
                if not ship_country_id and shipping.get('country_code'):
                    ship_country = env_user['res.country'].search([('code', '=', shipping.get('country_code'))],
                                                                  limit=1)
                    ship_country_id = ship_country.id if ship_country else False

                shipping_vals = {
                    'name': shipping.get('name'),
                    'email': shipping.get('email'),
                    'phone': shipping.get('phone'),
                    'street': shipping.get('street'),
                    'city': shipping.get('city'),
                    'zip': shipping.get('zip'),
                    'country_id': ship_country_id,
                    'type': 'delivery',
                    'parent_id': partner.id,
                }
                shipping_partner = Partner.create(shipping_vals)

            # Order Lines
            order_lines = []
            for line in cart.get('lines', []):
                product_id = line.get('product_id')
                qty = line.get('qty', 1.0)
                price_unit = line.get('price_unit', 0.0)

                product = env_user['product.product'].browse(product_id)
                if not product.exists():
                    return request.make_json_response({
                        'status': 'error',
                        'message': f'Product ID {product_id} does not exist.'
                    }, status=400)

                order_lines.append((0, 0, {
                    'product_id': product_id,
                    'product_uom_qty': qty,
                    'price_unit': price_unit,
                }))

            amount_shipping = cart.get('amount_shipping', 0.0)
            if amount_shipping > 0:
                delivery_product = env_user['product.product'].search([('name', 'ilike', 'Delivery')], limit=1)
                if delivery_product:
                    order_lines.append((0, 0, {
                        'product_id': delivery_product.id,
                        'product_uom_qty': 1.0,
                        'price_unit': amount_shipping,
                        'name': 'Shipping Fees',
                    }))

            # Create Sale Order under user context
            SaleOrder = env_user['sale.order']
            order_vals = {
                'partner_id': partner.id,
                'partner_shipping_id': shipping_partner.id,
                'client_order_ref': cart.get('name'),
                'order_line': order_lines,
            }
            sale_order = SaleOrder.create(order_vals)
            sale_order.action_confirm()

            # Handle Pickings / Waybills
            for picking in sale_order.picking_ids.filtered(lambda p: p.state != 'cancel'):
                if hasattr(picking, 'create_waybill'):
                    try:
                        picking.create_waybill()
                    except Exception as pick_err:
                        _logger.error("Failed to auto-create waybill for picking %s: %s", picking.name, str(pick_err))

            return request.make_json_response({
                'status': 'success',
                'message': 'Sale order created and confirmed successfully.',
                'data': {
                    'order_id': sale_order.id,
                    'order_name': sale_order.name,
                    'customer_id': partner.id,
                    'customer_name': partner.name,
                    'amount_total': sale_order.amount_total,
                }
            })

        except Exception as e:
            _logger.exception("Failed to create sale order from API")
            return request.make_json_response({
                'status': 'error',
                'message': 'An internal server error occurred while processing the order.'
            }, status=500)