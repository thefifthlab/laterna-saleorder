import logging
import json
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class APIOrderController(http.Controller):

    @http.route('/create/saleorder', type='http', auth='public', methods=['POST'], csrf=False, cors='*')
    def create_sale_order_from_json(self, **kwargs):
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
            Partner = request.env['res.partner'].sudo()
            country_id = int(billing.get('country_id', 0)) if billing.get('country_id') else False
            if not country_id and billing.get('country_code'):
                country = request.env['res.country'].sudo().search([('code', '=', billing.get('country_code'))], limit=1)
                country_id = country.id if country else False
            partner_email = billing.get('email')
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
                    ship_country = request.env['res.country'].sudo().search([('code', '=', shipping.get('country_code'))], limit=1)
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
            order_lines = []
            for line in cart.get('lines', []):
                product_id = line.get('product_id')
                qty = line.get('qty', 1.0)
                price_unit = line.get('price_unit', 0.0)
                product = request.env['product.product'].sudo().browse(product_id)
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
                delivery_product = request.env['product.product'].sudo().search([('name', 'ilike', 'Delivery')], limit=1)
                if delivery_product:
                    order_lines.append((0, 0, {
                        'product_id': delivery_product.id,
                        'product_uom_qty': 1.0,
                        'price_unit': amount_shipping,
                        'name': 'Shipping Fees',
                    }))
            SaleOrder = request.env['sale.order'].sudo()
            order_vals = {
                'partner_id': partner.id,
                'partner_shipping_id': shipping_partner.id,
                'client_order_ref': cart.get('name'),
                'order_line': order_lines,
            }
            sale_order = SaleOrder.create(order_vals)
            sale_order.action_confirm()

            for picking in sale_order.picking_ids.filtered(lambda p: p.state != 'cancel'):
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
            _logger.error("Failed to create sale order from API: %s", str(e))
            return request.make_json_response({
                'status': 'error',
                'message': str(e)
            }, status=500)


