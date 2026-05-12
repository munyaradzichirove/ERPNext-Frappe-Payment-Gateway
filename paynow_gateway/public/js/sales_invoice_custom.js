frappe.ui.form.on('Sales Invoice', {
    refresh: function(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.outstanding_amount > 0) {
            frm.add_custom_button(__('Paynow'), () => render_paynow_dialog(frm), __("Actions"));
        }
    }
});

function render_paynow_dialog(frm) {
    let d = new frappe.ui.Dialog({
        title: __('Paynow Mobile Payment'),
        fields: [
            {
                label: __('Mobile Number'),
                fieldname: 'mobile_number',
                fieldtype: 'Data',
                placeholder: 'e.g. 0771234567',
                reqd: 1
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Amount'),
                fieldname: 'amount',
                fieldtype: 'Currency',
                options: 'currency',
                default: frm.doc.outstanding_amount,
                reqd: 1
            },
            { fieldtype: 'Section Break' },
            {
                label: __('Currency'),
                fieldname: 'currency',
                fieldtype: 'Read Only',
                default: frm.doc.currency
            },
            {
                fieldtype: 'HTML',
                fieldname: 'helper_text',
                options: `<div class="text-muted small">
                            ${__('Enter EcoCash/OneMoney number. We will format it automatically.')}
                          </div>`
            }
        ],
        primary_action_label: __('Confirm & Pay'),
        primary_action(values) {
            const clean_number = validate_and_format_number(values.mobile_number);
            
            if (!clean_number) {
                return; // Stop if validation failed
            }

            // Secondary Confirmation
            frappe.confirm(
                __('Send payment prompt of <b>{0} {1}</b> to <b>{2}</b>?', [values.currency, values.amount, clean_number]),
                () => {
                    d.hide();
                    execute_paynow_call(frm, clean_number, values.amount);
                }
            );
        }
    });

    // Style the button green
    d.get_primary_btn().removeClass('btn-primary').addClass('btn-success');
    d.show();
}

// Logic to strip +263 and ensure 10 digits starting with 0
function validate_and_format_number(num) {
    if (!num) return null;

    // Remove all non-numeric characters (spaces, +, dashes)
    let cleaned = num.replace(/\D/g, '');

    // Handle 263 prefix
    if (cleaned.startsWith('263')) {
        cleaned = '0' + cleaned.substring(3);
    } 
    // If it starts with 7 (missing the 0)
    else if (cleaned.length === 9 && cleaned.startsWith('7')) {
        cleaned = '0' + cleaned;
    }

    // Final Validation
    if (cleaned.length !== 10 || !cleaned.startsWith('07')) {
        frappe.msgprint({
            title: __('Invalid Number'),
            indicator: 'red',
            message: __('Please enter a valid 10-digit Zimbabwean mobile number (e.g., 0771234567).')
        });
        return null;
    }

    return cleaned;
}

function execute_paynow_call(frm, phone, amount) {
    frappe.show_alert({ message: __('Initiating Paynow...'), indicator: 'blue' });

    frappe.call({
        method: "your_app.api.process_paynow_payment",  
        args: {
            invoice: frm.doc.name,
            phone: phone,
            amount: amount
        },
        freeze: true,
        freeze_message: __("Waiting for Paynow PIN prompt..."),
        callback: function(r) {
            if (r.message && r.message.status === 'success') {
                frappe.msgprint({
                    title: __('Success'),
                    indicator: 'green',
                    message: __('Payment prompt sent! Please check your phone.')
                });
            }
        }
    });
}