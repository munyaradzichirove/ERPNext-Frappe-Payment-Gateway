# Copyright (c) 2026, Munyaradzi Chirove and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestZohoCallBack(FrappeTestCase):
	def test_singleton_loads(self):
		frappe.get_single("Zoho Call Back")
