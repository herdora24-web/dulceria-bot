"""
================================================================
AGENTE VENDEDOR - DISTRIBUIDORA ALEJANDRA MARÍA v3
Flask + Claude API + Google Sheets + Vision + Whisper
ARQUITECTURA: Manejo de estados por cliente
================================================================
ESTADOS:
  identificacion  → esperando cédula, nombre, destino, motonave
  tomando_pedido  → recibiendo productos
  confirmando     → esperando que el cliente confirme el resumen
  eligiendo_pago  → esperando método de pago
  esperando_comprobante → esperando foto/confirmación de pago
  cerrado         → pedido registrado y cerrado
================================================================
VARIABLES DE ENTORNO en Railway:
  ANTHROPIC_API_KEY
  WHATSAPP_TOKEN / VERIFY_TOKEN / PHONE_NUMBER_ID
  OPENAI_API_KEY
  GOOGLE_CREDENTIALS_JSON
  GOOGLE_SHEET_ID_DULCERIA
================================================================
"""

import os, json, base64, requests, tempfile, re
from datetime import datetime
from flask import Flask, request, jsonify
import anthropic, gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
claude_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# ── Catálogo en memoria ───────────────────────────────────────
catalogo_cache = []   # lista de dicts {ID, NOMBRE, CODIGO_BARRAS, UNIDAD, PRECIO, CATEGORIA}

# ── Estado por cliente ────────────────────────────────────────
# sesiones[numero] = {
#   "estado": str,
#   "cedula": str, "nombre": str, "destino": str, "motonave": str,
#   "items": [ {nombre, cantidad, precio, codigo} ],
#   "metodo_pago": str,
#   "historial": [ {role, content} ]
# }
sesiones = {}

# ══════════════════════════════════════════════════════════════
# DICCIONARIO DE APODOS
# ══════════════════════════════════════════════════════════════
APODOS = {
    "pin pon polvo acido": "PIN PON MANGO VICHE",
    "pin pon acido": "PIN PON MANGO VICHE",
    "ristra de ponky": "PONKY X8 X24TIR/VAINILLA",
    "ristra ponky": "PONKY X8 X24TIR/VAINILLA",
    "ponky vainilla": "PONKY X8 X24TIR/VAINILLA",
    "ponky frutos rojos": "PONKY X8 X24TIR/FRUTOS ROJO",
    "ristra de chupi won": "CHUPI WOM RISTRA X24X24",
    "ristra chupi won": "CHUPI WOM RISTRA X24X24",
    "chao 5 pepas": "CHAO LINEA",
    "splot 5 pepas": "SPLOT LINEA",
    "leche de chocolate": "ALPIN",
    "tumix amarillo": "TUMIX MENTA",
    "jalea de fresa": "MERMELADA DE FRESA",
    "torta pastel": "TORTA REDONDA",
    "chuspa pastel": "TORTA REDONDA",
    "pastel": "TORTA REDONDA",
    "vaso para gaseosa": "VASO 7 ONZ",
    "yupi caramelo pequeñito": "SNACKY",
    "labios rojos": "BON BON TRES CORAZONES",
    "pinta corazon": "BON BON TRES CORAZONES",
    "boca dulce": "BOQUITA DULCE",
    "rosquilla morada": "ROSQUILLA FLAMINHOT",
    "yupi salado": "YUPI SAL",
    "loka loka": "COLA LOKA",
    "bianchi largo": "BIANCHI BARRA",
    "ganchela de aceite": "BIDON DE ACEITE",
    "galoneta de aceite": "BIDON DE ACEITE",
    "displey huevito": "HUEVO FRITO",
    "huevo dulce": "HUEVO FRITO",
    "pirulito de sal": "MANGOS",
    "bon bon con sal": "MANGOS",
    "super bon": "PEGANTE GREEN POWER",
    "bon bon de pasas": "MORDISQUETA",
    "mantecada": "TORTA CUADRADA",
    "platanitos con sal": "PRIMAVERA VERDE",
    "menta anisada": "BANANA ANISADA",
    "banana ani": "BANANA ANISADA",
    "bonbon grande de coco": "BIG BOM XXL X 48 UND CROCOCO",
    "saltin tradicional": "GALLETA SALTIN X 5",
    "saltin roja": "GALLETA SALTIN X 5",
    "aros de trigo limon": "ROSQUILLA LIMON X 30",
    "detodito amarillo": "DETODITO MIX",
    "detodito bbq": "DETODITO ROJO",
    "detodito natural": "DETODITO AZUL",
    "boliqueso economico": "BOLIQUESOX 25G",
    "bon bon azul": "BIG BOM DIAMANTE",
    "palomita pinguino": "POPETA",
    "jabon de color": "LIMPIDO ROPA COLOR",
    "banana envuelta": "BANANA DULCE RELLENO AMERICANDY",
    "menta saborizada": "MENTA HELADA SURTIDA",
    "rosquilla picante": "RODELIS FLAMING",
    "rulita limon": "PAPA RULITAS X24/LIMON",
    "rulita morada": "PAPA RULITAS X24/MORADA",
    "rulita roja": "PAPA RULITAS X24/ROJO",
    "rulita pollo": "PAPA RULITAS X24/POLLO",
    "rulita mayonesa": "PAPA RULITAS X24/MAYONESA",
    "papa salsa grande": "PAPA SALSA GRANDE X12",
    "papita grande": "PAPA SALSA GRANDE X12",
    "papa salsa pequeña": "PAPA SALSA PEQUENA X12",
    "arequipe x 6": "PROLECHE X 6 UND",
    "tira de proleche": "KLIM RISTRA X 16",
    "tostada": "TOSTADA PAN VALLE X 12 UND",
    "mallita acida": "MALLITA X 15 UND",
    "gelatina pequeña": "GELA PLAY X 10 UND",
    "gelatina grande": "GELA PLAY X 50 UND",
    "torta mantecada": "TORTA CUADRADA X 15 UND",
    "galleta azucarada": "CUCA AZUCARADA",
    "galleta mantecada": "CUCA MANTECADA",
    "galleta waffer": "GALLETA CAPRI",
    "display de rico": "CALDO RICO X 54 CUBOS",
    "pool personal": "GASEOSA POOL X 400 ML",
    "madurito": "PRIMAVERA MADURO",
}

# Productos con múltiples variantes — el bot debe preguntar el sabor
PRODUCTOS_CON_VARIANTES = {
    "bon bon bum": {
        "opciones": ["Surtido", "Rojo", "Tropical Surtido", "Cereza Intensa", "Fresa Intensa",
                     "Zombie", "Sandía Sensación", "Manzana Postobón", "Pink", "Halloween", "Fresa"],
        "precio_referencia": 146000,
        "unidad": "cartón (ctn)"
    },
    "rulita": {
        "opciones": ["Limón", "Morada", "Roja", "Pollo", "Mayonesa"],
        "precio_referencia": 7100,
        "unidad": "display"
    },
    "ponky": {
        "opciones": ["Vainilla ($9.200)", "Frutos Rojos ($12.700)", "Torta Negra ($9.200)",
                     "Leche Vainilla ($12.700)", "Choco Caramelo ($12.700)"],
        "precio_referencia": 9200,
        "unidad": "display"
    },
}

# ══════════════════════════════════════════════════════════════
# GOOGLE SHEETS
# ══════════════════════════════════════════════════════════════

