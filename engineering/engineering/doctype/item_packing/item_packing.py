# -*- coding: utf-8 -*-
# Copyright (c) 2020, FinByz and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt

from engineering.api import before_naming as bn

from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos

class ItemPacking(Document):
	def on_update(self):
		serial_no = get_serial_nos(self.serial_no)
		self.no_of_items = len(serial_no)
		self.not_yet_manufactured = 1
		if self.work_order:
			self.no_of_item_work_order = get_work_order_manufactured_qty(self.work_order)

		self.submit()

	def on_submit(self):
		serial_no = get_serial_nos(self.serial_no)

		if len(serial_no) != cint(frappe.db.get_value("Item", self.item_code,'qty_per_box')):
			frappe.throw(f"Cannot Have More than {cint(frappe.db.get_value('Item', self.item_code ,'qty_per_box'))} item in box")

		serial_no_check = []
		for item in serial_no:
			if item not in serial_no_check:
				serial_no_check.append(item)
			else:
				frappe.throw("You can not add same serial number more than once")

		self.create_serial_no(serial_no)

		# if self.include_for_manufacturing:
			# from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
			# se = frappe.new_doc("Stock Entry")
			# se.update(make_stock_entry(self.work_order,"Manufacture", qty=self.no_of_items))
			# se.set_posting_time = 1
			# se.posting_date = self.posting_date
			# se.posting_time = self.posting_time
			# se.from_warehouse = frappe.db.get_value("Work Order", self.work_order, 'wip_warehouse')
			# se.to_warehouse = frappe.db.get_value("Work Order", self.work_order, 'fg_warehouse')
			
			# # se.save()
			# for item in se.items:
			# 	if item.item_code == self.item_code:
			# 		item.serial_no = self.serial_no
			# 		item.t_warehouse = se.to_warehouse
			# 		item.qty = self.no_of_items
			# se.reference_doctype = "Item Packing"
			# se.reference_docname = self.name
			# se.save()
			# se.submit()
		
		self.submit()
	
	def on_cancel(self):
		serial_no = get_serial_nos(self.serial_no)

		for item in serial_no:
			sr = frappe.get_doc("Serial No", item)

			sr.box_serial_no = ''
			sr.save()
		# if self.include_for_manufacturing:
		# 	if frappe.db.exists("Stock Entry", {'reference_doctype': 'Item Packing', 'reference_docname': self.name, 'docstatus': 1}):
		# 		doc = frappe.get_doc("Stock Entry", {'reference_doctype': 'Item Packing', 'reference_docname': self.name, 'docstatus': 1})
		# 		doc.flags.ignore_permissions = True
		# 		doc.cancel()

	def create_serial_no(self, serial_no):
		for item in serial_no:
			args = {
				"warehouse": self.warehouse,
				"item_code": self.item_code,
				"company": self.company,
				"box_serial_no": self.name
			}

			make_serial_no(self, item, args)
	
	def print_package(self, commit=True):
		self.save()
		return self.name


def make_serial_no(self, serial_no, args):
	if frappe.db.exists("Serial No", serial_no):
		sr = frappe.get_doc("Serial No", serial_no)

		if sr.box_serial_no:
			frappe.throw("Serial No {} is already in box {}".format(frappe.bold(serial_no), frappe.bold(sr.box_serial_no)))
	else:
		sr = frappe.new_doc("Serial No")
	
	sr.serial_no = serial_no
	sr.company = args.get('company')
	sr.item_code = args.get('item_code')
	sr.flags.ignore_permissions = True
	sr.box_serial_no = self.name

	if not frappe.db.exists("Serial No", serial_no):
		sr.insert()
	
	sr.save()

	return sr.name

@frappe.whitelist()
def submit_form(docname):
	doc = frappe.get_doc("Item Packing", docname)
	# frappe.throw(doc.name)
	doc.save()
	doc.submit()

@frappe.whitelist()
def make_stock_entry(work_order = None, posting_date = None, posting_time = None):
	from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
	filters = {'include_for_manufacturing': 1, 'not_yet_manufactured': 1, 'docstatus': 1}
	if work_order:
		filters['work_order'] = work_order
	for i in frappe.get_all("Item Packing", filters, ['distinct work_order as work_order']):
		serial_no_list = []
		no_of_items = 0
		name_list = []
		for j in frappe.get_list("Item Packing", {'include_for_manufacturing': 1, 'not_yet_manufactured': 1, 'work_order': i.work_order, 'docstatus': 1}, ['name', 'serial_no', 'no_of_items']):
			serial_no_list.append(j.serial_no)
			no_of_items += j.no_of_items
			name_list.append(j.name)
		
		
		if no_of_items:
			serial_no = '\n'.join(serial_no_list)

			se = frappe.new_doc("Stock Entry")
			se.update(make_stock_entry(i.work_order,"Manufacture", qty=no_of_items))
			
			if posting_date and posting_time:
				se.set_posting_time = 1
				se.posting_date = posting_date
				se.posting_time = posting_time
				se.from_item_packing = 1
			
			se.from_warehouse = frappe.db.get_value("Work Order", i.work_order, 'wip_warehouse')
			se.to_warehouse = frappe.db.get_value("Work Order", i.work_order, 'fg_warehouse')
			# se.save()	
			for item in se.items:
				if item.item_code == frappe.db.get_value("Work Order",i.work_order,'production_item'):
					item.t_warehouse = se.to_warehouse
					item.qty = no_of_items
					item.serial_no = serial_no
			
			se.save()
			se.submit()
		
			for j in name_list:
				frappe.db.set_value("Item Packing", j, 'stock_entry', se.name)
				frappe.db.set_value("Item Packing", j, 'not_yet_manufactured', 0)

@frappe.whitelist()
def get_work_order_manufactured_qty(work_order):
	qty = flt(frappe.db.get_value("Work Order", work_order, 'produced_qty')) or 0

	qty_item_packing = flt(frappe.db.get_value("Item Packing", {'not_yet_manufactured': 1, 'work_order': work_order, 'docstatus': 1}, 'sum(no_of_items)')) or 0
	if qty + qty_item_packing > (flt(frappe.db.get_value("Work Order", work_order, 'qty')) or 0):
		frappe.throw(f"Work Order {work_order} completed.")
	return qty_item_packing + qty