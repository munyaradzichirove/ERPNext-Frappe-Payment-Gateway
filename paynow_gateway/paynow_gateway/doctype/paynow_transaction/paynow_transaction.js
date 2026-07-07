// Copyright (c) 2026, Munyaradzi Chirove and contributors
// For license information, please see license.txt

frappe.ui.form.on("Paynow Transaction", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Sync Now"), () => {
			frappe.call({
				method: "paynow_gateway.paynow_gateway.zoho_client.retry_zoho_payment",
				args: {
					transaction_name: frm.doc.name,
				},
				freeze: true,
				freeze_message: __("Syncing with Zoho..."),
				callback() {
					frappe.show_alert({
						message: __("Zoho sync completed"),
						indicator: "green",
					});
					frm.reload_doc();
				},
			});
		});
	},
});