def get_google_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
    return gspread.authorize(creds)


def cargar_catalogo():
    global catalogo_cache
    try:
        gc = get_google_client()
        sheet = gc.open_by_key(os.environ.get("GOOGLE_SHEET_ID_DULCERIA"))
        catalogo_cache = sheet.worksheet("Catalogo").get_all_records()
        print(f"✅ Catálogo cargado: {len(catalogo_cache)} productos")
    except Exception as e:
        print(f"❌ Error cargando catálogo: {e}")
        catalogo_cache = []


def limpiar_precio(valor) -> float:
    """Convierte precio en cualquier formato a float."""
    try:
        s = str(valor).strip().replace("$", "").replace(" ", "")
        # Si tiene coma y punto: 1.234,56 → separador miles=punto, decimal=coma
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        # Si solo tiene coma: 9,200 → separador miles
        elif "," in s:
            s = s.replace(",", "")
        # Si solo tiene punto y más de 2 decimales: 9.200 → miles
        elif "." in s and len(s.split(".")[-1]) == 3:
            s = s.replace(".", "")
        return float(s) if s else 0.0
    except:
        return 0.0


def buscar_producto(nombre_buscado: str) -> dict | None:
    nombre_buscado = nombre_buscado.upper().strip()
    for prod in catalogo_cache:
        if prod.get("NOMBRE", "").upper().strip() == nombre_buscado:
            return prod
    for prod in catalogo_cache:
        if nombre_buscado in prod.get("NOMBRE", "").upper():
            return prod
    # Búsqueda por palabras clave individuales
    palabras = [p for p in nombre_buscado.split() if len(p) > 3]
    if palabras:
        for prod in catalogo_cache:
            nombre_prod = prod.get("NOMBRE", "").upper()
            if all(p in nombre_prod for p in palabras):
                return prod
    return None


ADMIN_WHATSAPP = "573160511288"  # Número administradora para escalamiento

def registrar_en_sheets(sesion: dict, telefono: str):
    """Registra en Logistica y crea pestaña individual por pedido."""
    try:
        gc = get_google_client()
        sheet = gc.open_by_key(os.environ.get("GOOGLE_SHEET_ID_DULCERIA"))
        ahora = datetime.now()
        items = sesion.get("items", [])
        nombre = sesion.get("nombre", "cliente")
        resumen = " | ".join([f"{i['nombre']} x{int(i['cantidad'])}" for i in items])

        # ── Hoja Logistica ────────────────────────────────────
        ws_log = sheet.worksheet("Logistica")
        ws_log.append_row([
            ahora.strftime("%d/%m/%Y"),
            ahora.strftime("%H:%M"),
            sesion.get("cedula", ""),
            nombre,
            telefono,
            sesion.get("destino", ""),
            sesion.get("motonave", ""),
            resumen,
            sesion.get("metodo_pago", ""),
            "EMPAQUE"
        ])

        # ── Pestaña individual por pedido ─────────────────────
        # Nombre: PrimerNombre_HH:MM (máx 50 chars, sin caracteres inválidos)
        primer_nombre = nombre.split()[0] if nombre else "Cliente"
        hora_str = ahora.strftime("%H%M")
        nombre_pestaña = f"{primer_nombre}_{hora_str}"[:50]
        # Limpiar caracteres no permitidos en nombres de hojas
        for c in [":", "/", "\\", "?", "*", "[", "]"]:
            nombre_pestaña = nombre_pestaña.replace(c, "")

        try:
            ws_ped = sheet.add_worksheet(title=nombre_pestaña, rows=100, cols=11)
        except Exception:
            # Si ya existe, agregar sufijo
            nombre_pestaña = nombre_pestaña + "_2"
            ws_ped = sheet.add_worksheet(title=nombre_pestaña, rows=100, cols=11)

        # Encabezado idéntico al formato Importar_Software
        ws_ped.append_row([
            "Referencia o codigo de barras", "Nombre", "Precio Unitario",
            "Cantidad", "Descuento", "Impuesto", "SubTotal (No modificar)",
            "Estampilla(sino Aplica 0)", "Impoconsumo(sino Aplica 0)",
            "Total (No modificar)", "id_plan_cuenta (opcional solo Egresos)"
        ])
        # Info del cliente en fila 2
        ws_ped.append_row([
            f"Cliente: {nombre}", f"Cédula: {sesion.get('cedula','')}",
            f"Tel: {telefono}", f"Destino: {sesion.get('destino','')}",
            f"Motonave: {sesion.get('motonave','')}",
            f"Fecha: {ahora.strftime('%d/%m/%Y %H:%M')}",
            f"Pago: {sesion.get('metodo_pago','')}",
            "", "", "", ""
        ])
        ws_ped.append_row([""] * 11)  # Fila vacía separadora

        total = calcular_total(items)
        for item in items:
            subtotal = round(item["cantidad"] * item["precio"], 0)
            ws_ped.append_row([
                item.get("codigo", ""),
                item["nombre"],
                item["precio"],
                item["cantidad"],
                0, 0, subtotal, 0, 0, subtotal, ""
            ])

        # Fila de total al final
        ws_ped.append_row(["", "TOTAL PEDIDO", "", "", "", "", "", "", "", total, ""])

        print(f"✅ Registrado: {nombre} — pestaña {nombre_pestaña} — {len(items)} productos")
        return True
    except Exception as e:
        print(f"❌ Error registrando: {e}")
        return False


def verificar_comprobante_vision(image_id: str, sesion: dict) -> dict:
    """
    Descarga el comprobante y lo analiza con Claude Vision.
    Retorna: {valido: bool, confianza: alta/baja, detalle: str, valor_detectado: int}
    """
    try:
        token = os.environ.get("WHATSAPP_TOKEN")
        headers = {"Authorization": f"Bearer {token}"}
        url_info = requests.get(
            f"https://graph.facebook.com/v18.0/{image_id}", headers=headers
        ).json()
        img_resp = requests.get(url_info.get("url"), headers=headers)
        image_data = base64.standard_b64encode(img_resp.content).decode("utf-8")
        media_type = img_resp.headers.get("Content-Type", "image/jpeg")

        total_esperado = calcular_total(sesion["items"])
        nombre_cliente = sesion["nombre"]
        metodo = sesion.get("metodo_pago", "")

        resp = claude_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=400,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": image_data
                }},
                {"type": "text", "text": f"""
Analiza este comprobante de pago de {metodo} colombiano.

Datos esperados:
- Nombre del cliente que debió realizar el pago: {nombre_cliente}
- Valor esperado del pedido: ${total_esperado:,}

Responde SOLO con JSON:
{{
  "es_comprobante": true/false,
  "valor_detectado": número o 0,
  "nombre_detectado": "nombre en el comprobante o vacío",
  "valor_correcto": true/false,
  "confianza": "alta" o "baja",
  "observacion": "breve descripción de lo que ves"
}}

Si la imagen no es un comprobante de pago, pon es_comprobante: false.
"""}
            ]}]
        )
        resultado = resp.content[0].text.strip()
        if "```" in resultado:
            resultado = resultado.split("```")[1]
            if resultado.startswith("json"):
                resultado = resultado[4:]
        datos = json.loads(resultado.strip())
        return datos
    except Exception as e:
        print(f"Error verificando comprobante: {e}")
        return {"es_comprobante": False, "valor_correcto": False, "confianza": "baja", "observacion": str(e)}


