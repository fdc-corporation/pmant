from odoo import models, fields, api
#'''
class PlanEquipoProcesos(models.Model):
    _name               = 'planequipoproceso.mantenimiento'

    proceso = fields.Many2one('proceso.mantenimiento', string="Proceso", required=True)  # Cambiado a Many2one
    planequipo          = fields.Many2one('planequipo.mantenimiento',string='Plan Equipo')
    descripcion         = fields.Text(string="Comentarios")
    descripcion_proceso = fields.Text(related="proceso.descripcion")
    #estado              = fields.Many2one('estadoproceso.mantenimiento',string="Estado",required=True)
    estado              = fields.Many2one('estadoproceso.mantenimiento', string="Estado", required=False)
    tarea               = fields.Many2one('tarea.mantenimiento',string="Tarea")
    ots                 = fields.Many2one('maintenance.request',string="ots")
    plan                = fields.Many2one('plan.mantenimiento',related="planequipo.plan")
    adjunto             = fields.Binary(string="Adjunto 1")
    adjunto2            = fields.Binary(compute="_geadj", string="Adjunto 2")
    is_admin            = fields.Boolean(compute="_geadj")
    descripcion2        = fields.Text(compute="_geadj",default="falta poner Comentario...",string="Comentarios")
    name_file           = fields.Char(default="Adjunto")
    adjuntos            = fields.One2many('adjuntoimage.mantenimiento', 'planequipoproceso', string="Archivos Adjuntos")
    adjunto1            = fields.Binary(string="Adjunto 1")
    adjunto23           = fields.Binary(string="Adjunto 2")
    
    def _geadj(self):
        for rec in self:
            rec.is_admin = rec.env['res.users'].has_group('pmant.group_pmant_admin')
            rec.adjunto2 = rec.adjunto
            txt = str(rec.descripcion)
            if rec.descripcion:
                if len(txt) > 50:
                    txt = txt[0:50] + '...'
                rec.descripcion2=txt
            else:
                rec.descripcion2='falta poner Comentario...'

class GrupoParte(models.Model):
    _name   = 'grupoproceso.mantenimiento'
    name    = fields.Char(size=60,required=True,string='Nombre')

class Proceso(models.Model):
    _name = 'proceso.mantenimiento'
    name = fields.Char(size=60, required=True, string='Nombre')
    grupo = fields.Many2one('grupoproceso.mantenimiento', string="Grupo/Parte")
    plan = fields.Many2one('plan.mantenimiento')
    descripcion = fields.Text()

class EstadoProceso(models.Model):
   _name   = 'estadoproceso.mantenimiento'
   name    = fields.Char(size=5,required=True,string='Nombre')
   icono = fields.Binary(string="Icono", store=True)
#'''
