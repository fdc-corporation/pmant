from odoo import models, fields, _, api
from odoo.exceptions import ValidationError


class CheckList(models.Model):
    _name = "pmant.checklist"
    _description = "Checklist de Mantenimiento"


    name = fields.Char(string="Nombre del Checklist", required=True)
    description = fields.Text(string="Descripción")
    creado_por = fields.Many2one(
        comodel_name="res.users",
        string="Creado por",
        default=lambda self: self.env.user,
        readonly=True,
    )
    fecha_creacion = fields.Datetime(
        string="Fecha de Creación",
        default=fields.Datetime.now,
        readonly=True,
    )

    line_questions = fields.One2many(
        comodel_name="pmant.checklist.question",
        inverse_name="checklist_id",
        string="Preguntas del Checklist",
        help="Lista de preguntas asociadas a este checklist",
    )



class Question(models.Model):
    _name = "pmant.checklist.question"
    _description = "Pregunta del Checklist"

    name = fields.Char(string="Pregunta", required=True)
    checklist_id = fields.Many2one(
        comodel_name="pmant.checklist",
        string="Checklist Asociado",
        required=True,
        ondelete="cascade",
    )
    tipo_respuesta = fields.Selection(
        selection=[
            ("texto", "Texto"),
            ("si_no", "Sí/No"),
        ],
        string="Tipo de Respuesta",
        required=True,
        default="texto",
    )

class GroupChecklist(models.Model):
    _name = "pmant.checklist.group"
    _description = "Grupo de Checklists"
    _order = "create_date desc, id desc"

    name = fields.Char(
        string="Referencia",
        required=True,
        copy=False,
        readonly=True,
        default="New",
        index=True,
    )

    # Guarda el equipo directamente en el grupo
    equipo_id = fields.Many2one(
        comodel_name="maintenance.equipment",
        string="Equipo",
        required=True,
        ondelete="cascade",
        index=True,
    )

    respuestas_ids = fields.One2many(
        comodel_name="pmant.checklist.respuesta",
        inverse_name="group_id",
        string="Respuestas del Grupo",
        help="Respuestas asociadas a las preguntas del checklist de este grupo",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Asigna secuencia si está en 'New' o vacío
            if vals.get("name", "New") in (False, "New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("pmant.checklist.group") or _("GRP/%s") % fields.Date.today()
            
        return super().create(vals_list)

    @api.constrains("respuestas_ids", "equipo_id")
    def _check_respuestas_equipo(self):
        """Todas las respuestas del grupo deben pertenecer al mismo equipo del grupo."""
        for rec in self:
            if rec.respuestas_ids and any(r.equipo_id.id != rec.equipo_id.id for r in rec.respuestas_ids):
                raise ValidationError(_("Todas las respuestas del grupo deben pertenecer al equipo %s.") % (rec.equipo_id.display_name))



class Respuesta(models.Model):
    _name = "pmant.checklist.respuesta"
    _description = "Respuesta a una Pregunta del Checklist"

    question_id = fields.Many2one(
        "pmant.checklist.question",
        string="Pregunta",
        required=True,
        ondelete="cascade",
    )
    group_id = fields.Many2one(
        "pmant.checklist.group",
        string="Grupo de Checklist",
        required=False,
        ondelete="cascade",
    )
    equipo_id = fields.Many2one(
        "maintenance.equipment",
        string="Equipo",
        required=True,
        ondelete="cascade",
    )
    respuesta_texto = fields.Text(string="Respuesta (Texto)")
    respuesta_si_no = fields.Boolean(string="Respuesta (Sí/No)")
    fecha_respuesta = fields.Datetime(
        string="Fecha de Respuesta", default=fields.Datetime.now, readonly=True
    )
    usuario_responsable = fields.Many2one(
        comodel_name="res.users",
        string="Usuario Responsable",
        default=lambda self: self.env.user,
        readonly=True,
    )
    is_comentario = fields.Boolean(
        string="Tiene comentarios?",
        help="Indica si esta respuesta es un comentario adicional",
        default=False,
    )
    comentario = fields.Text(
        string="Comentario Adicional",
        help="Comentario adicional sobre la respuesta, si aplica",
        default="",
    )