def notificar_admin(numero_cliente: str, sesion: dict, motivo: str, image_id: str = ""):
    """Envía alerta a la administradora para revisión manual."""
    try:
        total = calcular_total(sesion["items"])
        nombre = sesion["nombre"]
        items_str = "\n".join([f"  - {i['nombre']} x{int(i['cantidad'])}" for i in sesion["items"]])
        mensaje = (
            f"🔔 *VERIFICACIÓN REQUERIDA*\n\n"
            f"Cliente: {nombre}\n"
            f"Tel: {numero_cliente}\n"
            f"Total pedido: ${total:,}\n"
            f"Pago: {sesion.get('metodo_pago','')}\n"
            f"Destino: {sesion['destino']} — {sesion['motonave']}\n\n"
            f"Productos:\n{items_str}\n\n"
            f"⚠️ Motivo: {motivo}\n\n"
            f"Responde *ok {numero_cliente}* para aprobar o *rechazar {numero_cliente}* para rechazar."
        )
        enviar_whatsapp(ADMIN_WHATSAPP, mensaje)
        print(f"📨 Admin notificada: {motivo}")
    except Exception as e:
        print(f"Error notificando admin: {e}")


# ══════════════════════════════════════════════════════════════
# CLAUDE — LLAMADAS ESPECÍFICAS POR TAREA
# ══════════════════════════════════════════════════════════════

def claude_extraer_identificacion(texto: str) -> dict | None:
    """Extrae cédula, nombre, destino y motonave del mensaje del cliente."""
    try:
        resp = claude_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=300,
            messages=[{"role": "user", "content": f"""
Extrae del siguiente mensaje los datos de identificación de un cliente de una distribuidora.
Responde SOLO con JSON, sin explicaciones.
Si no encuentras algún dato, usa cadena vacía "".

Mensaje: "{texto}"

Formato de respuesta:
{{"cedula":"...","nombre":"...","destino":"...","motonave":"..."}}

Notas:
- cedula: número de identificación
- nombre: nombre completo
- destino: municipio, corregimiento o zona
- motonave: nombre del barco o motonave
"""}]
        )
        resultado = resp.content[0].text.strip()
        if resultado.startswith("{"):
            return json.loads(resultado)
    except Exception as e:
        print(f"Error extrayendo identificación: {e}")
    return None


def claude_extraer_productos(texto: str, historial_pedido: list) -> dict:
    """
    Extrae productos del mensaje del cliente.
    Devuelve: {productos_encontrados, productos_con_variante, texto_respuesta}
    """
    apodos_str = json.dumps(APODOS, ensure_ascii=False)
    variantes_str = json.dumps(PRODUCTOS_CON_VARIANTES, ensure_ascii=False)

    pedido_actual = ""
    if historial_pedido:
        pedido_actual = "Productos ya anotados:\n" + "\n".join(
            [f"- {i['nombre']} x{i['cantidad']} = ${i['precio']:,}" for i in historial_pedido]
        )

    try:
        resp = claude_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=800,
            messages=[{"role": "user", "content": f"""
Eres el sistema de procesamiento de pedidos de Distribuidora Alejandra María en Buenaventura.

DICCIONARIO DE APODOS (nombre cliente → nombre oficial):
{apodos_str}

PRODUCTOS CON VARIANTES (requieren preguntar sabor):
{variantes_str}

{pedido_actual}

MENSAJE DEL CLIENTE: "{texto}"

Analiza el mensaje y extrae los productos pedidos.
Responde SOLO con JSON exactamente así:

{{
  "productos_encontrados": [
    {{"nombre_oficial": "NOMBRE EXACTO DEL CATALOGO", "cantidad": 1}}
  ],
  "productos_con_variante": [
    {{"producto_base": "bon bon bum", "cantidad": 1}}
  ],
  "necesita_aclaracion": false,
  "mensaje_aclaracion": ""
}}

Reglas:
- Traduce apodos al nombre oficial
- Si el producto tiene variantes, agrégalo a productos_con_variante en vez de productos_encontrados
- Si hay ambigüedad, pon necesita_aclaracion=true y explica en mensaje_aclaracion
- Si el mensaje no contiene productos, devuelve listas vacías
"""}]
        )
        resultado = resp.content[0].text.strip()
        if "```" in resultado:
            resultado = resultado.split("```")[1]
            if resultado.startswith("json"):
                resultado = resultado[4:]
        return json.loads(resultado.strip())
    except Exception as e:
        print(f"Error extrayendo productos: {e}")
        return {"productos_encontrados": [], "productos_con_variante": [], "necesita_aclaracion": False, "mensaje_aclaracion": ""}


def claude_respuesta_libre(system: str, historial: list, mensaje: str) -> str:
    """Llamada general a Claude para respuestas conversacionales."""
    historial_completo = historial[-20:] + [{"role": "user", "content": mensaje}]
    try:
        resp = claude_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=600,
            system=system,
            messages=historial_completo
        )
        return resp.content[0].text
    except Exception as e:
        print(f"Error Claude: {e}")
        return "Disculpa, tuve un problema. ¿Puedes repetir?"


# ══════════════════════════════════════════════════════════════
# MANEJO DE ESTADOS
# ══════════════════════════════════════════════════════════════

def nueva_sesion() -> dict:
    return {
        "estado": "identificacion",
        "cedula": "", "nombre": "", "destino": "", "motonave": "",
        "items": [],
        "metodo_pago": "",
        "historial": []
    }


def get_sesion(numero: str) -> dict:
    if numero not in sesiones:
        sesiones[numero] = nueva_sesion()
    return sesiones[numero]


def calcular_total(items: list) -> int:
    return sum(int(i["cantidad"] * i["precio"]) for i in items)


def formato_resumen(sesion: dict) -> str:
    items = sesion["items"]
    lineas = []
    for i in items:
        subtotal = int(i["cantidad"] * i["precio"])
        precio_u = int(i["precio"]) if i["precio"] == int(i["precio"]) else i["precio"]
        lineas.append(f"✅ {i['nombre']} — {int(i['cantidad'])} {i.get('unidad','und')} — ${precio_u:,} c/u — *${subtotal:,}*")
    total = calcular_total(items)
    resumen = "\n".join(lineas)
    advertencia = ""
    if total < 800000:
        advertencia = "\n\n⚠️ Tu pedido es menor a $800.000, debes pagar la entrada de la motonave por separado."
    return f"""📋 *Resumen de tu pedido:*

{resumen}

💰 *TOTAL: ${total:,}*
🚢 Destino: {sesion['destino']} — Motonave: {sesion['motonave']}{advertencia}

¿Confirmas este pedido? ✅"""


