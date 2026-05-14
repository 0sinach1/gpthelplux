# escrow/paystack.py
import os
import requests
from django.conf import settings

class Paystack:
    """
    A specific wrapper for Paystack API to handle Escrow transfers and verification.
    """
    
    # Base URL for all Paystack endpoints
    PAYSTACK_BASE_URL = "https://api.paystack.co"

    def __init__(self):
        # We grab the secret key from settings (Security First!)
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    def verify_account_number(self, account_number, bank_code):
        """
        Step 1 of Payout: Confirm the account name matches the Vendor/User.
        """
        url = f"{self.PAYSTACK_BASE_URL}/bank/resolve"
        params = {"account_number": account_number, "bank_code": bank_code}
        
        response = requests.get(url, headers=self.headers, params=params)
        
        if response.status_code == 200:
            return response.json()['data'] # Returns {'account_name': '...'}
        return None

    def create_transfer_recipient(self, name, account_number, bank_code):
        """
        Step 2 of Payout: Register the payee (Vendor or Customer) on Paystack.
        We need the 'recipient_code' from this to send money.
        """
        url = f"{self.PAYSTACK_BASE_URL}/transferrecipient"
        data = {
            "type": "nuban",
            "name": name,
            "account_number": account_number,
            "bank_code": bank_code,
            "currency": "NGN"
        }
        
        response = requests.post(url, headers=self.headers, json=data)
        
        if response.status_code == 201 or response.status_code == 200:
            # Returns 'RCP_gx2wn530mwy007'
            return response.json()['data']['recipient_code']
        
        # Log error in real production
        print(f"Paystack Error: {response.text}") 
        return None

    def initiate_transfer(self, amount_kobo, recipient_code, reason, reference):
        """
        Step 3 of Payout: Actually send the money.
        Requires a strict 'reference' to prevent Paystack from double-charging.
        """
        url = f"{self.PAYSTACK_BASE_URL}/transfer"
        data = {
            "source": "balance", 
            "amount": amount_kobo,
            "recipient": recipient_code,
            "reason": reason,
            "reference": reference  # CRITICAL: Idempotency enforcement
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=data, timeout=15)
            res_data = response.json()
            
            # Paystack Top-Level Status
            if response.status_code in [200, 201] and res_data.get('status') is True:
                return {
                    "api_state": "SUCCESS", 
                    "data": res_data.get('data', {})
                }
            
            # Synchronous failure (e.g., insufficient platform balance)
            return {
                "api_state": "FAILED", 
                "message": res_data.get('message', 'Transfer rejected by gateway.')
            }

        except requests.exceptions.Timeout:
            # Request might have reached Paystack, but we didn't get the answer.
            return {"api_state": "UNKNOWN", "message": "Bank network timeout."}
            
        except (requests.exceptions.RequestException, ValueError): 
            # Catches DNS failures, unreachable servers, OR HTML 502 Error pages
            return {"api_state": "UNKNOWN", "message": "Payment gateway unreachable or returned invalid data."}

    def verify_payment(self, reference):
        """
        For Deposits: Verify a customer actually paid money into the escrow wallet.
        """
        url = f"{self.PAYSTACK_BASE_URL}/transaction/verify/{reference}"
        
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 200:
            data = response.json()['data']
            if data['status'] == 'success':
                return True, data['amount'] # Amount is in KOBO
        
        return False, 0