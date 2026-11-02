# controllers/main.py
from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class CourierWebhookController(http.Controller):

    @http.route('/courier/webhook/status-update', type='json', auth='public', methods=['POST'], csrf=False)
    def handle_courier_webhook(self, **kwargs):
        try:
            data = request.jsonrequest
            reference_no = data.get('referenceNo')
            status = data.get('status')

            if not reference_no:
                return {"status": "error", "message": "Missing referenceNo"}

            picking = request.env['stock.picking'].sudo().search([('name', '=', reference_no)], limit=1)
            if picking:
                picking.write({'courier_status': status})
                _logger.info("Updated picking %s with status %s", reference_no, status)
                return {"status": "success", "message": "Status updated successfully"}
            else:
                return {"status": "error", "message": "Delivery order not found"}

        except Exception as e:
            _logger.error("Error processing courier webhook: %s", e)
            return {"status": "error", "message": str(e)}