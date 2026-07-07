import frappe
from paynow import Paynow
from frappe import _
import uuid
from frappe.utils import now
from paynow_gateway.paynow_gateway.zoho_client import (
	extract_zoho_invoice_fields,
	get_request_data,
	record_zoho_invoice_payment,
)

@frappe.whitelist()
def process_paynow_payment(invoice, phone, amount):
    print(f"\n{'='*70}")
    print(f"DEBUG: PAYNOW START")
    print(f"DEBUG: Invoice: {invoice}")
    print(f"DEBUG: Phone: {phone}")
    print(f"DEBUG: Amount: {amount}")

    txn_id = str(uuid.uuid4())
    inv_doc = frappe.get_doc("Sales Invoice", invoice)
    settings = frappe.get_single("Paynow Settings")
    print(f"DEBUG: Doc Currency: {inv_doc.currency}")
    if inv_doc.currency == "USD":
        integration_id = settings.usd_integration_id
        integration_key = settings.usd_integration_key
        integration_id = settings.zwg_integration_id
        integration_key = settings.zwg_integration_key
    elif inv_doc.currency in ["ZiG", "ZWG"]:
        integration_id = settings.zwg_integration_id
        integration_key = settings.zwg_integration_key
    else:
        print(f"DEBUG ERROR: Currency {inv_doc.currency} not handled")
        frappe.throw(_("Paynow is not configured for currency: {0}").format(inv_doc.currency))
    paynow = Paynow(
        integration_id,
        integration_key,
        settings.return_url,
        settings.result_url 
    )
    payment = paynow.create_payment(txn_id, settings.email)
    payment.add(f"Payment for Invoice {inv_doc.name}", amount)
    try:
        print("DEBUG: Sending Request to Paynow Server...")
        raw_response = paynow.send_mobile(payment, phone, 'ecocash')
        print("DEBUG RESPONSE:", raw_response)
        if raw_response.success: 
            poll_url = raw_response.poll_url
            print(f"DEBUG: Response Success. Poll URL: {poll_url}")
            inv_doc.db_set("custom_paynow_poll_url", poll_url)
            frappe.log_error(f"Paynow Prompt Sent: {inv_doc.name}", "Paynow Info Success")
            print("DEBUG: PAYNOW END SUCCESS")
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(poll_url)
            params = parse_qs(parsed.query)
            guid = params.get("guid", [None])[0]
            payment_txn = frappe.get_doc({
                    "doctype": "Paynow Transaction",
                    "transaction_id":txn_id,
                    "payment_gateway": "Paynow",
                    "sales_invoice":inv_doc.name,
                    "amount": amount,
                    "status": "Initiated",
                    "phone_number": phone,
                    "poll_url": poll_url,
                    "guid": guid
                    })

            payment_txn.insert(ignore_permissions=True)
            frappe.db.commit()

            return {
                "status": "success",
                "message": _("Payment prompt sent to {0}").format(phone),
                "poll_url": poll_url
            }
        else:
            print("\nPAYNOW FAILED DEBUG START")

            print("SUCCESS:", raw_response.success)
            print("STATUS:", raw_response.status)

            print("RAW DATA:", raw_response.data)

            try:
                print("ERROR FIELD:", raw_response.data.get("error"))
            except Exception:
                pass

            frappe.log_error(
                title="PAYNOW REAL FAILURE",
                message=str(raw_response.data)
            )

            frappe.throw(_("Paynow failed: {0}").format(raw_response.data))

    except Exception as e:
        print(f"DEBUG: Critical Exception: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Paynow Integration Error")
        frappe.throw(_("An error occurred while connecting to Paynow. Please check logs."))

@frappe.whitelist(allow_guest=True)
def paynow_webhook():
    frappe.set_user("Administrator")

    print("\n🔥 WEBHOOK RECEIVED")

    data = get_request_data()

    print("FINAL DATA:", data)

    process_paynow_webhook(data)

    return "ok"

