import requests
from django.conf import settings
import urllib3
import uuid

# Disable SSL warnings (for development/testing)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://smeplug.ng/api/v1"


class SMEPlugAPIError(Exception):
    """Raised when the SME Plug API returns an error."""
    pass


def _headers():
    """Build request headers with Bearer token auth."""
    api_key ="900fd38e4873cdf10f501db5ca4bc95c0984f559bf89706ce52513123a6cf6a4"
    return {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }


def _post(endpoint, payload):
    """POST to SME Plug API."""
    url = f"{BASE_URL}{endpoint}"
    try:
        response = requests.post(url, json=payload, headers=_headers(), timeout=60, verify=False)
        response.raise_for_status()
        return response.json()
    except requests.ConnectionError as e:
        raise SMEPlugAPIError(f"Connection failed. Check internet connection and URL: {url}")
    except requests.Timeout as e:
        raise SMEPlugAPIError(f"Request timed out after 60 seconds.")
    except requests.RequestException as e:
        raise SMEPlugAPIError(f"API request failed: {e}")


def _get(endpoint):
    """GET from SME Plug API."""
    url = f"{BASE_URL}{endpoint}"
    try:
        response = requests.get(url, headers=_headers(), timeout=30, verify=False)
        response.raise_for_status()
        return response.json()
    except requests.ConnectionError as e:
        raise SMEPlugAPIError(f"Connection failed. Check internet connection and URL: {url}")
    except requests.Timeout as e:
        raise SMEPlugAPIError(f"Request timed out after 30 seconds.")
    except requests.RequestException as e:
        raise SMEPlugAPIError(f"API request failed: {e}")





def get_data_plans():
    """Return data plans grouped by network ID."""
    return _get("/data/plans")


def purchase_data(network_id, plan_id, phone, customer_reference=None):
    """
    Purchase data plan.
    Args:
        network_id (int): 1=MTN, 2=Airtel, 3=9Mobile, 4=Glo
        plan_id (str): Plan ID from get_data_plans()
        phone (str): Recipient phone number
        customer_reference (str, optional): Your own reference
    Returns:
        dict: API response with reference, status, msg
    """
    payload = {
        "network_id": network_id,
        "plan_id": plan_id,
        "phone": phone,
    }
    if customer_reference:
        payload["customer_reference"] = customer_reference
    return _post("/data/purchase", payload)


def purchase_airtime(network_id, phone, amount, customer_reference=None):
    """
    Purchase airtime.
    Args:
        network_id (int): 1=MTN, 2=Airtel, 3=9Mobile, 4=Glo
        phone (str): Recipient phone number
        amount (float): Airtime amount in NGN
        customer_reference (str, optional): Your own reference
    Returns:
        dict: API response with reference, status, msg
    """
    payload = {
        "network_id": network_id,
        "phone": phone,
        "amount": amount,
    }
    if customer_reference:
        payload["customer_reference"] = customer_reference
    return _post("/airtime/purchase", payload)


def get_transaction(reference):
    """
    Query transaction status by reference.
    reference can be SME Plug reference or your customer_reference.
    """
    return _get(f"/transactions/{reference}")


def generate_reference():
    """Generate a unique customer reference."""
    return str(uuid.uuid4()).replace('-', '')[:20]
