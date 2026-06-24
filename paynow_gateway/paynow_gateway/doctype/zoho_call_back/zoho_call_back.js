// Copyright (c) 2026, Munyaradzi Chirove and contributors
// For license information, please see license.txt

frappe.ui.form.on("Zoho Call Back", {
	refresh(frm) {
		frm.add_custom_button(__("Refresh Access Token"), () => {
			frappe.call({
				method: "paynow_gateway.paynow_gateway.zoho_client.refresh_zoho_access_token",
				callback() {
					frm.reload_doc();
				},
			});
		});
	},
});
