import frappe
from frappe import _
from frappe.utils import flt, cint
import json
from erpnext.controllers.accounts_controller import set_sales_order_defaults, set_purchase_order_defaults, validate_and_delete_children


@frappe.whitelist()
def update_child_qty_rate(parent_doctype, trans_items, parent_doctype_name, child_docname="items"):
	data = json.loads(trans_items)

	sales_doctypes = ['Sales Order', 'Sales Invoice', 'Delivery Note', 'Quotation']
	parent = frappe.get_doc(parent_doctype, parent_doctype_name)

	validate_and_delete_children(parent, data)

	for d in data:
		new_child_flag = False
		if not d.get("docname"):
			new_child_flag = True
			if parent_doctype == "Sales Order":
				child_item  = set_sales_order_defaults(parent_doctype, parent_doctype_name, child_docname, d)
			if parent_doctype == "Purchase Order":
				child_item = set_purchase_order_defaults(parent_doctype, parent_doctype_name, child_docname, d)
		else:
			child_item = frappe.get_doc(parent_doctype + ' Item', d.get("docname"))
			if flt(child_item.get("rate")) == flt(d.get("rate")) and flt(child_item.get("qty")) == flt(d.get("qty")) and flt(child_item.get("discounted_rate")) == flt(d.get("discounted_rate")) and flt(child_item.get("real_qty")) == flt(d.get("real_qty")):
				continue

		if parent_doctype == "Sales Order" and flt(d.get("qty")) < flt(child_item.delivered_qty):
			frappe.throw(_("Cannot set quantity less than delivered quantity"))
		
		# FinByz Changes Start
		if parent_doctype == "Sales Order" and flt(d.get("real_qty")) < flt(child_item.delivered_real_qty):
			frappe.throw(_("Cannot set real quantity less than delivered real quantity"))

		if parent_doctype == "Sales Order" and (flt(d.get("real_qty")) - flt(child_item.delivered_real_qty)) > (flt(d.get("qty")) - flt(child_item.delivered_qty)):
			frappe.throw(_("Real Qty difference cannot be greater than Qty difference"))

		if parent_doctype == "Sales Order" and d.get("item_code") != child_item.item_code and child_item.delivered_qty:
			frappe.throw(_("Cannot change item as delivery note is already made"))

		if parent_doctype == "Sales Order" and (flt(d.get("rate")) != child_item.rate or flt(d.get("discounted_rate")) != child_item.discounted_rate) and child_item.delivered_qty:
			frappe.throw(_("Cannot change rate as delivery note is already made"))
		# FinByz Changes End

		if parent_doctype == "Purchase Order" and flt(d.get("qty")) < flt(child_item.received_qty):
			frappe.throw(_("Cannot set quantity less than received quantity"))

		child_item.qty = flt(d.get("qty"))
		# FinByz Changes Start
		child_item.real_qty = flt(d.get("real_qty"))
		child_item.discounted_amount = flt(child_item.real_qty) * flt(child_item.discounted_rate)
		# FinByz Changes End
		precision = child_item.precision("rate") or 2
		
		if flt(child_item.billed_amt, precision) > flt(flt(d.get("rate")) * flt(d.get("qty")), precision):
			frappe.throw(_("Row #{0}: Cannot set Rate if amount is greater than billed amount for Item {1}.")
						 .format(child_item.idx, child_item.item_code))
		else:
			child_item.rate = flt(d.get("rate"))
			# FinByz Changes Start
			child_item.discounted_rate = flt(d.get("discounted_rate"))
			# FinByz Changes End

		if flt(child_item.price_list_rate):
			if flt(child_item.rate) > flt(child_item.price_list_rate):
				#  if rate is greater than price_list_rate, set margin
				#  or set discount
				child_item.discount_percentage = 0

				if parent_doctype in sales_doctypes:
					child_item.margin_type = "Amount"
					child_item.margin_rate_or_amount = flt(child_item.rate - child_item.price_list_rate,
						child_item.precision("margin_rate_or_amount"))
					child_item.rate_with_margin = child_item.rate
			else:
				child_item.discount_percentage = flt((1 - flt(child_item.rate) / flt(child_item.price_list_rate)) * 100.0,
					child_item.precision("discount_percentage"))
				child_item.discount_amount = flt(
					child_item.price_list_rate) - flt(child_item.rate)

				if parent_doctype in sales_doctypes:
					child_item.margin_type = ""
					child_item.margin_rate_or_amount = 0
					child_item.rate_with_margin = 0

		child_item.flags.ignore_validate_update_after_submit = True
		if new_child_flag:
			child_item.idx = len(parent.items) + 1
			child_item.insert()
		else:
			child_item.save()

	parent.reload()
	parent.flags.ignore_validate_update_after_submit = True
	parent.set_qty_as_per_stock_uom()
	parent.calculate_taxes_and_totals()
	if parent_doctype == "Sales Order":
		parent.set_gross_profit()
	frappe.get_doc('Authorization Control').validate_approving_authority(parent.doctype,
		parent.company, parent.base_grand_total)

	parent.set_payment_schedule()
	if parent_doctype == 'Purchase Order':
		parent.validate_minimum_order_qty()
		parent.validate_budget()
		if parent.is_against_so():
			parent.update_status_updater()
	else:
		parent.check_credit_limit()
	parent.save()

	if parent_doctype == 'Purchase Order':
		update_last_purchase_rate(parent, is_submit = 1)
		parent.update_prevdoc_status()
		parent.update_requested_qty()
		parent.update_ordered_qty()
		parent.update_ordered_and_reserved_qty()
		parent.update_receiving_percentage()
		if parent.is_subcontracted == "Yes":
			parent.update_reserved_qty_for_subcontract()
	else:
		parent.update_reserved_qty()
		parent.update_project()
		parent.update_prevdoc_status('submit')
		parent.update_delivery_status()

	parent.update_blanket_order()
	parent.update_billing_percentage()
	parent.set_status()
