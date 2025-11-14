# from odoo import http
from odoo.http import request, route, Controller
import smtplib
from math import ceil
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import base64
import math
import urllib.parse
import base64
import json

_logger = logging.getLogger(__name__)


class PortalPmant(Controller):

    @route(
        ["/my/sedes/", "/my/sedes/page/<int:pagina>"],
        type="http",
        auth="user",
        website=True,
    )
    def sedes_portal(self, pagina=1, search=None):
        user_partner = request.env.user.partner_id

        _logger.info(f"User Partner: {user_partner}")
        dominio_web = request.httprequest.host

        # Número de registros por página
        registros_por_pagina = 15

        if user_partner.is_company and user_partner.tienen_areas == False:
            # Crear dominio base para filtrar las sedes
            dominio = [("parent_id", "=", user_partner.id)]

            # Si hay un término de búsqueda, agregarlo al dominio
            if search:
                dominio.append(("name", "ilike", search))

            # Obtener el total de sedes y calcular el número de páginas
            total_sedes = request.env["res.partner"].sudo().search_count(dominio)
            total_paginas = math.ceil(total_sedes / registros_por_pagina)

            # Obtener las sedes para la página actual
            offset = (pagina - 1) * registros_por_pagina
            sedes = (
                request.env["res.partner"]
                .sudo()
                .search(dominio, limit=registros_por_pagina, offset=offset)
            )

            _logger.info(f"Sedes found: {sedes}")
            return request.render(
                "pmant.sedes_portal",
                {
                    "sedes": sedes,
                    "user_partner": user_partner,
                    "dominio": dominio_web,
                    "pagina_actual": pagina,
                    "total_paginas": total_paginas,
                    "search": search or "",
                },
            )
        elif user_partner.tienen_areas == True :
            return request.redirect(f"/my/sede/{user_partner.id}/areas/")
        elif user_partner.is_area == True:
            return request.redirect(f"/my/area/{user_partner.id}/equipos/")
        else:
            return request.redirect(f"/my/sede/{user_partner.id}/equipos/")


    # Areas de las sedes
    @route(
        [
            "/my/sede/<int:sede_id>/areas/",
            "/my/sede/<int:sede_id>/areas/page/<int:pagina>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def areas_sede(self, sede_id, filtro=None, pagina=1, **kw):
        # Número de registros por página
        per_page = 15
        domain = [("id_sede", "=", sede_id)]  # Filtrar por 'id_sede'

        # Si existe un filtro, agregarlo al dominio
        if filtro:
            domain.append(("name", "ilike", filtro))  # Filtrado por nombre del área

        user_partner = request.env.user.partner_id

        # Calcular el total de áreas y el número total de páginas
        total_areas = request.env["res.partner"].sudo().search_count(domain)
        total_paginas = math.ceil(total_areas / per_page)

        # Validación de la página solicitada
        pagina = max(1, min(pagina, total_paginas))  # Asegurar que la página esté dentro del rango

        # Calcular el offset para la página actual
        offset = (pagina - 1) * per_page

        # Obtener las áreas para la página actual
        areas = request.env["res.partner"].sudo().search(domain, limit=per_page, offset=offset)
        
        # Buscar la sede
        sede = request.env["res.partner"].browse(sede_id)

        # Renderizar la plantilla con los datos
        return request.render(
            "pmant.areas_sede",
            {
                "areas": areas,
                "filtro": filtro,
                "pagina_actual": pagina,
                "total_paginas": total_paginas,
                "user_partner": user_partner,
                "sede_id": sede_id,  # Pasar el ID de la sede a la plantilla para los enlaces de paginación
                "ubicacion": sede,  # Pasar la sede a la plantilla
            },
        )


    # EQUIPOS POR SEDES - REGISTRADO A LA UBICACION
    @route(
        [
            "/my/sede/<int:sede_id>/equipos/",
            "/my/sede/<int:sede_id>/equipos/page/<int:pagina>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def equipos_sede(self, sede_id, filtro=None, pagina=1, **kw):
        # Número de registros por página
        per_page = 15
        domain = [("ubicacion", "=", sede_id)]
        user_partner = request.env.user.partner_id

        # Aplicar filtro si existe
        if filtro:
            domain.append(("name", "ilike", filtro))

        # Calcular el total de equipos y el número total de páginas
        total_equipos = request.env["maintenance.equipment"].sudo().search_count(domain)
        total_paginas = math.ceil(total_equipos / per_page)
        if total_equipos == 0:
            domain = [("propietario", "=", sede_id)]
            total_equipos = request.env["maintenance.equipment"].sudo().search_count(domain)
            total_paginas = math.ceil(total_equipos / per_page)

        # Calcular el offset para la página actual
        offset = (pagina - 1) * per_page

        # Obtener los equipos para la página actual
        equipos = (
            request.env["maintenance.equipment"]
            .sudo()
            .search(domain, limit=per_page, offset=offset)
        )
        ubicacion = request.env["res.partner"].sudo().browse(sede_id)

        return request.render(
            "pmant.equipos_sede",
            {
                "equipos": equipos,
                "ubicacion": ubicacion,
                "filtro": filtro,
                "pagina_actual": pagina,
                "total_paginas": total_paginas,
                "user_partner" : user_partner,
                "is_area" : False,
            },
        )

    
    # EQUIPOS POR SEDES - REGISTRADO A LA UBICACION
    @route(
        [
            "/my/area/<int:sede_id>/equipos/",
            "/my/area/<int:sede_id>/equipos/page/<int:pagina>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def equipos_areas(self, sede_id, filtro=None, pagina=1, **kw):
        # Número de registros por página
        per_page = 15
        domain = [("area", "=", sede_id)]
        user_partner = request.env.user.partner_id

        # Aplicar filtro si existe
        if filtro:
            domain.append(("name", "ilike", filtro))

        # Calcular el total de equipos y el número total de páginas
        total_equipos = request.env["maintenance.equipment"].sudo().search_count(domain)
        total_paginas = math.ceil(total_equipos / per_page)
        if total_equipos == 0:
            domain = [("propietario", "=", sede_id)]
            total_equipos = request.env["maintenance.equipment"].sudo().search_count(domain)
            total_paginas = math.ceil(total_equipos / per_page)

        # Calcular el offset para la página actual
        offset = (pagina - 1) * per_page

        # Obtener los equipos para la página actual
        equipos = (
            request.env["maintenance.equipment"]
            .sudo()
            .search(domain, limit=per_page, offset=offset)
        )
        ubicacion = request.env["res.partner"].sudo().browse(sede_id)

        return request.render(
            "pmant.equipos_sede",
            {
                "equipos": equipos,
                "ubicacion": ubicacion,
                "filtro": filtro,
                "pagina_actual": pagina,
                "total_paginas": total_paginas,
                "user_partner" : user_partner,
                "is_area" : True,

            },
        )

    # EQUIPOS REGISTRADOS AL USUARIO DE LA CENTRAL

    @route(
        [
            "/my/<int:empresa_id>/equipos/",
            "/my/<int:empresa_id>/equipos/page/<int:pagina>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def equipos_portal(self, empresa_id, pagina=1, search=None):
        user_partner = request.env.user.partner_id
        per_page = 15  # Número de registros por página

        # Definir el dominio base para la búsqueda
        domain = [("propietario", "=", empresa_id)]

        # Si hay un término de búsqueda, agregarlo al dominio
        if search:
            domain.append(("name", "ilike", search))

        # Obtener ubicaciones del usuario
        ubicaciones = (
            request.env["res.partner"]
            .sudo()
            .search([("parent_id", "=", user_partner.id)])
        )

        # Obtener el total de registros y calcular el número de páginas
        total_equipos = request.env["maintenance.equipment"].sudo().search_count(domain)
        total_paginas = math.ceil(total_equipos / per_page)

        # Calcular el offset para la página actual
        offset = (pagina - 1) * per_page

        # Obtener los equipos para la página actual
        equipos = (
            request.env["maintenance.equipment"]
            .sudo()
            .search(domain, limit=per_page, offset=offset)
        )

        return request.render(
            "pmant.equipos_central",
            {
                "equipos": equipos,
                "user_partner": user_partner,
                "pagina_actual": pagina,
                "total_paginas": total_paginas,
                "ubicaciones": ubicaciones,
                "empresa_id": empresa_id,
                "search": search or "",
            },
        )


    # SOLICITUD DE REGISTRO DE EQUIPO - SEDE -  CENTRAL
    @route(
        ["/solicitud/equipo/"], type="http", auth="user", methods=["POST"], website=True
    )
    def solicitud_registro_equipo(self, **kwargs):
        # Recuperar los valores enviados desde el formulario
        ubicacion_id = kwargs.get("ubicacion_id")  # ID de la ubicación
        nombre_equipo = kwargs.get("nombre_equipo")  # Nombre del equipo
        marca_equipo = kwargs.get("marca_equipo")  # Marca del equipo
        modelo_equipo = kwargs.get("modelo")  # Marca del equipo
        numero_serie = kwargs.get("numero_serie")  # Número de serie
        fecha_registro = kwargs.get("fecha_registro")  # Fecha de registro
        imagen = kwargs.get("formFileMultiple")  # Archivo subido
        user_partner = request.env.user.partner_id

        # Validar que todos los campos requeridos estén presentes
        if not (
            nombre_equipo
            and marca_equipo
            and modelo_equipo
            and numero_serie
            and fecha_registro
        ):
            return request.render(
                "pmant.error_template", {"error": "Todos los campos son obligatorios."}
            )
        image_data = base64.b64encode(imagen.read()) if imagen else False
        # Crear el equipo en el modelo maintenance.equipment
        equipment = (
            request.env["maintenance.equipment"]
            .sudo()
            .create(
                {
                    "propietario": int(user_partner),
                    "ubicacion": int(ubicacion_id) if ubicacion_id else None,
                    "name": nombre_equipo,
                    "marca": marca_equipo,
                    "marca": modelo_equipo,
                    "model": numero_serie,
                    "effective_date": fecha_registro,
                    "image": image_data,  # Leer contenido del archivo
                }
            )
        )
        if ubicacion_id:
            return request.redirect(f"/my/sede/{int(ubicacion_id)}/equipos/")

        # Redirigir a una página de éxito o mostrar un mensaje
        return request.redirect(f"/my/{user_partner.id}/equipos/")

    # SOLICITUD DE REGISTRO DE HNUEVO SERVICIO
    @route(
        ["/solicitud/equipo/"], type="http", auth="user", methods=["POST"], website=True
    )
    def solicitud_registro_equipo(self, **kwargs):
        # Recuperar los valores enviados desde el formulario
        ubicacion_id = kwargs.get("ubicacion_id")  # ID de la ubicación
        nombre_equipo = kwargs.get("nombre_equipo")  # Nombre del equipo
        marca_equipo = kwargs.get("marca_equipo")  # Marca del equipo
        modelo_equipo = kwargs.get("modelo")  # Marca del equipo
        numero_serie = kwargs.get("numero_serie")  # Número de serie
        fecha_registro = kwargs.get("fecha_registro")  # Fecha de registro
        imagen = kwargs.get("formFileMultiple")  # Archivo subido
        user_partner = request.env.user.partner_id

        # Validar que todos los campos requeridos estén presentes
        if not (
            nombre_equipo
            and marca_equipo
            and modelo_equipo
            and numero_serie
            and fecha_registro
        ):
            return request.render(
                "pmant.error_template", {"error": "Todos los campos son obligatorios."}
            )
        image_data = base64.b64encode(imagen.read()) if imagen else False
        # Crear el equipo en el modelo maintenance.equipment
        equipment = (
            request.env["maintenance.equipment"]
            .sudo()
            .create(
                {
                    "propietario": int(user_partner),
                    "ubicacion": int(ubicacion_id) if ubicacion_id else None,
                    "name": nombre_equipo,
                    "marca": marca_equipo,
                    "marca": modelo_equipo,
                    "model": numero_serie,
                    "effective_date": fecha_registro,
                    "image": image_data,  # Leer contenido del archivo
                }
            )
        )
        if ubicacion_id:
            return request.redirect(f"/my/sede/{int(ubicacion_id)}/equipos/")

        # Redirigir a una página de éxito o mostrar un mensaje
        return request.redirect(f"/my/{user_partner.id}/equipos/")

    # REGISTROS - DETALLES DEL EQUIPO

    @route(
        ["/my/equipos/<int:equipo_id>/detalles"], type="http", auth="user", website=True
    )
    def detalle_equipo(self, equipo_id, filtro=None, pagina=1, **kw):
        user_partner = request.env.user.partner_id
        equipo = request.env["maintenance.equipment"].sudo().browse(equipo_id)
        domain = request.httprequest.host
        numero = "51908912551"
        if domain == "compresores.com.pe":
            numero = "51993694375"
        if equipo:
            texto = f"""Hola FDC CORPORATION E.I.R.L. 
            Deseo solicitar un servicio nuevo para mi equipo {equipo.name if equipo.name else 'N/A'} modelo {equipo.model} marca {equipo.marca}, ubicado en {equipo.ubicacion.street if equipo.ubicacion.street else 'N/A' } empresa {equipo.propietario.name if equipo.propietario.name else 'N/A'}"""

            # Codificar el texto para URL
            texto_url = urllib.parse.quote(texto)

            # Construir la URL de WhatsApp
            whatsapp_url = f"https://wa.me/{numero}?text={texto_url}"
            return request.render(
                "pmant.detalle_equipo",
                {
                    "equipo": equipo,
                    "whatsapp_url": whatsapp_url,
                },
            )

    # DETALLES DE HISTORIALD E MNATENIMIENTO - EQUIPO
    @route([
            "/my/equipo/<int:equipo_id>/historial",
            "/my/equipo/<int:equipo_id>/historial/page/<int:pagina>",
        ],
        type="http",
        methods=["GET"],
        auth="user",
        website=True,
    )
    def historial_mantenimiento(self, equipo_id, pagina=1, **kwargs):

        env = request.env
        pagina = int(pagina)

        equipo = env["maintenance.equipment"].sudo().browse(equipo_id)
        if not equipo.exists():
            return request.not_found()

        per_page = 10

        # Ordenamiento
        orden = (kwargs.get("filtro") or "desc").lower()
        reverse_sort = True if orden == "desc" else False
        next_sort = "asc" if orden == "desc" else "desc"

        # Dominio
        domain = [("equipo", "=", equipo_id)]

        # Buscar registros
        historial_1 = env["planequipo.mantenimiento"].sudo().search(domain)
        historial_2 = env["mantenimento.equipo.otros"].sudo().search(domain)

        # Convertir a listas combinadas con estructura uniforme
        def convert(rec, is_otro):
            return {
                "record": rec,
                "fecha_ejec": rec.fecha_ejec or date.min,
                "is_otro": is_otro,
            }

        lista_1 = [convert(r, False) for r in historial_1]
        lista_2 = [convert(r, True) for r in historial_2]

        combinado = lista_1 + lista_2

        # Ordenar
        combinado_ordenado = sorted(combinado, key=lambda x: x["fecha_ejec"], reverse=reverse_sort)

        total = len(combinado_ordenado)
        total_paginas = max(1, math.ceil(total / per_page))

        # Ajustar página fuera de rango
        if pagina < 1:
            pagina = 1
        elif pagina > total_paginas:
            pagina = total_paginas

        offset = (pagina - 1) * per_page
        historial_paginado = combinado_ordenado[offset:offset + per_page]

        # Navegación
        prev_page = pagina - 1 if pagina > 1 else False
        next_page = pagina + 1 if pagina < total_paginas else False

        return request.render("pmant.historial_servicios", {
            "equipo": equipo,
            "historial": historial_paginado,
            "pagina": pagina,
            "total_paginas": total_paginas,
            "prev_page": prev_page,
            "next_page": next_page,
            "has_prev": bool(prev_page),
            "has_next": bool(next_page),
            "filtro": orden,
            "next_sort": next_sort,
            "total": total,
        })



    @route("/my/equipo/<int:equipo_id>/solicitudes/servicios", methods=["GET"], type="http", auth='user', website=True)
    def view_solicitudes_servicios(self, equipo_id, page=1, sort='desc', **kwargs):
        page = int(page)
        sort = request.params.get('sort', 'desc').lower()
        sort = sort if sort in ['asc', 'desc'] else 'desc'
        solicitudes_per_page = 10

        # Buscar las solicitudes de servicio de ese equipo
        dominio = [('equipo_id.id', '=', equipo_id)]
        total_solicitudes = request.env["servicio.solicitud"].sudo().search_count(dominio)
        equipo = request.env["maintenance.equipment"].sudo().browse(equipo_id)

        # Obtener las solicitudes ordenadas por fecha_servicio
        solicitudes = request.env["servicio.solicitud"].sudo().search(
            dominio,
            order=f"fecha_servicio {sort}",
            limit=solicitudes_per_page,
            offset=(page - 1) * solicitudes_per_page,
        )

        total_pages = ceil(total_solicitudes / solicitudes_per_page)

        return request.render("pmant.solicitudes_servicio", {
            'equipo': equipo,
            'solicitudes': solicitudes,
            'page': page,
            'total_pages': total_pages,
            'sort': sort,
            'next_sort': 'asc' if sort == 'desc' else 'desc',
        })


    @route("/my/equipo/<int:equipo_id>/cotizaciones", methods=["GET"], type="http", auth='user', website=True)
    def view_cotizaciones_equipo(self, equipo_id, page=1, **kwargs):
        equipo = request.env["maintenance.equipment"].sudo().browse(equipo_id)
        user_partner = request.env.user.partner_id

        search_query = kwargs.get('search', '').strip()
        page = int(page)
        per_page = 10

        name_domain = equipo.name + " / " + equipo.serial_no if equipo.serial_no else equipo.name

        # Construcción del dominio
        domain = [("order_line.name", "=", name_domain)]
        if search_query:
            domain += [("name", "ilike", search_query)]

        total = request.env["sale.order"].sudo().search_count(domain)

        cotizaciones = request.env["sale.order"].sudo().search(
            domain,
            order="date_order desc",
            limit=per_page,
            offset=(page - 1) * per_page,
        )
        for sale in cotizaciones :
            sale.access_token = None  
            sale._portal_ensure_token()

        total_pages = ceil(total / per_page) if total > 0 else 1

        return request.render("pmant.cotizaciones_pmant", {
            'cotizaciones': cotizaciones,
            'user_partner': user_partner,
            'search': search_query,
            'pagina_actual': page,
            'total_paginas': total_pages,
            'equipo': equipo,
        })



    @route(
        ["/my/servicios/ejecucion", "/my/servicios/ejecucion/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def get_servicio_ejecucion(self, page=1, **kw):
        user = request.env.user.partner_id
        domain = []

        if user.company_type == "person":
            domain = [
                ("ubicacion", "=", user.id),
                ("planequipo.tarea.ots.stage_id", "in", [1, 2]),
            ]
        else:
            domain = [
                ("propietario", "=", user.id),
                ("planequipo.tarea.ots.stage_id", "in", [1, 2]),
            ]

        equipo_model = request.env["maintenance.equipment"].sudo()

        # Paginación
        page = int(page)
        page_size = 12
        total = equipo_model.search_count(domain)
        equipos = equipo_model.search(
            domain, offset=(page - 1) * page_size, limit=page_size
        )

        pager = request.website.pager(
            url="/my/servicios/ejecucion",
            total=total,
            page=page,
            step=page_size,
            scope=5,
            url_args=kw,
        )

        return request.render(
            "pmant.servicios_ejecucion",
            {
                "equipo": equipos,
                "user": user,
                "pager": pager,
            },
        )

    @route(
        [
            "/my/equipo/<int:equipo_id>/adjuntos",
            "/my/equipo/<int:equipo_id>/adjuntos/page/<int:pagina>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def adjuntos_equipo(self, equipo_id, pagina=1, **kwargs):

        env = request.env
        pagina = int(pagina)
        per_page = 10

        equipo = env["maintenance.equipment"].sudo().browse(equipo_id)
        if not equipo.exists():
            return request.not_found()

        # Dominio
        domain = [("equipo", "=", equipo_id)]

        # Total de registros
        total_adj = env["adjunto.mantenimiento"].sudo().search_count(domain)
        total_paginas = max(1, ceil(total_adj / per_page))

        # Asegurar página válida
        if pagina < 1:
            pagina = 1
        elif pagina > total_paginas:
            pagina = total_paginas

        offset = (pagina - 1) * per_page

        # Obtener adjuntos paginados
        adjuntos = (
            env["adjunto.mantenimiento"]
            .sudo()
            .search(domain, offset=offset, limit=per_page)
        )

        # Prev / Next
        prev_page = pagina - 1 if pagina > 1 else False
        next_page = pagina + 1 if pagina < total_paginas else False

        # Numeración central
        pages = list(range(1, total_paginas + 1))

        return request.render(
            "pmant.adjuntos_equipo",
            {
                "equipo": equipo,
                "adjuntos": adjuntos,
                "pagina": pagina,
                "total_paginas": total_paginas,
                "prev_page": prev_page,
                "next_page": next_page,
                "pages": pages,
                "total": total_adj,
            },
        )


    @route(
        "/descargas/reporte/mantenimiento/<int:tarea_id>",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def descarga_reporte_mantenimiento(self, tarea_id, **kw):
        report_action = http.request.env["ir.actions.report"].sudo()
        tarea = request.env["planequipo.mantenimiento"].sudo().browse(tarea_id)
        if tarea.is_informe_file:
            filecontent = base64.b64decode(tarea.informe_file)
            filename = f'reporte_mantenimiento_{tarea.equipo.name}.pdf'

            return request.make_response(
                filecontent,
                headers=[
                    ('Content-Type', 'application/octet-stream'),
                    ('Content-Disposition', f'attachment; filename="{filename}"')
                ]
            )
        else:
            for record in tarea:
                content, _content_type = report_action._render_qweb_pdf(
                    "pmant.action_report_equipo", res_ids=record.ids
                )
            filename = f"Reporte Tecnico.pdf"
            headers = [
                ("Content-Type", "application/pdf"),
                ("Content-Length", len(content)),
                ("Content-Disposition", f"attachment; filename={filename}"),
            ]
            return request.make_response(content, headers=headers)
    # RUTA PARA LOS ADJUNTOS DEL EQUIPO
    @route(
        ["/descargas/adjuntos/equipo/<int:id_adjunto>"],
        type="http",
        auth="user",
        methods=["GET"],
        website=True,
    )
    def descarga_adjuntos_equipo(self, id_adjunto):
        adjunto = request.env["adjunto.mantenimiento"].sudo().browse(id_adjunto)
        if not adjunto or not adjunto.adjunto:
            return request.not_found()

        # Decodificar el contenido binario del archivo adjunto
        file_content_decoded = base64.b64decode(adjunto.adjunto)

        # Generar encabezado manualmente
        filename = urllib.parse.quote(adjunto.name or "archivo.bin")
        headers = [
            ("Content-Type", "application/octet-stream"),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
        ]

        return request.make_response(file_content_decoded, headers=headers)

    # RUTA PARA DESCARGA DE DOCUMENTOS DEL EQUIPO
    @route(
        ["/descargas/documento/equipo/<int:id_equipo>"],
        type="http",
        auth="user",
        methods=["GET"],
        website=True,
    )
    def descarga_documento_equipo(self, id_equipo):
        documento = request.env["documents.document"].sudo().browse(id_equipo)
        if not documento or not documento.datas:
            return request.not_found()

        # Decodificar el contenido binario del archivo adjunto
        file_content_decoded = base64.b64decode(documento.datas)

        # Generar encabezado manualmente
        filename = urllib.parse.quote(documento.name or "archivo.bin")
        headers = [
            ("Content-Type", "application/octet-stream"),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
        ]

        return request.make_response(file_content_decoded, headers=headers)

    # RUTA PARA LOS CERTIFICADOS DE OPERATIVIDAD DEL EQUIPO
    @route(
        ["/my/equipo/<int:id_equipo>/certificados"],
        type="http",
        auth="user",
        website=True,
    )
    def certificados_operatividad_equipo(self, id_equipo):
        equipo = request.env["maintenance.equipment"].sudo().browse(id_equipo)
        return request.render("pmant.certificados_equipo", {"equipo": equipo})

    # RUTA PARA LOS ADJUNTOS DEL EQUIPO
    @route(
        ["/descargas/certificado/equipo/<int:id_adjunto>"],
        type="http",
        methods=["GET"],
        auth="user",
        website=True,
    )
    def descarga_certificado_equipo(self, id_adjunto):
        attachment = request.env["ir.attachment"].sudo().search([("name", "ilike", "Certificado"),("res_model", "=", "sign.request"),("res_id", "=", id_adjunto)], limit=1)
        file_content_decoded = base64.b64decode(attachment.datas)

        # Generar encabezado manualmente
        filename = urllib.parse.quote(attachment.name or "archivo.bin")
        headers = [
            ("Content-Type", attachment.mimetype),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
        ]
        return request.make_response(file_content_decoded, headers=headers)



    @route('/solicitud/mantenimiento/servicio', type='http', auth='public', methods=['POST'], csrf=True)
    def recibir_solicitud_servicio(self, **post):
        try:
            print("📩 Iniciando procesamiento del formulario de servicio...")

            # Extraer datos del formulario
            id_equipo = int(post.get('id_equipo') or 0)
            ubicacion_id = int(post.get('ubicacion_id') or 0)
            tipo_servicio = post.get('tipo_servicio')
            fecha_servicio = post.get('fecha_servicio')
            razon = post.get('razon')

            print(f"➡️ Datos recibidos: equipo={id_equipo}, ubicacion={ubicacion_id}, tipo={tipo_servicio}, fecha={fecha_servicio}")

            # Obtener archivo
            file = request.httprequest.files.get('formFileMultiple')
            file_encoded = False
            filename = False
            if file:
                print(f"📎 Archivo recibido: {file.filename}")
                file_encoded = base64.b64encode(file.read())
                filename = file.filename
            else:
                print("ℹ️ No se adjuntó archivo.")

            # Crear el registro
            solicitud = request.env['servicio.solicitud'].sudo().create({
                'equipo_id': id_equipo,
                'ubicacion_id': ubicacion_id,
                'tipo_servicio': tipo_servicio,
                'fecha_servicio': fecha_servicio,
                'detalle_problema': razon,
                'imagen_referencial': file_encoded,
                'nombre_imagen': filename,
                'estado': 'nuevo',
            })
            print(f"✅ Solicitud creada con ID: {solicitud.id}")

            equipo = solicitud.equipo_id

            # HTML del correo
            html_body = f"""<html><body>
            <h1>Nuevo Servicio de {tipo_servicio}</h1>
            <p>{razon}</p>
            <p><strong>Equipo:</strong> {equipo.name}</p>
            <p><strong>Fecha:</strong> {fecha_servicio}</p>
            </body></html>"""

            # Buscar usuarios del grupo
            group = request.env.ref('pmant.group_pmant_planner')
            internal_users = group.sudo().user_ids.filtered(lambda u: u.email)
            print(f"👥 Usuarios internos con permiso: {[u.login for u in internal_users]}")

            destinatarios = [u.email for u in internal_users]
            if request.env.user and request.env.user.email:
                destinatarios.append(request.env.user.email)
            print(f"✉️ Correos destino: {destinatarios}")

            # Enviar correo
            try:
                mail = request.env['mail.mail'].sudo().create({
                    'subject': f'Solicitud de Servicio - {tipo_servicio}',
                    'email_to': ','.join(destinatarios),
                    'body_html': html_body,
                })
                mail.send()
                print("✅ Correo enviado correctamente.")
            except Exception as mail_error:
                print(f"❌ Error al enviar correo: {mail_error}")
                print("📢 Generando notificaciones internas...")

                for user in internal_users:
                    request.env['mail.message'].sudo().create({
                        'model': 'servicio.solicitud',
                        'res_id': solicitud.id,
                        'message_type': 'notification',
                        'subtype_id': request.env.ref('mail.mt_note').id,
                        'body': (
                            f"<p><strong>📩 Nueva solicitud de servicio creada</strong></p>"
                            f"<p>El equipo <strong>{equipo.name}</strong> tiene una nueva solicitud de tipo <strong>{tipo_servicio}</strong>.</p>"
                        ),
                        'author_id': request.env.user.partner_id.id,
                        'partner_ids': [(4, user.partner_id.id)],
                    })
                print("✅ Notificaciones internas creadas.")

            print("🎉 Proceso completado correctamente.")
            return request.make_response(
                '{"result": {"success": true, "redirect_url": "/my/equipo/' + str(id_equipo) +'/solicitudes/servicios"}}',
                headers=[('Content-Type', 'application/json')]
            )

        except Exception as e:
            print(f"🔥 Error general en la solicitud: {str(e)}")
            return request.make_response(
                '{"result": {"success": false}}',
                headers=[('Content-Type', 'application/json')],
                status=500
            )




    # EVALUACIONES DEL EQUIPO, HISTORIAL
    @route(
        [
            "/my/equipo/<int:id_equipo>/evaluaciones",
            "/my/equipo/<int:id_equipo>/evaluaciones/page/<int:pagina>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def evaluaciones(self, id_equipo, pagina=1, **post):
        per_page = 12  # Número de registros por página
        offset = (pagina - 1) * per_page  # Calcular el inicio de la página actual

        # Obtener todas las tareas relacionadas con el equipo y con tipo "Evaluación"
        domain = [
            "&",
            ("planequipo.equipo", "=", id_equipo),
            ("is_evaluacion", "=", "True"),
        ]
        total_tareas = (
            request.env["tarea.mantenimiento"].sudo().search_count(domain)
        )  # Total de tareas
        tareas = (
            request.env["tarea.mantenimiento"]
            .sudo()
            .search(domain, limit=per_page, offset=offset)
        )  # Tareas por página

        equipo = (
            request.env["maintenance.equipment"]
            .sudo()
            .search([("id", "=", int(id_equipo))], limit=1)
        )

        # Calcular total de páginas
        total_paginas = ceil(total_tareas / per_page)

        # Renderizar la vista con los datos de las tareas y paginación
        return request.render(
            "pmant.evaluaciones_equipo",
            {
                "tareas": tareas,
                "equipo": equipo,
                "pagina_actual": pagina,
                "total_paginas": total_paginas,
            },
        )

    # DECARGA DE LA HOJA DE EVALUACION
    @route(
        ["/descargas/reporte/evaluacion/<int:tarea_id>"],
        type="http",
        auth="user",
        methods=["GET"],
        website=True,
    )
    def descarga_reporte_evaluacion(self, tarea_id, **kw):
        report_action = http.request.env["ir.actions.report"].sudo()
        tarea = request.env["tarea.mantenimiento"].sudo().browse(tarea_id)
        for record in tarea:
            content, _content_type = report_action._render_qweb_pdf(
                "pmant.action_reporte_recepcion", res_ids=record.ids
            )

        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(content)),
            ("Content-Disposition", "attachment; filename=" + "Hoja de recepcion.pdf;"),
        ]
        return request.make_response(content, headers=headers)

    # Descarga de reprote de equipos de la sede
    @route(
        ["/download/reporte_sede_equipos/<int:id_ubicacion>"],
        type="http",
        auth="user",
        website=True,
    )
    def download_reporte_sede_equipos(self, id_ubicacion):
        # Renderizar el PDF pasando el ID de la ubicación como una lista
        pdf = (
            request.env.ref("pmant.report_reporte_sede_equipos")
            .sudo()
            ._render_qweb_pdf([id_ubicacion])[0]
        )

        # Definir las cabeceras para la descarga del PDF
        pdfhttpheaders = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf)),
            ("Content-Disposition", f'attachment; filename="Reporte_Sede_Equipos.pdf"'),
        ]

        # Retornar la respuesta para descargar el archivo
        return request.make_response(pdf, headers=pdfhttpheaders)

    @route(
        ["/download/planequipo/<int:planequipo>"],
        type="http",
        auth="public",
        website=True,
    )
    def download_plaequipo(self, planequipo):
        # Renderizar el PDF pasando el ID de la ubicación como una lista
        pdf = (
            request.env.ref("pmant.action_reporte_cert_operatividad")
            .sudo()
            ._render_qweb_pdf([planequipo])
        )

        # Definir las cabeceras para la descarga del PDF
        pdfhttpheaders = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf)),
            (
                "Content-Disposition",
                f'attachment; filename="Certificafo-operatividad.pdf"',
            ),
        ]

        # Retornar la respuesta para descargar el archivo
        return request.make_response(pdf, headers=pdfhttpheaders)


    @route("/calificacion/<int:order_id>", type="http", auth="public", website=True)
    def page_calificacion(self, order_id, **kwargs):
        order = request.env["maintenance.request"].sudo().browse(int(order_id))
        if order.exists():
            return request.render("pmant.form_calificaciones", { "object" : order })


    @route(
        "/rate_service", type="http", auth="public", methods=["GET"], csrf=False
    )
    def rate_service(self, **post):
        order_id = post.get("order_id")
        p1 = int(post.get("p1") or 0)
        p2 = int(post.get("p2") or 0)
        p3 = int(post.get("p3") or 0)
        comment = post.get("comment", "")

        if order_id:
            order = request.env["maintenance.request"].sudo().browse(int(order_id))
            if order.exists():
                order.sudo().write(
                    {
                        "rating_p1": p1,
                        "rating_p2": p2,
                        "rating_p3": p3,
                        "rating_comment": comment,
                    }
                )

        return request.redirect("/gracias")

    @route("/gracias", type="http", auth="public", website=True)
    def page_gracias(self, **kwargs):

        return request.render("pmant.page_gracias_form")

    @route('/guardar/medicion/equipo', type='json', auth='user', csrf=False)
    def guardar_medicion_equipo(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            equipo_id = int(data.get('equipo_id', 0))
            hora_uso = float(data.get('uso_promedio', 0.0))
            temperatura_elemento = float(data.get('temperatura', 0.0))
            presion_actual = float(data.get('presion', 0.0))
            temperatura_ambiente = float(data.get('tem_ambiente', 0.0))
            print("DATOS DE CONTROLADOR")
            print(equipo_id)
            print(hora_uso)
            print(temperatura_elemento)
            print(presion_actual)
            print(temperatura_ambiente)
            request.env['medicion.equipo'].sudo().create({
                'equipo_id': equipo_id,
                'hora_uso': hora_uso,
                'temperatura_elemento': temperatura_elemento,
                'presion_actual': presion_actual,
                'temperatura_ambiente': temperatura_ambiente,
            })

            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}


