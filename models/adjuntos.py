from odoo import models, fields, api
import mimetypes
class Adjunto(models.Model):
    _name        = 'adjunto.mantenimiento'
    _description = 'Adjuntos de Mantenimiento'
    name         = fields.Char(size=60,string='Referencia Archivo')
    adjunto      = fields.Binary(attachment=True)
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
    equipo_id = fields.Many2one("maintenance.equipment", string="Equipo")
    
class DocumentoFirmado(models.Model):
    _inherit="sign.request"

    ot_id = fields.Many2one("maintenance.request", related="template_id.ot_id", string="Orden de trabajo")
    equipo_id = fields.Many2one("maintenance.equipment", related="template_id.equipo_id", string="Equipo")

class ModelFirma(models.TransientModel):
    _inherit="sign.send.request"

    ot_id = fields.Many2one("maintenance.request", related="template_id.ot_id", string="Orden de trabajo")
    equipo_id = fields.Many2one("maintenance.equipment", related="template_id.equipo_id", string="Equipo")


class AdjuntoImagw(models.Model):
    _name = "adjuntoimage.mantenimiento"
    name = fields.Char(size=60, string="Referencia Archivo")
    adjunto = fields.Binary(attachment=True)
    # equipo       = fields.Many2one('maintenance.equipment',string='Equipo')
    planequipoproceso = fields.Many2one("planequipoproceso.mantenimiento")
    comentario = fields.Text()


class DocuemntosEquipo(models.Model):
    _inherit = "documents.document"

    equipo = fields.Many2many("maintenance.equipment", string="Equipo")


class WizardOpenActaConfirmidad(models.TransientModel):
    _name = 'wizard.open.acta.confirmidad'
    _description = 'Wizard para abrir Acta de Conformidad'

    fecha_finalizado = fields.Date(string="Fecha de Finalización", required=True, default=fields.Date.context_today)
    ots_id = fields.Many2one('maintenance.request', string="Órdenes de Trabajo", default=lambda self: self.get_default_ots())
    
    def get_default_ots(self):
        active_ids = self.env.context.get('default_ots_id', [])
        return self.env['maintenance.request'].browse(active_ids)


    def action_generate_acta(self):
        self.ensure_one()
        self.ots_id.fecha_acta = self.fecha_finalizado
        self.ots_id.set_firma_empresa_acta()
    
    def action_generate_pdf_acta(self):
        self.ensure_one()
        self.ots_id.fecha_acta = self.fecha_finalizado

        return self.ots_id.print_acta_conformidad()