# -*- coding: utf-8 -*-
{
    "name": "pmant",
    "summary": """
            Modulo para Fdcorp""",
    "description": """
        Long description of module's purpose
    """,
    "author": "My Company",
    "website": "http://www.yourcompany.com",
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/11.0/odoo/addons/base/module/module_data.xml
    # for the full list
    "category": "Uncategorized",
    "version": "1.9",
    # any module necessary for this one to work correctly
    "depends": [
        "base",
        "sale",
        "web",
        "documents",
        "oc_compras",
        "product",
        "crm",
        "portal",
        "mail",
        "maintenance",
        "hr",
        "contacts",
        "hr_maintenance",
        "web_digital_sign",
        "calendar",
    ],
    # always loaded
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/reportes/hoja_recepcion.xml",
        "views/reportes/report_acta.xml",
        "views/reportes/report_certificado_operatividad.xml",
        "views/ots.xml",
        "views/views.xml",
        "views/templates.xml",
        "views/general.xml",
        "views/herencia.xml",
        "views/configuracion.xml",
        "views/wizard.xml",
        # 'views/reportecertificado.xml',
        "views/reporteticket.xml",
        "views/planequipo_reporte.xml",
        "views/planequipo.xml",
        "views/equipos.xml",
        "views/rules_cliente.xml",
        "views/rules_cliente_empresa.xml",
        "views/rules_tecnico.xml",
        "views/res_partner.xml",
        "views/adjuntos.xml",
        "views/planequipoproceso.xml",
        "views/paramatros.xml",
        "data/ir_module_category_data.xml",
        "views/reporteweb.xml",
        # VISTAS DEL PORTAL MANTENIMIENTO
        "views/web/index_portal.xml",
        "views/web/sedes_portal.xml",
        "views/web/equipos_sede.xml",
        "views/web/detalle_equipo.xml",
        "views/web/tarea_asignada_web.xml",
        "views/web/form_solicitud.xml",
        "views/web/error_template.xml",
        "views/web/reporte_sede_equipos_template.xml",
        "views/web/equipos_central.xml",
        "views/web/historial_mantenimiento.xml",
        "views/web/adjuntos_equipos.xml",
        "views/web/evaluciones_equipo.xml",
        "views/web/certificados_equipo.xml",
        "views/web/servicios_ejecucion.xml",
        "views/web/index_servicios_ejecuccion.xml",
        "views/pmant_view_inherit_kanban.xml",
        # CODIGO - VENTAS A PMANT SERVICIOS
        "views/ventas/create_mantenimiento.xml",
        "views/ventas/sale_order_views.xml",
        # ARCHIVOS DE PRODUCTOS - TEMPLATE - EQUIPOS
        "views/productos/product_template_views.xml",
        # VISTA - CAMPOS PARA CRM
        "views/crm/orden_trabajo.xml",
        # REPORTES DE MODELOS
        "views/reporteots.xml",
        "views/reportetecnico.xml",
        "views/reporteequipo.xml",
        # PLANTILLAS DE CORREOS PMANT - PETICIONES DE MANTENIMIENTO
        "views/email/email_empresa_ot.xml",
        "views/email/email_sucursal_ot.xml",
        "views/email/email_hoja_recepcion.xml",
        "views/contacto/equipo_contacto.xml",
        # VISTAS DE MODELO DE EVENTO
        "views/eventos/eventos-mant.xml",
        "views/adjunto/it_attchment_inherit.xml",
        # Vista en el modelo de DOCUMENTS
        "views/documents/documentos_inherit.xml",
        "views/code/compartir.xml",
        "wizard/wizard-share.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "pmant/static/src/css/sedes_portal.css",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
