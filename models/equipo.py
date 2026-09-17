from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.http import request
import qrcode
import base64
from io import BytesIO
from datetime import date, datetime, timedelta, time


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
            record.is_tecnico = self.env.user.has_group(
                "pmant.group_pmant_tecnico")

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
    fecha_registro = fields.Datetime(
        string="Fecha de registro", default=fields.Datetime.now)


class Equipo(models.Model):
    _name = "maintenance.equipment"
    _inherit = "maintenance.equipment"

    propietario = fields.Many2one(
        "res.partner",
        string="Propietario",
        required=True,
        domain=[("is_company", "=", "True")], tracking=True,
    )
    parent_id = fields.Integer(related="propietario.id")
    ubicacion = fields.Many2one(
        "res.partner", string="Ubicacion", tracking=True)
    area = fields.Many2one(
        "res.partner", string="Area asignada", tracking=True)
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
        "planequipo.mantenimiento", "equipo", string="Planes Equipos", tracking=True
    )
    qr_image = fields.Binary(
        "QR equipo", compute="_generate_qr_code", attachment=True, store=True
    )
    qr_image2 = fields.Binary(
        "QR equipo", compute="_generate_qr_code", attachment=True)
    url_qr = fields.Char(string="URL del QR", compute="_generate_qr_code")
    fecha_prox = fields.Date(string="Proximo Mantenimiento",
                             compute="_generate_qr_code", store=True, readonly=False)
    image = fields.Binary("Image", attachment=True)
    certificados = fields.One2many(
        "sign.request", "equipo_id", domain=[("state", "=", "signed")], string="Certificados de operatividad"
    )
    certificados_manuales = fields.One2many(
        "pmant.certificado.operatividad",
        "equipo_id",
        string="Certificados PDF firmados",
    )
    documentos = fields.Many2many(
        "documents.document", "equipo", string="Documentos")
    cotizacion_cantidad = fields.Integer(compute="_total_cotizaciones")
    mediciones = fields.One2many(
        "medicion.equipo", "equipo_id", string="Mediciones")

    solicitudes_servicio = fields.One2many(
        "servicio.solicitud", "equipo_id", string="Solicitudes de Mantenimiento")
    cantidad_certificados = fields.Integer(
        compute="_get_certificados", string="Cantidad de Certificados")
    otros_mantenimientos = fields.One2many(
        "mantenimento.equipo.otros", "equipo", string="Otros mantenimientos")
    count_recordatorios = fields.Integer(
        compute="_compute_count_recordatorios", string="Cantidad de Recordatorios"
    )
    count_programacion = fields.Integer(
        compute="_compute_count_programacion", string="Cantidad de Programaciones"
    )
    serial_no = fields.Char(string="Número de serie", copy=False, index=True)

    def action_view_certificados(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Documentos y certificados de firma",
            "res_model": "sign.template",
            "view_mode": "kanban,form",
            "target": "current",  # O usa 'new' si deseas que se abra como ventana modal
            "domain": [
                "|",
                ("equipo_id", "=", self.id),
                ("ot_id.tarea.planequipo.equipo", "=", self.id),
            ],
            "context": {
                "default_equipo_id": self.id,
            },
        }

    @api.model
    def create(self, vals):
        record = super().create(vals)
        record.generar_qr()
        if not record.serial_no:
            record.generar_n_serie()
        return record

    def generar_qr(self):
        # 1. Buscamos los registros que cumplen el criterio (ej: sin QR)
        registros = self.search([('qr_image', '=', False)])

        # 2. Iteramos sobre ellos
        for equipo in registros:
            # Aquí va tu lógica para generar el QR o buscar la OC
            equipo._generate_qr_code()

    def _get_certificados(self):
        for equipment in self:
            equipment.cantidad_certificados = self.env["sign.template"].search_count(
                [
                    "|",
                    ("equipo_id", "=", equipment.id),
                    ("ot_id.tarea.planequipo.equipo", "=", equipment.id),
                ]
            )

    def action_view_cotizaciones(self):
        for record in self:
            cotizaciones = self.env["sale.order"].search(
                [("order_line.id_equipo", "in", [record.id])]
            )
            return {
                "name": "Cotizaciones del Equipo",
                "type": "ir.actions.act_window",  # ¡Este es el campo que faltaba!
                "domain": [("id", "in", cotizaciones.ids)],
                "view_mode": "list,form",  # puedes permitir también la vista formulario
                "res_model": "sale.order",
                "context": {"create": False},
            }

    def _total_cotizaciones(self):
        for record in self:
            cotizaciones = self.env["sale.order"].search(
                [("order_line.id_equipo", "in", [record.id])]
            )
            record.cotizacion_cantidad = len(cotizaciones)

    def _generate_qr_code(self):
        base_url = self.env["ir.config_parameter"].sudo(
        ).get_param("web.base.url")

        for record in self:
            # Generar URL
            url = f"{base_url}/my/equipos/{record.id}/detalles"

            # Generar QR como imagen base64
            qr = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_H)
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

            fecha_max = max(fechas) if fechas else False

            # Asignar a campos
            record.qr_image = qr_image_b64
            record.qr_image2 = qr_image_b64
            record.url_qr = url
            if fecha_max:
                if not record.fecha_prox or record.fecha_prox < fecha_max:
                    record.fecha_prox = fecha_max
                # Si fecha_prox ya es mayor a la fecha máxima, la dejamos (modificada a mano)
            else:
                # Si no hay fechas futuras, dejamos la fecha actual sin cambio
                record.fecha_prox = record.fecha_prox

    def generar_n_serie(self):
        equipos_filtro = self.search(
            ["|", ("serial_no", "=", False), ("serial_no", "ilike", "FDC-%")]
        )
        for equipo in equipos_filtro:
            if not equipo.serial_no:
                equipo.serial_no = "FDC-" + str(equipo.id)

    def programar_mantenimiento(self):
        for record in self:
            # Buscar grupo planificador
            if not record.fecha_prox:
                raise UserError(
                    _(f"El equipo {record.name} no tiene una fecha de próximo mantenimiento definida."))
            group = self.env.ref('pmant.group_pmant_planner',
                                 raise_if_not_found=False)

            # Buscar usuario del grupo
            user = self.env['res.users'].search([
                ('group_ids', 'in', [group.id]),
                ('share', '=', False)
            ], limit=1) if group else False

            # Buscar TODAS las alarmas disponibles
            alarms = self.env['calendar.alarm'].sudo().search([])

            # Construir lista de partners (sin None)
            partner_ids = []
            if record.propietario:
                partner_ids.append(record.propietario.id)
            if record.ubicacion:
                partner_ids.append(record.ubicacion.id)
            if user and user.partner_id:
                partner_ids.append(user.partner_id.id)

            # Crear evento de calendario con todas las alarmas
            calendario = self.env['calendar.event'].create({
                'name': f'Proximo mantenimiento para {record.name}',
                'start': datetime.combine(record.fecha_prox, time(hour=13)),
                'stop': datetime.combine(record.fecha_prox, time(hour=14)),
                'alarm_ids': [(6, 0, alarms.ids)],  # 🔔 Todas las alarmas
                'equipos_ids': [(6, 0, [record.id])],
                'partner_ids': [(6, 0, partner_ids)],
            })

        # Mostrar el último evento creado
        return {
            'type': 'ir.actions.act_window',
            'name': 'Calendario',
            'res_model': 'calendar.event',
            'view_mode': 'form',
            'res_id': calendario.id,
        }

    @api.depends('fecha_prox')
    def _compute_prox_mant(self):
        for record in self:
            if record.fecha_prox:
                record.prox_mant = record.fecha_prox

    def _compute_count_recordatorios(self):
        for record in self:
            record.count_recordatorios = self.env['calendar.event'].search_count([
                ('equipos_ids', 'in', record.id),
                ('start', '>=', fields.Date.today())
            ])

    def action_view_prox_mant(self):
        for record in self:
            return {
                "name": "Próximos Mantenimientos",
                "type": "ir.actions.act_window",
                "res_model": "calendar.event",
                "view_mode": "list,form",
                "domain": [
                    ('equipos_ids', 'in', record.id),
                    ('start', '>=', fields.Date.today())
                ],
            }

    def _compute_count_programacion(self):
        for record in self:
            record.count_programacion = self.env['calendar.event'].search_count([
                ('equipos_ids', 'in', record.id),
                ('start', '>=', fields.Date.today())
            ])

    def action_programacion_equipo(self):
        for record in self:
            return {
                "name": "Historial de Programaciones",
                "type": "ir.actions.act_window",
                "res_model": "calendar.event",
                "view_mode": "list,form",
                "domain": [
                    ('equipos_ids', 'in', record.id)
                ],
            }


class MasMantenimiento (models.Model):
    _name = "mantenimento.equipo.otros"
    _descriptiion = "Mas mantenimitnos externos"

    name = fields.Char(string="Nombre", required=True)
    # planequipo = fields.Many2one("planequipo.mantenimiento", string="Plan de mantenimiento")
    fecha_ejec = fields.Date(string="Fecha ejecutada")
    file_adjunto = fields.Binary(string="Reporte Tecnico")
    file_name = fields.Char(string="Nombre de archivo")
    tipo = fields.Many2one("tipotarea.mantenimiento",
                           string="tipo de mantenimiento")
    equipo = fields.Many2one("maintenance.equipment", string="Equipo")