def extraer_datos_regex(texto: str) -> dict:
    """Extracción robusta de datos del cliente."""
    datos = {"cedula": "", "nombre": "", "destino": "", "motonave": ""}
    texto_lower = texto.lower()

    # ── Método 1: formato por comas (más común) ───────────────
    # Ej: "12345678, Pedro Pérez, Juanchaco, motonave San José"
    partes = [p.strip() for p in texto.split(",")]
    if len(partes) >= 2:
        # Primera parte con solo dígitos = cédula
        if re.match(r"^\d{6,12}$", partes[0]):
            datos["cedula"] = partes[0]
            if len(partes) >= 2:
                datos["nombre"] = partes[1].strip().title()
            if len(partes) >= 3:
                dest = partes[2].strip()
                dest = re.sub(r"(?i)destino:?\s*", "", dest).strip()
                datos["destino"] = dest.title()
            if len(partes) >= 4:
                moto = partes[3].strip()
                moto = re.sub(r"(?i)(motonave|barco|lancha|nave):?\s*", "", moto).strip()
                datos["motonave"] = moto.title()
            print(f"Extraído por comas: {datos}")
            return datos

    # ── Método 2: regex por palabras clave ────────────────────
    cedula_m = re.search(r"\b(\d{6,12})\b", texto)
    if cedula_m:
        datos["cedula"] = cedula_m.group(1)

    moto_m = re.search(r"(?i)(?:motonave|barco|lancha|nave)\s*:?\s*([\w\sáéíóúñ]+?)(?:,|$)", texto)
    if moto_m:
        datos["motonave"] = moto_m.group(1).strip().title()

    dest_m = re.search(r"(?i)(?:destino|para|hacia|a)\s*:?\s*([\w\sáéíóúñ]+?)(?:,|motonave|barco|$)", texto)
    if dest_m:
        datos["destino"] = dest_m.group(1).strip().title()

    print(f"Extraído por regex: {datos}")
    return datos


def procesar_estado_identificacion(sesion: dict, texto: str) -> str:
    # Saludo inicial — no intentar extraer datos
    if texto.lower().strip() in ["hola", "buenas", "buenos días", "buenas tardes", "buenas noches", "hi", "hey"]:
        return ("¡Bienvenido a Distribuidora Alejandra María! 👋\n"
                "Para atenderte necesito:\n"
                "1️⃣ Número de cédula\n"
                "2️⃣ Nombre completo\n"
                "3️⃣ Destino (municipio o corregimiento)\n"
                "4️⃣ Motonave o barco\n\n"
                "¡Con esos datos tomamos tu pedido! 📦")

    # Intentar extraer con Claude
    datos = claude_extraer_identificacion(texto)
    print(f"Datos extraídos por Claude: {datos}")

    # Respaldo con regex si Claude falla
    if not datos or not any(datos.values()):
        datos = extraer_datos_regex(texto)
        print(f"Datos extraídos por regex: {datos}")

    if datos:
        if datos.get("cedula"): sesion["cedula"] = datos["cedula"]
        if datos.get("nombre"): sesion["nombre"] = datos["nombre"]
        if datos.get("destino"): sesion["destino"] = datos["destino"]
        if datos.get("motonave"): sesion["motonave"] = datos["motonave"]

    faltan = []
    if not sesion["cedula"]: faltan.append("número de cédula")
    if not sesion["nombre"]: faltan.append("nombre completo")
    if not sesion["destino"]: faltan.append("destino")
    if not sesion["motonave"]: faltan.append("motonave o barco")

    print(f"Sesión actual: {sesion}")
    print(f"Faltan: {faltan}")

    if faltan:
        return f"Gracias, me falta: *{', '.join(faltan)}*. ¿Me los compartes?"

    sesion["estado"] = "tomando_pedido"
    return (f"¡Perfecto {sesion['nombre'].split()[0]}! 😊 Ya tengo tus datos:\n"
            f"✅ Cédula: {sesion['cedula']}\n"
            f"✅ Destino: {sesion['destino']} — Motonave: {sesion['motonave']}\n\n"
            f"Ahora sí, ¿qué productos necesitas? 📦\n"
            f"Puedes escribir la lista, enviar audio o foto. ¡Yo me encargo! 🛒")


def detectar_intencion_cliente(texto: str, tiene_items: bool) -> str:
    """
    Usa Claude para detectar qué quiere el cliente.
    Retorna: "agregar_productos" | "cerrar_pedido" | "consulta_precio" | "modificar"
    """
    if not tiene_items:
        return "agregar_productos"
    try:
        resp = claude_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=50,
            messages=[{"role": "user", "content": f"""
Un cliente de una distribuidora de dulcería en Colombia está haciendo un pedido por WhatsApp.
Ya tiene productos en su pedido. Ahora dice: "{texto}"

¿Qué quiere hacer? Responde SOLO una de estas opciones exactas:
- agregar_productos (quiere añadir más cosas al pedido)
- cerrar_pedido (quiere terminar, ver el total, confirmar, ya no quiere más)
- modificar (quiere cambiar o quitar algo del pedido)

Ejemplos de cerrar_pedido: "solo eso", "cuánto sería", "eso es todo", "listo", 
"cuánto me sale", "ya terminé", "nada más", "con eso está bien", "cuánto es",
"sí confirmo", "dale", "okay", "perfecto", "solo eso cuánto sería"

Responde solo la opción, sin puntos ni explicaciones.
"""}]
        )
        intencion = resp.content[0].text.strip().lower()
        print(f"Intención detectada: '{intencion}' para: '{texto}'")
        if "cerrar" in intencion:
            return "cerrar_pedido"
        elif "modificar" in intencion:
            return "modificar"
        return "agregar_productos"
    except Exception as e:
        print(f"Error detectando intención: {e}")
        return "agregar_productos"


def procesar_estado_tomando_pedido(sesion: dict, texto: str) -> str:
    # Detectar intención del cliente con Claude
    intencion = detectar_intencion_cliente(texto, bool(sesion["items"]))

    if intencion == "cerrar_pedido" and sesion["items"]:
        sesion["estado"] = "confirmando"
        return formato_resumen(sesion)

    if intencion == "modificar":
        return ("Claro, dime qué quieres cambiar 📝\n"
                "¿Quieres quitar algún producto, cambiar la cantidad o agregar algo diferente?")

    resultado = claude_extraer_productos(texto, sesion["items"])

    # Agregar productos encontrados al pedido
    productos_agregados = []
    for prod in resultado.get("productos_encontrados", []):
        nombre = prod["nombre_oficial"]
        cantidad = prod.get("cantidad", 1)
        # Buscar en catálogo
        encontrado = buscar_producto(nombre)
        precio = limpiar_precio(encontrado["PRECIO"]) if encontrado else 0
        codigo = str(encontrado.get("CODIGO_BARRAS", "")) if encontrado else ""
        unidad = encontrado.get("UNIDAD", "und") if encontrado else "und"

        if precio == 0:
            print(f"⚠️ Producto sin precio en catálogo: {nombre}")

        sesion["items"].append({
            "nombre": nombre,
            "cantidad": cantidad,
            "precio": precio,
            "codigo": codigo,
            "unidad": unidad
        })
        precio_fmt = f"${int(precio):,}" if precio == int(precio) else f"${precio:,.0f}"
        productos_agregados.append(f"✅ {nombre} x{cantidad} — {precio_fmt}")

    # Productos con variantes — preguntar sabor
    preguntas_variante = []
    for pv in resultado.get("productos_con_variante", []):
        producto_base = pv["producto_base"].lower()
        cantidad = pv.get("cantidad", 1)
        if producto_base in PRODUCTOS_CON_VARIANTES:
            info = PRODUCTOS_CON_VARIANTES[producto_base]
            opciones = "\n".join([f"  {i+1}. {op}" for i, op in enumerate(info["opciones"])])
            preguntas_variante.append(
                f"Para *{cantidad} {producto_base}* necesito saber el sabor/variante:\n{opciones}"
            )

    if resultado.get("necesita_aclaracion"):
        preguntas_variante.append(resultado["mensaje_aclaracion"])

    respuesta_partes = []
    if productos_agregados:
        respuesta_partes.append("Anotado:\n" + "\n".join(productos_agregados))
    if preguntas_variante:
        respuesta_partes.append("\n".join(preguntas_variante))

    if not respuesta_partes and not sesion["items"]:
        return "No entendí bien el pedido. ¿Puedes decirme qué productos necesitas? 😊"

    if respuesta_partes:
        respuesta = "\n\n".join(respuesta_partes)
        if sesion["items"] and not preguntas_variante:
            respuesta += "\n\n¿Deseas agregar algo más o terminamos? 😊"
        return respuesta

    return "¿Qué más necesitas agregar? 😊"


