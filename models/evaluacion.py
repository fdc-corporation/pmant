# from datetime import date, datetime, timedelta, time
# from odoo import _, models, fields, api
# from odoo.exceptions import UserError
# import smtplib
# from email.mime.multipart import MIMEMultipart
# from email.mime.text import MIMEText
# import logging
# import base64
# from odoo.tools import html2plaintext


# class OtEvaluaciones (models.Model):
#     _name = 'ot.evaluaciones'
#     _description = 'Evaluaciones de OTs Correctivas'

#     name = fields.Char(String="Nombre", required=True)
#     creado_por = fields.Many2one('res.users', string="Creado por")
#     fecha_creacion = fields.Date(String="Fecha de Creación", default=fields.Date.today())
#     ot_id = fields.Many2one('maintenance.request', 'evaluacion', string="Orden de trabajo")
#     fecha_ingreso = fields.Date(string="Fecha de ingreso", default=fields.Date.today())
#     compania = fields.Many2one('res.company', string="Compañia")
#     tecnico_id = fields.Many2one('res.users', string="Tecnico")
#     cliente = fields.Many2one('res.partner', string="Cliente")
#     ubicacion = fields.Many2one('res.partner', string="Ubicación")
#     plan_mantenimiento = fields.Many2one('plan.mantenimiento', string="Plan de Mantenimiento")
#     equipo = fields.Many2one('maintenance.equipment', string="Equipo")
    