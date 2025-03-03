from odoo import models, fields, api
from odoo.http import request
import qrcode
import base64
from io import BytesIO
from datetime import date, datetime, timedelta

def generate_qr_code(url):
    qr = qrcode.QRCode(
             version=1,
             error_correction=qrcode.constants.ERROR_CORRECT_L,
             box_size=20,
             border=4,
             )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image()
    temp = BytesIO()
    img.save(temp, format="PNG")
    qr_img = base64.b64encode(temp.getvalue())
    return qr_img

class Prioridad(models.Model):
    _name = 'prioridad.mantenimiento'
    name = fields.Char(size=25, required=True)

class Equipo(models.Model):
    _name        = 'maintenance.equipment'
    _inherit     = 'maintenance.equipment'
    propietario  = fields.Many2one('res.partner', string="Propietario", required=True,
                                  domain=[('is_company', '=', 'True')])
    parent_id    = fields.Integer(related='propietario.id')
    ubicacion    = fields.Many2one('res.partner',string="Ubicacion")
    fabricante   = fields.Char(size=60)
    marca        = fields.Char(size=60)
    frecuencia_m = fields.Integer(string="Frecuencia de Mantenimiento")
    fecha_compra = fields.Date()
    otro1        = fields.Char(size=50,string="Clasificacion 1")
    otro2        = fields.Char(size=50, string = "Clasificacion 2")
    time_uso     = fields.Float(string="Horas Promedio")
    prioridad    = fields.Many2one('prioridad.mantenimiento',string="Prioridad")
    adjunto      = fields.One2many('adjunto.mantenimiento','equipo',string="Archivos Adjuntos")
    planequipo   = fields.One2many('planequipo.mantenimiento','equipo',string="Planes Equipos")
    qr_image     = fields.Binary("QR equipo", compute='_generate_qr_code', attachment=True, store=True)
    qr_image2    = fields.Binary("QR equipo", compute='_generate_qr_code', attachment=True)
    url_qr       = fields.Char(string='URL del QR',compute='_generate_qr_code')
    fecha_prox   = fields.Date(string="Fecha aprox")
    hoy          = fields.Date(default=str(datetime.now()))
    avisado_prox = fields.Char(compute='_comparar_fechas')
    avisado_prox = fields.Char(string="Avisado aprox")
    fecha_ult    = fields.Date(compute='_generate_f_prox')
    plan         = fields.Char(compute='_generate_f_prox')
    avisado      = fields.Boolean(compute='_comparar_fechas')
    avisado      = fields.Boolean(string="Avisado")
    anticipo     = fields.Integer(compute='_generate_f_prox')
    image        = fields.Binary("Image", attachment=True)
    certificados = fields.Many2many('ir.attachment', 'id_equipo', string="Certificados de operatividad" )
    documentos   = fields.Many2many('documents.document', 'equipo', string="Documentos")


    @api.model
    def _generate_qr_code(self):
        for record in self:
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            base_url += '/my/equipos/' + str(record.id) + '/detalles'
            qr_image = generate_qr_code(base_url)
            url_qr = base_url
            
            lista_fechas = []
            for tarea in record.planequipo:
                if tarea and tarea.plan.frecuencia > 0:
                    lista_fechas.append(tarea.fecha_ejecprox)
            fecha_prox = lista_fechas[-1] if lista_fechas else False

            record.write({
                'qr_image': qr_image,
                'qr_image2': qr_image,
                'url_qr': url_qr,
                'fecha_prox': fecha_prox,
            })

    def _get_certificados(self):
        for record in self:
            certificados = self.env['ir.attachment'].search([('id_equipo', '=', record.id)])
            record.certificados = certificados.mapped('id')




    def generar_n_serie(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        print('--------------------------------------------------')
        print(base_url)
        equipos_filtro = ''
        if base_url == "https://equiposindustriales.pe":
            equipos_filtro = self.search([
                '|',
                ('serial_no', '=', False),
                ('serial_no', 'ilike', 'FDC-%')
            ])  
            for equipo in equipos_filtro:
                if not equipo.serial_no:
                    equipo.serial_no = self._generate_serial_number(equipo)

        if base_url == "https://compresores.com.pe":
            equipos_filtro = self.search([
                '|',
                ('serial_no', '=', False),
                ('serial_no', 'ilike', 'CT-%')
            ]) 
            for equipo in equipos_filtro:
                if not equipo.serial_no:
                    equipo.serial_no = self._generate_serial_number_ct(equipo)
        if base_url != "https://equiposindustriales.pe" and base_url != "http://compresores.com.pe":
            equipos_filtro = self.search([
                '|',
                ('serial_no', '=', False),
                ('serial_no', 'ilike', 'NSR-%')
            ]) 
            for equipo in equipos_filtro:
                if not equipo.serial_no:
                    equipo.serial_no = self._generate_serial_number_general(equipo)

    def _generate_serial_number(self, equipo):
        return "FDC-" + str(equipo.id)

    def _generate_serial_number_ct(self, equipo):
        return "CT-" + str(equipo.id)
    def _generate_serial_number_general(self, equipo):
        return "NSR-" + str(equipo.id)


class Adjunto(models.Model):
    _name        = 'adjunto.mantenimiento'
    _description = 'Adjuntos de Mantenimiento'
    name         = fields.Char(size=60,string='Referencia Archivo')
    adjunto      = fields.Binary()
    equipo       = fields.Many2one('maintenance.equipment',string='Equipo')
    #planequipoproceso   = fields.Many2one('planequipo.mantenimiento')
    
class AdjuntoImagw(models.Model):
    _name        = 'adjuntoimage.mantenimiento'
    name         = fields.Char(size=60,string='Referencia Archivo')
    adjunto      = fields.Binary()
    #equipo       = fields.Many2one('maintenance.equipment',string='Equipo')
    planequipoproceso   = fields.Many2one('planequipoproceso.mantenimiento')
    comentario          = fields.Text()


class EquiposUbicacion(models.Model):
    _inherit = "res.partner"

    equipos_ubicacion = fields.One2many(
        'maintenance.equipment',
        'ubicacion',  # Campo inverso definido en maintenance.equipment
        string="Equipos"
    )
    is_tecnico = fields.Boolean(
        compute='_compute_is_tecnico',
        string='Is Técnico',
        store=False
    )


    def _compute_is_tecnico(self):
        for record in self:
            record.is_tecnico = self.env.user.has_group('pmant.group_pmant_tecnico')

    @api.model
    def equipos_model(self):
        for record in self :
            equipos = self.env['maintenance.equipment'].search([('ubiccacion.id', '=', self.id)])
            for equipo in equipos:
                self.write({
                    'equipos_ubicacion' : equipo.id
                })


class DocuemntosEquipo (models.Model):
    _inherit = "documents.document"

    equipo = fields.Many2many('maintenance.equipment', string='Equipo')