def detectar_confirmacion(texto: str) -> str:
    """Detecta si el cliente confirma, rechaza o pregunta algo. Retorna: confirma | rechaza | pregunta"""
    try:
        resp = claude_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=20,
            messages=[{"role": "user", "content": f"""
El cliente acaba de ver el resumen de su pedido con precios y dice: "{texto}"
¿Qué responde? Solo una opción:
- confirma (acepta el pedido tal como está)
- rechaza (quiere cambiar, quitar o agregar algo)
- pregunta (tiene una duda o pregunta algo)
Responde solo la palabra.
"""}]
        )
        resp_text = resp.content[0].text.strip().lower()
        if "confirma" in resp_text: return "confirma"
        if "rechaza" in resp_text: return "rechaza"
        return "pregunta"
    except:
        return "pregunta"


def procesar_estado_confirmando(sesion: dict, texto: str) -> str:
    accion = detectar_confirmacion(texto)
    print(f"Confirmación detectada: '{accion}' para: '{texto}'")

    if accion == "rechaza":
        sesion["estado"] = "tomando_pedido"
        return ("Claro, dime qué quieres cambiar 📝\n"
                "¿Quieres quitar algo, cambiar cantidades o agregar más productos?")

    if accion == "confirma":
        sesion["estado"] = "eligiendo_pago"
        return ("¡Perfecto! ¿Cómo vas a realizar el pago?\n\n"
                "1️⃣ Nequi\n"
                "2️⃣ Bancolombia\n"
                "3️⃣ Efectivo contra entrega")

    # Si tiene una pregunta, responderla con contexto
    total = calcular_total(sesion["items"])
    if any(p in texto.lower() for p in ["cuánto", "cuanto", "precio", "total", "vale", "cuesta"]):
        return (f"El total de tu pedido es *${total:,}* 💰\n\n"
                f"¿Confirmas el pedido? ✅")

    return formato_resumen(sesion) + "\n\n¿Lo confirmamos? ✅"


def detectar_metodo_pago(texto: str) -> str:
    """Detecta método de pago. Retorna: nequi | bancolombia | efectivo | ninguno"""
    try:
        resp = claude_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=20,
            messages=[{"role": "user", "content": f"""
El cliente debe elegir cómo pagar su pedido y dice: "{texto}"
¿Qué método eligió? Solo una opción:
- nequi
- bancolombia
- efectivo
- ninguno (no queda claro)
Responde solo la palabra.
"""}]
        )
        metodo = resp.content[0].text.strip().lower()
        for m in ["nequi", "bancolombia", "efectivo"]:
            if m in metodo:
                return m
        return "ninguno"
    except:
        return "ninguno"


def procesar_estado_eligiendo_pago(sesion: dict, texto: str, telefono: str) -> str:
    metodo = detectar_metodo_pago(texto)
    print(f"Método de pago detectado: '{metodo}' para: '{texto}'")
    total = calcular_total(sesion["items"])

    if metodo == "nequi":
        sesion["metodo_pago"] = "Nequi"
        sesion["estado"] = "esperando_comprobante"
        registrar_en_sheets(sesion, telefono)
        return (f"¡Perfecto! Realiza tu transferencia a:\n\n"
                f"📱 *Nequi:* 300 000 0000\n"
                f"👤 Distribuidora Alejandra María\n"
                f"💰 *Valor: ${total:,}*\n\n"
                f"Cuando realices el pago envíame el comprobante 📸 y procesamos tu pedido.\n"
                f"⏰ Tiempo de entrega: 2 a 3 horas.")

    elif metodo == "bancolombia":
        sesion["metodo_pago"] = "Bancolombia"
        sesion["estado"] = "esperando_comprobante"
        registrar_en_sheets(sesion, telefono)
        return (f"¡Perfecto! Realiza tu transferencia a:\n\n"
                f"🏦 *Bancolombia:* Cuenta 000-000000-00\n"
                f"👤 Distribuidora Alejandra María\n"
                f"💰 *Valor: ${total:,}*\n\n"
                f"Cuando realices el pago envíame el comprobante 📸 y procesamos tu pedido.\n"
                f"⏰ Tiempo de entrega: 2 a 3 horas.")

    elif metodo == "efectivo":
        sesion["metodo_pago"] = "Efectivo"
        sesion["estado"] = "cerrado"
        registrar_en_sheets(sesion, telefono)
        return (f"¡Perfecto! Pago en *efectivo contra entrega* ✅\n\n"
                f"📦 Tu pedido está confirmado:\n"
                f"💰 Ten listo: *${total:,}*\n"
                f"🚢 Sale hacia {sesion['destino']} en motonave {sesion['motonave']}\n"
                f"⏰ Tiempo de entrega: 2 a 3 horas.\n\n"
                f"{"⚠️ Recuerda pagar la entrada de la motonave por separado." if total < 800000 else ""}\n\n"
                f"¡Gracias por tu compra {sesion['nombre'].split()[0]}! 🙌")

    return ("No entendí el método de pago. Por favor elige:\n\n"
            "1️⃣ *Nequi*\n"
            "2️⃣ *Bancolombia*\n"
            "3️⃣ *Efectivo* contra entrega")


