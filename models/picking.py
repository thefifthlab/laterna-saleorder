import requests
import json
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    courier_waybill_no = fields.Char(string="Courier Waybill Reference", readonly=True, copy=False)
    courier_status = fields.Char(string="Courier Status", readonly=True, copy=False)

    def create_waybill(self):
        self.ensure_one()
        get_param = self.env['ir.config_parameter'].sudo().get_param
        base_url = get_param('my_integration.api_base_url', '')
        api_token = get_param('my_integration.api_token', '')

        if not base_url:
            raise UserError("API Base URL is not configured. Please check your system settings.")

        url = f"{base_url.rstrip('/')}/waybill/create-waybill"

        sender = self.company_id
        receiver = self.partner_id

        item_descriptions = ", ".join(
            [f"{move.product_uom_qty} {move.product_id.name}" for move in self.move_ids_without_package])

        payload = {
            "originStateCode": sender.state_id.code,
            "destinationStateCode": receiver.state_id.code,
            "originTownCode": sender.zip,
            "destinationTownCode": receiver.zip,
            "itemDescription": item_descriptions,
            "senderName": sender.name,
            "senderAddress": sender.street,
            "senderPhone": sender.phone,
            "senderEmail": sender.email,
            "senderPostalCode": sender.zip,
            "receiverName": receiver.name,
            "receiverAddress": f"{receiver.street}, {receiver.city}",
            "receiverEmail": receiver.email,
            "receiverPhone": receiver.phone,
            "receiverAltPhone": receiver.mobile,
            "receiverPostalCode": receiver.zip,
            "productTypeCode": "DE",
            "insured": "no",
            "measureWeight": self.weight or 1.0,
            "quantity": sum(self.move_ids_without_package.mapped('product_uom_qty')),
            "declaredValue": sum(
                self.move_ids_without_package.mapped(lambda m: m.product_id.list_price * m.product_uom_qty)),
            "cashOnDelivery": "no",
            "cashOnDeliveryAmount": 0,
            "dimWidth": 15,
            "dimLength": 12,
            "dimHeight": 15,
            "referenceNo": self.name,
            "zoneType": "domestic",
            "requestPickup": "yes",
            "pickupDate": fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "receiverDeliveryOtp": "120934"
        }

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer '+ api_token,
        }

        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
            try:
                response_data = response.json()
            except ValueError:
                response_data = {'message': response.text}

            if response.status_code in [200, 201]:
                waybill_ref = response_data.get('waybillNumber') or self.name
                self.write({
                    'courier_waybill_no': waybill_ref,
                    'courier_status': 'Waybill Created'
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success',
                        'message': f'Courier waybill created successfully: {waybill_ref}',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                error_msg = response_data.get('message') or response.text
                raise UserError(f"Courier API Error ({response.status_code}): {error_msg}")

        except requests.exceptions.RequestException as e:
            _logger.error("Failed to connect to courier API: %s", e)
            raise UserError("Could not connect to the courier service. Please check your network or API settings.")