from odoo import models, fields, _
from odoo.exceptions import UserError

class ServicioSolicitud(models.Model):
    _name = 'servicio.solicitud'
    _description = 'Solicitud de Mantenimiento'
    _order = 'create_date desc'

    equipo_id = fields.Many2one(
        'maintenance.equipment',
        string='Equipo',
        required=True
    )

    ubicacion_id = fields.Many2one(
        'res.partner',
        string='Ubicación del servicio',
        required=True
    )

    tipo_servicio = fields.Selection([
        ('Preventivo', 'Preventivo'),
        ('Instalación', 'Instalación'),
        ('Mantenimiento', 'Mantenimiento'),
        ('Modificación', 'Modificación'),
    ], string='Tipo de Servicio', required=True)

    fecha_servicio = fields.Date(
        string='Fecha Solicitada',
        required=True
    )

    detalle_problema = fields.Text(
        string='Descripción del Problema'
    )

    imagen_referencial = fields.Binary(
        string='Imagen Referencial', attachment=True
    )

    nombre_imagen = fields.Char(
        string='Nombre del Archivo'
    )

    estado = fields.Selection([
        ('nuevo', 'Nuevo'),
        ('atendido', 'Atendido'),
    ], string='Estado', default='nuevo')

    def create_tarea (self):
        id_eqipo = self.equipo_id.id
        ubicacion = self.equipo_id.ubicacion.id
        cliente = self.equipo_id.propietario.id
        name = f"Servicio {self.tipo_servicio} - {self.equipo_id.propietario.name}"

        tarea_id = self.env["tarea.mantenimiento"].create({
            "name" : name,
            "cliente" : cliente,
            "ubicacion" : ubicacion,
        })
        
        if tarea_id:
            self.env["planequipo.mantenimiento"].create({
                "equipo" : id_eqipo,
                "tarea" : tarea_id.id,
            })
            self.estado = "atendido"
        else :
            raise UserError(_("Hubo un error al crear la tarea"))

        return {
                "name": "Tarea de mantenimiento",
                "type": "ir.actions.act_window",
                "res_id": tarea_id.id,
                "view_mode": "form",  # puedes permitir también la vista formulario
                "res_model": "tarea.mantenimiento",
                "target": "current"
            }