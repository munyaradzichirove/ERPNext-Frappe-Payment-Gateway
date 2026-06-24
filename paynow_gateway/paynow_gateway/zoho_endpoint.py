import frappe
from paynow import Paynow
from frappe import _
import uuid
from frappe.utils import now
from paynow_gateway.paynow_gateway.zoho_client import record_zoho_invoice_payment

# ============================================================
# MAIN ENDPOINT — Called by Zoho Billing custom button
# POST /api/method/your_app.paynow_zoho.zoho_trigger_payment
#
# Expected POST body from Zoho Deluge invokeurl:
# {
#     "invoice_id"   : "INV-000003",
#     "customer_name": "Mr. John Doe",
#     "amount"       : "150.00",
#     "currency"     : "USD",
#     "paynow_number": "0771234567"
# }
# ==================================================================
@frappe.whitelist(allow_guest=True)
def zoho_trigger_payment():
    print("=======================invoked===========================")
    import json
    data = dict(frappe.local.form_dict or {})
    print(data)
    frappe.set_user("Administrator")
    # --------------------------------------------------------
    # STEP 2: Log the raw received query into Frappe Error Log
    # so we can see exactly what Zoho sent
    # --------------------------------------------------------
    frappe.log_error(
        title="Zoho Paynow - Request Received",
        message=f"""
ZOHO BILLING TRIGGER RECEIVED
==============================
invoice_id   : {data.get('invoice_id')}
customer_name: {data.get('customer_name')}
amount       : {data.get('currency')} {data.get('amount')}
paynow_number: {data.get('paynow_number')}
------------------------------
RAW DATA: {data}
        """
    )

    print(f"\n{'='*70}")
    print(f"ZOHO BILLING TRIGGER RECEIVED")
    print(f"RAW DATA: {data}")

    # --------------------------------------------------------
    # STEP 3: Validate required fields
    # --------------------------------------------------------
    invoice_number = data.get("invoice_number") or data.get("invoice")
    zoho_invoice_id = data.get("invoice_id")
    invoice_id = invoice_number or zoho_invoice_id
    customer_name = data.get("customer_name")
    amount        = data.get("amount")
    currency      = data.get("currency")
    phone         = data.get("paynow_number")

    if not phone:
        frappe.log_error("Missing paynow_number in request", "Zoho Paynow - Validation Error")
        return {"status": "error", "message": "Missing paynow_number"}

    if not amount:
        frappe.log_error("Missing amount in request", "Zoho Paynow - Validation Error")
        return {"status": "error", "message": "Missing amount"}

    if not invoice_id:
        frappe.log_error("Missing invoice_id in request", "Zoho Paynow - Validation Error")
        return {"status": "error", "message": "Missing invoice_id"}

    # --------------------------------------------------------
    # STEP 4: Load settings and trigger Paynow
    # Using existing Paynow Settings doctype — no changes needed
    # --------------------------------------------------------
    try:
        txn_id   = str(uuid.uuid4())
        settings = frappe.get_single("Paynow Settings")

        print(f"Currency: {currency}")

        # Pick credentials by currency — same logic as original
        if currency == "USD":
            integration_id  = settings.zwg_integration_id
            integration_key = settings.zwg_integration_key
        elif currency in ["ZiG", "ZWG"]:
            integration_id  = settings.zwg_integration_id
            integration_key = settings.zwg_integration_key
        else:
            # Default to ZWG if currency unknown
            integration_id  = settings.zwg_integration_id
            integration_key = settings.zwg_integration_key

        # ---- Init Paynow ----
        paynow = Paynow(
            integration_id,
            integration_key,
            settings.return_url,
            settings.result_url
        )

        payment = paynow.create_payment(txn_id, settings.email)
        payment.add(f"Payment for {invoice_id} - {customer_name}", float(amount))

        print("Sending to Paynow...")
        raw_response = paynow.send_mobile(payment, phone, 'ecocash')
        print("Paynow Response:", raw_response)

        # ---- Log Paynow raw response ----
        frappe.log_error(
            title="Zoho Paynow - Paynow Response",
            message=f"""
PAYNOW RESPONSE
==============================
Success  : {raw_response.success}
Status   : {raw_response.status}
Poll URL : {getattr(raw_response, 'poll_url', 'N/A')}
Raw Data : {raw_response.data}
            """
        )

        # ---- Handle success ----
        if raw_response.success:
            poll_url = raw_response.poll_url

            # Extract GUID from poll URL
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(poll_url)
            params = parse_qs(parsed.query)
            guid   = params.get("guid", [None])[0]

            # ---- Create Paynow Transaction record ----
            # Uses your existing Paynow Transaction doctype
            payment_txn = frappe.get_doc({
                "doctype"        : "Paynow Transaction",
                "transaction_id" : txn_id,
                "payment_gateway": "Paynow",
                "amount"         : float(amount),
                "currency"       : currency,
                "status"         : "Initiated",
                "phone_number"   : phone,
                "poll_url"       : poll_url,
                "guid"           : guid,
                "zoho_invoice_number": invoice_id,
                "zoho_invoice_id": zoho_invoice_id if zoho_invoice_id != invoice_id else None,
                "zoho_sync_status": "Pending",
            })
            payment_txn.insert(ignore_permissions=True)
            frappe.db.commit()

            print(f"Transaction created: {payment_txn.name}")

            return {
                "status"        : "success",
                "message"       : f"Payment prompt sent to {phone}",
                "poll_url"      : poll_url,
                "transaction_id": txn_id
            }

        # ---- Handle Paynow failure ----
        else:
            frappe.log_error(
                title="Zoho Paynow - Paynow Failed",
                message=str(raw_response.data)
            )
            return {
                "status" : "error",
                "message": f"Paynow failed: {raw_response.data}"
            }

    except Exception as e:
        print(f"Critical Exception: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Zoho Paynow - Critical Error")
        return {
            "status" : "error",
            "message": f"An error occurred: {str(e)}"
        }


