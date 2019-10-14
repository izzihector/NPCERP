# -*- coding: utf-8 -*-

from __future__ import division
from dateutil import relativedelta
from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError,Warning
from datetime import datetime,date
from datetime import date, datetime, time
from pytz import timezone

class Payslip(models.Model):
    _name = 'hr.payslip'
    _inherit = ['mail.thread','hr.payslip']

    payment_method = fields.Selection(related='employee_id.payment_method', store=True,track_visibility='onchange')
    absent_times = fields.Integer(string="Absent Times",  required=False ,track_visibility='onchange')

    struct_id = fields.Many2one('hr.payroll.structure', string='Structure', related='contract_id.struct_id',track_visibility='onchange',
                                readonly=True, states={'draft': [('readonly', False)]},
                                help='Defines the rules that have to be applied to this payslip, accordingly '
                                     'to the contract chosen. If you let empty the field contract, this field isn\'t '
                                     'mandatory anymore and thus the rules applied will be all the rules set on the '
                                     'structure of all contracts of the employee valid for the chosen period')

    name = fields.Char(string='Payslip Name', readonly=True,track_visibility='onchange',
                       states={'draft': [('readonly', False)]})
    number = fields.Char(string='Reference', readonly=True, copy=False,track_visibility='onchange',
                         states={'draft': [('readonly', False)]})
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, readonly=True,track_visibility='onchange',
                                  states={'draft': [('readonly', False)]})
    date_from = fields.Date(string='Date From', readonly=True, required=True,track_visibility='onchange',
                            default=lambda self: fields.Date.to_string(date.today().replace(day=1)),
                            states={'draft': [('readonly', False)]})
    date_to = fields.Date(string='Date To', readonly=True, required=True,track_visibility='onchange',
                          default=lambda self: fields.Date.to_string(
                              (datetime.now() + relativedelta(months=+1, day=1, days=-1)).date()),
                          states={'draft': [('readonly', False)]})
    # this is chaos: 4 states are defined, 3 are used ('verify' isn't) and 5 exist ('confirm' seems to have existed)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('verify', 'Waiting'),
        ('done', 'Done'),
        ('cancel', 'Rejected'),
    ], string='Status', index=True, readonly=True, copy=False, default='draft',track_visibility='onchange',
        help="""* When the payslip is created the status is \'Draft\'
                    \n* If the payslip is under verification, the status is \'Waiting\'.
                    \n* If the payslip is confirmed then status is set to \'Done\'.
                    \n* When user cancel payslip the status is \'Rejected\'.""")
    @api.one
    def _compute_absent_days(self):
        for record in self:
            f_time = 0
            s_time = 0
            t_time = 0
            date_from = fields.Datetime.from_string(record.date_from)
            start_date = fields.Date.to_string(date_from.replace(day=1,month=1))
            payslips = self.search([('employee_id','=',record.employee_id.id),('date_from','>=',start_date),('date_from','<',date_from)])

            for rule in payslips.mapped('worked_days_line_ids'):
                if rule.code == 'Absence':
                    if 1 <= rule.number_of_days <= 6:
                        f_time += 1
                    elif 7 <= rule.number_of_days <= 10:
                        s_time += 1
                    elif 11 <= rule.number_of_days <= 14:
                        t_time += 1
                    else:
                        if rule.number_of_days != 0:
                            t_time = 3
            for rrule in record.mapped('worked_days_line_ids'):
                if rrule.code == 'Absence':
                    if 1 <= rrule.number_of_days <= 6:
                        f_time += 1
                        if f_time == 1:
                            record.absent_times = 11
                        elif f_time == 2:
                            record.absent_times = 12
                        elif f_time == 3:
                            record.absent_times = 13
                        else:
                            if f_time != 0:
                                record.absent_times = 13

                    elif 7 <= rrule.number_of_days <= 10:
                        s_time += 1
                        if s_time == 1:
                            record.absent_times = 21
                        elif s_time == 2:
                            record.absent_times = 22
                        elif s_time == 3:
                            record.absent_times = 23
                        else:
                            if s_time != 0:
                                record.absent_times = 23
                    elif 11 <= rrule.number_of_days <= 14:
                        t_time += 1
                        if t_time == 1:
                            record.absent_times = 31
                        elif t_time == 2:
                            record.absent_times = 32
                        else:
                            if t_time != 0:
                                record.absent_times = 32
            # if record.absent_times in [23,32]:
            #     raise UserError(_('You can not Compute Payslip Absence Days Exceeded %s' %record.employee_id.name))

    @api.multi
    def compute_sheet(self):
        for record in self:
            record._compute_absent_days()
        res = super(Payslip, self).compute_sheet()
        for record in self:
            net = record.line_ids.filtered(lambda line: line.salary_rule_id.code == 'NET')
            if net:
                if net.total <= 0.0:
                    raise Warning(
                        _('You Can not Create Payslip with NET equal or less Than Zero , Employee %s and Amount is %s') % (
                            record.employee_id.name, net.total))
        return res

    @api.model
    def create(self, values):
        res = super(Payslip, self).create(values)
        if not res.employee_id.active:
            raise UserError(_('You Cannot Create Payslip For Archive Employee.%s')%(res.employee_id.name))
        if not res.contract_id:
            raise UserError(_('You Cannot Create Payslip For Employee %s has not contract.')%(res.employee_id.name))
        return res

    @api.model
    def get_worked_day_lines(self, contract_ids, date_from, date_to):
        res = super(Payslip, self).get_worked_day_lines(contract_ids, date_from, date_to)
        working_days = 0.0
        hours_per_day = 8.0
        for contract in contract_ids:
            hours_per_day = contract.resource_calendar_id.hours_per_day or 8.0
            if str(contract.date_start) > str(date_from):
                date_from = fields.Datetime.from_string(date_from)
                start_date = fields.Datetime.from_string(contract.date_start)
                diff = start_date - date_from
                working_days += diff.days
            if str(contract.date_end) < str(date_to):
                date_to = fields.Datetime.from_string(date_to)
                end_date = fields.Datetime.from_string(contract.date_end)
                diff = date_to - end_date
                working_days += diff.days
        for rule in res:
            if rule['code'] == 'WORK100':
                rule['number_of_days'] = float(rule['number_of_days']) - working_days
                rule['number_of_hours'] = float(rule['number_of_hours']) - (working_days * hours_per_day)
        return res

class PayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    state = fields.Selection(selection_add=[('done', 'Confirm')])

    @api.onchange('date_start', 'date_end')
    def onchange_batch_dates(self):
        if self.date_start:
            date_from = fields.Datetime.from_string(self.date_start)
            self.date_end = str(date_from + relativedelta.relativedelta(months=+1, day=1, days=-1))[:10]

    @api.multi
    def compute_sheet(self):
        if self.slip_ids:
            for line in self.slip_ids:
                line.compute_sheet()

    @api.multi
    def action_payslip_done(self):
        if self.slip_ids:
            for line in self.slip_ids.filtered(lambda pay: pay.state == 'draft'):
                line.action_payslip_done()
        self.write({'state': 'done'})