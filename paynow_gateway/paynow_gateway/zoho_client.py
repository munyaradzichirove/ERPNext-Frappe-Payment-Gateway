import json
from urllib.parse import parse_qs

import frappe
import requests
from frappe import _
from frappe.utils import add_to_date, flt, get_datetime, now, now_datetime, today


def _settings():
	settings = frappe.get_single("Zoho Call Back")
	if not settings.enabled:
		frappe.throw(_("Zoho Call Back is disabled"))
	return settings


def _get_password(settings, fieldname):
	value = settings.get_password(fieldname)
	if value:
		return value
	return settings.get(fieldname)


def _base_url(settings, fieldname, default):
	return (settings.get(fieldname) or default).rstrip("/")


def _coerce_payload(value):
	if isinstance(value, str):
		value = value.strip()
		if not value:
			return {}
		try:
			return json.loads(value)
		except ValueError:
			return {}
	return value if isinstance(value, dict) else {}


def get_request_data():
	data = dict(frappe.local.form_dict or {})
	raw_body = frappe.request.get_data(as_text=True) if frappe.request else ""

	if raw_body:
		body_data = _coerce_payload(raw_body)
		if body_data:
			data.update(body_data)
		elif not data:
			parsed = parse_qs(raw_body)
			data = {key: value[0] for key, value in parsed.items()}

	for fieldname in ("data", "payload", "invoice"):
		nested = _coerce_payload(data.get(fieldname))
		if nested:
			data.update(nested)

	return data


def extract_zoho_invoice_fields(data):
	data = data or {}
	invoice_data = data.get("invoice") if isinstance(data.get("invoice"), dict) else {}

	invoice_number = (
		data.get("invoice_number")
		or data.get("invoice_no")
		or data.get("zoho_invoice_number")
		or invoice_data.get("invoice_number")
		or invoice_data.get("invoice_no")
	)
	invoice_id = (
		data.get("zoho_invoice_id")
		or data.get("invoice_id")
		or invoice_data.get("invoice_id")
		or invoice_data.get("id")
	)

	invoice_value = data.get("invoice")
	if isinstance(invoice_value, str):
		if invoice_value.upper().startswith("INV-"):
			invoice_number = invoice_number or invoice_value
		elif invoice_value.isdigit():
			invoice_id = invoice_id or invoice_value

	if invoice_number and str(invoice_number).isdigit() and not invoice_id:
		invoice_id = invoice_number
		invoice_number = None

	if invoice_id and str(invoice_id).upper().startswith("INV-") and not invoice_number:
		invoice_number = invoice_id
		invoice_id = None

	return invoice_number, invoice_id


def _token_is_expired(settings):
	expires_at = settings.get("token_expires_at")
	if not expires_at:
		return True
	return get_datetime(expires_at) <= add_to_date(now_datetime(), minutes=5)


@frappe.whitelist()
def refresh_zoho_access_token():
	settings = frappe.get_single("Zoho Call Back")
	refresh_token = _get_password(settings, "refresh_token")
	client_id = settings.get("client_id")
	client_secret = _get_password(settings, "client_secret")

	if not refresh_token or not client_id or not client_secret:
		frappe.throw(_("Zoho client id, client secret and refresh token are required"))

	url = f"{_base_url(settings, 'accounts_domain', 'https://accounts.zoho.com')}/oauth/v2/token"
	response = requests.post(
		url,
		data={
			"refresh_token": refresh_token,
			"client_id": client_id,
			"client_secret": client_secret,
			"grant_type": "refresh_token",
		},
		timeout=30,
	)

	try:
		payload = response.json()
	except ValueError:
		payload = {"raw_response": response.text}

	if response.status_code >= 400 or not payload.get("access_token"):
		settings.db_set("last_error", json.dumps(payload))
		frappe.throw(_("Could not refresh Zoho access token: {0}").format(payload))

	expires_in = int(payload.get("expires_in") or 3600)
	settings.db_set("access_token", payload.get("access_token"))
	settings.db_set("token_expires_at", add_to_date(now_datetime(), seconds=expires_in - 60))
	settings.db_set("last_refresh", now())
	settings.db_set("last_error", None)
	frappe.db.commit()

	return {"status": "success"}


