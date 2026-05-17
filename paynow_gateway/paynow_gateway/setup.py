# paynow_gateway/setup.py

import frappe

def after_install():
    create_ecocash_mode_of_payment()

def create_ecocash_mode_of_payment():
    if not frappe.db.exists("Mode of Payment", "Ecocash"):
        doc = frappe.get_doc({
            "doctype": "Mode of Payment",
            "mode_of_payment": "Ecocash",
            "enabled": 1
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print("✅ Ecocash Mode of Payment created")