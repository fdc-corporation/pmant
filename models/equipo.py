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


class EquiposUbicacion(models.Model):
    _inherit = "res.partner"
    _description = "Informacion de equipos en Contactos"

    email_jefe = fields.Char(
        string="Correo Jefe de taller",
        help="Este correo se usara para el envio de correos para programacion de servicios"
    )
    equipos_ubicacion = fields.One2many(
        "maintenance.equipment",
        "ubicacion",  # Campo inverso definido en maintenance.equipment
        string="Equipos",
    )
    is_tecnico = fields.Boolean(
        compute="_compute_is_tecnico", string="Is Técnico", store=False
    )

    def _compute_is_tecnico(self):
        for record in self:
            record.is_tecnico = self.env.user.has_group("pmant.group_pmant_tecnico")

    @api.model
    def equipos_model(self):
        for record in self:
            equipos = self.env["maintenance.equipment"].search(
                [("ubiccacion.id", "=", self.id)]
            )
            for equipo in equipos:
                self.write({"equipos_ubicacion": equipo.id})


class Prioridad(models.Model):
    _name = "prioridad.mantenimiento"
    name = fields.Char(size=25, required=True)



class DataEquipo(models.Model):
    _name = "medicion.equipo"

    hora_uso = fields.Float(string="Horas de uso promedio al dia")
    temperatura_elemento = fields.Float(string="Temperatura del elemento")
    presion_actual = fields.Float(string="Presion actual")
    temperatura_ambiente = fields.Float(string="Temperatura del ambiente")
    equipo_id = fields.Many2one('maintenance.equipment', string="Equipo")
    fecha_registro = fields.Datetime(string="Fecha de registro", default=fields.Datetime.now)

