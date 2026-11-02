import logging
import requests
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class LocationApiController(http.Controller):

    @http.route('/api/location/all-state/<string:country_code>', type='http', auth='public', methods=['GET'], csrf=False)
    def fetch_states(self, country_code, **kwargs):
        get_param = request.env['ir.config_parameter'].sudo().get_param
        base_url = get_param('my_integration.api_base_url', '')
        api_token = get_param('my_integration.api_token', '')

        if not base_url:
            return request.make_response(
                '{"error": "API Base URL is not configured in Odoo settings."}',
                headers={'Content-Type': 'application/json'},
                status=500
            )

        target_url = f"{base_url.rstrip('/')}/location/all-state/{country_code.upper()}"

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + api_token,
        }

        try:
            response = requests.get(target_url, headers=headers, timeout=10)
            response.raise_for_status()

            return request.make_response(
                response.text,
                headers={'Content-Type': 'application/json'},
                status=response.status_code
            )

        except requests.exceptions.RequestException as e:
            _logger.error("Failed to fetch states for country %s: %s", country_code, str(e))
            error_payload = '{"error": "Failed to communicate with external service", "details": "%s"}' % str(e)
            return request.make_response(
                error_payload,
                headers={'Content-Type': 'application/json'},
                status=500
            )

    @http.route('/api/location/all-city/<string:state_code>', type='http', auth='public', methods=['GET'], csrf=False)
    def fetch_cities_by_state(self, state_code, **kwargs):
        get_param = request.env['ir.config_parameter'].sudo().get_param
        base_url = get_param('my_integration.api_base_url', '')
        api_token = get_param('my_integration.api_token', '')

        if not base_url:
            return request.make_response(
                '{"error": "API Base URL is not configured in Odoo settings."}',
                headers={'Content-Type': 'application/json'},
                status=500
            )

        target_url = f"{base_url.rstrip('/')}/location/all-city/{state_code.upper()}"

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + api_token,
        }

        try:
            response = requests.get(target_url, headers=headers, timeout=10)
            response.raise_for_status()

            return request.make_response(
                response.text,
                headers={'Content-Type': 'application/json'},
                status=response.status_code
            )

        except requests.exceptions.RequestException as e:
            _logger.error("Failed to fetch cities for state code %s: %s", state_code, str(e))
            error_payload = '{"error": "Failed to communicate with external service", "details": "%s"}' % str(e)
            return request.make_response(
                error_payload,
                headers={'Content-Type': 'application/json'},
                status=500
            )