def process_paynow_webhook(data):
    reference = data.get("reference")
    paynow_reference = data.get("paynowreference")
    status = data.get("status")
    poll_url = data.get("pollurl")

    print("\n===== PROCESSING WEBHOOK =====")
    print("Reference:", reference)
    print("Paynow Ref:", paynow_reference)
    print("Status:", status)

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

    txn = frappe.get_doc("Paynow Transaction", txn_name)

    if txn.status == "Completed":
        print("Already processed, skipping")
        return

    txn.status = status or txn.status
    txn.paynow_reference = paynow_reference or txn.paynow_reference
    txn.poll_url = poll_url or txn.poll_url
    incoming_invoice_number, incoming_invoice_id = extract_zoho_invoice_fields(data)
    if incoming_invoice_number or not txn.zoho_invoice_number:
        txn.zoho_invoice_number = incoming_invoice_number
    if incoming_invoice_id or not txn.zoho_invoice_id:
        txn.zoho_invoice_id = incoming_invoice_id

    txn.log = (txn.log or "") + f"""
        [{frappe.utils.now()}] WEBHOOK UPDATE:
        Status: {status}
        Paynow Ref: {paynow_reference}
        Poll URL: {poll_url}
        RAW: {data}
        """
    txn.save(ignore_permissions=True)
    frappe.db.commit()
    # 🔥 trigger payment entry logic
    handle_paid_transaction(txn, data)
    print("✅ TRANSACTION UPDATED")

def handle_paid_transaction(txn, data):
    if txn.status == "Completed":
        print("⚠️ Already processed, skipping")
        return

    if (data.get("status") or "").lower() != "paid":
        return

    print("\n💰 PAYMENT CONFIRMED - CREATING PAYMENT ENTRY")

    if txn.zoho_invoice_number or txn.zoho_invoice_id:
        try:
            record_zoho_invoice_payment(txn, data)
        except Exception:
            txn.db_set("zoho_sync_status", "Failed")
            txn.db_set("zoho_error", frappe.get_traceback())
            frappe.log_error(frappe.get_traceback(), "Zoho Paynow - Payment Sync Failed")
            raise
    elif not txn.sales_invoice:
        txn.db_set("zoho_sync_status", "Failed")
        txn.db_set("zoho_error", "Missing Zoho invoice_number or invoice_id on paid Paynow webhook")
        frappe.log_error(str(data), "Zoho Paynow - Missing Invoice Reference")
        return

    if not txn.sales_invoice:
        txn.status = "Paid"
        txn.save(ignore_permissions=True)
        frappe.db.commit()
        return

    inv = frappe.get_doc("Sales Invoice", txn.sales_invoice)
    settings = frappe.get_single("Paynow Settings")
    if inv.currency == "USD":
        paid_to_account = settings.usd_paid_to_account
    else:
        paid_to_account = settings.zwg_payment_accout

    # 🔥 Create Payment Entry
    payment_entry = frappe.get_doc({
        "doctype": "Payment Entry",
        "payment_type": "Receive",
        "party_type": "Customer",
        "party": inv.customer,
        "paid_amount": txn.amount,
        "received_amount": txn.amount,
        "mode_of_payment": "Ecocash",  # adjust if needed
        "reference_no": txn.paynow_reference or txn.transaction_id,
        "reference_date": now(),
        "paid_to":paid_to_account,  # adjust your account
    })

    payment_entry.append("references", {
        "reference_doctype": "Sales Invoice",
        "reference_name": inv.name,
        "allocated_amount": txn.amount
    })

    payment_entry.insert(ignore_permissions=True)
    payment_entry.submit()

    print("✅ Payment Entry Created:", payment_entry.name)

    # 🔥 update invoice
    inv.db_set("status", "Paid")

    # 🔥 update transaction
    txn.status = "Completed"
    txn.payment_entry = payment_entry.name
    txn.save(ignore_permissions=True)

    frappe.db.commit()