class Equipo(models.Model):
    _name = "maintenance.equipment"
    _inherit = "maintenance.equipment"
    propietario = fields.Many2one(
        "res.partner",
        string="Propietario",
        required=True,
        # domain=[("is_company", "=", "True")],
    )
    parent_id = fields.Integer(related="propietario.id")
    ubicacion = fields.Many2one("res.partner", string="Ubicacion", tracking=True)
    area = fields.Many2one("res.partner", string="Area asignada", tracking=True)
    fabricante = fields.Char(size=60)
    marca = fields.Char(size=60)
    frecuencia_m = fields.Integer(string="Frecuencia de Mantenimiento")
    fecha_compra = fields.Date()
    # otro1 = fields.Char(size=50, string="Clasificacion 1")
    # otro2 = fields.Char(size=50, string="Clasificacion 2")
    time_uso = fields.Float(string="Horas Promedio")
    prioridad = fields.Many2one("prioridad.mantenimiento", string="Prioridad")
    adjunto = fields.One2many(
        "adjunto.mantenimiento", "equipo", string="Archivos Adjuntos"
    )
    planequipo = fields.One2many(
        "planequipo.mantenimiento", "equipo", string="Planes Equipos"
    )
    qr_image = fields.Binary(
        "QR equipo", compute="_generate_qr_code", attachment=True, store=True
    )
    qr_image2 = fields.Binary("QR equipo", compute="_generate_qr_code", attachment=True)
    url_qr = fields.Char(string="URL del QR", compute="_generate_qr_code")
    fecha_prox = fields.Date(string="Fecha aprox", compute="_generate_qr_code")
    hoy = fields.Date(default=str(datetime.now()))
    avisado_prox = fields.Char(compute="_comparar_fechas")
    avisado_prox = fields.Char(string="Avisado aprox")
    fecha_ult = fields.Date(compute="_generate_f_prox")
    plan = fields.Char(compute="_generate_f_prox")
    avisado = fields.Boolean(compute="_comparar_fechas")
    avisado = fields.Boolean(string="Avisado")
    anticipo = fields.Integer(compute="_generate_f_prox")
    image = fields.Binary("Image", attachment=True)
    certificados = fields.One2many(
        "sign.request", "equipo_id", domain=[("state", "=", "signed")], string="Certificados de operatividad"
    )
    documentos = fields.Many2many("documents.document", "equipo", string="Documentos")
    cotizacion_cantidad = fields.Integer(compute="_total_cotizaciones")
    mediciones = fields.One2many("medicion.equipo", "equipo_id", string="Mediciones")
    otros_mantenimento = fields.One2many("mantenimento.equipo.otros", "equipo", string="Otros mantenimientos")
    solicitudes_servicio = fields.One2many("servicio.solicitud", "equipo_id", string="Solicitudes de Mantenimiento")
    cantidad_certificados = fields.Integer(
        compute="_get_certificados", string="Cantidad de Certificados"
    )

    def action_view_certificados(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Certificados de Operatividad",
            "res_model": "sign.request",
            "view_mode": "kanban,form",
            "target": "current",  # O usa 'new' si deseas que se abra como ventana modal
            "domain": [("state", "=", "signed"), ("equipo_id", "=", self.id)],
            "context": {
                "default_equipo_id": self.id,
            },
        }

    def _get_certificados(self):
        documentos = self.env["sign.request"].search_count(
            [("equipo_id", "=", self.id), ("state", "=", "signed")]
        )
        self.cantidad_certificados = documentos

    def action_view_cotizaciones(self):
        for record in self:
            cotizaciones = self.env["sale.order"].search(
               [("order_line.id_equipo", "in", [record.id])]
            )
            return {
                "name": "Cotizaciones del Equipo",
                "type": "ir.actions.act_window",  # ¡Este es el campo que faltaba!
                "domain": [("id", "in", cotizaciones.ids)],
                "view_mode": "tree,form",  # puedes permitir también la vista formulario
                "res_model": "sale.order",
                "context": {"create": False},
            }

    def set_servico_tecnico(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Agregar Mantenimiento",
            "res_model": "wiizard.mantenimiento",
            "view_mode": "form",
            "view_type": "form",
            "target": "new",
            "context": {
                "default_equipo_id": self.id,
                # "default_url": self.id,
                # "active_id": active_id,
            },
        }

    def _total_cotizaciones(self):
        for record in self:
            cotizaciones = self.env["sale.order"].search(
                [("order_line.id_equipo", "in", [record.id])]
            )
            record.cotizacion_cantidad = len(cotizaciones)

    def _generate_qr_code(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")

        for record in self:
            # Generar URL
            url = f"{base_url}/my/equipos/{record.id}/detalles"

            # Generar QR como imagen base64
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            qr_image_b64 = base64.b64encode(buffer.getvalue())

            # Obtener última fecha
            fechas = [
                tarea.fecha_ejecprox
                for tarea in record.planequipo
                if tarea and tarea.plan and tarea.plan.frecuencia > 0 and tarea.fecha_ejecprox
            ]

            fecha_prox = max(fechas) if fechas else False

            # Asignar a campos
            record.qr_image = qr_image_b64
            record.qr_image2 = qr_image_b64
            record.url_qr = url
            record.fecha_prox = fecha_prox

    def generar_n_serie(self):
        prefix = "CT-"
        
        equipos_filtro = self.env['maintenance.equipment'].search(
            ["|", ("serial_no", "=", False), ("serial_no", "ilike", prefix + "%")]
        )
        
        for equipo in equipos_filtro:
            if not equipo.serial_no:
                equipo.serial_no = f"{prefix}{equipo.id}"

        return ''



class Adjunto(models.Model):
    _name = "adjunto.mantenimiento"
    _description = "Adjuntos de Mantenimiento"
    name = fields.Char(size=60, string="Referencia Archivo")
    adjunto = fields.Binary()
    equipo = fields.Many2one("maintenance.equipment", string="Equipo")
    # planequipoproceso   = fields.Many2one('planequipo.mantenimiento')


class AdjuntoImagw(models.Model):
    _name = "adjuntoimage.mantenimiento"
    name = fields.Char(size=60, string="Referencia Archivo")
    adjunto = fields.Binary()
    # equipo       = fields.Many2one('maintenance.equipment',string='Equipo')
    planequipoproceso = fields.Many2one("planequipoproceso.mantenimiento")
    comentario = fields.Text()


class DocuemntosEquipo(models.Model):
    _inherit = "documents.document"

    equipo = fields.Many2many("maintenance.equipment", string="Equipo")

class MasMantenimiento (models.Model):
    _name = "mantenimento.equipo.otros"
    _descriptiion = "Mas mantenimitnos externos"

    name = fields.Char(string="Nombre", required="1")
    # planequipo = fields.Many2one("planequipo.mantenimiento", string="Plan de mantenimiento")
    fecha_ejec = fields.Date(string="Fecha ejecutada")
    file_adjunto = fields.Binary(string="Reporte Tecnico")
    file_name = fields.Char(string="Nombre de archivo")
    tipo = fields.Many2one("tipotarea.mantenimiento", string="tipo de mantenimiento")
    equipo = fields.Many2one("maintenance.equipment", string="Equipo")

    