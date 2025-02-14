from odoo import http
from odoo.http import request
from datetime import date, datetime, timedelta
import smtplib
from math import ceil
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import base64
import math
import urllib.parse
import base64
_logger = logging.getLogger(__name__)

class PortalPmant(http.Controller):



    @http.route(['/my/sedes/', '/my/sedes/page/<int:pagina>'], type='http', auth="user", website=True)
    def sedes_portal(self, pagina=1, search=None):
        user_partner = request.env.user.partner_id
        _logger.info(f"User Partner: {user_partner}")
        dominio_web = request.httprequest.host

        # Número de registros por página
        registros_por_pagina = 15

        if user_partner.is_company:
            # Crear dominio base para filtrar las sedes
            dominio = [('parent_id', '=', user_partner.id), ("type", "=", "delivery")]
            
            # Si hay un término de búsqueda, agregarlo al dominio
            if search:
                dominio.append(('name', 'ilike', search))

            # Obtener el total de sedes y calcular el número de páginas
            total_sedes = request.env['res.partner'].sudo().search_count(dominio)
            total_paginas = math.ceil(total_sedes / registros_por_pagina)

            # Obtener las sedes para la página actual
            offset = (pagina - 1) * registros_por_pagina
            sedes = request.env['res.partner'].sudo().search(
                dominio, 
                limit=registros_por_pagina, 
                offset=offset
            )

            _logger.info(f"Sedes found: {sedes}")
            return request.render('pmant.sedes_portal', {
                'sedes': sedes,
                'user_partner': user_partner,
                'dominio': dominio_web,
                'pagina_actual': pagina,
                'total_paginas': total_paginas,
                'search': search or '',
            })
        else:
            return request.redirect(f"/my/sede/{user_partner.id}/equipos/")



    # EQUIPOS POR SEDES - REGISTRADO A LA UBICACION
    @http.route([
        '/my/sede/<int:sede_id>/equipos/', 
        '/my/sede/<int:sede_id>/equipos/page/<int:pagina>'
    ], type="http", auth="user", website=True)
    def equipos_sede(self, sede_id, filtro=None, pagina=1, **kw):
        # Número de registros por página
        per_page = 15
        domain = [('ubicacion', '=', sede_id)]

        # Aplicar filtro si existe
        if filtro:
            domain.append(('name', 'ilike', filtro))

        # Calcular el total de equipos y el número total de páginas
        total_equipos = request.env['maintenance.equipment'].sudo().search_count(domain)
        total_paginas = math.ceil(total_equipos / per_page)

        # Calcular el offset para la página actual
        offset = (pagina - 1) * per_page

        # Obtener los equipos para la página actual
        equipos = request.env['maintenance.equipment'].sudo().search(domain, limit=per_page, offset=offset)
        ubicacion = request.env['res.partner'].sudo().browse(sede_id)

        return request.render('pmant.equipos_sede', {
            'equipos': equipos,
            'ubicacion': ubicacion,
            'filtro': filtro,
            'pagina_actual': pagina,
            'total_paginas': total_paginas,
        })


    # EQUIPOS REGISTRADOS AL USUARIO DE LA CENTRAL

    @http.route(['/my/<int:empresa_id>/equipos/', '/my/<int:empresa_id>/equipos/page/<int:pagina>'], type="http", auth="user", website=True)
    def equipos_portal(self, empresa_id, pagina=1, search=None):
        user_partner = request.env.user.partner_id
        per_page = 15  # Número de registros por página

        # Definir el dominio base para la búsqueda
        domain = [
            ('propietario', '=', empresa_id)        ]

        # Si hay un término de búsqueda, agregarlo al dominio
        if search:
            domain.append(('name', 'ilike', search))

        # Obtener ubicaciones del usuario
        ubicaciones = request.env['res.partner'].sudo().search([('parent_id', '=', user_partner.id)])

        # Obtener el total de registros y calcular el número de páginas
        total_equipos = request.env['maintenance.equipment'].sudo().search_count(domain)
        total_paginas = math.ceil(total_equipos / per_page)

        # Calcular el offset para la página actual
        offset = (pagina - 1) * per_page

        # Obtener los equipos para la página actual
        equipos = request.env['maintenance.equipment'].sudo().search(domain, limit=per_page, offset=offset)

        return request.render('pmant.equipos_central', {
            'equipos': equipos,
            'user_partner': user_partner,
            'pagina_actual': pagina,
            'total_paginas': total_paginas,
            'ubicaciones': ubicaciones,
            'empresa_id': empresa_id,
            'search': search or ''
        })

    # SOLICITUD DE REGISTRO DE EQUIPO - SEDE -  CENTRAL
    @http.route(['/solicitud/equipo/'], type='http', auth="user", methods=['POST'], website=True)
    def solicitud_registro_equipo (self, **kwargs):
        # Recuperar los valores enviados desde el formulario
        ubicacion_id = kwargs.get('ubicacion_id')  # ID de la ubicación
        nombre_equipo = kwargs.get('nombre_equipo')  # Nombre del equipo
        marca_equipo = kwargs.get('marca_equipo')  # Marca del equipo
        modelo_equipo = kwargs.get('modelo')  # Marca del equipo
        numero_serie = kwargs.get('numero_serie')  # Número de serie
        fecha_registro = kwargs.get('fecha_registro')  # Fecha de registro
        imagen = kwargs.get('formFileMultiple')  # Archivo subido
        user_partner = request.env.user.partner_id

        # Validar que todos los campos requeridos estén presentes
        if not (nombre_equipo and marca_equipo and modelo_equipo and numero_serie and fecha_registro):
            return request.render('pmant.error_template', {'error': 'Todos los campos son obligatorios.'})
        image_data = base64.b64encode(imagen.read()) if imagen else False
        # Crear el equipo en el modelo maintenance.equipment
        equipment = request.env['maintenance.equipment'].sudo().create({
            'propietario': int(user_partner),
            'ubicacion': int(ubicacion_id) if ubicacion_id else None,
            'name': nombre_equipo,
            'marca': marca_equipo,
            'marca': modelo_equipo,
            'model': numero_serie,
            'effective_date': fecha_registro,
            'image': image_data  # Leer contenido del archivo
        })
        if ubicacion_id :
            return request.redirect(f"/my/sede/{int(ubicacion_id)}/equipos/")

        # Redirigir a una página de éxito o mostrar un mensaje
        return request.redirect(f"/my/{user_partner.id}/equipos/")



    
    # SOLICITUD DE REGISTRO DE HNUEVO SERVICIO
    @http.route(['/solicitud/equipo/'], type='http', auth="user", methods=['POST'], website=True)
    def solicitud_registro_equipo (self, **kwargs):
        # Recuperar los valores enviados desde el formulario
        ubicacion_id = kwargs.get('ubicacion_id')  # ID de la ubicación
        nombre_equipo = kwargs.get('nombre_equipo')  # Nombre del equipo
        marca_equipo = kwargs.get('marca_equipo')  # Marca del equipo
        modelo_equipo = kwargs.get('modelo')  # Marca del equipo
        numero_serie = kwargs.get('numero_serie')  # Número de serie
        fecha_registro = kwargs.get('fecha_registro')  # Fecha de registro
        imagen = kwargs.get('formFileMultiple')  # Archivo subido
        user_partner = request.env.user.partner_id

        # Validar que todos los campos requeridos estén presentes
        if not (nombre_equipo and marca_equipo and modelo_equipo and numero_serie and fecha_registro):
            return request.render('pmant.error_template', {'error': 'Todos los campos son obligatorios.'})
        image_data = base64.b64encode(imagen.read()) if imagen else False
        # Crear el equipo en el modelo maintenance.equipment
        equipment = request.env['maintenance.equipment'].sudo().create({
            'propietario': int(user_partner),
            'ubicacion': int(ubicacion_id) if ubicacion_id else None,
            'name': nombre_equipo,
            'marca': marca_equipo,
            'marca': modelo_equipo,
            'model': numero_serie,
            'effective_date': fecha_registro,
            'image': image_data  # Leer contenido del archivo
        })
        if ubicacion_id :
            return request.redirect(f"/my/sede/{int(ubicacion_id)}/equipos/")

        # Redirigir a una página de éxito o mostrar un mensaje
        return request.redirect(f"/my/{user_partner.id}/equipos/")



    # REGISTROS - DETALLES DEL EQUIPO

    @http.route(['/my/equipos/<int:equipo_id>/detalles'], type="http", auth="user", website=True)
    def detalle_equipo(self, equipo_id, filtro=None, pagina=1, **kw):
        user_partner = request.env.user.partner_id
        equipo = request.env['maintenance.equipment'].sudo().browse(equipo_id)
        domain = request.httprequest.host
        numero = '51908912551'
        if domain == 'compresores.com.pe':
            numero = '51993694375'
        if equipo :
            texto = f"""Hola FDC CORPORATION E.I.R.L. 
            Deseo solicitar un servicio nuevo para mi equipo {equipo.name if equipo.name else 'N/A'} modelo {equipo.model} marca {equipo.marca}, ubicado en {equipo.ubicacion.street if equipo.ubicacion.street else 'N/A' } empresa {equipo.propietario.name if equipo.propietario.name else 'N/A'}"""

            # Codificar el texto para URL
            texto_url = urllib.parse.quote(texto)

            # Construir la URL de WhatsApp
            whatsapp_url = f"https://wa.me/{numero}?text={texto_url}"
            return request.render('pmant.detalle_equipo', {
                'equipo': equipo,
                'whatsapp_url': whatsapp_url,
            })





    # DETALLES DE HISTORIALD E MNATENIMIENTO - EQUIPO
    @http.route(['/my/equipo/<int:equipo_id>/historial', '/my/equipo/<int:equipo_id>/historial/page/<int:pagina>'], type="http", methods=['GET'], auth="user", website=True)
    def historial_mantenimiento(self, equipo_id, pagina=1, **kwargs):
        equipo = request.env['maintenance.equipment'].sudo().browse(equipo_id)
        per_page = 10  # Registros por página
        # Filtrar historial de mantenimiento relacionado con el equipo
        filtro = kwargs.get('filtro', False)
        if filtro == False : 
            filtro = "fecha_ejec"
        domain = [("equipo", "=", equipo_id)]
        total = request.env['planequipo.mantenimiento'].sudo().search_count(domain)
        total_paginas = math.ceil(total / per_page)

        # Paginador
        pager = {
            'page': pagina,
            'size': total_paginas,
        }

        # Obtener registros de la página actual
        offset = (pagina - 1) * per_page
        filtro = f"{filtro} desc" 

        historial = request.env['planequipo.mantenimiento'].sudo().search(domain, offset=offset, limit=per_page, order=filtro)

        return request.render('pmant.historial_mantenimiento', {
            'equipo': equipo,
            'historial': historial,
            'pager': pager,
            'pagina_actual': pagina,
            'total_paginas': total_paginas,
        })




    @http.route(['/my/servicios/ejecucion'], type="http", auth="user", website=True)
    def get_servicio_ejecucion (self):
        user = request.env.user.partner_id
        # Filtrar servicios ejecutados por el usuario
        domain = ["|", ("ubicacion", "=", user.id), ("planequipo.tarea.ots.stage_id", "in", [1, 2])]
        equipos = request.env["maintenance.equipment"].sudo().search(domain)
        # print(equipos)
        return request.render('pmant.servicios_ejecucion', {
            'equipo': equipos,
        })



    

    @http.route(['/my/equipo/<int:equipo_id>/adjuntos', '/my/equipo/<int:equipo_id>/adjuntos/page/<int:pagina>'], type="http", auth="user", website=True)
    def adjuntos_equipo(self, equipo_id, pagina=1):
        per_page = 10  # Registros por página

        # Filtrar adjuntos relacionados con el equipo
        domain = [("equipo", "=", equipo_id)]  # Ajusta el campo "equipo_id" según tu modelo
        total_adjuntos = request.env['adjunto.mantenimiento'].sudo().search_count(domain)
        total_paginas = math.ceil(total_adjuntos / per_page)

        # Calcular el offset para la página actual
        offset = (pagina - 1) * per_page
        adjuntos = request.env['adjunto.mantenimiento'].sudo().search(domain, offset=offset, limit=per_page)

        # Paginador
        pager = {
            'page': pagina,
            'size': total_paginas,
            'has_prev': pagina > 1,
            'has_next': pagina < total_paginas,
        }

        equipo = request.env['maintenance.equipment'].sudo().browse(equipo_id)

        return request.render('pmant.adjuntos_equipo', {
            'equipo': equipo,
            'adjuntos': adjuntos,
            'pager': pager,
        })

    
    @http.route('/descargas/reporte/mantenimiento/<int:tarea_id>', type='http', auth='user', website=True,  methods=['GET'])
    def descarga_reporte_mantenimiento(self, tarea_id, **kw):
        report_action = http.request.env['ir.actions.report'].sudo()
        tarea = request.env['tarea.mantenimiento'].sudo().browse(tarea_id)
        for record in tarea :
            content, _content_type = report_action._render_qweb_pdf('pmant.action_ot_mantenimiento', res_ids=record.ids)
        filename = f"Reporte Tecnico.pdf"
        headers = [
                ('Content-Type', 'application/pdf'),
                ('Content-Length', len(content)),
                ('Content-Disposition', f'attachment; filename={filename}')
        ]
        return request.make_response(content, headers=headers)



    # RUTA PARA LOS ADJUNTOS DEL EQUIPO
    @http.route(['/descargas/adjuntos/equipo/<int:id_adjunto>'], type="http", auth="user", methods=['GET'], website=True)
    def descarga_adjuntos_equipo(self, id_adjunto):
        adjunto = request.env['adjunto.mantenimiento'].sudo().browse(id_adjunto)
        if not adjunto or not adjunto.adjunto:
            return request.not_found()

        # Decodificar el contenido binario del archivo adjunto
        file_content_decoded = base64.b64decode(adjunto.adjunto)

        # Generar encabezado manualmente
        filename = urllib.parse.quote(adjunto.name or 'archivo.bin')
        headers = [
            ('Content-Type', 'application/octet-stream'),
            ('Content-Disposition', f'attachment; filename="{filename}"')
        ]

        return request.make_response(file_content_decoded, headers=headers)


    # RUTA PARA DESCARGA DE DOCUMENTOS DEL EQUIPO
    @http.route(['/descargas/documento/equipo/<int:id_equipo>'], type="http", auth="user", methods=['GET'], website=True)
    def descarga_documento_equipo(self, id_equipo):
        documento = request.env['documents.document'].sudo().browse(id_equipo)
        if not documento or not documento.datas:
            return request.not_found()

        # Decodificar el contenido binario del archivo adjunto
        file_content_decoded = base64.b64decode(documento.datas)

        # Generar encabezado manualmente
        filename = urllib.parse.quote(documento.name or 'archivo.bin')
        headers = [
            ('Content-Type', 'application/octet-stream'),
            ('Content-Disposition', f'attachment; filename="{filename}"')
        ]

        return request.make_response(file_content_decoded, headers=headers)



    # RUTA PARA LOS CERTIFICADOS DE OPERATIVIDAD DEL EQUIPO
    @http.route(['/my/equipo/<int:id_equipo>/certificados'], type="http", auth="user", website=True)
    def certificados_operatividad_equipo (self,id_equipo):
        equipo = request.env['maintenance.equipment'].sudo().browse(id_equipo)
        return request.render('pmant.certificados_equipo', {'equipo' : equipo})

    # RUTA PARA LOS ADJUNTOS DEL EQUIPO
    @http.route(['/descargas/certificado/equipo/<int:id_adjunto>'], type="http", methods=['GET'], auth="user", website=True)
    def descarga_certificado_equipo(self, id_adjunto):
        attachment = request.env['ir.attachment'].sudo().browse(id_adjunto)
        file_content_decoded = base64.b64decode(attachment.datas)

        # Generar encabezado manualmente
        filename = urllib.parse.quote(attachment.name or 'archivo.bin')
        headers = [
            ('Content-Type', attachment.mimetype),
            ('Content-Disposition', f'attachment; filename="{filename}"')
        ]
        return request.make_response(file_content_decoded, headers=headers)


    @http.route(["/solicitud/mantenimiento/servicio"], type="http", methods=['POST'], auth="user", website=True)
    def solicitud_servicio_crm(self, **kwargs):
        ubicacion = kwargs.get('ubicacion')
        ubicacion_id = kwargs.get('ubicacion_id')
        nombre_equipo = kwargs.get('nombre_equipo')
        id_equipo = kwargs.get('id_equipo')
        marca_equipo = kwargs.get('marca_equipo')
        modelo = kwargs.get('modelo')
        numero_serie = kwargs.get('numero_serie')
        razon = kwargs.get('razon')
        tipo_sevicio = kwargs.get('tipo_servicio')
        imagen = kwargs.get('formFileMultiple')
        fecha_servicio = kwargs.get('fecha_servicio')
        user_partner = request.env.user.partner_id
        
        # Validar id_equipo
        if not id_equipo:
            return request.not_found()  # Redirigir si el equipo no está especificado

        equipo = request.env['maintenance.equipment'].sudo().search([('id', '=', int(id_equipo))], limit=1)
        if not equipo:
            return request.not_found()  # Redirigir si el equipo no existe

        equipos = [equipo.id]  # Agregar ID del equipo a la lista

        print('-------------------ID DEL EQUIPO-------------------------')
        print(id_equipo)           
        # Buscar usuario vendedor
        creado_por = request.env['res.groups'].sudo().search([('name', '=', 'Mantenimiento -  Vendedor')], limit=1)
        supervisores = request.env['res.groups'].sudo().search([('name', '=', 'Mantenimiento - ADMIN')], limit=1)
        usuario_vemder = creado_por.users[0].id if creado_por else None
        
        # Crear lead
        lead = request.env['crm.lead'].sudo().create({
            'name': f"Solicitud de Mantenimiento - {user_partner.name} - {equipo.name}",
            'partner_id': user_partner.id,
            'equipo_tarea': [(6, 0, equipos)],  # Relación Many2many
            'ubicacion': int(ubicacion_id) if ubicacion_id else None,
            'user_id': int(usuario_vemder) if usuario_vemder else None,
            'description': f"<p><strong>Tipo de servicios:</strong> {tipo_sevicio}</p> <p> <strong>Fecha de Servicio:</strong> {fecha_servicio}</p>   <p>{razon}</p>",
        })

        # Adjuntar imagen
        if imagen:
            imagen_binario = base64.b64encode(imagen.read())
            attachment = request.env['ir.attachment'].sudo().create({
                'name': imagen.filename,
                'type': "binary",
                'datas': imagen_binario,
                'res_model': 'crm.lead',
                'res_id': lead.id,
                'mimetype': imagen.content_type,
                'public': True,
            })

            # Crear mensaje con el adjunto
            request.env['mail.message'].sudo().create({
                'body': f"Imagen adjunta: <img src='/web/content/{attachment.id}' width='100'/>",
                'model': 'crm.lead',
                'res_id': lead.id,
                'attachment_ids': [(4, attachment.id)],
            })
        datos = {
            'ubicacion' : ubicacion,
            'equipo': equipo,            
        }
        self.enviar_correo_personalizado(supervisores, equipo, tipo_sevicio, fecha_servicio, razon)
        # Redirigir al historial del equipo
        return request.redirect(f'/my/equipos/{equipo.id}/detalles')




    # ENVIO DE EMAIL - SOLICITUD DE SEVICIOS
    def enviar_correo_personalizado (self, supervisores, equipo, tipo_sevicio, fecha_servicio,razon):
        domain = request.httprequest.host
        smtp_server = "smtp.hostinger.com"
        smtp_port = 465
        
        smtp_username = "fdccorp@fdc-corporation.com"
        smtp_password = "Fdc@2024"

        if domain == 'compresores.com.pe' :
            smtp_username = "asistenteadmin@compresoresdetornillo.com.pe"
            smtp_password = "Asistente2024!"

        from_email = smtp_username
        to_emails = [user.login for user in supervisores.users if user.login]
        if not to_emails:
            print("No se encontraron correos electrónicos de supervisores.")
            return
        subject = "Nueva Solicitud de Mantenimiento"
        body = f"""
        <html>
<head>
    <style>
        table {{
            width: 100%;
            border-collapse: collapse;
            font-family: Arial, sans-serif;
            margin: 20px 0;
            font-size: 16px;
            text-align: left;
        }}
        thead {{
            background-color: #007BFF;
            color: white;
        }}
        th, td {{
            padding: 12px 15px;
            border: 1px solid #ddd;
        }}
        tbody tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        tbody tr:hover {{
            background-color: #f1f1f1;
        }}
        th {{
            text-transform: uppercase;
        }}
        td {{
            color: #333;
        }}
    </style>
</head>
<body>
    <table style="width: 100%;" style="border:0px;">
        <tr style="border:0px;">
            <td style="text-align: left; border: 0px; vertical-align: middle;">
                <img src="https://fdc-corporation.com/public/assets/img/logo-empresa.png" alt="Logo FDC CORP"
                     style="max-width: 100px; height: auto;">
            </td>
            <td style="border:0px;"></td>
            <td style="border:0px;"></td>
            <td style="border:0px;"></td>
        </tr>
    </table>
    <br>
    <h1>Nuevo Servicio de {tipo_sevicio}</h1>
    <p>{ razon }</p>
    <br>
    <p><strong>Cliente: </strong>{equipo.propietario.name}</p>
    <p><strong>Ubicación: </strong>{equipo.ubicacion.name}</p>
    <p><strong>Teléfono: </strong>{equipo.ubicacion.mobile}</p>
    <p><strong>Correo: </strong>{equipo.ubicacion.email}</p>
    <br>
    <table>
        <thead>
            <tr>
                <th>Equipo</th>
                <th>Marca</th>
                <th>Modelo</th>
                <th>N° de Serie</th>
                <th>Fecha de Servicio</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>{equipo.name}</td>
                <td>{equipo.marca}</td>
                <td>{equipo.model}</td>
                <td>{equipo.serial_no}</td>
                <td>{fecha_servicio}</td>
            </tr>
        </tbody>
    </table>
</body>
</html>
        """
        message = MIMEMultipart()
        message["From"] = from_email
        message["To"] = ", ".join(to_emails)
        message["Subject"] = subject
        # Adjuntar el cuerpo del mensaje como HTML
        message.attach(MIMEText(body, "html"))
        
        try:
            # Enviar correo usando SMTP
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                server.login(smtp_username, smtp_password)
                server.sendmail(from_email, to_emails, message.as_string())
                print("Correo enviado con éxito.")
        except Exception as e:
            print(f"Error al enviar el correo: {e}")  



    # EVALUACIONES DEL EQUIPO, HISTORIAL
    @http.route(["/my/equipo/<int:id_equipo>/evaluaciones", "/my/equipo/<int:id_equipo>/evaluaciones/page/<int:pagina>"], 
                type="http", auth="user", website=True)
    def evaluaciones(self, id_equipo, pagina=1, **post):
        per_page = 12  # Número de registros por página
        offset = (pagina - 1) * per_page  # Calcular el inicio de la página actual

        # Obtener todas las tareas relacionadas con el equipo y con tipo "Evaluación"
        domain = ["&", ("planequipo.equipo", "=", id_equipo), ("is_evaluacion", "=", "True")]
        total_tareas = request.env['tarea.mantenimiento'].sudo().search_count(domain)  # Total de tareas
        tareas = request.env['tarea.mantenimiento'].sudo().search(domain, limit=per_page, offset=offset)  # Tareas por página

        equipo = request.env['maintenance.equipment'].sudo().search([('id', '=', int(id_equipo))], limit=1)

        # Calcular total de páginas
        total_paginas = ceil(total_tareas / per_page)

        # Renderizar la vista con los datos de las tareas y paginación
        return request.render('pmant.evaluaciones_equipo', {
            'tareas': tareas,
            'equipo': equipo,
            'pagina_actual': pagina,
            'total_paginas': total_paginas,
        })

    
    # DECARGA DE LA HOJA DE EVALUACION
    @http.route(['/descargas/reporte/evaluacion/<int:tarea_id>'], type='http', auth="user", methods=['GET'], website=True)
    def descarga_reporte_evaluacion(self, tarea_id, **kw):
        report_action = http.request.env['ir.actions.report'].sudo()
        tarea = request.env['tarea.mantenimiento'].sudo().browse(tarea_id)
        for record in tarea :
            content, _content_type = report_action._render_qweb_pdf('pmant.action_reporte_recepcion', res_ids=record.ids)

        headers = [
                ('Content-Type', 'application/pdf'),
                ('Content-Length', len(content)),
                ('Content-Disposition', 'attachment; filename=' + "Hoja de recepcion.pdf;")
        ]
        return request.make_response(content, headers=headers)








    # Descarga de reprote de equipos de la sede
    @http.route(['/download/reporte_sede_equipos/<int:id_ubicacion>'], type='http', auth='user', website=True)
    def download_reporte_sede_equipos(self, id_ubicacion):
        # Renderizar el PDF pasando el ID de la ubicación como una lista
        pdf = request.env.ref('pmant.report_reporte_sede_equipos').sudo()._render_qweb_pdf([id_ubicacion])[0]

        # Definir las cabeceras para la descarga del PDF
        pdfhttpheaders = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', f'attachment; filename="Reporte_Sede_Equipos.pdf"')
        ]

        # Retornar la respuesta para descargar el archivo
        return request.make_response(pdf, headers=pdfhttpheaders)

    @http.route(['/download/planequipo/<int:planequipo>'], type='http', auth='public', website=True)
    def download_plaequipo(self, planequipo):
        # Renderizar el PDF pasando el ID de la ubicación como una lista
        pdf = request.env.ref('pmant.action_reporte_cert_operatividad').sudo()._render_qweb_pdf([planequipo])

        # Definir las cabeceras para la descarga del PDF
        pdfhttpheaders = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', f'attachment; filename="Certificafo-operatividad.pdf"')
        ]

        # Retornar la respuesta para descargar el archivo
        return request.make_response(pdf, headers=pdfhttpheaders)


