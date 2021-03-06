# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.addons.sale_timesheet.tests.common import TestCommonSaleTimesheetNoChart
from odoo.exceptions import UserError


class TestSaleService(TestCommonSaleTimesheetNoChart):
    """ This test suite provide checks for miscellaneous small things. """

    @classmethod
    def setUpClass(cls):
        super(TestSaleService, cls).setUpClass()
        # set up
        cls.setUpEmployees()
        cls.setUpServiceProducts()

        cls.sale_order = cls.env['sale.order'].with_context(mail_notrack=True, mail_create_nolog=True).create({
            'partner_id': cls.partner_customer_usd.id,
            'partner_invoice_id': cls.partner_customer_usd.id,
            'partner_shipping_id': cls.partner_customer_usd.id,
        })

    def test_sale_service(self):
        """ Test task creation when confirming a sale_order with the corresponding product """
        sale_order_line = self.env['sale.order.line'].create({
            'order_id': self.sale_order.id,
            'name': self.product_delivery_timesheet2.name,
            'product_id': self.product_delivery_timesheet2.id,
            'product_uom_qty': 50,
            'product_uom': self.product_delivery_timesheet2.uom_id.id,
            'price_unit': self.product_delivery_timesheet2.list_price
        })

        self.sale_order.order_line._compute_product_updatable()
        self.assertTrue(sale_order_line.product_updatable)
        self.sale_order.action_confirm()
        self.sale_order.order_line._compute_product_updatable()

        self.sale_order.action_confirm()
        self.sale_order.order_line._compute_product_updatable()
        self.assertFalse(sale_order_line.product_updatable)
        self.assertEqual(self.sale_order.invoice_status, 'no', 'Sale Service: there should be nothing to invoice after validation')

        # check task creation
        project = self.project_global
        task = project.task_ids.filtered(lambda t: t.name == '%s: %s' % (self.sale_order.name, self.product_delivery_timesheet2.name))
        self.assertTrue(task, 'Sale Service: task is not created, or it badly named')
        self.assertEqual(task.partner_id, self.sale_order.partner_id, 'Sale Service: customer should be the same on task and on SO')
        self.assertEqual(task.email_from, self.sale_order.partner_id.email, 'Sale Service: Task Email should be the same as the SO customer Email')

        # log timesheet on task
        self.env['account.analytic.line'].create({
            'name': 'Test Line',
            'project_id': project.id,
            'task_id': task.id,
            'unit_amount': 50,
            'employee_id': self.employee_manager.id,
        })
        self.assertEqual(self.sale_order.invoice_status, 'to invoice', 'Sale Service: there should be sale_ordermething to invoice after registering timesheets')
        self.sale_order.action_invoice_create()

        self.assertTrue(sale_order_line.product_uom_qty == sale_order_line.qty_delivered == sale_order_line.qty_invoiced, 'Sale Service: line should be invoiced completely')
        self.assertEqual(self.sale_order.invoice_status, 'invoiced', 'Sale Service: SO should be invoiced')
        self.assertEqual(self.sale_order.tasks_count, 1, "A task should have been created on SO confirmation.")

        # Add a line on the confirmed SO, and it should generate a new task directly
        product_service_task = self.env['product.product'].create({
            'name': "Delivered Service",
            'standard_price': 30,
            'list_price': 90,
            'type': 'service',
            'invoice_policy': 'delivery',
            'uom_id': self.env.ref('uom.product_uom_hour').id,
            'uom_po_id': self.env.ref('uom.product_uom_hour').id,
            'default_code': 'SERV-DELI',
            'service_type': 'timesheet',
            'service_tracking': 'task_global_project',
            'project_id': project.id
        })

        self.env['sale.order.line'].create({
            'name': product_service_task.name,
            'product_id': product_service_task.id,
            'product_uom_qty': 10,
            'product_uom': product_service_task.uom_id.id,
            'price_unit': product_service_task.list_price,
            'order_id': self.sale_order.id,
        })

        self.assertEqual(self.sale_order.tasks_count, 2, "Adding a new service line on a confirmer SO should create a new task.")

    def test_timesheet_uom(self):
        """ Test timesheet invoicing and uom conversion """
        # create SO and confirm it
        uom_days = self.env.ref('uom.product_uom_day')
        sale_order_line = self.env['sale.order.line'].create({
            'order_id': self.sale_order.id,
            'name': self.product_delivery_timesheet3.name,
            'product_id': self.product_delivery_timesheet3.id,
            'product_uom_qty': 5,
            'product_uom': uom_days.id,
            'price_unit': self.product_delivery_timesheet3.list_price
        })
        self.sale_order.action_confirm()
        task = self.env['project.task'].search([('sale_line_id', '=', sale_order_line.id)])

        # let's log some timesheets
        self.env['account.analytic.line'].create({
            'name': 'Test Line',
            'project_id': task.project_id.id,
            'task_id': task.id,
            'unit_amount': 16,
            'employee_id': self.employee_manager.id,
        })
        self.assertEqual(sale_order_line.qty_delivered, 2, 'Sale: uom conversion of timesheets is wrong')

        self.env['account.analytic.line'].create({
            'name': 'Test Line',
            'project_id': task.project_id.id,
            'task_id': task.id,
            'unit_amount': 24,
            'employee_id': self.employee_user.id,
        })
        self.sale_order.action_invoice_create()
        self.assertEqual(self.sale_order.invoice_status, 'invoiced', 'Sale Timesheet: "invoice on delivery" timesheets should not modify the invoice_status of the so')

    def test_task_so_line_assignation(self):
        # create SO line and confirm it
        so_line_deliver_global_project = self.env['sale.order.line'].create({
            'name': self.product_delivery_timesheet2.name,
            'product_id': self.product_delivery_timesheet2.id,
            'product_uom_qty': 10,
            'product_uom': self.product_delivery_timesheet2.uom_id.id,
            'price_unit': self.product_delivery_timesheet2.list_price,
            'order_id': self.sale_order.id,
        })
        so_line_deliver_global_project.product_id_change()
        self.sale_order.action_confirm()
        task_serv2 = self.env['project.task'].search([('sale_line_id', '=', so_line_deliver_global_project.id)])

        # let's log some timesheets (on the project created by so_line_ordered_project_only)
        timesheets = self.env['account.analytic.line']
        timesheets |= self.env['account.analytic.line'].create({
            'name': 'Test Line',
            'project_id': task_serv2.project_id.id,
            'task_id': task_serv2.id,
            'unit_amount': 4,
            'employee_id': self.employee_user.id,
        })
        timesheets |= self.env['account.analytic.line'].create({
            'name': 'Test Line',
            'project_id': task_serv2.project_id.id,
            'task_id': task_serv2.id,
            'unit_amount': 1,
            'employee_id': self.employee_manager.id,
        })
        self.assertTrue(all([billing_type == 'billable_time' for billing_type in timesheets.mapped('timesheet_invoice_type')]), "All timesheets linked to the task should be on 'billable time'")
        self.assertEqual(so_line_deliver_global_project.qty_to_invoice, 5, "Quantity to invoice should have been increased when logging timesheet on delivered quantities task")

        # make task non billable
        task_serv2.write({'sale_line_id': False})
        self.assertTrue(all([billing_type == 'non_billable' for billing_type in timesheets.mapped('timesheet_invoice_type')]), "Timesheet to a non billable task should be non billable too")

        # make task billable again
        task_serv2.write({'sale_line_id': so_line_deliver_global_project.id})
        self.assertTrue(all([billing_type == 'billable_time' for billing_type in timesheets.mapped('timesheet_invoice_type')]), "Timesheet to a billable time task should be billable")

        # invoice SO, and validate invoice
        invoice_id = self.sale_order.action_invoice_create()[0]
        invoice = self.env['account.invoice'].browse(invoice_id)
        invoice.action_invoice_open()

        # try to update timesheets, catch error 'You cannot modify invoiced timesheet'
        with self.assertRaises(UserError):
            task_serv2.write({'sale_line_id': False})

    def test_delivered_quantity(self):
        # create SO line and confirm it
        so_line_deliver_new_task_project = self.env['sale.order.line'].create({
            'name': self.product_delivery_timesheet3.name,
            'product_id': self.product_delivery_timesheet3.id,
            'product_uom_qty': 10,
            'product_uom': self.product_delivery_timesheet3.uom_id.id,
            'price_unit': self.product_delivery_timesheet3.list_price,
            'order_id': self.sale_order.id,
        })
        so_line_deliver_new_task_project.product_id_change()
        self.sale_order.action_confirm()
        task_serv2 = self.env['project.task'].search([('sale_line_id', '=', so_line_deliver_new_task_project.id)])

        # add a timesheet
        timesheet1 = self.env['account.analytic.line'].create({
            'name': 'Test Line',
            'project_id': task_serv2.project_id.id,
            'task_id': task_serv2.id,
            'unit_amount': 4,
            'employee_id': self.employee_user.id,
        })
        self.assertEqual(so_line_deliver_new_task_project.qty_delivered, timesheet1.unit_amount, 'Delivered quantity should be the same then its only related timesheet.')

        # remove the only timesheet
        timesheet1.unlink()
        self.assertEqual(so_line_deliver_new_task_project.qty_delivered, 0.0, 'Delivered quantity should be reset to zero, since there is no more timesheet.')

        # log 2 new timesheets
        timesheet2 = self.env['account.analytic.line'].create({
            'name': 'Test Line 2',
            'project_id': task_serv2.project_id.id,
            'task_id': task_serv2.id,
            'unit_amount': 4,
            'employee_id': self.employee_user.id,
        })
        timesheet3 = self.env['account.analytic.line'].create({
            'name': 'Test Line 3',
            'project_id': task_serv2.project_id.id,
            'task_id': task_serv2.id,
            'unit_amount': 2,
            'employee_id': self.employee_user.id,
        })
        self.assertEqual(so_line_deliver_new_task_project.qty_delivered, timesheet2.unit_amount + timesheet3.unit_amount, 'Delivered quantity should be the sum of the 2 timesheets unit amounts.')

        # remove timesheet2
        timesheet2.unlink()
        self.assertEqual(so_line_deliver_new_task_project.qty_delivered, timesheet3.unit_amount, 'Delivered quantity should be reset to the sum of remaining timesheets unit amounts.')

    def test_sale_create_project(self):
        """ A SO with multiple product that should create project (with and without template) like ;
                Line 1 : Service 1 create project with Template A ===> project created with template A
                Line 2 : Service 2 create project no template ==> empty project created
                Line 3 : Service 3 create project with Template A ===> Don't create any project because line 1 has already created a project with template A
                Line 4 : Service 4 create project no template ==> Don't create any project because line 2 has already created an empty project
                Line 5 : Service 5 create project with Template B ===> project created with template B
        """
        # second project template and its associated product
        project_template2 = self.env['project.project'].create({
            'name': 'Second Project TEMPLATE for services',
            'allow_timesheets': True,
        })
        Stage = self.env['project.task.type'].with_context(default_project_id=project_template2.id)
        stage1_tmpl2 = Stage.create({
            'name': 'Stage 1',
            'sequence': 1
        })
        stage2_tmpl2 = Stage.create({
            'name': 'Stage 2',
            'sequence': 2
        })
        product_deli_ts_tmpl = self.env['product.product'].create({
            'name': "Service delivered, create project only based on template B",
            'standard_price': 17,
            'list_price': 34,
            'type': 'service',
            'invoice_policy': 'delivery',
            'uom_id': self.env.ref('uom.product_uom_hour').id,
            'uom_po_id': self.env.ref('uom.product_uom_hour').id,
            'default_code': 'SERV-DELI4',
            'service_type': 'timesheet',
            'service_tracking': 'project_only',
            'project_template_id': project_template2.id,
            'project_id': False,
            'taxes_id': False,
            'property_account_income_id': self.account_sale.id,
        })

        # create 5 so lines
        so_line1 = self.env['sale.order.line'].create({
            'name': self.product_delivery_timesheet5.name,
            'product_id': self.product_delivery_timesheet5.id,
            'product_uom_qty': 11,
            'product_uom': self.product_delivery_timesheet5.uom_id.id,
            'price_unit': self.product_delivery_timesheet5.list_price,
            'order_id': self.sale_order.id,
        })
        so_line2 = self.env['sale.order.line'].create({
            'name': self.product_order_timesheet4.name,
            'product_id': self.product_order_timesheet4.id,
            'product_uom_qty': 10,
            'product_uom': self.product_order_timesheet4.uom_id.id,
            'price_unit': self.product_order_timesheet4.list_price,
            'order_id': self.sale_order.id,
        })
        so_line3 = self.env['sale.order.line'].create({
            'name': self.product_delivery_timesheet5.name,
            'product_id': self.product_delivery_timesheet5.id,
            'product_uom_qty': 5,
            'product_uom': self.product_delivery_timesheet5.uom_id.id,
            'price_unit': self.product_delivery_timesheet5.list_price,
            'order_id': self.sale_order.id,
        })
        so_line4 = self.env['sale.order.line'].create({
            'name': self.product_delivery_manual3.name,
            'product_id': self.product_delivery_manual3.id,
            'product_uom_qty': 4,
            'product_uom': self.product_delivery_manual3.uom_id.id,
            'price_unit': self.product_delivery_manual3.list_price,
            'order_id': self.sale_order.id,
        })
        so_line5 = self.env['sale.order.line'].create({
            'name': product_deli_ts_tmpl.name,
            'product_id': product_deli_ts_tmpl.id,
            'product_uom_qty': 8,
            'product_uom': product_deli_ts_tmpl.uom_id.id,
            'price_unit': product_deli_ts_tmpl.list_price,
            'order_id': self.sale_order.id,
        })

        # confirm SO
        self.sale_order.action_confirm()

        # check each line has or no generate something
        self.assertTrue(so_line1.project_id, "Line1 should have create a project based on template A")
        self.assertTrue(so_line2.project_id, "Line2 should have create an empty project")
        self.assertFalse(so_line3.project_id, "Line3 should not have create a project, since line1 already create a project based on template A")
        self.assertFalse(so_line4.project_id, "Line4 should not have create a project, since line1 already create an empty project")
        self.assertTrue(so_line4.task_id, "Line4 should have create a new task, even if no project created.")
        self.assertTrue(so_line5.project_id, "Line5 should have create a project based on template B")

        # check generated stuff are correct
        self.assertTrue(so_line1.project_id in self.project_template_state.project_ids, "Stage 1 from template B should be part of project from so line 1")
        self.assertTrue(so_line1.project_id in self.project_template_state.project_ids, "Stage 1 from template B should be part of project from so line 1")

        self.assertTrue(so_line5.project_id in stage1_tmpl2.project_ids, "Stage 1 from template B should be part of project from so line 5")
        self.assertTrue(so_line5.project_id in stage2_tmpl2.project_ids, "Stage 2 from template B should be part of project from so line 5")

        self.assertTrue(so_line1.project_id.allow_timesheets, "Create project should allow timesheets")
        self.assertTrue(so_line2.project_id.allow_timesheets, "Create project should allow timesheets")
        self.assertTrue(so_line5.project_id.allow_timesheets, "Create project should allow timesheets")

        self.assertEqual(so_line4.task_id.project_id, so_line2.project_id, "Task created with line 4 should have the project based on template A of the SO.")

        self.assertEqual(so_line1.project_id.sale_line_id, so_line1, "SO line of project with template A should be the one that create it.")
        self.assertEqual(so_line2.project_id.sale_line_id, so_line2, "SO line of project should be the one that create it.")
        self.assertEqual(so_line5.project_id.sale_line_id, so_line5, "SO line of project with template B should be the one that create it.")

    def test_billable_task_and_subtask(self):
        """ Test if subtasks and tasks are billed on the correct SO line """
        # create SO line and confirm it
        so_line_deliver_new_task_project = self.env['sale.order.line'].create({
            'name': self.product_delivery_timesheet3.name,
            'product_id': self.product_delivery_timesheet3.id,
            'product_uom_qty': 10,
            'product_uom': self.product_delivery_timesheet3.uom_id.id,
            'price_unit': self.product_delivery_timesheet3.list_price,
            'order_id': self.sale_order.id,
        })
        so_line_deliver_new_task_project.product_id_change()
        self.sale_order.action_confirm()

        project = so_line_deliver_new_task_project.project_id
        task = so_line_deliver_new_task_project.task_id

        self.assertEqual(project.sale_line_id, so_line_deliver_new_task_project, "The created project should be linked to the so line")
        self.assertEqual(task.sale_line_id, so_line_deliver_new_task_project, "The created task should be linked to the so line")

        # create a new task and subtask
        subtask = self.env['project.task'].create({
            'parent_id': task.id,
            'project_id': project.id,
            'name': '%s: substask1' % (task.name,),
            'sale_line_id': False  # forcing, but should have not effect
        })
        task2 = self.env['project.task'].create({
            'project_id': project.id,
            'name': '%s: substask1' % (task.name,)
        })

        self.assertEqual(subtask.sale_line_id, task.sale_line_id, "A child task should have the same SO line than its mother")
        self.assertEqual(task2.sale_line_id, project.sale_line_id, "A new task in a billable project should have the same SO line than its project")
        self.assertEqual(task2.partner_id, so_line_deliver_new_task_project.order_partner_id, "A new task in a billable project should have the same SO line than its project")

        # moving subtask in another project
        subtask.write({'project_id': self.project_global.id})

        self.assertEqual(subtask.sale_line_id, task.sale_line_id, "A child task should always have the same SO line than its mother, even when changing project")