def _headers(settings, force_refresh=False):
	if force_refresh or _token_is_expired(settings) or not _get_password(settings, "access_token"):
		refresh_zoho_access_token()
		settings.reload()

	access_token = _get_password(settings, "access_token")
	if not access_token:
		frappe.throw(_("Zoho access token is missing"))

	return {
		"Authorization": f"Zoho-oauthtoken {access_token}",
		"X-com-zoho-subscriptions-organizationid": settings.instance_id,
		"Content-Type": "application/json",
	}


def _request_with_refresh(method, url, settings, refresh_on_failure=False, **kwargs):
	response = requests.request(method, url, headers=_headers(settings), timeout=30, **kwargs)
	if response.status_code in (401, 403) or (refresh_on_failure and response.status_code >= 400):
		response = requests.request(method, url, headers=_headers(settings, force_refresh=True), timeout=30, **kwargs)
	return response


def _parse_response(response):
	try:
		payload = response.json()
	except ValueError:
		payload = {"raw_response": response.text}

	if response.status_code >= 400:
		frappe.throw(_("Zoho API error: {0}").format(payload))

	return payload


def _find_invoice(settings, invoice_number):
	url = f"{_base_url(settings, 'api_domain', 'https://www.zohoapis.com')}/billing/v1/invoices"

	if str(invoice_number).isdigit():
		response = _request_with_refresh("GET", f"{url}/{invoice_number}", settings)
		payload = _parse_response(response)
		return payload.get("invoice") or payload

	response = _request_with_refresh("GET", url, settings, params={"invoice_number": invoice_number})
	payload = _parse_response(response)
	invoices = payload.get("invoices") or []

	if not invoices:
		frappe.throw(_("Could not find Zoho invoice {0}").format(invoice_number))

	return invoices[0]


def record_zoho_invoice_payment(txn, data=None):
	if not txn.get("zoho_invoice_number") and not txn.get("zoho_invoice_id"):
		invoice_number, invoice_id = extract_zoho_invoice_fields(data or {})
		if invoice_number:
			txn.db_set("zoho_invoice_number", invoice_number)
		if invoice_id:
			txn.db_set("zoho_invoice_id", invoice_id)

	invoice_lookup = txn.get("zoho_invoice_number") or txn.get("zoho_invoice_id")
	if not invoice_lookup:
		return

	settings = _settings()
	invoice = _find_invoice(settings, invoice_lookup)
	real_invoice_id = invoice.get("invoice_id")
	real_customer_id = invoice.get("customer_id")
	real_invoice_number = invoice.get("invoice_number")

	if not real_invoice_id or not real_customer_id:
		frappe.throw(_("Zoho invoice lookup did not return invoice/customer ids"))

	amount = flt(txn.amount)
	reference_number = txn.paynow_reference or txn.transaction_id
	payment_data = {
		"customer_id": real_customer_id,
		"payment_mode": settings.payment_mode or "cash",
		"amount": amount,
		"date": today(),
		"reference_number": reference_number,
		"description": settings.payment_description or f"Applied payment to {txn.zoho_invoice_number} via Paynow",
		"invoices": [
			{
				"invoice_id": real_invoice_id,
				"amount_applied": amount,
			}
		],
	}

	url = f"{_base_url(settings, 'api_domain', 'https://www.zohoapis.com')}/billing/v1/payments"
	response = _request_with_refresh("POST", url, settings, refresh_on_failure=True, data=json.dumps(payment_data))
	payload = _parse_response(response)

	txn.db_set("zoho_invoice_id", real_invoice_id)
	if real_invoice_number and real_invoice_number != txn.zoho_invoice_number:
		txn.db_set("zoho_invoice_number", real_invoice_number)
	txn.db_set("zoho_customer_id", real_customer_id)
	txn.db_set("zoho_payment_id", (payload.get("payment") or {}).get("payment_id"))
	txn.db_set("zoho_sync_status", "Completed")
	txn.db_set("zoho_last_sync", now())

	settings.db_set("last_response", json.dumps(payload, indent=2))
	settings.db_set("last_error", None)
	frappe.db.commit()

	return payload


@frappe.whitelist()
def retry_zoho_payment(transaction_name):
	txn = frappe.get_doc("Paynow Transaction", transaction_name)
	payload = record_zoho_invoice_payment(txn)
	txn.status = "Completed"
	txn.save(ignore_permissions=True)
	frappe.db.commit()
	return payload
