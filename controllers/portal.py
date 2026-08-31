from odoo import fields
from odoo.http import request, route, Controller
from datetime import date, datetime, timedelta
import logging
import base64
from math import ceil
import urllib.parse
import json
import re

_logger = logging.getLogger(__name__)


class PortalPmant(Controller):

    @staticmethod
    def _portal_partner():
        """Contacto del usuario en un entorno seguro para renderizar el portal."""
        return request.env.user.sudo().partner_id

    @staticmethod
    def _commercial_partner():
        return PortalPmant._portal_partner().commercial_partner_id

    def _partner_is_allowed(self, partner):
        partner = partner.sudo().exists()
        return bool(
            partner
            and partner.commercial_partner_id.id == self._commercial_partner().id
        )

    def _equipment_is_allowed(self, equipment):
        equipment = equipment.sudo().exists()
        commercial_partner = self._commercial_partner()
        return bool(
            equipment
            and (
                equipment.propietario.commercial_partner_id.id == commercial_partner.id
                or equipment.ubicacion.commercial_partner_id.id == commercial_partner.id
            )
        )

    def _task_is_allowed(self, task):
        task = task.sudo().exists()
        return bool(
            task
            and (
                self._partner_is_allowed(task.cliente)
                or self._partner_is_allowed(task.ubicacion)
            )
        )

    @route(
        ["/my/sedes", "/my/sedes/page/<int:pagina>"],
        type="http",
        auth="user",
        website=True,
    )
    def sedes_portal(self, pagina=1, search=None):
        user_partner = self._portal_partner()
        commercial_partner = user_partner.commercial_partner_id
        dominio_web = request.httprequest.host
        registros_por_pagina = 15

        if user_partner == commercial_partner:
            dominio = [("parent_id", "=", commercial_partner.id), ("is_area", "=", False)]
        elif user_partner.is_area and user_partner.id_sede:
            dominio = [("id", "=", user_partner.id_sede.id)]
        else:
            dominio = [("id", "=", user_partner.id)]
        if search:
            dominio.append(("name", "ilike", search))

        partner_model = request.env["res.partner"].sudo()
        total_sedes = partner_model.search_count(dominio)
        total_paginas = max(1, ceil(total_sedes / registros_por_pagina))
        pagina = max(1, min(pagina, total_paginas))
        sedes = partner_model.search(
            dominio,
            limit=registros_por_pagina,
            offset=(pagina - 1) * registros_por_pagina,
            order="name",
        )

        equipment_domain = [
            "|",
            ("propietario", "child_of", commercial_partner.id),
            ("ubicacion", "child_of", commercial_partner.id),
        ]
        equipment_model = request.env["maintenance.equipment"].sudo()
        equipment_ids = equipment_model.search(equipment_domain).ids
        task_domain = [
            "|",
            ("cliente", "=", commercial_partner.id),
            ("ubicacion", "child_of", commercial_partner.id),
        ]
        tasks = request.env["tarea.mantenimiento"].sudo().search(task_domain)
        service_domain = [("tarea", "in", tasks.ids)]
        service_model = request.env["maintenance.request"].sudo()

        today = date.today()
        maintenance_plan_model = request.env["planequipo.mantenimiento"].sudo()
        upcoming_records = maintenance_plan_model.search(
            [
                ("equipo", "in", equipment_ids),
                ("fecha_ejecprox", "!=", False),
                ("fecha_ejecprox", ">=", today),
            ],
            order="fecha_ejecprox asc, id desc",
            limit=5,
        )
        upcoming_services = [
            {
                "record": plan,
                "days_remaining": (plan.fecha_ejecprox - today).days,
            }
            for plan in upcoming_records
        ]
        alert_candidates = maintenance_plan_model.search(
            [
                ("equipo", "in", equipment_ids),
                ("fecha_ejecprox", "!=", False),
            ],
            order="id desc",
        )
        latest_plan_by_equipment = {}
        for plan in alert_candidates:
            latest_plan_by_equipment.setdefault(plan.equipo.id, plan)
        alert_records = sorted(
            (
                plan
                for plan in latest_plan_by_equipment.values()
                if plan.fecha_ejecprox <= today + timedelta(days=30)
            ),
            key=lambda plan: (plan.fecha_ejecprox, -plan.id),
        )[:6]
        company_phone = "".join(
            character
            for character in (request.env.company.sudo().partner_id.phone or "")
            if character.isdigit()
        )
        maintenance_alerts = []
        for plan in alert_records:
            days_remaining = (plan.fecha_ejecprox - today).days
            status = "overdue" if days_remaining < 0 else ("today" if days_remaining == 0 else "soon")
            equipment = plan.equipo
            message = (
                f"Hola, deseo solicitar mantenimiento para el equipo {equipment.name or '-'}"
                f" (serie: {equipment.serial_no or '-'}, ubicación: "
                f"{equipment.ubicacion.name if equipment.ubicacion else '-'}). "
                f"Su próximo mantenimiento figura para el {plan.fecha_ejecprox.strftime('%d/%m/%Y')}."
            )
            maintenance_alerts.append({
                "record": plan,
                "days_remaining": days_remaining,
                "status": status,
                "whatsapp_url": f"https://wa.me/{company_phone}?text={urllib.parse.quote(message)}",
            })
        last_service = maintenance_plan_model.search(
            [("equipo", "in", equipment_ids), ("fecha_ejec", "!=", False)],
            order="fecha_ejec desc, id desc",
            limit=1,
        )

        return request.render("pmant.sedes_portal", {
            "sedes": sedes,
            "user_partner": user_partner,
            "dominio": dominio_web,
            "pagina_actual": pagina,
            "total_paginas": total_paginas,
            "search": search or "",
            "equipment_count": len(equipment_ids),
            "task_count": len(tasks),
            "active_service_count": service_model.search_count(service_domain + [("archive", "=", False)]),
            "request_count": request.env["servicio.solicitud"].sudo().search_count([("equipo_id", "in", equipment_ids)]),
            "recent_services": service_model.search(service_domain, order="write_date desc", limit=5),
            "upcoming_services": upcoming_services,
            "last_service": last_service,
            "maintenance_alerts": maintenance_alerts,
            "overdue_maintenance_count": sum(1 for item in maintenance_alerts if item["status"] == "overdue"),
            "due_soon_count": sum(1 for item in maintenance_alerts if item["status"] in ("today", "soon")),
        })


    # Areas de las sedes
    @route(
        [
            "/my/sede/<int:sede_id>/areas",
            "/my/sede/<int:sede_id>/areas/page/<int:pagina>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def areas_sede(self, sede_id, filtro=None, pagina=1, **kw):
        if not self._partner_is_allowed(request.env["res.partner"].sudo().browse(sede_id)):
            return request.not_found()
        # Número de registros por página
        per_page = 15
        domain = [("id_sede", "=", sede_id)]  # Filtrar por 'id_sede'

        # Si existe un filtro, agregarlo al dominio
        if filtro:
            domain.append(("name", "ilike", filtro))  # Filtrado por nombre del área

        user_partner = self._portal_partner()

        # Calcular el total de áreas y el número total de páginas
        total_areas = request.env["res.partner"].sudo().search_count(domain)
        total_paginas = max(1, ceil(total_areas / per_page))

        # Validación de la página solicitada
        pagina = max(1, min(pagina, total_paginas))  # Asegurar que la página esté dentro del rango

        # Calcular el offset para la página actual
        offset = (pagina - 1) * per_page

        # Obtener las áreas para la página actual
        areas = request.env["res.partner"].sudo().search(domain, limit=per_page, offset=offset, order="name")
        
        # Buscar la sede
        sede = request.env["res.partner"].sudo().browse(sede_id)

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
            "/my/sede/<int:sede_id>/equipos",
            "/my/sede/<int:sede_id>/equipos/page/<int:pagina>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def equipos_sede(self, sede_id, filtro=None, pagina=1, **kw):
        if not self._partner_is_allowed(request.env["res.partner"].sudo().browse(sede_id)):
            return request.not_found()
        # Número de registros por página
        per_page = 15
        domain = [("ubicacion", "=", sede_id)]
        user_partner = self._portal_partner()

        # Aplicar filtro si existe
        if filtro:
            domain.append(("name", "ilike", filtro))

        # Calcular el total de equipos y el número total de páginas
        total_equipos = request.env["maintenance.equipment"].sudo().search_count(domain)
        total_paginas = max(1, ceil(total_equipos / per_page))
        if total_equipos == 0 and not filtro:
            domain = [("propietario", "=", sede_id)]
            total_equipos = request.env["maintenance.equipment"].sudo().search_count(domain)
            total_paginas = max(1, ceil(total_equipos / per_page))

        pagina = max(1, min(pagina, total_paginas))

        # Calcular el offset para la página actual
        offset = (pagina - 1) * per_page

        # Obtener los equipos para la página actual
        equipos = (
            request.env["maintenance.equipment"]
            .sudo()
            .search(domain, limit=per_page, offset=offset, order="name")
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
            "/my/area/<int:sede_id>/equipos",
            "/my/area/<int:sede_id>/equipos/page/<int:pagina>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def equipos_areas(self, sede_id, filtro=None, pagina=1, **kw):
        if not self._partner_is_allowed(request.env["res.partner"].sudo().browse(sede_id)):
            return request.not_found()
        # Número de registros por página
        per_page = 15
        domain = [("area", "=", sede_id)]
        user_partner = self._portal_partner()

        # Aplicar filtro si existe
        if filtro:
            domain.append(("name", "ilike", filtro))

        # Calcular el total de equipos y el número total de páginas
        total_equipos = request.env["maintenance.equipment"].sudo().search_count(domain)
        total_paginas = max(1, ceil(total_equipos / per_page))
        if total_equipos == 0 and not filtro:
            domain = [("propietario", "=", sede_id)]
            total_equipos = request.env["maintenance.equipment"].sudo().search_count(domain)
            total_paginas = max(1, ceil(total_equipos / per_page))

        pagina = max(1, min(pagina, total_paginas))

        # Calcular el offset para la página actual
        offset = (pagina - 1) * per_page

        # Obtener los equipos para la página actual
        equipos = (
            request.env["maintenance.equipment"]
            .sudo()
            .search(domain, limit=per_page, offset=offset, order="name")
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
            "/my/<int:empresa_id>/equipos",
            "/my/<int:empresa_id>/equipos/page/<int:pagina>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def equipos_portal(self, empresa_id, pagina=1, search=None):
        if not self._partner_is_allowed(request.env["res.partner"].sudo().browse(empresa_id)):
            return request.not_found()
        user_partner = self._portal_partner()
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
        total_paginas = max(1, ceil(total_equipos / per_page))

        pagina = max(1, min(pagina, total_paginas))

        # Calcular el offset para la página actual
        offset = (pagina - 1) * per_page

        # Obtener los equipos para la página actual
        equipos = (
            request.env["maintenance.equipment"]
            .sudo()
            .search(domain, limit=per_page, offset=offset, order="name")
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


    # SOLICITUD DE REGISTRO DE EQUIPO
    @route(
        ["/solicitud/equipo"], type="http", auth="user", methods=["POST"], website=True
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
        user_partner = self._portal_partner()

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
        ubicacion = request.env["res.partner"].sudo().browse(int(ubicacion_id)) if ubicacion_id else user_partner
        if not self._partner_is_allowed(ubicacion):
            return request.not_found()

        # Crear el equipo en el modelo maintenance.equipment
        request.env["maintenance.equipment"].sudo().create({
            "propietario": user_partner.commercial_partner_id.id,
            "ubicacion": ubicacion.id,
            "name": nombre_equipo,
            "marca": marca_equipo,
            "model": modelo_equipo,
            "serial_no": numero_serie,
            "effective_date": fecha_registro,
            "image": image_data,
        })
        if ubicacion_id:
            return request.redirect(f"/my/sede/{int(ubicacion_id)}/equipos")

        # Redirigir a una página de éxito o mostrar un mensaje
        return request.redirect(f"/my/{user_partner.id}/equipos")

    # REGISTROS - DETALLES DEL EQUIPO

    @route(
        ["/my/equipos/<int:equipo_id>/detalles"], type="http", auth="user", website=True
    )
    def detalle_equipo(self, equipo_id, filtro=None, pagina=1, **kw):
        if not self._equipment_is_allowed(request.env["maintenance.equipment"].sudo().browse(equipo_id)):
            return request.not_found()
        user_partner = self._portal_partner()
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
        if not self._equipment_is_allowed(request.env["maintenance.equipment"].sudo().browse(equipo_id)):
            return request.not_found()

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
        total_paginas = max(1, ceil(total / per_page))

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
        if not self._equipment_is_allowed(request.env["maintenance.equipment"].sudo().browse(equipo_id)):
            return request.not_found()
        page = int(page)
        sort = request.params.get('sort', 'desc').lower()
        sort = sort if sort in ['asc', 'desc'] else 'desc'
        solicitudes_per_page = 10

        # Buscar las solicitudes de servicio de ese equipo
        dominio = [('equipo_id.id', '=', equipo_id)]
        total_solicitudes = request.env["servicio.solicitud"].sudo().search_count(dominio)
        equipo = request.env["maintenance.equipment"].sudo().browse(equipo_id)
        total_pages = max(1, ceil(total_solicitudes / solicitudes_per_page))
        page = max(1, min(page, total_pages))

        # Obtener las solicitudes ordenadas por fecha_servicio
        solicitudes = request.env["servicio.solicitud"].sudo().search(
            dominio,
            order=f"fecha_servicio {sort}",
            limit=solicitudes_per_page,
            offset=(page - 1) * solicitudes_per_page,
        )

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
        if not self._equipment_is_allowed(request.env["maintenance.equipment"].sudo().browse(equipo_id)):
            return request.not_found()
        equipo = request.env["maintenance.equipment"].sudo().browse(equipo_id)
        user_partner = self._portal_partner()

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
        user = self._portal_partner()
        commercial_partner = self._commercial_partner()
        equipments = request.env["maintenance.equipment"].sudo().search([
            "|",
            ("propietario", "child_of", commercial_partner.id),
            ("ubicacion", "child_of", commercial_partner.id),
        ])
        search = (kw.get("search") or "").strip().lower()
        active_services = []
        for equipment in equipments:
            for plan in equipment.planequipo:
                for work_order in plan.tarea.ots:
                    if work_order.stage_id.id not in (1, 2):
                        continue
                    searchable = " ".join(filter(None, [
                        equipment.name, equipment.serial_no,
                        plan.plan.name if plan.plan else "",
                        work_order.name, work_order.stage_id.name,
                    ])).lower()
                    if search and search not in searchable:
                        continue
                    active_services.append({
                        "equipment": equipment,
                        "plan": plan,
                        "work_order": work_order,
                    })

        active_services.sort(key=lambda item: (
            item["work_order"].schedule_date or datetime.max,
            item["work_order"].id,
        ))
        page = max(int(page), 1)
        page_size = 10
        total = len(active_services)
        page_services = active_services[(page - 1) * page_size:page * page_size]

        pager = request.website.pager(
            url="/my/servicios/ejecucion",
            total=total,
            page=page,
            step=page_size,
            scope=5,
            url_args={"search": search} if search else {},
        )

        return request.render(
            "pmant.servicios_ejecucion",
            {
                "active_services": page_services,
                "active_service_count": total,
                "equipment_service_count": len({item["equipment"].id for item in active_services}),
                "user": user,
                "search": search,
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
        if not self._equipment_is_allowed(request.env["maintenance.equipment"].sudo().browse(equipo_id)):
            return request.not_found()

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
        tarea = request.env["planequipo.mantenimiento"].sudo().browse(tarea_id)
        if not tarea.exists() or not self._equipment_is_allowed(tarea.equipo):
            return request.not_found()
        report_action = request.env["ir.actions.report"].sudo()
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

    @route(
        "/descargas/reporte/mantenimiento/<int:tarea_id>/otros",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def descarga_reporte_mantenimiento_otro(self, tarea_id, **kw):
        tarea = request.env["mantenimento.equipo.otros"].sudo().browse(tarea_id)
        if (
            not tarea.exists()
            or not tarea.file_adjunto
            or not self._equipment_is_allowed(tarea.equipo)
        ):
            return request.not_found()
        filename = urllib.parse.quote(tarea.file_name or f"reporte_mantenimiento_{tarea.id}.pdf")
        return request.make_response(
            base64.b64decode(tarea.file_adjunto),
            headers=[
                ("Content-Type", "application/octet-stream"),
                ("Content-Disposition", f"attachment; filename*=UTF-8''{filename}"),
            ],
        )
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
        if not adjunto.exists() or not adjunto.adjunto or not self._equipment_is_allowed(adjunto.equipo):
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
        if not documento.exists() or not documento.datas or not any(self._equipment_is_allowed(equipo) for equipo in documento.equipo):
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
    def certificados_operatividad_equipo(self, id_equipo, **kw):
        equipo = request.env["maintenance.equipment"].sudo().browse(id_equipo)
        if not self._equipment_is_allowed(equipo):
            return request.not_found()
        certificados_manuales = request.env["pmant.certificado.operatividad"].sudo().search(
            [("equipo_id", "=", equipo.id)],
            order="fecha_firma desc, id desc",
        )
        return request.render("pmant.certificados_equipo", {
            "equipo": equipo,
            "certificados_manuales": certificados_manuales,
            "upload_status": kw.get("upload"),
        })

    @route(
        ["/my/equipo/<int:id_equipo>/certificados/subir"],
        type="http",
        auth="user",
        methods=["POST"],
        website=True,
        csrf=True,
    )
    def subir_certificado_firmado(self, id_equipo, **post):
        equipo = request.env["maintenance.equipment"].sudo().browse(id_equipo)
        if not equipo.exists() or not self._equipment_is_allowed(equipo):
            return request.not_found()
        uploaded_file = request.httprequest.files.get("certificado_pdf")
        if not uploaded_file or not uploaded_file.filename:
            return request.redirect(f"/my/equipo/{equipo.id}/certificados?upload=missing")
        content = uploaded_file.read(10 * 1024 * 1024 + 1)
        filename = re.sub(r"[^A-Za-z0-9._ -]", "_", uploaded_file.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
        if len(content) > 10 * 1024 * 1024:
            return request.redirect(f"/my/equipo/{equipo.id}/certificados?upload=size")
        if not filename.lower().endswith(".pdf") or not content.startswith(b"%PDF-"):
            return request.redirect(f"/my/equipo/{equipo.id}/certificados?upload=type")
        try:
            signed_date = fields.Date.to_date(post.get("fecha_firma")) if post.get("fecha_firma") else fields.Date.context_today(equipo)
        except (TypeError, ValueError):
            signed_date = fields.Date.context_today(equipo)
        certificate_name = (post.get("nombre_certificado") or filename.rsplit(".", 1)[0]).strip()[:120]
        request.env["pmant.certificado.operatividad"].sudo().create({
            "name": certificate_name or "Certificado firmado",
            "equipo_id": equipo.id,
            "archivo_firmado": base64.b64encode(content),
            "nombre_archivo": filename[:255],
            "fecha_firma": signed_date,
            "usuario_id": request.env.user.id,
            "origen": "portal",
        })
        return request.redirect(f"/my/equipo/{equipo.id}/certificados?upload=success")

    @route(
        ["/descargas/certificado/manual/<int:certificate_id>"],
        type="http",
        methods=["GET"],
        auth="user",
        website=True,
    )
    def descarga_certificado_manual(self, certificate_id):
        certificate = request.env["pmant.certificado.operatividad"].sudo().browse(certificate_id)
        if not certificate.exists() or not self._equipment_is_allowed(certificate.equipo_id):
            return request.not_found()
        content = base64.b64decode(certificate.archivo_firmado or b"")
        if not content:
            return request.not_found()
        filename = urllib.parse.quote(certificate.nombre_archivo or "certificado-firmado.pdf")
        return request.make_response(content, headers=[
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(content)),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
        ])

    # RUTA PARA LOS ADJUNTOS DEL EQUIPO
    @route(
        ["/descargas/certificado/equipo/<int:id_adjunto>"],
        type="http",
        methods=["GET"],
        auth="user",
        website=True,
    )
    def descarga_certificado_equipo(self, id_adjunto):
        sign_request = request.env["sign.request"].sudo().browse(id_adjunto)
        if not sign_request.exists() or not self._equipment_is_allowed(sign_request.equipo_id):
            return request.not_found()
        attachment = request.env["ir.attachment"].sudo().search([("name", "ilike", "Certificado"),("res_model", "=", "sign.request"),("res_id", "=", id_adjunto)], limit=1)
        if not attachment or not attachment.datas:
            return request.not_found()
        file_content_decoded = base64.b64decode(attachment.datas)

        # Generar encabezado manualmente
        filename = urllib.parse.quote(attachment.name or "archivo.bin")
        headers = [
            ("Content-Type", attachment.mimetype),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
        ]
        return request.make_response(file_content_decoded, headers=headers)



    @route('/solicitud/mantenimiento/servicio', type='http', auth='user', methods=['POST'], csrf=True)
    def recibir_solicitud_servicio(self, **post):
        is_ajax = request.httprequest.headers.get("X-Requested-With") == "XMLHttpRequest"
        try:
            _logger.info("Procesando una solicitud de servicio del portal")

            # Extraer datos del formulario
            id_equipo = int(post.get('id_equipo') or 0)
            ubicacion_id = int(post.get('ubicacion_id') or 0)
            tipo_servicio = post.get('tipo_servicio')
            fecha_servicio = post.get('fecha_servicio')
            razon = post.get('razon')

            if not all((id_equipo, ubicacion_id, tipo_servicio, fecha_servicio, razon)):
                if is_ajax:
                    return request.make_json_response({"result": {"success": False, "message": "Complete los campos obligatorios."}}, status=400)
                return request.render("pmant.error_template", {"error": "Complete todos los campos obligatorios."})

            equipo = request.env['maintenance.equipment'].sudo().browse(id_equipo)
            ubicacion = request.env['res.partner'].sudo().browse(ubicacion_id)
            if not self._equipment_is_allowed(equipo) or not self._partner_is_allowed(ubicacion):
                return request.not_found()


            # Obtener archivo
            file = request.httprequest.files.get('formFileMultiple')
            file_encoded = False
            filename = False
            if file:
                _logger.info("Solicitud con archivo adjunto: %s", file.filename)
                file_content = file.read(8 * 1024 * 1024 + 1)
                if len(file_content) > 8 * 1024 * 1024 or not (file.mimetype or "").startswith("image/"):
                    if is_ajax:
                        return request.make_json_response({"result": {"success": False, "message": "La imagen debe ser válida y pesar menos de 8 MB."}}, status=400)
                    return request.render("pmant.error_template", {"error": "La imagen debe ser válida y pesar menos de 8 MB."})
                file_encoded = base64.b64encode(file_content)
                filename = file.filename
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
            _logger.info("Solicitud de servicio %s creada", solicitud.id)

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

            destinatarios = [u.email for u in internal_users]
            if request.env.user and request.env.user.email:
                destinatarios.append(request.env.user.email)

            # Enviar correo
            try:
                mail = request.env['mail.mail'].sudo().create({
                    'subject': f'Solicitud de Servicio - {tipo_servicio}',
                    'email_to': ','.join(destinatarios),
                    'body_html': html_body,
                })
                mail.send()
                _logger.info("Correo de la solicitud %s enviado", solicitud.id)
            except Exception as mail_error:
                _logger.exception("No se pudo enviar el correo de la solicitud %s", solicitud.id)

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
                        'author_id': self._portal_partner().id,
                        'partner_ids': [(4, user.partner_id.id)],
                    })

            redirect_url = f"/my/equipo/{id_equipo}/solicitudes/servicios"
            if is_ajax:
                return request.make_json_response({"result": {"success": True, "redirect_url": redirect_url}})
            return request.redirect(redirect_url)

        except Exception as e:
            _logger.exception("Error procesando una solicitud de servicio del portal")
            if is_ajax:
                return request.make_json_response({"result": {"success": False, "message": "No se pudo registrar la solicitud."}}, status=500)
            return request.render("pmant.error_template", {"error": "No se pudo registrar la solicitud."})




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
        equipo = request.env["maintenance.equipment"].sudo().browse(id_equipo)
        if not equipo.exists() or not self._equipment_is_allowed(equipo):
            return request.not_found()
        per_page = 12  # Número de registros por página
        # Obtener todas las tareas relacionadas con el equipo y con tipo "Evaluación"
        domain = [
            ("planequipo.equipo", "=", equipo.id),
            ("is_evaluacion", "=", True),
        ]
        total_tareas = (
            request.env["tarea.mantenimiento"].sudo().search_count(domain)
        )  # Total de tareas
        total_paginas = max(1, ceil(total_tareas / per_page))
        pagina = max(1, min(int(pagina), total_paginas))
        offset = (pagina - 1) * per_page
        tareas = (
            request.env["tarea.mantenimiento"]
            .sudo()
            .search(domain, limit=per_page, offset=offset, order="create_date desc, id desc")
        )  # Tareas por página

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
        report_action = request.env["ir.actions.report"].sudo()
        tarea = request.env["tarea.mantenimiento"].sudo().browse(tarea_id)
        if not tarea.exists() or not self._task_is_allowed(tarea):
            return request.not_found()
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
        if not self._partner_is_allowed(request.env["res.partner"].sudo().browse(id_ubicacion)):
            return request.not_found()
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
        auth="user",
        website=True,
    )
    def download_plaequipo(self, planequipo):
        plan_equipo = request.env["planequipo.mantenimiento"].sudo().browse(planequipo)
        if not plan_equipo.exists() or not self._equipment_is_allowed(plan_equipo.equipo):
            return request.not_found()
        # Renderizar el PDF pasando el ID de la ubicación como una lista
        pdf = (
            request.env.ref("pmant.action_reporte_cert_operatividad")
            .sudo()
            ._render_qweb_pdf([planequipo])[0]
        )

        # Definir las cabeceras para la descarga del PDF
        pdfhttpheaders = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf)),
            (
                "Content-Disposition",
                'attachment; filename="Certificado-operatividad.pdf"',
            ),
        ]

        # Retornar la respuesta para descargar el archivo
        return request.make_response(pdf, headers=pdfhttpheaders)


    @route("/calificacion/<int:order_id>", type="http", auth="user", website=True)
    def page_calificacion(self, order_id, **kwargs):
        order = request.env["maintenance.request"].sudo().browse(int(order_id))
        if not order.exists() or not self._partner_is_allowed(order.empresa):
            return request.not_found()
        return request.render("pmant.form_calificaciones", {"object": order})


    @route(
        "/rate_service", type="http", auth="user", methods=["POST"], csrf=True
    )
    def rate_service(self, **post):
        order_id = post.get("order_id")
        ratings = [int(post.get(key) or 0) for key in ("p1", "p2", "p3")]
        comment = post.get("comment", "")

        if order_id:
            order = request.env["maintenance.request"].sudo().browse(int(order_id))
            if order.exists() and self._partner_is_allowed(order.empresa) and all(1 <= value <= 5 for value in ratings):
                order.sudo().write(
                    {
                        "rating_p1": ratings[0],
                        "rating_p2": ratings[1],
                        "rating_p3": ratings[2],
                        "rating_comment": comment,
                    }
                )

        return request.redirect("/gracias")

    @route("/gracias", type="http", auth="public", website=True)
    def page_gracias(self, **kwargs):

        return request.render("pmant.page_gracias_form")

    @route('/guardar/medicion/equipo', type='jsonrpc', auth='user', csrf=False)
    def guardar_medicion_equipo(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            equipo_id = int(data.get('equipo_id', 0))
            hora_uso = float(data.get('uso_promedio', 0.0))
            temperatura_elemento = float(data.get('temperatura', 0.0))
            presion_actual = float(data.get('presion', 0.0))
            temperatura_ambiente = float(data.get('tem_ambiente', 0.0))
            equipo = request.env['maintenance.equipment'].sudo().browse(equipo_id)
            if not self._equipment_is_allowed(equipo):
                return {"success": False, "message": "Equipo no autorizado"}
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