def procesar_estado_esperando_comprobante(sesion: dict, es_imagen: bool, texto: str, numero_cliente: str = "", image_id: str = "") -> str:
    nombre = sesion["nombre"].split()[0]
    total = calcular_total(sesion["items"])

    if es_imagen and image_id:
        # ── Verificar comprobante con Claude Vision ───────────
        verificacion = verificar_comprobante_vision(image_id, sesion)
        print(f"Verificación comprobante: {verificacion}")

        if not verificacion.get("es_comprobante"):
            return (f"Esa imagen no parece un comprobante de pago 🤔\n"
                    f"Por favor envíame la *captura de pantalla del pago* por {sesion.get('metodo_pago','Nequi')}. 📸")

        valor_ok = verificacion.get("valor_correcto", False)
        confianza = verificacion.get("confianza", "baja")

        if valor_ok and confianza == "alta":
            # ✅ Pago verificado automáticamente
            sesion["estado"] = "cerrado"
            return (f"✅ *¡Pago verificado, {nombre}!*\n\n"
                    f"Tu pedido está confirmado y en proceso:\n"
                    f"📦 {len(sesion['items'])} productos — *${total:,}*\n"
                    f"🚢 Sale hacia {sesion['destino']} en motonave {sesion['motonave']}\n"
                    f"⏰ Tiempo de entrega: 2 a 3 horas.\n\n"
                    f"Te avisamos cuando esté despachado. ¡Gracias! 🙌")
        else:
            # ⚠️ Duda — escalar a administradora
            valor_detectado = verificacion.get("valor_detectado", 0)
            observacion = verificacion.get("observacion", "")
            motivo = f"Valor detectado: ${valor_detectado:,} — Esperado: ${total:,}. {observacion}"
            notificar_admin(numero_cliente, sesion, motivo, image_id)
            sesion["estado"] = "pendiente_aprobacion"
            return (f"📋 Recibí tu comprobante, {nombre}.\n\n"
                    f"Estamos verificando el pago con nuestro equipo 🔍\n"
                    f"En unos minutos te confirmamos.\n"
                    f"⏰ Tiempo de entrega: 2 a 3 horas desde la confirmación.")

    elif es_imagen and not image_id:
        # Imagen desde interfaz web (prueba) — simular aprobación
        sesion["estado"] = "cerrado"
        return (f"✅ *¡Comprobante recibido, {nombre}!*\n\n"
                f"Tu pedido está confirmado:\n"
                f"📦 {len(sesion['items'])} productos — *${total:,}*\n"
                f"🚢 Destino: {sesion['destino']} — Motonave: {sesion['motonave']}\n"
                f"⏰ Tiempo de entrega: 2 a 3 horas.\n\n"
                f"¡Gracias por tu compra! 🙌")

    # Si escribe texto en vez de foto
    afirmaciones = ["listo", "ya pagué", "ya pague", "hecho", "pague", "pagué", "transferí"]
    if any(a in texto.lower() for a in afirmaciones):
        notificar_admin(numero_cliente, sesion, "Cliente dice que pagó pero no envió comprobante.")
        sesion["estado"] = "pendiente_aprobacion"
        return (f"Entendido {nombre}. Nuestro equipo está verificando el pago 🔍\n"
                f"Por favor envíame también la *foto del comprobante* para agilizar el proceso. 📸")

    return (f"Estoy esperando tu comprobante de pago 📸\n"
            f"Envíame la captura de pantalla del pago por {sesion.get('metodo_pago','Nequi')} "
            f"y procesamos tu pedido de inmediato.")


# ══════════════════════════════════════════════════════════════
# MEDIA — AUDIO E IMÁGENES
# ══════════════════════════════════════════════════════════════

def transcribir_audio(audio_id: str) -> str | None:
    try:
        token = os.environ.get("WHATSAPP_TOKEN")
        headers = {"Authorization": f"Bearer {token}"}
        url_info = requests.get(f"https://graph.facebook.com/v18.0/{audio_id}", headers=headers).json()
        audio_resp = requests.get(url_info.get("url"), headers=headers)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_resp.content)
            temp_path = f.name
        from openai import OpenAI
        oc = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        with open(temp_path, "rb") as af:
            transcript = oc.audio.transcriptions.create(model="whisper-1", file=af, language="es")
        os.unlink(temp_path)
        return transcript.text
    except Exception as e:
        print(f"Error audio: {e}")
        return None


def leer_imagen_lista(image_id: str) -> str:
    try:
        token = os.environ.get("WHATSAPP_TOKEN")
        headers = {"Authorization": f"Bearer {token}"}
        url_info = requests.get(f"https://graph.facebook.com/v18.0/{image_id}", headers=headers).json()
        img_resp = requests.get(url_info.get("url"), headers=headers)
        image_data = base64.standard_b64encode(img_resp.content).decode("utf-8")
        media_type = img_resp.headers.get("Content-Type", "image/jpeg")
        response = claude_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1000,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                {"type": "text", "text": (
                    "Esta es una lista de pedido de una distribuidora de dulcería en Colombia (Buenaventura). "
                    "Lee TODOS los productos con sus cantidades exactamente como aparecen, uno por línea. "
                    "Formato: CANTIDAD PRODUCTO. Si hay texto ilegible escribe [ilegible]. "
                    "Solo devuelve la lista, sin comentarios ni encabezados."
                )}
            ]}]
        )
        return response.content[0].text
    except Exception as e:
        print(f"Error leyendo imagen: {e}")
        return ""


# ══════════════════════════════════════════════════════════════
# WHATSAPP
# ══════════════════════════════════════════════════════════════

def enviar_whatsapp(numero: str, mensaje: str):
    token = os.environ.get("WHATSAPP_TOKEN")
    phone_id = os.environ.get("PHONE_NUMBER_ID")
    requests.post(
        f"https://graph.facebook.com/v18.0/{phone_id}/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"messaging_product": "whatsapp", "to": numero,
              "type": "text", "text": {"body": mensaje}}
    )


# ══════════════════════════════════════════════════════════════
# MOTOR PRINCIPAL — PROCESAR MENSAJE
# ══════════════════════════════════════════════════════════════

def procesar_mensaje(numero: str, texto: str, es_imagen: bool = False, telefono: str = "", image_id: str = "") -> str:
    sesion = get_sesion(numero)
    estado = sesion["estado"]

    kwargs = {"image_id": image_id}
    print(f"[{numero}] Estado: {estado} | Mensaje: {texto[:60]}")

    # Estado cerrado — permitir nuevo pedido
    if estado == "cerrado":
        palabras_nuevo = ["hola", "buenas", "otro pedido", "nuevo pedido", "quiero pedir"]
        if any(p in texto.lower() for p in palabras_nuevo):
            sesiones[numero] = nueva_sesion()
            sesion = sesiones[numero]
            estado = "identificacion"
        else:
            return (f"Tu pedido anterior ya está registrado ✅\n"
                    f"Si quieres hacer un nuevo pedido escríbeme *hola* y comenzamos. 😊")

    if estado == "identificacion":
        return procesar_estado_identificacion(sesion, texto)

    elif estado == "tomando_pedido":
        return procesar_estado_tomando_pedido(sesion, texto)

    elif estado == "confirmando":
        return procesar_estado_confirmando(sesion, texto)

    elif estado == "eligiendo_pago":
        return procesar_estado_eligiendo_pago(sesion, texto, telefono or numero)

    elif estado == "esperando_comprobante":
        return procesar_estado_esperando_comprobante(sesion, es_imagen, texto, numero, kwargs.get("image_id",""))

    elif estado == "pendiente_aprobacion":
        return (f"Tu pedido sigue en verificación 🔍\n"
                f"En cuanto confirmemos el pago te avisamos. ¡Gracias por tu paciencia!")

    return "Disculpa, ocurrió un error. Escribe *hola* para comenzar de nuevo."


# ══════════════════════════════════════════════════════════════
# WEBHOOKS
# ══════════════════════════════════════════════════════════════

@app.route("/webhook", methods=["GET"])
def verificar_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == os.environ.get("VERIFY_TOKEN"):
        return challenge, 200
    return "Token incorrecto", 403


