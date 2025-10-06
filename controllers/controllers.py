# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
#import requests

class Reporte(http.Controller):
    @http.route('/reporte', type='http', auth="public", website=True)
    #'''
    def index(self, **post):
        id_ots =  post.get("id")
        #buscar la ots
        if id_ots:
            ots = request.env['maintenance.request'].sudo().search([('id', '=', int(id_ots))])
            if ots:
                data = {
                    'docs': ots
                }
                return http.request.render("pmant.prueba_reporte", data)

class ReportePlain(http.Controller):
    @http.route('/reporte2', type='http', auth="public", website=True)
    def index(self, **post):
        id_ots =  post.get("id")
        #buscar la ots
        if id_ots:
            ots = request.env['maintenance.request'].sudo().search([('id', '=', int(id_ots))])
            if ots:
                data = {
                    'docs': ots
                }
                return http.request.render("pmant.prueba_reporte", data)