# ============================================================
# WEBHOOK — Called by Paynow when payment status changes
# Unchanged from your original — just keeping it here
# ============================================================
@frappe.whitelist(allow_guest=True)
def paynow_webhook():
    frappe.set_user("Administrator")

    print("\n WEBHOOK RECEIVED")

    form_data = frappe.local.form_dict or {}
    raw_body  = frappe.request.get_data(as_text=True)
    data      = dict(form_data)

    if not data and raw_body:
        from urllib.parse import parse_qs
        parsed = parse_qs(raw_body)
        data   = {k: v[0] for k, v in parsed.items()}

    print("FINAL DATA:", data)
    process_paynow_webhook(data)

    return "ok"


def process_paynow_webhook(data):
    reference        = data.get("reference")
    paynow_reference = data.get("paynowreference")
    status           = data.get("status")
    poll_url         = data.get("pollurl")

    print(f"Reference : {reference}")
    print(f"Paynow Ref: {paynow_reference}")
    print(f"Status    : {status}")

    if not reference:
        print("Missing reference")
        return

    txn_name = frappe.get_value(
        "Paynow Transaction",
        {"transaction_id": reference},
        "name"
    )

    if not txn_name:
        frappe.log_error(str(data), "Paynow - Transaction Not Found")
        return

    txn                  = frappe.get_doc("Paynow Transaction", txn_name)

    if txn.status == "Completed":
        print("Already processed, skipping")
        return

    txn.status           = status or txn.status
    txn.paynow_reference = paynow_reference or txn.paynow_reference
    txn.poll_url         = poll_url or txn.poll_url
    incoming_invoice_number = data.get("invoice_number") or data.get("invoice")
    if incoming_invoice_number or not txn.zoho_invoice_number:
        txn.zoho_invoice_number = incoming_invoice_number or data.get("invoice_id")
    txn.log              = (txn.log or "") + f"""
[{now()}] WEBHOOK UPDATE:
Status    : {status}
Paynow Ref: {paynow_reference}
Poll URL  : {poll_url}
RAW       : {data}
"""
    txn.save(ignore_permissions=True)
    frappe.db.commit()

    handle_paid_transaction(txn, data)
    print("TRANSACTION UPDATED")


def handle_paid_transaction(txn, data):
    if txn.status == "Completed":
        print("Already processed, skipping")
        return

    if (data.get("status") or "").lower() != "paid":
        return

    print("PAYMENT CONFIRMED")

    if txn.zoho_invoice_number:
        try:
            record_zoho_invoice_payment(txn, data)
        except Exception:
            txn.db_set("zoho_sync_status", "Failed")
            txn.db_set("zoho_error", frappe.get_traceback())
            frappe.log_error(frappe.get_traceback(), "Zoho Paynow - Payment Sync Failed")
            raise

    if txn.sales_invoice:
        print("CREATING ERPNext PAYMENT ENTRY")

        settings        = frappe.get_single("Paynow Settings")
        paid_to_account = settings.zwg_payment_accout

        inv = frappe.get_doc("Sales Invoice", txn.sales_invoice)
        payment_entry = frappe.get_doc({
            "doctype"          : "Payment Entry",
            "payment_type"     : "Receive",
            "party_type"       : "Customer",
            "party"            : inv.customer,
            "paid_amount"      : txn.amount,
            "received_amount"  : txn.amount,
            "mode_of_payment"  : "Ecocash",
            "reference_no"     : txn.paynow_reference or txn.transaction_id,
            "reference_date"   : now(),
            "paid_to"          : paid_to_account,
        })

        payment_entry.append("references", {
            "reference_doctype": "Sales Invoice",
            "reference_name": inv.name,
            "allocated_amount": txn.amount
        })

        payment_entry.insert(ignore_permissions=True)
        payment_entry.submit()

        print("Payment Entry Created:", payment_entry.name)
        txn.payment_entry = payment_entry.name

    txn.status        = "Completed"
    txn.save(ignore_permissions=True)

    frappe.db.commit()