@app.route("/webhook", methods=["POST"])
def recibir_mensaje():
    try:
        data = request.get_json()
        entry = data.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        messages = changes.get("value", {}).get("messages", [])
        if not messages:
            return jsonify({"status": "ok"}), 200

        msg = messages[0]
        numero = msg.get("from")
        tipo = msg.get("type")

        es_imagen = False
        texto = ""
        image_id_recibido = ""

        if tipo == "text":
            texto = msg["text"]["body"]
        elif tipo == "audio":
            texto = transcribir_audio(msg["audio"]["id"]) or ""
            if not texto:
                enviar_whatsapp(numero, "No pude escuchar tu nota de voz 😅 ¿Puedes escribirlo?")
                return jsonify({"status": "ok"}), 200
        elif tipo == "image":
            sesion = get_sesion(numero)
            img_id = msg["image"]["id"]
            if sesion["estado"] in ["esperando_comprobante", "pendiente_aprobacion"]:
                es_imagen = True
                texto = "[comprobante de pago]"
                image_id_recibido = img_id
            else:
                texto = leer_imagen_lista(img_id)
                if not texto:
                    enviar_whatsapp(numero, "No pude leer la foto. ¿Puedes escribir la lista? 😊")
                    return jsonify({"status": "ok"}), 200
                image_id_recibido = ""
        else:
            enviar_whatsapp(numero, "Recibo texto, notas de voz y fotos de listas 📝")
            return jsonify({"status": "ok"}), 200

        respuesta = procesar_mensaje(numero, texto, es_imagen, numero, image_id_recibido if "image_id_recibido" in dir() else "")
        enviar_whatsapp(numero, respuesta)
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print(f"❌ Error webhook: {e}")
        return jsonify({"status": "error", "detail": str(e)}), 500


