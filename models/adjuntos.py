from odoo import models, fields, api
import mimetypes
class Adjunto(models.Model):
    _name        = 'adjunto.mantenimiento'
    _description = 'Adjuntos de Mantenimiento'
    name         = fields.Char(size=60,string='Referencia Archivo')
    adjunto      = fields.Binary()
    equipo       = fields.Many2one('maintenance.equipment',string='Equipo')
    #planequipoproceso   = fields.Many2one('planequipo.mantenimiento')


    def get_mimetype(self, filename):
        """Devuelve el tipo MIME basado en la extensión del archivo."""
        mimetype, _ = mimetypes.guess_type(filename)
        return mimetype or 'application/octet-stream'

class Adjunto_Atchmento(models.Model):
    _inherit = 'ir.attachment'

    id_equipo       = fields.Many2one('maintenance.equipment',string='Equipo')

class FirmasElectronica (models.Model):
    _inherit="sign.template"
    
    ot_id = fields.Many2one("maintenance.request", string="Orden de trabajo")
    
class DocumentoFirmado(models.Model):
    _inherit="sign.request"

    ot_id = fields.Many2one("maintenance.request", related="template_id.ot_id", string="Orden de trabajo")

class ModelFirma(models.TransientModel):
    _inherit="sign.send.request"

    ot_id = fields.Many2one("maintenance.request", related="template_id.ot_id", string="Orden de trabajo")


class VoltajeLinea(models.Model):
    _name = "voltaje.linea"

    l1_l2 = fields.Float("L1/L2")
    l2_l3 = fields.Float("L2/L3")
    l1_l3 = fields.Float("L1/L3")
    l1_gnd = fields.Float("L1/GND")
    l2_gnd = fields.Float("L2/GND")
    l3_gnd = fields.Float("L3/GND")
    supply = fields.Float("Supply")
    planequipo_id = fields.Many2one('planequipo.mantenimiento', string="Plan equipo")

class AmperajeLinea(models.Model):
    _name = 'amperaje.linea'
    _description = 'Medición de amperaje por línea y fase'

    linea = fields.Char(string='Línea')

    carga_linea = fields.Float("Carga Línea")
    descarga_linea = fields.Float("Descarga Línea")

    fase = fields.Char("Fase")
    carga_fase = fields.Char("Carga Fase")
    descarga_fase = fields.Char("Descarga Fase")
    planequipo_id = fields.Many2one('planequipo.mantenimiento', string="Plan equipo")

class UnidadMedidaModulo(models.Model):
    _name = 'unidad.medida.modulo'
    _description = 'Unidad de Medida del Parámetro'

    name = fields.Char(string="Unidad", required=True)


class ParametroModulo(models.Model):
    _name = 'parametro.modulo'
    _description = 'Parámetro del módulo del compresor'

    name = fields.Char(string="Nombre del parámetro", required=True)

class ParametrosOperacion (models.Model):
    _name = 'paremetros.operacion'
    _descripcion = "Parámetros de operación del compresor"

    paremetro_id = fields.Many2one("parametro.modulo", string="Párametros del modulo")
    valor_trabajo = fields.Char(string="Valores de trabajo")
    valor_parada = fields.Char(string="Valores de parada")
    unidad_medida = fields.Many2one("unidad.medida.modulo", string="Unidad de medida")
    planequipo_id = fields.Many2one('planequipo.mantenimiento', string="Plan equipo")