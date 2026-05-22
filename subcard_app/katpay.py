import requests
import uuid
from django.conf import settings

BASE_URL = getattr(settings, 'KATPAY_BASE_URL', 'https://api.katpay.co/v1')

class KatpayAPIError(Exception):
    """Raised when the Katpay API returns an error."""
    pass

def _headers():
    """Build request headers with Bearer token auth."""
    secret_key = getattr(settings, 'KATPAY_SECRET_KEY', '')
    public_key = getattr(settings, 'KATPAY_PUBLIC_KEY', '')
    return {
        'Authorization': f'Bearer {secret_key}',
        'Content-Type': 'application/json',
        'api-key': public_key
    }

def create_static_virtual_account(email, name, phone):
    """
    Create a static virtual account for a customer.
    """
    merchant_id = getattr(settings, 'KATPAY_MERCHANT_ID', '')
    
    # Format phone to +234 if it starts with 0
    if phone.startswith('0') and len(phone) == 11:
        phone = '+234' + phone[1:]
    elif not phone.startswith('+'):
        phone = '+234' + phone # Assume Nigeria if no prefix
        
    payload = {
        "email": email,
        "name": name,
        "phoneNumber": phone,
        "bankCode": ["PALMPAY"],
        "merchantID": merchant_id
    }
    
    url = f"{BASE_URL.rstrip('/')}/virtual-accounts"
    try:
        print(f"Katpay Static VA Request: {payload}")
        response = requests.post(url, json=payload, headers=_headers(), timeout=60)
        print(f"Katpay Static VA Response [{response.status_code}]: {response.text}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        eb = e.response.text if hasattr(e, 'response') and e.response is not None else str(e)
        raise KatpayAPIError(f"Virtual account creation failed: {eb}")

def create_dynamic_virtual_account(amount, customer_name, customer_email, customer_phone, reference, description):
    """
    Create a dynamic virtual account (transfer payment) for a customer.
    """
    payload = {
        "amount": float(amount),
        "customer_name": customer_name,
        "customer_email": customer_email,
        "customer_phone": customer_phone,
        "merchant_reference": reference,
        "description": description,
        "expires_in": 60
    }
    
    url = f"{BASE_URL.rstrip('/')}/transfer-payments"
    try:
        print(f"Katpay Dynamic VA Request: {payload}")
        response = requests.post(url, json=payload, headers=_headers(), timeout=60)
        print(f"Katpay Dynamic VA Response [{response.status_code}]: {response.text}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        eb = e.response.text if hasattr(e, 'response') and e.response is not None else str(e)
        raise KatpayAPIError(f"Dynamic account creation failed: {eb}")

def generate_reference():
    """Generate a unique transaction reference."""
    return str(uuid.uuid4()).replace('-', '')
