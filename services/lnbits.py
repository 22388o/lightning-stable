from configs import LNBITS_WALLET_ADMIN_KEY, LNBITS_WALLET_INVOICE_KEY, LNBITS_HOST, LNBITS_WEBHOOK_URL
from lnbits import Lnbits

import logging
import sys

lnbits = Lnbits(admin_key=LNBITS_WALLET_ADMIN_KEY, invoice_key=LNBITS_WALLET_INVOICE_KEY, url=LNBITS_HOST)
try:
    if (lnbits.get_wallet().get("detail")):
        raise Exception("Wallet does not exist.")
except:
    logging.critical("Unable to connect with Lnbits.")
    logging.critical("Exit")
    sys.exit(0)

def pay_invoice(payment_request: str) -> dict:
    """Pay lightning invoice."""
    pay_invoice = lnbits.pay_invoice(payment_request)
    if not (pay_invoice.get("payment_hash")):
        return { "message": "Unable to pay invoice." }

    payment_hash = pay_invoice["payment_hash"]
    payments = lnbits.list_payments(limit=5)
    
    payment = filter(lambda data: (data["payment_hash"] == payment_hash), payments)
    payment = list(payment)[0]

    checking_id = payment["checking_id"]
    preimage = payments["preimage"]
    fee_sat = round(float(payment["fee"]) / 1000)
    
    amount = int(str(payment["amount"]).replace("-", ""))
    amount = round(amount / 1000)
    return { "id": checking_id, "preimage": preimage, "amount": amount, "payment_hash": payment_hash, "fee_sat": fee_sat }

def create_invoice(amount: int, memo="", expiry=86400) -> dict:
    """Create a new lightning invoice containing metadata that will be used in 
    later contracts for debt settlement.
    """

    invoice = lnbits.create_invoice(amount, memo=memo, webhook=LNBITS_WEBHOOK_URL)
    if not invoice.get("payment_hash"):
        return {"message": invoice}
    
    # Get the hash payment.
    payment_hash = invoice["payment_hash"]

    # Get payment request.
    payment_request = invoice["payment_request"]
    return {"payment_hash": payment_hash, "payment_request": payment_request, "expiry": expiry}