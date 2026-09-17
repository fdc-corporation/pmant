from odoo import models, fields, api


def _get_defaultx(self):
    return """
     <p><font style="font-size: 18px;">señores:</font></p> 
     <p><font style="font-size: 18px;">@propietario@ </font></p> 
     <p><font style="font-size: 18px;">RUC: @propietario_ruc@</font></p> 
     <p><font style="font-size: 18px;">Dirección: @propietario_direccion@</font></p> 
     <p><font style="font-size: 14px;"><br></font></p> <p style="text-align: center; "> 
     <b><font style="font-size: 36px;">CERTIFICADO DE OPERATIVIDAD</font></b></p> 
     <p style="text-align: justify;"> 
     <span style='background-color: rgb(250, 250, 250); color: rgb(46, 46, 46); 
     font-family: "Whitney normal A", "Whitney normal B", "Whitney A", "Whitney B", Arial; 
     font-size: 18px; letter-spacing: -0.1px; text-align: start;'>Mediante la presente FDC CORP extiende el certificado de operatividad del equipo en referencia el cual cuenta con las condiciones óptimas de funcionamiento en base a las recomendaciones indicadas para su próximo mantenimiento. El equipo se encuentra ubicado en @equipo_ubicacion@.</span><br><br><b>
     <font style="font-size: 18px;"><u>Datos del Equipo:</u></font></b></p>
     <p style="text-align: justify;"> <br>
     <font style="font-size: 18px;">Denominación del Equipo: @equipo@</font></p>
     <p style="text-align: justify;"><font style="font-size: 18px;">Marca: @marca@<br></font></p>
     <p style="text-align: justify;"><font style="font-size: 18px;">Procedecia: @procedencia@</font></p>
     <p style="text-align: justify;"><font style="font-size: 18px;">Modelo: @modelo@</font></p>
     <p style="text-align: justify;"><font style="font-size: 18px;">Serie: @serie@</font></p>
     <p style="text-align: justify;"><font style="font-size: 18px;">Fecha de Mantenimiento: @fecha@</font></p>
     <p style="text-align: justify;"><font style="font-size: 18px;">Plan: @plan@</font></p>
     <p style="text-align: justify;"><font style="font-size: 18px;">Vencimiento del Certificado @vence@</font></p>
     <p style="text-align: justify;"><font style="font-size: 18px;"><br></font>
     <span style="font-size: 14px;"><u><b>Recomendaciones:<br></b>
     </u>realizar el mantenimiento preventivo de acuerdo al programa</span><br><br></p>
   """
def _get_plantillaticket(self):
    return """
       <div style="text-align: left;"><small><b><font style="font-size: 14px;">Equipo:</font></b><font style="font-size: 14px;">  </font><span style="font-weight: normal;"><font style="font-size: 14px;">@equipo@</font><br><b><font style="font-size: 14px;">Marca:</font></b><font style="font-size: 14px;"> @marca@   </font><b><font style="font-size: 14px;">Modelo:</font></b><font style="font-size: 14px;"> @modelo@   </font><b><font style="font-size: 14px;">Serie:</font></b><font style="font-size: 14px;"> @serie@</font></span></small><br><small><b><font style="font-size: 14px;">Fecha de Mantenimiento: </font></b><font style="font-size: 14px;">@fecha@</font></small><small><b><font style="font-size: 14px;">  Fecha Proximo Servicio:</font></b><font style="font-size: 14px;"> @vence@</font></small></div> 
    """

def concat_direccion(contac):
    dd=""
    direc =  str(contac.street)+" "
    if contac.street != False:
        dd+=direc
    direc2 =  str(contac.street2)+" - "
    if contac.street2 != False:
        dd+=direc2
    city = str(contac.city)+" - "
    if contac.city != False:
        dd+=city
    state = str(contac.state_id.name)+" - "
    if contac.state_id.name != False:
        dd+=state
    country = str(contac.country_id.name)
    if contac.country_id.name != False:
        dd+=country
    return dd

def cont_reemplaze(contenidox,self):
    contenido = contenidox
    contenido = contenido.replace('@propietario@',self.planequipo.equipo.propietario.name)
    ruc = self.planequipo.equipo.propietario.vat
    if ruc==False:
        ruc = "N/A"
    contenido = contenido.replace('@propietario_ruc@',ruc)
    dd = concat_direccion(self.planequipo.equipo.propietario)
    contenido = contenido.replace('@propietario_direccion@',dd)
    ubi = concat_direccion(self.planequipo.equipo.ubicacion)
    contenido = contenido.replace('@equipo_ubicacion@',ubi)
    contenido = contenido.replace('@equipo@',self.planequipo.equipo.name)
    marca = self.planequipo.equipo.marca
    if marca == False:
        marca = "N/A"
    contenido = contenido.replace('@marca@',marca)
    proce = self.planequipo.equipo.partner_id.country_id.name
    if proce == False:
        proce = "N/A"
    contenido = contenido.replace('@procedencia@',proce)
    modelo = self.planequipo.equipo.model
    if modelo == False:
        modelo = "N/A"
    contenido = contenido.replace('@modelo@',modelo)
    serie = self.planequipo.equipo.serial_no
    if serie == False:
        serie = "N/A"
    contenido = contenido.replace('@serie@',serie)
    vence = str(self.planequipo.fecha_ejecprox)
    if vence == False:
        vence = "N/A"
    contenido = contenido.replace('@vence@',vence)
    plan = self.planequipo.plan.tipo.name
    if plan == False:
        plan = "N/A"
    contenido = contenido.replace('@plan@',plan)
    ult = str(self.planequipo.fecha_ejec)
    if ult == False:
        ult = "N/A"
    contenido = contenido.replace('@fecha@',str(ult))
    return contenido

class Plantilla(models.Model):
    _name = 'plantilla.mantenimiento'
    name = fields.Char(size=25, required=True)
    contenido = fields.Html(default=_get_defaultx('1'), required=True)
    firma = fields.Binary()
    pie = fields.Char(default="*Terminos y condiciones de acuerdo a https://www.fdc-corporation.com/")

class PlantillaTicket(models.Model):
    _name = 'plantillaticket.mantenimiento'
    name = fields.Char(size=25, required=True)
    contenido = fields.Html(default=_get_plantillaticket('1'), required=True)
    smsqr = fields.Char(default="Conoce el Historial de este equipo Aqui")