import frappe
from paynow import Paynow
from frappe import _


@frappe.whitelist()
def process_paynow_payment(invoice, phone, amount):
    print(f"\n{'='*70}")
    print(f"DEBUG: PAYNOW START")
    print(f"DEBUG: Invoice: {invoice}")
    print(f"DEBUG: Phone: {phone}")
    print(f"DEBUG: Amount: {amount}")
    
    inv_doc = frappe.get_doc("Sales Invoice", invoice)
    settings = frappe.get_single("Paynow Settings")
    
    print(f"DEBUG: Doc Currency: {inv_doc.currency}")

    if inv_doc.currency == "USD":
        integration_id = settings.usd_integration_id
        integration_key = settings.usd_integration_key
    elif inv_doc.currency in ["ZiG", "ZWG"]:
        integration_id = settings.zwg_integration_id
        integration_key = settings.zwg_integration_key
    else:
        print(f"DEBUG ERROR: Currency {inv_doc.currency} not handled")
        frappe.throw(_("Paynow is not configured for currency: {0}").format(inv_doc.currency))
    paynow = Paynow(
        integration_id,
        integration_key,
        settings.return_url or "https://example.com/return",
        settings.result_url or "https://example.com/result"
    )

    payment = paynow.create_payment(f"Inv-{inv_doc.name}","chirovemunyaradzi@gmail.com")
    payment.add(f"Payment for Invoice {inv_doc.name}", amount)
    try:

        print("DEBUG: Sending Request to Paynow Server...")
        raw_response = paynow.send_mobile(payment, phone, 'ecocash')
        print("DEBUG RESPONSE:", raw_response)

        if raw_response.success: 
            poll_url = raw_response.poll_url
            print(f"DEBUG: Response Success. Poll URL: {poll_url}")
            inv_doc.db_set("custom_paynow_poll_url", poll_url)
            frappe.log_error(f"Paynow Prompt Sent: {inv_doc.name}", "Paynow Info {Success}")
            print("DEBUG: PAYNOW END SUCCESS")
            return {
                "status": "success",
                "message": _("Payment prompt sent to {0}").format(phone),
                "poll_url": poll_url
            }
        else:
            print(f"error {raw_response.error}")
 
            print("❌ PAYNOW FAILED DEBUG START")
            print("TYPE:", type(raw_response))
            print("REPR:", repr(raw_response))
            print("DIR:", dir(raw_response))

            # try extract everything possible
            print("SUCCESS:", getattr(raw_response, "success", None))
            print("ERROR:", getattr(raw_response, "error", None))
            print("MESSAGE:", getattr(raw_response, "message", None))
            print("STATUS:", getattr(raw_response, "status", None))

            frappe.log_error(str(raw_response), "PAYNOW RAW FAILURE")

            frappe.throw(_("Paynow failed. Check Error Log in Frappe."))

    except Exception as e:
        print(f"DEBUG: Critical Exception: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Paynow Integration Error")
        frappe.throw(_("An error occurred while connecting to Paynow. Please check logs."))







def safe_paynow_response(response):
    if isinstance(response, str):
        return {
            "success": False,
            "error": response
        }

    if not hasattr(response, "success"):
        return {
            "success": False,
            "error": str(response)
        }

    return {
        "success": response.success,
        "poll_url": getattr(response, "poll_url", None),
        "error": getattr(response, "error", None)
    }