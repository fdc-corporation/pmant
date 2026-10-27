# PMANT unificado

Desde la versión `19.0.3.0.0`, `pmant` contiene directamente las funcionalidades
que antes estaban repartidas entre:

- `pmant_alert_notification`
- `pmant_checklist`
- `pmant_stock_move`

Los tres módulos anteriores se conservan únicamente como puentes de migración y
ya no importan modelos, controladores, vistas ni datos propios.

## Actualización de una base existente

1. Hacer una copia de seguridad de la base de datos y del filestore.
2. Actualizar juntos `pmant`, `pmant_alert_notification`, `pmant_checklist` y
   `pmant_stock_move`.
3. Verificar alertas, checklist, recepción de equipos y movimientos de repuestos.
4. Desinstalar los tres módulos puente cuando la validación haya terminado.
5. Reiniciar Odoo y actualizar la lista de aplicaciones.

No se deben eliminar manualmente las tablas de checklist, requerimientos o
movimientos: `pmant` usa los mismos nombres técnicos de modelo y conserva esos
datos.

## Instalaciones nuevas

Solo es necesario instalar `pmant`. Los módulos puente no deben instalarse.