# ══════════════════════════════════════════════════════════════
# INTERFAZ WEB DE PRUEBAS
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Distribuidora Alejandra María</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',sans-serif;background:#111b21;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;padding:16px}
.phone{width:100%;max-width:420px;height:92vh;max-height:760px;background:#111b21;border-radius:24px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 32px 80px rgba(0,0,0,0.6)}
.wa-header{background:#202c33;padding:10px 16px;display:flex;align-items:center;gap:12px;border-bottom:1px solid #2a3942}
.avatar{width:40px;height:40px;border-radius:50%;background:#25d366;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0}
.header-info{flex:1}
.header-name{color:#e9edef;font-size:15px;font-weight:600}
.header-status{color:#8696a0;font-size:12px}
.estado-badge{background:#2a3942;color:#8696a0;font-size:10px;padding:2px 8px;border-radius:10px;margin-left:8px}
.btn-nuevo{background:none;border:none;cursor:pointer;padding:6px;border-radius:50%;color:#8696a0;display:flex;transition:background .2s}
.btn-nuevo:hover{background:#2a3942;color:#e9edef}
.btn-nuevo svg{width:20px;height:20px}
.chat-bg{flex:1;overflow-y:auto;padding:12px 16px;background:#0b141a}
.chat-bg::-webkit-scrollbar{width:4px}
.chat-bg::-webkit-scrollbar-thumb{background:#2a3942;border-radius:4px}
.msg{display:flex;margin-bottom:4px}
.msg.user{justify-content:flex-end}
.msg.bot{justify-content:flex-start}
.burbuja{max-width:78%;padding:8px 12px 6px;border-radius:8px;font-size:14px;line-height:1.5;white-space:pre-wrap;word-break:break-word}
.msg.user .burbuja{background:#005c4b;color:#e9edef;border-top-right-radius:2px}
.msg.bot .burbuja{background:#202c33;color:#e9edef;border-top-left-radius:2px}
.hora{font-size:10px;color:#8696a0;text-align:right;margin-top:2px;display:block}
.typing{display:none;align-items:center;gap:4px;padding:8px 12px;background:#202c33;border-radius:8px;width:fit-content;margin-bottom:4px}
.typing.visible{display:flex}
.dot{width:7px;height:7px;border-radius:50%;background:#8696a0;animation:bounce 1.2s infinite}
.dot:nth-child(2){animation-delay:.2s}.dot:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-6px)}}
.fecha-sep{text-align:center;margin:12px 0}
.fecha-sep span{background:#182229;color:#8696a0;font-size:11px;padding:4px 12px;border-radius:12px}
.input-bar{background:#202c33;padding:8px 12px;display:flex;align-items:flex-end;gap:8px}
.input-wrap{flex:1;background:#2a3942;border-radius:24px;display:flex;align-items:center;padding:8px 14px;gap:8px;min-height:44px}
#msg{flex:1;background:none;border:none;outline:none;color:#e9edef;font-size:15px;font-family:'Inter',sans-serif;resize:none;max-height:100px;line-height:1.4}
#msg::placeholder{color:#8696a0}
.icon-btn{background:none;border:none;cursor:pointer;color:#8696a0;display:flex;padding:2px;transition:color .2s}
.icon-btn:hover{color:#e9edef}
.icon-btn svg{width:22px;height:22px}
.send-btn{width:44px;height:44px;border-radius:50%;background:#00a884;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,168,132,.3)}
.send-btn:hover{background:#06cf9c}
.send-btn svg{width:20px;height:20px;fill:white}
.rec-bar{display:none;background:#202c33;padding:8px 16px;align-items:center;gap:12px}
.rec-bar.visible{display:flex}
.rec-dot{width:10px;height:10px;border-radius:50%;background:#f44336;animation:pulse 1s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.rec-time{color:#e9edef;font-size:14px;flex:1}
.rec-cancel{color:#8696a0;font-size:13px;cursor:pointer;padding:4px 8px}
.rec-send{background:#00a884;color:white;border:none;border-radius:20px;padding:6px 16px;font-size:13px;cursor:pointer}
.foto-preview{display:none;position:relative;margin-bottom:6px}
.foto-preview.visible{display:block}
.foto-preview img{max-width:180px;border-radius:8px;border:2px solid #25d366}
.foto-preview .quitar{position:absolute;top:-6px;right:-6px;background:#f44336;color:white;border:none;border-radius:50%;width:20px;height:20px;cursor:pointer;font-size:12px}
#file-input{display:none}
</style>
</head>
<body>
<div class="phone">
  <div class="wa-header">
    <div class="avatar">🛒</div>
    <div class="header-info">
      <div class="header-name">Distribuidora Alejandra María <span class="estado-badge" id="badge-estado">identificación</span></div>
      <div class="header-status" id="estado-header">en línea</div>
    </div>
    <button class="btn-nuevo" onclick="nuevaConversacion()" title="Nueva conversación">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>
    </button>
  </div>

  <div class="chat-bg" id="chat">
    <div class="fecha-sep"><span>HOY</span></div>
    <div class="typing" id="typing"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>
  </div>

  <div class="input-bar" id="input-bar">
    <div style="flex:1;display:flex;flex-direction:column;gap:6px">
      <div class="foto-preview" id="foto-preview">
        <img id="foto-img" src="" alt="foto">
        <button class="quitar" onclick="quitarFoto()">✕</button>
      </div>
      <div class="input-wrap">
        <button class="icon-btn" onclick="abrirCamara()" title="Foto de lista o comprobante">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
        </button>
        <textarea id="msg" rows="1" placeholder="Escribe un mensaje..." oninput="autoResize(this)" onkeydown="teclaEnter(event)"></textarea>
        <button class="icon-btn" onclick="toggleMic()" title="Nota de voz">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8"/></svg>
        </button>
      </div>
    </div>
    <button class="send-btn" onclick="enviar()"><svg viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2v7z"/></svg></button>
  </div>

  <div class="rec-bar" id="rec-bar">
    <div class="rec-dot"></div>
    <span class="rec-time" id="rec-time">0:00</span>
    <span class="rec-cancel" onclick="cancelarGrabacion()">Cancelar</span>
    <button class="rec-send" onclick="enviarAudio()">Enviar 🎤</button>
  </div>
</div>

<input type="file" id="file-input" accept="image/*" capture="environment" onchange="seleccionarFoto(event)">

<script>
let numero = "test_web_" + Math.random().toString(36).slice(2,8);
let mediaRecorder=null, audioChunks=[], recTimer=null, recSecs=0, fotoBase64=null, grabando=false;

function autoResize(el){el.style.height='auto';el.style.height=Math.min(el.scrollHeight,100)+'px';}
function teclaEnter(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();enviar();}}
function horaActual(){return new Date().toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit'});}

function agregar(texto, tipo, esImagen=false){
  const chat=document.getElementById("chat");
  const typing=document.getElementById("typing");
  const div=document.createElement("div");
  div.className="msg "+tipo;
  let contenido = esImagen
    ? `<img src="${texto}" style="max-width:180px;border-radius:8px;display:block">`
    : texto.replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\*(.*?)\\*/g,'<strong>$1</strong>');
  div.innerHTML=`<div class="burbuja">${contenido}<span class="hora">${horaActual()}</span></div>`;
  chat.insertBefore(div, typing);
  chat.scrollTop=chat.scrollHeight;
}

function setTyping(v){
  document.getElementById("typing").classList.toggle("visible",v);
  document.getElementById("estado-header").textContent=v?"escribiendo...":"en línea";
  if(v) document.getElementById("chat").scrollTop=99999;
}

function actualizarBadge(estado){
  const badge=document.getElementById("badge-estado");
  const labels={
    identificacion:"identificación",
    tomando_pedido:"tomando pedido",
    confirmando:"confirmando",
    eligiendo_pago:"eligiendo pago",
    esperando_comprobante:"esperando comprobante",
    cerrado:"cerrado"
  };
  badge.textContent=labels[estado]||estado;
  badge.style.background=estado==="cerrado"?"#1a5c3a":estado==="esperando_comprobante"?"#5c3a1a":"#2a3942";
}

async function enviarAlBot(mensaje, esImagenBot=false){
  setTyping(true);
  try{
    const resp=await fetch("/test",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({numero, mensaje, es_imagen: esImagenBot})});
    const data=await resp.json();
    setTyping(false);
    agregar(data.respuesta,"bot");
    if(data.estado) actualizarBadge(data.estado);
  }catch(e){
    setTyping(false);
    agregar("Error de conexión. Intenta de nuevo.","bot");
  }
}

async function enviar(){
  const input=document.getElementById("msg");
  const texto=input.value.trim();
  if(fotoBase64){
    agregar(fotoBase64,"user",true);
    input.value=""; input.style.height='auto';
    await enviarAlBot("[imagen enviada por el cliente]", true);
    quitarFoto(); return;
  }
  if(!texto) return;
  agregar(texto,"user");
  input.value=""; input.style.height='auto';
  await enviarAlBot(texto);
}

function nuevaConversacion(){
  if(!confirm("¿Iniciar nueva conversación?")) return;
  numero="test_web_"+Math.random().toString(36).slice(2,8);
  document.getElementById("chat").innerHTML=`
    <div class="fecha-sep"><span>HOY</span></div>
    <div class="typing" id="typing"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>`;
  actualizarBadge("identificacion");
  quitarFoto();
}

function abrirCamara(){document.getElementById("file-input").click();}
function seleccionarFoto(e){
  const file=e.target.files[0]; if(!file) return;
  const reader=new FileReader();
  reader.onload=function(ev){
    fotoBase64=ev.target.result;
    document.getElementById("foto-img").src=fotoBase64;
    document.getElementById("foto-preview").classList.add("visible");
  };
  reader.readAsDataURL(file); e.target.value="";
}
function quitarFoto(){fotoBase64=null;document.getElementById("foto-preview").classList.remove("visible");document.getElementById("foto-img").src="";}

async function toggleMic(){if(!grabando) await iniciarGrabacion();}
async function iniciarGrabacion(){
  try{
    const stream=await navigator.mediaDevices.getUserMedia({audio:true});
    audioChunks=[]; mediaRecorder=new MediaRecorder(stream);
    mediaRecorder.ondataavailable=e=>audioChunks.push(e.data);
    mediaRecorder.start(); grabando=true; recSecs=0;
    document.getElementById("input-bar").style.display="none";
    document.getElementById("rec-bar").classList.add("visible");
    recTimer=setInterval(()=>{recSecs++;const m=Math.floor(recSecs/60),s=recSecs%60;
      document.getElementById("rec-time").textContent=m+":"+(s<10?"0":"")+s;},1000);
  }catch(e){alert("No se pudo acceder al micrófono.");}
}
function cancelarGrabacion(){
  if(mediaRecorder){mediaRecorder.stop();mediaRecorder.stream.getTracks().forEach(t=>t.stop());}
  clearInterval(recTimer); grabando=false;
  document.getElementById("rec-bar").classList.remove("visible");
  document.getElementById("input-bar").style.display="flex";
}
async function enviarAudio(){
  if(!mediaRecorder) return;
  mediaRecorder.stop(); mediaRecorder.stream.getTracks().forEach(t=>t.stop());
  clearInterval(recTimer); grabando=false;
  await new Promise(r=>setTimeout(r,200));
  const chat=document.getElementById("chat");
  const typing=document.getElementById("typing");
  const div=document.createElement("div"); div.className="msg user";
  div.innerHTML=`<div class="burbuja">🎤 <em style="color:#a8d5c2;font-size:13px">Nota de voz (${document.getElementById("rec-time").textContent})</em><span class="hora">${horaActual()}</span></div>`;
  chat.insertBefore(div,typing); chat.scrollTop=chat.scrollHeight;
  document.getElementById("rec-bar").classList.remove("visible");
  document.getElementById("input-bar").style.display="flex";
  await enviarAlBot("[El cliente envió una nota de voz con su pedido]");
}
</script>
</body></html>"""


@app.route("/test", methods=["POST"])
def test_bot():
    data = request.get_json()
    numero = data.get("numero", "test")
    mensaje = data.get("mensaje", "")
    es_imagen = data.get("es_imagen", False)
    respuesta = procesar_mensaje(numero, mensaje, es_imagen, numero)
    sesion = get_sesion(numero)
    return jsonify({"respuesta": respuesta, "estado": sesion["estado"]})


@app.route("/estado/<numero>")
def ver_estado(numero):
    sesion = get_sesion(numero)
    return jsonify({
        "estado": sesion["estado"],
        "nombre": sesion["nombre"],
        "destino": sesion["destino"],
        "items": sesion["items"],
        "total": calcular_total(sesion["items"])
    })


@app.route("/catalogo/total")
def total_catalogo():
    return jsonify({"productos_cargados": len(catalogo_cache)})


@app.route("/catalogo/buscar")
def buscar_en_catalogo():
    resultado = buscar_producto(request.args.get("q", ""))
    return jsonify({"encontrado": bool(resultado), "producto": resultado})


# ══════════════════════════════════════════════════════════════
# INICIO
# ══════════════════════════════════════════════════════════════

with app.app_context():
    cargar_catalogo()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
