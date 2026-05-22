import requests
import json
from django.conf import settings

# Directortechs API Configuration
DIRECTORTECHS_BASE_URL = "https://directortechs.com/api"
DIRECTORTECHS_API_KEY = "66f2e5c39ac8640f13cd888f161385b12f7e5e92"

HEADERS = {
    'Authorization': f'Bearer {DIRECTORTECHS_API_KEY}',
    'Content-Type': 'application/json'
}

def get_cable_providers():
    """Get available cable TV providers"""
    try:
        # Based on API docs, this endpoint returns provider info
        url = f"{DIRECTORTECHS_BASE_URL}/cablesub"
        print(f"Fetching providers from: {url}")
        response = requests.get(url, headers=HEADERS, timeout=30, verify=False)
        print(f"Response status: {response.status_code}")
        response.raise_for_status()
        result = response.json()
        print(f"Response data: {result}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"API Error: {str(e)}")
        return {'error': f'Network error: {str(e)}', 'success': False}
    except json.JSONDecodeError as e:
        print(f"JSON Error: {str(e)}")
        return {'error': f'Invalid response format: {str(e)}', 'success': False}

def validate_smart_card(smart_card_number, cable_provider):
    """Validate smart card/IUC number"""
    try:
        url = f"{DIRECTORTECHS_BASE_URL}/validateiuc"
        params = {
            'smart_card_number': smart_card_number,
            'cablename': cable_provider
        }
        print(f"Validating smart card: {url} with params: {params}")
        response = requests.get(url, headers=HEADERS, params=params, timeout=30, verify=False)
        print(f"Validation response status: {response.status_code}")
        response.raise_for_status()
        result = response.json()
        print(f"Validation result: {result}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"Validation API Error: {str(e)}")
        return {'error': f'Network error: {str(e)}', 'success': False}
    except json.JSONDecodeError as e:
        print(f"Validation JSON Error: {str(e)}")
        return {'error': f'Invalid response format: {str(e)}', 'success': False}

def validate_meter(meter_number, disco_name, meter_type):
    """Validate electricity meter"""
    try:
        url = f"{DIRECTORTECHS_BASE_URL}/validatemeter"
        params = {
            'meternumber': meter_number,
            'disconame': disco_name,
            'mtype': meter_type
        }
        print(f"Validating meter: {url} with params: {params}")
        response = requests.get(url, headers=HEADERS, params=params, timeout=30, verify=False)
        print(f"Meter validation response status: {response.status_code}")
        response.raise_for_status()
        result = response.json()
        print(f"Meter validation result: {result}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"Meter validation API Error: {str(e)}")
        return {'error': f'Network error: {str(e)}', 'success': False}
    except json.JSONDecodeError as e:
        print(f"Meter validation JSON Error: {str(e)}")
        return {'error': f'Invalid response format: {str(e)}', 'success': False}

def purchase_cable_subscription(smart_card_number, cable_provider, plan_code, customer_reference):
    """Purchase cable TV subscription"""
    try:
        url = f"{DIRECTORTECHS_BASE_URL}/cablesub"
        data = {
            'smart_card_number': smart_card_number,
            'cablename': cable_provider,
            'plan_code': plan_code,
            'customer_reference': customer_reference
        }
        print(f"Purchasing subscription: {url} with data: {data}")
        response = requests.post(url, headers=HEADERS, json=data, timeout=30, verify=False)
        print(f"Purchase response status: {response.status_code}")
        response.raise_for_status()
        result = response.json()
        print(f"Purchase result: {result}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"Purchase API Error: {str(e)}")
        return {'error': f'Network error: {str(e)}', 'success': False}
    except json.JSONDecodeError as e:
        print(f"Purchase JSON Error: {str(e)}")
        return {'error': f'Invalid response format: {str(e)}', 'success': False}
