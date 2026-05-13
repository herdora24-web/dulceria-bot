"""
================================================================
AGENTE VENDEDOR - DISTRIBUIDORA DULCERÍA v2
Flask + Claude API + Google Sheets + Vision + Whisper
================================================================
VARIABLES DE ENTORNO en Railway:
ANTHROPIC_API_KEY
WHATSAPP_TOKEN
VERIFY_TOKEN
PHONE_NUMBER_ID
OPENAI_API_KEY
GOOGLE_CREDENTIALS_JSON
GOOGLE_SHEET_ID_DULCERIA
================================================================
"""

import os
import json
import base64
import requests
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify
import anthropic
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

claude_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
conversaciones = {}
catalogo_cache = []

# ══════════════════════════════════════════════════════════════
# DICCIONARIO DE APODOS
# ══════════════════════════════════════════════════════════════

APODOS = {
    "pin pon polvo acido": "PIN PON MANGO VICHE",
    "pin pon acido": "PIN PON MANGO VICHE",
    "ristra de ponky": "PONKY X8X24TIRA/VAINILLA",
    "ristra ponky": "PONKY X8X24TIRA/VAINILLA",
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
    "rulita x 24": "PAPITA X 24",
    "rulita": "PAPITA X 24",
    "papa salsa grande": "PAPITA GRANDE",
    "bonbom grande": "BIG BON X 48 UND",
    "confites surtidos": "BANANAS SURTIDAS X 100 UND",
    "bananas surtidas": "BANANAS SURTIDAS X 100 UND",
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

UNIDADES = """
REFERENCIAS DE UNIDADES POR PRODUCTO:
- BON BON BUM: 24 und/caja | CRAKENA: 24 | FESTIVAL: 24 | DUZ ORIGINAL: 24
- ANISADA: 24 | MORITA: 24 | MAX COCO: 16 | MINIBUM: 16
- SALCHICHA VIENA: 48/caja | JAMONETA GRANDE: 24 | JAMONETA PEQUEÑA: 48
- ATUN ISABEL: 48/caja | LECHERA X 100: 96 | PROLECHE X 6: 6/display
- PAPITA X 24 (RULITA): 24/paca | PAPITA GRANDE: 12/paca
- YUPIS JUANCHIS: paca=72 und | CHEETOS PICANTE: 40/paca
- DETODITOS/PAPITAS MARGARITAS: paca=72 und
- POOL X 400 ML: 24/display | POSTOBON 1.5L: 12 | GASEOSAS LITRO: 12 | POSTOBON PERSONAL: 15
- SERVILLETA X 200: 30/caja
- Pedido MENOR a $800.000: cliente paga la entrada de la motonave
"""

# ══════════════════════════════════════════════════════════════
# PROMPT DEL SISTEMA
# ══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = f"""Eres el vendedor virtual de Distribuidora Alejandra María, una distribuidora de dulcería, líquidos, gaseosas y abarrotes en Buenaventura. Eres TÚ quien atiende, asesora, cotiza y cierra la venta completa. NUNCA menciones que un asesor o vendedor se va a comunicar — tú eres ese vendedor. Tono: amable, ágil y confiable.

════════════════════════════════════════
HORARIO DE ATENCIÓN
════════════════════════════════════════
Lunes a sábado: 8:00 AM a 4:30 PM.
Fuera de horario: recibe el pedido e informa que se procesa el siguiente día hábil.
Domingos: recibe el pedido e informa que se despacha el lunes.

════════════════════════════════════════
PASO 1 — SALUDO E IDENTIFICACIÓN
════════════════════════════════════════
Al primer mensaje responde SIEMPRE:
"¡Bienvenido a Distribuidora Alejandra María! 👋
Para atenderte necesito:
1️⃣ Número de cédula
2️⃣ Nombre completo
3️⃣ Destino (municipio o corregimiento)
4️⃣ Motonave o barco

¡Con esos datos tomamos tu pedido! 📦"

No tomes el pedido hasta tener: cédula, nombre, destino y motonave.

════════════════════════════════════════
PASO 2 — TOMAR EL PEDIDO
════════════════════════════════════════
Recibe el pedido en cualquier formato (texto, lista, voz o foto).
- Traduce apodos al nombre oficial usando el diccionario
- Convierte unidades usando la tabla de referencias
- Si un producto no está claro pregunta al cliente
- Ve anotando cada producto confirmado

DICCIONARIO DE APODOS:
{json.dumps(APODOS, ensure_ascii=False, indent=2)}

TABLA DE UNIDADES:
{UNIDADES}

════════════════════════════════════════
PASO 3 — PRESENTAR RESUMEN CON PRECIOS
════════════════════════════════════════
Cuando el cliente termine de pedir, presenta el resumen así:

"📋 *Resumen de tu pedido:*

✅ NOMBRE_PRODUCTO — X und — $PRECIO_UNIT c/u — *$SUBTOTAL*
✅ NOMBRE_PRODUCTO — X und — $PRECIO_UNIT c/u — *$SUBTOTAL*
...

💰 *TOTAL: $TOTAL_PEDIDO*
🚢 Destino: [destino] — Motonave: [motonave]

⚠️ [Si el total es menor a $800.000]: Tu pedido es menor a $800.000, por lo que debes pagar la entrada de la motonave por separado.

¿Confirmas este pedido? ✅"

IMPORTANTE: Usa los precios reales del catálogo. Suma correctamente.

════════════════════════════════════════
PASO 4 — CONFIRMAR Y COBRAR
════════════════════════════════════════
Cuando el cliente confirme (diga "sí", "dale", "listo", "confirmo", "si señor" o similar), pregunta el método de pago:

"¡Perfecto! ¿Cómo vas a realizar el pago?
1️⃣ Nequi
2️⃣ Bancolombia  
3️⃣ Efectivo contra entrega"

Si elige Nequi:
"Realiza tu transferencia a:
📱 *Nequi:* 300 000 0000
👤 Distribuidora Alejandra María

Cuando me envíes el comprobante, procesamos tu pedido de inmediato. ⏰ Tiempo de entrega: 2 a 3 horas."

Si elige Bancolombia:
"Realiza tu transferencia a:
🏦 *Bancolombia:* Cuenta 000-000000-00
👤 Distribuidora Alejandra María

Cuando me envíes el comprobante, procesamos tu pedido de inmediato. ⏰ Tiempo de entrega: 2 a 3 horas."

Si elige efectivo:
"Perfecto, pagas al recibir. ✅
⏰ Tiempo de entrega: 2 a 3 horas después de confirmado.
📌 Recuerda pagar la entrada de la motonave si aplica."

════════════════════════════════════════
PASO 5 — REGISTRO AUTOMÁTICO (CRÍTICO)
════════════════════════════════════════
En el mismo mensaje donde confirmas el pedido y das los datos de pago, DEBES incluir obligatoriamente al final, en UNA SOLA LÍNEA, el siguiente marcador. SIN ESTE MARCADOR EL PEDIDO NO SE REGISTRA EN EL SISTEMA Y SE PIERDE:

##PEDIDO_CONFIRMADO##{{\"cedula\":\"CEDULA\",\"nombre\":\"NOMBRE\",\"telefono\":\"TELEFONO\",\"destino\":\"DESTINO\",\"motonave\":\"MOTONAVE\",\"items\":\"PRODUCTO1|CANTIDAD1|PRECIO1;PRODUCTO2|CANTIDAD2|PRECIO2\",\"observaciones\":\"TOTAL:TOTAL_PEDIDO\"}}##

Reglas del campo items:
- Productos separados por ;
- Cada ítem: NOMBRE_EXACTO|cantidad|precioUnitario
- Precio unitario: solo el número, sin $ ni puntos ni comas
- Ejemplo: PONKY X8X24TIRA/VAINILLA|2|15000;BON BON BUM X 24|1|8500;PAPITA X 24|3|12000

════════════════════════════════════════
FOTOS DE LISTAS
════════════════════════════════════════
Cuando el cliente envíe una foto de lista escrita a mano:
- Lee todos los productos con cantidades
- Traduce apodos al nombre oficial
- Convierte unidades
- Muestra la lista traducida al cliente para que confirme

════════════════════════════════════════
TIEMPO DE ENTREGA Y DESPACHO
════════════════════════════════════════
2 a 3 horas después de confirmado el pago.
Cuando esté despachado: "Su pedido fue despachado ✅. En cuanto se confirme el recibido de la lancha se le avisa."

════════════════════════════════════════
REGLAS DE ORO
════════════════════════════════════════
1. TÚ eres el vendedor — NUNCA digas que un asesor se va a comunicar
2. NUNCA inventes precios — usa solo los precios del catálogo
3. SIEMPRE identifica al cliente antes de tomar el pedido
4. SIEMPRE presenta el resumen con precios y total antes de confirmar
5. SIEMPRE pregunta el método de pago al confirmar
6. SIEMPRE incluye el marcador ##PEDIDO_CONFIRMADO## al cerrar la venta
7. Sé amable, claro y ágil
"""


# ══════════════════════════════════════════════════════════════
# GOOGLE SHEETS - CONEXIÓN
# ══════════════════════════════════════════════════════════════

def get_google_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
    return gspread.authorize(creds)


# ══════════════════════════════════════════════════════════════
# CATÁLOGO - CARGAR Y BUSCAR
# ══════════════════════════════════════════════════════════════

def cargar_catalogo():
    """Carga el catálogo desde Google Sheets al iniciar."""
    global catalogo_cache
    try:
        gc = get_google_client()
        sheet = gc.open_by_key(os.environ.get("GOOGLE_SHEET_ID_DULCERIA"))
        ws = sheet.worksheet("Catalogo")
        catalogo_cache = ws.get_all_records()
        print(f"✅ Catálogo cargado: {len(catalogo_cache)} productos")
    except Exception as e:
        print(f"❌ Error cargando catálogo: {e}")
        catalogo_cache = []


def buscar_producto(nombre_buscado: str) -> dict | None:
    """Busca producto por nombre exacto o parcial."""
    nombre_buscado = nombre_buscado.upper().strip()
    for prod in catalogo_cache:
        if prod.get("NOMBRE", "").upper().strip() == nombre_buscado:
            return prod
    for prod in catalogo_cache:
        if nombre_buscado in prod.get("NOMBRE", "").upper():
            return prod
    return None


# ══════════════════════════════════════════════════════════════
# GOOGLE SHEETS - REGISTRAR PEDIDO
# ══════════════════════════════════════════════════════════════

def registrar_pedido_sheets(datos_pedido: dict):
    """Registra en Logistica y en Importar_Software."""
    try:
        gc = get_google_client()
        sheet = gc.open_by_key(os.environ.get("GOOGLE_SHEET_ID_DULCERIA"))
        ahora = datetime.now()
        fecha = ahora.strftime("%d/%m/%Y")
        hora = ahora.strftime("%H:%M")

        # Parsear items: "nombre|cantidad|precio;..."
        items = []
        for item_str in datos_pedido.get("items", "").split(";"):
            partes = item_str.strip().split("|")
            if len(partes) < 1 or not partes[0].strip():
                continue
            nombre = partes[0].strip()
            try:
                cantidad = float(partes[1].strip()) if len(partes) > 1 else 1
            except:
                cantidad = 1
            try:
                precio = float(partes[2].strip()) if len(partes) > 2 else 0
            except:
                precio = 0
            # Si no hay precio, buscarlo en catálogo
            prod = buscar_producto(nombre)
            if precio == 0 and prod:
                try:
                    precio = float(prod.get("PRECIO", 0))
                except:
                    precio = 0
            codigo = str(prod.get("CODIGO_BARRAS", "")) if prod else ""
            items.append({
                "nombre": nombre,
                "cantidad": cantidad,
                "precio": precio,
                "codigo": codigo,
                "subtotal": round(cantidad * precio, 0)
            })

        resumen = " | ".join(
            [f"{i['nombre']} x{int(i['cantidad'])}" for i in items]
        ) or datos_pedido.get("productos", "")

        # ── Hoja Logistica ────────────────────────────────────
        ws_log = sheet.worksheet("Logistica")
        ws_log.append_row([
            fecha, hora,
            datos_pedido.get("cedula", ""),
            datos_pedido.get("nombre", ""),
            datos_pedido.get("telefono", ""),
            datos_pedido.get("destino", ""),
            datos_pedido.get("motonave", ""),
            resumen,
            datos_pedido.get("observaciones", ""),
            "EMPAQUE"
        ])
        print(f"✅ Logistica: {datos_pedido.get('nombre')}")

        # ── Hoja Importar_Software ────────────────────────────
        ws_fact = sheet.worksheet("Importar_Software")
        for item in items:
            ws_fact.append_row([
                item["codigo"],     # Referencia o codigo de barras
                item["nombre"],     # Nombre
                item["precio"],     # Precio Unitario
                item["cantidad"],   # Cantidad
                0,                  # Descuento
                0,                  # Impuesto
                item["subtotal"],   # SubTotal (No modificar)
                0,                  # Estampilla
                0,                  # Impoconsumo
                item["subtotal"],   # Total (No modificar)
                ""                  # id_plan_cuenta
            ])
        print(f"✅ Importar_Software: {len(items)} líneas")

    except Exception as e:
        print(f"❌ Error registrando pedido: {e}")


# ══════════════════════════════════════════════════════════════
# EXTRAER Y LIMPIAR PEDIDO
# ══════════════════════════════════════════════════════════════

def extraer_pedido_confirmado(texto: str) -> dict | None:
    if "##PEDIDO_CONFIRMADO##" in texto:
        try:
            inicio = texto.index("##PEDIDO_CONFIRMADO##") + len("##PEDIDO_CONFIRMADO##")
            fin = texto.index("##", inicio)
            return json.loads(texto[inicio:fin])
        except Exception as e:
            print(f"Error extrayendo pedido: {e}")
    return None


def limpiar_respuesta(texto: str) -> str:
    if "##PEDIDO_CONFIRMADO##" in texto:
        texto = texto[:texto.index("##PEDIDO_CONFIRMADO##")].strip()
    return texto


# ══════════════════════════════════════════════════════════════
# WHISPER - TRANSCRIBIR AUDIO
# ══════════════════════════════════════════════════════════════

def transcribir_audio(audio_id: str) -> str | None:
    try:
        token = os.environ.get("WHATSAPP_TOKEN")
        headers = {"Authorization": f"Bearer {token}"}
        url_info = requests.get(
            f"https://graph.facebook.com/v18.0/{audio_id}", headers=headers
        ).json()
        audio_resp = requests.get(url_info.get("url"), headers=headers)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_resp.content)
            temp_path = f.name
        from openai import OpenAI
        oc = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        with open(temp_path, "rb") as af:
            transcript = oc.audio.transcriptions.create(
                model="whisper-1", file=af, language="es"
            )
        os.unlink(temp_path)
        return transcript.text
    except Exception as e:
        print(f"Error audio: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# CLAUDE VISION - LEER IMAGEN
# ══════════════════════════════════════════════════════════════

def leer_imagen_lista(image_id: str) -> str:
    try:
        token = os.environ.get("WHATSAPP_TOKEN")
        headers = {"Authorization": f"Bearer {token}"}
        url_info = requests.get(
            f"https://graph.facebook.com/v18.0/{image_id}", headers=headers
        ).json()
        img_resp = requests.get(url_info.get("url"), headers=headers)
        image_data = base64.standard_b64encode(img_resp.content).decode("utf-8")
        media_type = img_resp.headers.get("Content-Type", "image/jpeg")
        response = claude_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1000,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": image_data
                }},
                {"type": "text", "text": (
                    "Lista de pedido de una distribuidora de dulcería en Colombia. "
                    "Lee todos los productos con cantidades, uno por línea. "
                    "Texto ilegible: escribe [ilegible]. Solo devuelve la lista."
                )}
            ]}]
        )
        return f"[Lista leída de imagen]\n{response.content[0].text}"
    except Exception as e:
        print(f"Error imagen: {e}")
        return "[No pude leer la foto. Pide al cliente que escriba el pedido.]"


# ══════════════════════════════════════════════════════════════
# CLAUDE - PROCESAR MENSAJE
# ══════════════════════════════════════════════════════════════

def procesar_con_claude(numero: str, mensaje_usuario: str) -> str:
    if numero not in conversaciones:
        conversaciones[numero] = []
    conversaciones[numero].append({"role": "user", "content": mensaje_usuario})
    historial = conversaciones[numero][-30:]
    respuesta = claude_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=historial
    )
    texto = respuesta.content[0].text
    conversaciones[numero].append({"role": "assistant", "content": texto})
    return texto


# ══════════════════════════════════════════════════════════════
# WHATSAPP - ENVIAR
# ══════════════════════════════════════════════════════════════

def enviar_whatsapp(numero: str, mensaje: str):
    token = os.environ.get("WHATSAPP_TOKEN")
    phone_id = os.environ.get("PHONE_NUMBER_ID")
    resp = requests.post(
        f"https://graph.facebook.com/v18.0/{phone_id}/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"messaging_product": "whatsapp", "to": numero,
              "type": "text", "text": {"body": mensaje}}
    )
    print(f"WA → {resp.status_code}")


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

        if tipo == "text":
            texto_cliente = msg["text"]["body"]
        elif tipo == "audio":
            texto_cliente = transcribir_audio(msg["audio"]["id"])
            if not texto_cliente:
                enviar_whatsapp(numero, "No pude escuchar tu nota de voz 😅 ¿Puedes escribirlo?")
                return jsonify({"status": "ok"}), 200
        elif tipo == "image":
            texto_cliente = leer_imagen_lista(msg["image"]["id"])
        else:
            enviar_whatsapp(numero, "Recibo texto, notas de voz y fotos de listas 📝")
            return jsonify({"status": "ok"}), 200

        respuesta_claude = procesar_con_claude(numero, texto_cliente)
        pedido = extraer_pedido_confirmado(respuesta_claude)
        if pedido:
            pedido["telefono"] = numero
            registrar_pedido_sheets(pedido)

        enviar_whatsapp(numero, limpiar_respuesta(respuesta_claude))
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print(f"❌ Error webhook: {e}")
        return jsonify({"status": "error", "detail": str(e)}), 500


# ══════════════════════════════════════════════════════════════
# INTERFAZ WEB
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Distribuidora Alejandra María - Pruebas</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',sans-serif;background:#111b21;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;padding:16px}

/* Contenedor tipo teléfono */
.phone{width:100%;max-width:420px;height:92vh;max-height:760px;background:#111b21;border-radius:24px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 32px 80px rgba(0,0,0,0.6)}

/* Header estilo WhatsApp */
.wa-header{background:#202c33;padding:10px 16px;display:flex;align-items:center;gap:12px;border-bottom:1px solid #2a3942}
.avatar{width:40px;height:40px;border-radius:50%;background:#25d366;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0}
.header-info{flex:1}
.header-name{color:#e9edef;font-size:15px;font-weight:600;line-height:1.2}
.header-status{color:#8696a0;font-size:12px}
.btn-nuevo{background:none;border:none;cursor:pointer;padding:6px;border-radius:50%;color:#8696a0;display:flex;align-items:center;justify-content:center;transition:background .2s}
.btn-nuevo:hover{background:#2a3942;color:#e9edef}
.btn-nuevo svg{width:20px;height:20px}

/* Fondo del chat con patrón */
.chat-bg{flex:1;overflow-y:auto;padding:12px 16px;background:#0b141a;background-image:url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23182229' fill-opacity='0.6'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")}
.chat-bg::-webkit-scrollbar{width:4px}
.chat-bg::-webkit-scrollbar-thumb{background:#2a3942;border-radius:4px}

/* Burbujas */
.msg{display:flex;margin-bottom:4px}
.msg.user{justify-content:flex-end}
.msg.bot{justify-content:flex-start}
.burbuja{max-width:78%;padding:8px 12px 6px;border-radius:8px;font-size:14px;line-height:1.5;white-space:pre-wrap;word-break:break-word;position:relative}
.msg.user .burbuja{background:#005c4b;color:#e9edef;border-top-right-radius:2px}
.msg.bot .burbuja{background:#202c33;color:#e9edef;border-top-left-radius:2px}
.hora{font-size:10px;color:#8696a0;text-align:right;margin-top:2px;display:block}
.msg.bot .hora{text-align:left}

/* Indicador de escritura */
.typing{display:none;align-items:center;gap:4px;padding:8px 12px;background:#202c33;border-radius:8px;width:fit-content;margin-bottom:4px}
.typing.visible{display:flex}
.dot{width:7px;height:7px;border-radius:50%;background:#8696a0;animation:bounce 1.2s infinite}
.dot:nth-child(2){animation-delay:.2s}
.dot:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-6px)}}

/* Fecha separadora */
.fecha-sep{text-align:center;margin:12px 0}
.fecha-sep span{background:#182229;color:#8696a0;font-size:11px;padding:4px 12px;border-radius:12px}

/* Barra inferior */
.input-bar{background:#202c33;padding:8px 12px;display:flex;align-items:flex-end;gap:8px}
.input-wrap{flex:1;background:#2a3942;border-radius:24px;display:flex;align-items:center;padding:8px 14px;gap:8px;min-height:44px}
#msg{flex:1;background:none;border:none;outline:none;color:#e9edef;font-size:15px;font-family:'Inter',sans-serif;resize:none;max-height:100px;line-height:1.4}
#msg::placeholder{color:#8696a0}

.icon-btn{background:none;border:none;cursor:pointer;color:#8696a0;display:flex;align-items:center;justify-content:center;padding:2px;transition:color .2s;flex-shrink:0}
.icon-btn:hover{color:#e9edef}
.icon-btn svg{width:22px;height:22px}

.send-btn{width:44px;height:44px;border-radius:50%;background:#00a884;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:background .2s;box-shadow:0 2px 8px rgba(0,168,132,0.3)}
.send-btn:hover{background:#06cf9c}
.send-btn svg{width:20px;height:20px;fill:white}

/* Grabando */
.rec-bar{display:none;background:#202c33;padding:8px 16px;align-items:center;gap:12px}
.rec-bar.visible{display:flex}
.rec-dot{width:10px;height:10px;border-radius:50%;background:#f44336;animation:pulse 1s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.rec-time{color:#e9edef;font-size:14px;flex:1}
.rec-cancel{color:#8696a0;font-size:13px;cursor:pointer;padding:4px 8px}
.rec-cancel:hover{color:#e9edef}
.rec-send{background:#00a884;color:white;border:none;border-radius:20px;padding:6px 16px;font-size:13px;cursor:pointer;font-family:'Inter',sans-serif}

/* Foto preview */
.foto-preview{display:none;position:relative;margin-bottom:8px}
.foto-preview.visible{display:block}
.foto-preview img{max-width:200px;border-radius:8px;border:2px solid #25d366}
.foto-preview .quitar{position:absolute;top:-6px;right:-6px;background:#f44336;color:white;border:none;border-radius:50%;width:20px;height:20px;cursor:pointer;font-size:12px;display:flex;align-items:center;justify-content:center}

/* Input file oculto */
#file-input{display:none}
</style>
</head>
<body>

<div class="phone">

  <!-- Header -->
  <div class="wa-header">
    <div class="avatar">🛒</div>
    <div class="header-info">
      <div class="header-name">Distribuidora Alejandra María</div>
      <div class="header-status" id="estado-header">en línea</div>
    </div>
    <button class="btn-nuevo" onclick="nuevaConversacion()" title="Nueva conversación">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 5v14M5 12h14"/>
      </svg>
    </button>
  </div>

  <!-- Chat -->
  <div class="chat-bg" id="chat">
    <div class="fecha-sep"><span>HOY</span></div>
    <div class="typing" id="typing">
      <div class="dot"></div><div class="dot"></div><div class="dot"></div>
    </div>
  </div>

  <!-- Input bar -->
  <div class="input-bar" id="input-bar">
    <div style="flex:1;display:flex;flex-direction:column;gap:6px">
      <!-- Preview foto -->
      <div class="foto-preview" id="foto-preview">
        <img id="foto-img" src="" alt="foto">
        <button class="quitar" onclick="quitarFoto()">✕</button>
      </div>
      <div class="input-wrap">
        <button class="icon-btn" onclick="abrirCamara()" title="Enviar foto de lista">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
            <circle cx="12" cy="13" r="4"/>
          </svg>
        </button>
        <textarea id="msg" rows="1" placeholder="Escribe un mensaje..." oninput="autoResize(this)" onkeydown="teclaEnter(event)"></textarea>
        <button class="icon-btn" id="btn-mic" onclick="toggleMic()" title="Nota de voz">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
            <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8"/>
          </svg>
        </button>
      </div>
    </div>
    <button class="send-btn" onclick="enviar()" title="Enviar">
      <svg viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2v7z"/></svg>
    </button>
  </div>

  <!-- Barra de grabación -->
  <div class="rec-bar" id="rec-bar">
    <div class="rec-dot"></div>
    <span class="rec-time" id="rec-time">0:00</span>
    <span class="rec-cancel" onclick="cancelarGrabacion()">Cancelar</span>
    <button class="rec-send" onclick="enviarAudio()">Enviar 🎤</button>
  </div>

</div>

<!-- Input de archivo oculto -->
<input type="file" id="file-input" accept="image/*" capture="environment" onchange="seleccionarFoto(event)">

<script>
let numero = "test_web_" + Math.random().toString(36).slice(2,8);
let mediaRecorder = null;
let audioChunks = [];
let recTimer = null;
let recSecs = 0;
let fotoBase64 = null;
let grabando = false;

// ── Auto-resize textarea ──────────────────────────────────────
function autoResize(el){
  el.style.height='auto';
  el.style.height=Math.min(el.scrollHeight,100)+'px';
}

function teclaEnter(e){
  if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); enviar(); }
}

// ── Hora actual ───────────────────────────────────────────────
function horaActual(){
  return new Date().toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit'});
}

// ── Agregar burbuja ───────────────────────────────────────────
function agregar(texto, tipo, esImagen=false){
  const chat = document.getElementById("chat");
  const typing = document.getElementById("typing");
  const div = document.createElement("div");
  div.className = "msg " + tipo;
  let contenido = '';
  if(esImagen){
    contenido = `<img src="${texto}" style="max-width:200px;border-radius:8px;display:block">`;
  } else {
    contenido = texto.replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
  div.innerHTML = `<div class="burbuja">${contenido}<span class="hora">${horaActual()}</span></div>`;
  chat.insertBefore(div, typing);
  chat.scrollTop = chat.scrollHeight;
}

// ── Mostrar/ocultar typing ────────────────────────────────────
function setTyping(visible){
  const t = document.getElementById("typing");
  const h = document.getElementById("estado-header");
  t.classList.toggle("visible", visible);
  h.textContent = visible ? "escribiendo..." : "en línea";
  if(visible) document.getElementById("chat").scrollTop = 99999;
}

// ── Enviar texto ──────────────────────────────────────────────
async function enviar(){
  const input = document.getElementById("msg");
  const texto = input.value.trim();

  // Si hay foto adjunta
  if(fotoBase64){
    agregar(fotoBase64, "user", true);
    input.value=""; input.style.height='auto';
    await enviarAlBot("[El usuario envió una foto de lista de pedido]");
    quitarFoto();
    return;
  }

  if(!texto) return;
  agregar(texto, "user");
  input.value=""; input.style.height='auto';
  await enviarAlBot(texto);
}

async function enviarAlBot(mensaje){
  setTyping(true);
  try {
    const resp = await fetch("/test", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({numero, mensaje})
    });
    const data = await resp.json();
    setTyping(false);
    agregar(data.respuesta, "bot");
  } catch(e){
    setTyping(false);
    agregar("Error de conexión. Intenta de nuevo.", "bot");
  }
}

// ── Nueva conversación ────────────────────────────────────────
function nuevaConversacion(){
  if(!confirm("¿Iniciar una nueva conversación?")) return;
  numero = "test_web_" + Math.random().toString(36).slice(2,8);
  const chat = document.getElementById("chat");
  chat.innerHTML = `
    <div class="fecha-sep"><span>HOY</span></div>
    <div class="typing" id="typing">
      <div class="dot"></div><div class="dot"></div><div class="dot"></div>
    </div>`;
  quitarFoto();
}

// ── Cámara / foto ─────────────────────────────────────────────
function abrirCamara(){
  document.getElementById("file-input").click();
}

function seleccionarFoto(e){
  const file = e.target.files[0];
  if(!file) return;
  const reader = new FileReader();
  reader.onload = function(ev){
    fotoBase64 = ev.target.result;
    const preview = document.getElementById("foto-preview");
    document.getElementById("foto-img").src = fotoBase64;
    preview.classList.add("visible");
  };
  reader.readAsDataURL(file);
  e.target.value = "";
}

function quitarFoto(){
  fotoBase64 = null;
  document.getElementById("foto-preview").classList.remove("visible");
  document.getElementById("foto-img").src = "";
}

// ── Micrófono / grabación ─────────────────────────────────────
async function toggleMic(){
  if(!grabando) await iniciarGrabacion();
}

async function iniciarGrabacion(){
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio:true});
    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
    mediaRecorder.start();
    grabando = true;
    recSecs = 0;
    document.getElementById("input-bar").style.display = "none";
    document.getElementById("rec-bar").classList.add("visible");
    recTimer = setInterval(()=>{
      recSecs++;
      const m = Math.floor(recSecs/60);
      const s = recSecs%60;
      document.getElementById("rec-time").textContent = m+":"+(s<10?"0":"")+s;
    }, 1000);
  } catch(e){
    alert("No se pudo acceder al micrófono. Verifica los permisos del navegador.");
  }
}

function cancelarGrabacion(){
  if(mediaRecorder){ mediaRecorder.stop(); mediaRecorder.stream.getTracks().forEach(t=>t.stop()); }
  clearInterval(recTimer);
  grabando = false;
  document.getElementById("rec-bar").classList.remove("visible");
  document.getElementById("input-bar").style.display = "flex";
}

async function enviarAudio(){
  if(!mediaRecorder) return;
  mediaRecorder.stop();
  mediaRecorder.stream.getTracks().forEach(t=>t.stop());
  clearInterval(recTimer);
  grabando = false;

  await new Promise(r => setTimeout(r, 200));

  const blob = new Blob(audioChunks, {type:'audio/webm'});
  const reader = new FileReader();
  reader.onload = async function(ev){
    // Mostrar burbuja de audio
    const chat = document.getElementById("chat");
    const typing = document.getElementById("typing");
    const div = document.createElement("div");
    div.className = "msg user";
    div.innerHTML = `<div class="burbuja">
      🎤 <em style="color:#a8d5c2;font-size:13px">Nota de voz (${document.getElementById("rec-time").textContent})</em>
      <span class="hora">${horaActual()}</span>
    </div>`;
    chat.insertBefore(div, typing);
    chat.scrollTop = chat.scrollHeight;

    document.getElementById("rec-bar").classList.remove("visible");
    document.getElementById("input-bar").style.display = "flex";

    // Enviar al bot como texto simulado
    await enviarAlBot("[El usuario envió una nota de voz con su pedido]");
  };
  reader.readAsDataURL(blob);
}
</script>
</body>
</html>"""


@app.route("/test", methods=["POST"])
def test_bot():
    data = request.get_json()
    respuesta = procesar_con_claude(data.get("numero", "test"), data.get("mensaje", ""))
    return jsonify({"respuesta": limpiar_respuesta(respuesta)})


@app.route("/catalogo/buscar")
def buscar_en_catalogo():
    """Buscar producto manualmente: /catalogo/buscar?q=bon+bon+bum"""
    resultado = buscar_producto(request.args.get("q", ""))
    if resultado:
        return jsonify({"encontrado": True, "producto": resultado})
    return jsonify({"encontrado": False})


@app.route("/catalogo/total")
def total_catalogo():
    """Verificar cuántos productos están cargados."""
    return jsonify({"productos_cargados": len(catalogo_cache)})


# ══════════════════════════════════════════════════════════════
# INICIO - carga el catálogo al arrancar
# ══════════════════════════════════════════════════════════════

with app.app_context():
    cargar_catalogo()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
