"""
================================================================
AGENTE VENDEDOR - DISTRIBUIDORA DULCERÍA
Servidor Flask para WhatsApp + Claude API + Google Sheets
================================================================
VARIABLES DE ENTORNO necesarias en Railway:
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

# ── Clientes API ──────────────────────────────────────────────
claude_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# ── Memoria de conversaciones (por número de teléfono) ────────
conversaciones = {}

# ── Datos del cliente (cédula, nombre, destino, motonave) ─────
datos_clientes = {}

# ══════════════════════════════════════════════════════════════
# DICCIONARIO DE APODOS DE PRODUCTOS
# (Nombre como lo pide el cliente → Nombre oficial en catálogo)
# ══════════════════════════════════════════════════════════════

APODOS = {
    # BOT.docx
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
    # BOT2.docx
    "rulita x 24": "PAPITA X 24",
    "rulita": "PAPITA X 24",
    "papa salsa grande": "PAPITA GRANDE",
    "papita grande": "PAPITA GRANDE",
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

# ══════════════════════════════════════════════════════════════
# TABLA DE UNIDADES POR PRODUCTO
# ══════════════════════════════════════════════════════════════

UNIDADES = """
REFERENCIAS DE UNIDADES POR PRODUCTO (para convertir cuando el cliente pide "una paca", "una caja" o "un display"):

DULCES Y CONFITES:
- BON BON BUM: 24 und por caja
- CRAKENA: 24 und por caja
- FESTIVAL: 24 und por caja
- DUZ ORIGINAL: 24 und por caja
- ANISADA: 24 und por caja
- MORITA: 24 und por caja
- MAX COCO: 16 und por caja
- MINIBUM: 16 und por caja
- BANANAS SURTIDAS X 100: 100 und

CARNES FRÍAS:
- SALCHICHA VIENA: 48 und por caja
- JAMONETA GRANDE: 24 und por caja
- JAMONETA PEQUEÑA: 48 und por caja

LÁCTEOS Y ENLATADOS:
- ATUN ISABEL: 48 und por caja
- LECHERA X 100: 96 und por caja
- PROLECHE X 6: 6 und por display

PAPITAS Y SNACKS:
- PAPITA X 24 (RULITA): 24 und por paca
- PAPITA GRANDE (PAPA SALSA GRANDE): 12 und por paca
- YUPIS JUANCHIS: paca = 6 paquetes de 12 und (72 und total)
- CHEETOS PICANTE: 40 und por paca
- DETODITOS y PAPITAS MARGARITAS: paca = 6 paquetes de 12 und (72 und total)

GASEOSAS:
- POOL X 400 ML: display = 24 und
- POSTOBON 1.5 LT: display = 12 und
- GASEOSAS LITRO: display = 12 und
- POSTOBON PERSONAL: display = 15 und

SERVILLETAS:
- SERVILLETA X 200: 30 und por caja
- SERVILLETA X 300: preguntar al asesor

BOMBONES Y CAJAS:
- Caja de Bombones: preguntar entre CARTON, MEDIA CAJA, UND o DISPLAY

ENVÍO EN BARCO O MOTONAVE:
- Si el pedido es MENOR a $800.000 el cliente paga la entrada de la motonave
"""

# ══════════════════════════════════════════════════════════════
# PROMPT DEL SISTEMA
# ══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = f"""Eres el asistente virtual de ventas de una distribuidora de dulcería, líquidos, gaseosas y abarrotes ubicada en Buenaventura. Atiendes pedidos de clientes de la costa que llegan principalmente por WhatsApp. Tu tono es amable, ágil y profesional.

════════════════════════════════════════
HORARIO DE ATENCIÓN
════════════════════════════════════════
De lunes a sábado: 8:00 AM a 4:30 PM.

Si un cliente escribe FUERA de ese horario (incluyendo domingos), responde:
"¡Hola! Por el momento estamos fuera de nuestro horario de atención (8:00 AM – 4:30 PM). Con gusto recibo tu pedido y lo procesamos el siguiente día hábil en la mañana. ¡Cuéntame qué necesitas!"

Si escribe un DOMINGO, recíbele el pedido pero infórmale:
"Recibí tu pedido. Ten en cuenta que los domingos no despachamos, pero el día lunes a primera hora lo procesamos. Nuestro horario es de lunes a sábado de 8:00 AM a 4:30 PM."

════════════════════════════════════════
SALUDO INICIAL
════════════════════════════════════════
Al primer mensaje del cliente responde siempre:
"¡Bienvenido a la distribuidora! 👋
Para atenderte necesito algunos datos:
1️⃣ Número de cédula
2️⃣ Nombre completo
3️⃣ Destino (¿a qué municipio o corregimiento va el pedido?)
4️⃣ Motonave o barco en que viaja el pedido

Una vez los tenga, ¡con mucho gusto tomamos tu pedido! 📦"

════════════════════════════════════════
IDENTIFICACIÓN DEL CLIENTE
════════════════════════════════════════
Antes de tomar el pedido SIEMPRE debes tener:
- Número de cédula
- Nombre completo
- Destino
- Motonave / barco

Si el cliente ya está registrado por su número de teléfono, salúdalo por su nombre y confirma si el destino y motonave son los mismos.

════════════════════════════════════════
DICCIONARIO DE APODOS DE PRODUCTOS
════════════════════════════════════════
Los clientes usan nombres informales. Tradúcelos siempre al nombre oficial:

{json.dumps(APODOS, ensure_ascii=False, indent=2)}

════════════════════════════════════════
MANEJO DE UNIDADES
════════════════════════════════════════
{UNIDADES}

Cuando el cliente pida "una paca", "una caja" o "un display", usa la tabla anterior para convertir a unidades exactas. Si el producto no está en la tabla, pregunta al cliente cuántas unidades quiere.

════════════════════════════════════════
PROCESAMIENTO DE PEDIDOS
════════════════════════════════════════
1. Identifica al cliente (cédula, nombre, destino, motonave)
2. Escucha o lee lo que pide (texto, voz o foto de lista)
3. Traduce apodos al nombre oficial usando el diccionario
4. Convierte unidades cuando aplique
5. Si algo no está claro o no está en el inventario, avisa al cliente que lo vas a validar en el sistema o transfiere al asesor
6. Presenta resumen completo del pedido con productos y cantidades
7. Confirma el pedido

════════════════════════════════════════
FOTOS DE LISTAS
════════════════════════════════════════
Cuando el cliente envíe una foto de una lista escrita a mano:
- Lee todos los productos de la imagen
- Traduce los apodos al nombre oficial
- Convierte unidades
- Muestra el listado al cliente para que confirme antes de procesar

════════════════════════════════════════
TIEMPO DE ENTREGA
════════════════════════════════════════
El tiempo promedio de entrega es de 2 a 3 horas después de que el cliente haya cancelado su pedido.

Cuando el pedido esté despachado responde:
"Su pedido ya fue despachado con éxito ✅. En cuanto se tenga el recibido de la lancha se le enviará confirmación."

════════════════════════════════════════
AMBIGÜEDAD Y PRODUCTOS NO ENCONTRADOS
════════════════════════════════════════
Si el cliente pide algo que no reconoces o que no está claro:
- Opción A: "Voy a validar ese producto en el sistema, espera un momento."
- Opción B: "No encontré ese producto. ¿Me puedes dar más detalles o te transfiero con un asesor?"

════════════════════════════════════════
TRANSFERENCIA A ASESOR
════════════════════════════════════════
Si el cliente tiene una queja, devolución o consulta que no puedes resolver:
"Con gusto te comunico con uno de nuestros asesores para ayudarte mejor. En un momento te contactamos."

════════════════════════════════════════
CUANDO EL PEDIDO ESTÉ CONFIRMADO
════════════════════════════════════════
Cuando tengas toda la información (datos del cliente + productos + cantidades confirmadas), incluye al FINAL de tu respuesta esta línea especial EXACTAMENTE así, sin espacios extra:
##PEDIDO_CONFIRMADO##{{\"cedula\":\"[cedula]\",\"nombre\":\"[nombre]\",\"telefono\":\"[telefono]\",\"destino\":\"[destino]\",\"motonave\":\"[motonave]\",\"productos\":\"[lista de productos y cantidades]\",\"observaciones\":\"[observaciones si hay]\"}}##

════════════════════════════════════════
REGLAS
════════════════════════════════════════
1. NUNCA inventes productos ni precios
2. SIEMPRE identifica al cliente antes de tomar el pedido
3. SIEMPRE traduce apodos al nombre oficial
4. SIEMPRE convierte unidades usando la tabla
5. Si hay ambigüedad, pregunta o transfiere al asesor
6. Solo habla de temas de la distribuidora
7. Sé amable, claro y ágil
"""


# ══════════════════════════════════════════════════════════════
# GOOGLE SHEETS
# ══════════════════════════════════════════════════════════════

def get_google_client():
    """Crea el cliente de Google Sheets desde variable de entorno."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    # Intentar desde variable de entorno (Railway)
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        # Fallback: archivo local (desarrollo)
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
    return gspread.authorize(creds)


def registrar_pedido_sheets(datos_pedido: dict):
    """Registra el pedido confirmado en Google Sheets - Hoja Logística."""
    try:
        gc = get_google_client()
        sheet = gc.open_by_key(os.environ.get("GOOGLE_SHEET_ID_DULCERIA"))

        # Hoja 1: Logística (seguimiento de estados)
        ws_logistica = sheet.worksheet("Logistica")
        ahora = datetime.now()
        ws_logistica.append_row([
            ahora.strftime("%d/%m/%Y"),
            ahora.strftime("%H:%M"),
            datos_pedido.get("cedula", ""),
            datos_pedido.get("nombre", ""),
            datos_pedido.get("telefono", ""),
            datos_pedido.get("destino", ""),
            datos_pedido.get("motonave", ""),
            datos_pedido.get("productos", ""),
            datos_pedido.get("observaciones", ""),
            "EMPAQUE"  # Estado inicial
        ])
        print(f"✅ Pedido registrado en Logística: {datos_pedido.get('nombre')}")

    except Exception as e:
        print(f"❌ Error al registrar en Sheets: {e}")


def extraer_pedido_confirmado(texto: str) -> dict | None:
    """Busca el marcador de pedido confirmado en la respuesta de Claude."""
    if "##PEDIDO_CONFIRMADO##" in texto:
        try:
            inicio = texto.index("##PEDIDO_CONFIRMADO##") + len("##PEDIDO_CONFIRMADO##")
            fin = texto.index("##", inicio)
            json_str = texto[inicio:fin]
            return json.loads(json_str)
        except Exception as e:
            print(f"Error extrayendo pedido: {e}")
    return None


def limpiar_respuesta(texto: str) -> str:
    """Elimina el marcador técnico antes de enviar al cliente."""
    if "##PEDIDO_CONFIRMADO##" in texto:
        inicio = texto.index("##PEDIDO_CONFIRMADO##")
        texto = texto[:inicio].strip()
    return texto


# ══════════════════════════════════════════════════════════════
# TRANSCRIPCIÓN DE NOTAS DE VOZ (Whisper)
# ══════════════════════════════════════════════════════════════

def transcribir_audio(audio_id: str) -> str | None:
    """Descarga y transcribe una nota de voz de WhatsApp con Whisper."""
    try:
        token = os.environ.get("WHATSAPP_TOKEN")
        headers = {"Authorization": f"Bearer {token}"}

        url_info = requests.get(
            f"https://graph.facebook.com/v18.0/{audio_id}",
            headers=headers
        ).json()
        audio_url = url_info.get("url")

        audio_resp = requests.get(audio_url, headers=headers)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_resp.content)
            temp_path = f.name

        from openai import OpenAI
        openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        with open(temp_path, "rb") as audio_file:
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es"
            )
        os.unlink(temp_path)
        return transcript.text

    except Exception as e:
        print(f"Error transcribiendo audio: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# LEER IMAGEN DE LISTA (Claude Vision)
# ══════════════════════════════════════════════════════════════

def leer_imagen_lista(image_id: str) -> str:
    """Descarga la imagen de WhatsApp y la envía a Claude Vision para leer la lista."""
    try:
        token = os.environ.get("WHATSAPP_TOKEN")
        headers = {"Authorization": f"Bearer {token}"}

        # Obtener URL de la imagen
        url_info = requests.get(
            f"https://graph.facebook.com/v18.0/{image_id}",
            headers=headers
        ).json()
        image_url = url_info.get("url")

        # Descargar la imagen
        img_resp = requests.get(image_url, headers=headers)
        image_data = base64.standard_b64encode(img_resp.content).decode("utf-8")
        media_type = img_resp.headers.get("Content-Type", "image/jpeg")

        # Enviar a Claude Vision para leer la lista
        response = claude_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Esta es una lista de pedido de un cliente de una distribuidora de dulcería en Colombia. "
                            "Lee todos los productos que aparecen en la imagen, incluyendo cantidades si las hay. "
                            "Escríbelos tal como aparecen, uno por línea. "
                            "Si hay texto que no puedes leer claramente, escribe [ilegible] en ese lugar. "
                            "Solo devuelve la lista de productos, sin comentarios adicionales."
                        )
                    }
                ],
            }]
        )
        lista_leida = response.content[0].text
        return f"[Lista leída de la imagen]\n{lista_leida}"

    except Exception as e:
        print(f"Error leyendo imagen: {e}")
        return "[El cliente envió una foto de lista pero no pude leerla. Por favor pide que la escriba.]"


# ══════════════════════════════════════════════════════════════
# CLAUDE - PROCESAR MENSAJE
# ══════════════════════════════════════════════════════════════

def procesar_con_claude(numero: str, mensaje_usuario: str) -> str:
    """Envía el mensaje a Claude manteniendo el historial de conversación."""
    if numero not in conversaciones:
        conversaciones[numero] = []

    conversaciones[numero].append({
        "role": "user",
        "content": mensaje_usuario
    })

    # Mantener máximo 30 turnos para controlar costos
    historial = conversaciones[numero][-30:]

    respuesta = claude_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=historial
    )

    texto_respuesta = respuesta.content[0].text

    conversaciones[numero].append({
        "role": "assistant",
        "content": texto_respuesta
    })

    return texto_respuesta


# ══════════════════════════════════════════════════════════════
# WHATSAPP - ENVIAR MENSAJE
# ══════════════════════════════════════════════════════════════

def enviar_whatsapp(numero: str, mensaje: str):
    """Envía un mensaje de texto por WhatsApp."""
    token = os.environ.get("WHATSAPP_TOKEN")
    phone_id = os.environ.get("PHONE_NUMBER_ID")

    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": mensaje}
    }
    resp = requests.post(url, headers=headers, json=data)
    print(f"WhatsApp send → {resp.status_code}: {resp.text}")


# ══════════════════════════════════════════════════════════════
# WEBHOOK - VERIFICACIÓN
# ══════════════════════════════════════════════════════════════

@app.route("/webhook", methods=["GET"])
def verificar_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == os.environ.get("VERIFY_TOKEN"):
        print("✅ Webhook verificado correctamente")
        return challenge, 200
    else:
        return "Token incorrecto", 403


# ══════════════════════════════════════════════════════════════
# WEBHOOK - RECIBIR MENSAJES
# ══════════════════════════════════════════════════════════════

@app.route("/webhook", methods=["POST"])
def recibir_mensaje():
    """Recibe todos los mensajes entrantes de WhatsApp."""
    try:
        data = request.get_json()
        print(f"Mensaje recibido: {json.dumps(data, indent=2)}")

        entry = data.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return jsonify({"status": "ok"}), 200

        msg = messages[0]
        numero = msg.get("from")
        tipo = msg.get("type")

        # ── Procesar según tipo de mensaje ────────────────────
        if tipo == "text":
            texto_cliente = msg["text"]["body"]

        elif tipo == "audio":
            audio_id = msg["audio"]["id"]
            texto_cliente = transcribir_audio(audio_id)
            if not texto_cliente:
                enviar_whatsapp(numero, "No pude escuchar bien tu nota de voz 😅 ¿Puedes escribir el pedido?")
                return jsonify({"status": "ok"}), 200

        elif tipo == "image":
            # Intentar leer lista de la imagen con Claude Vision
            image_id = msg["image"]["id"]
            texto_cliente = leer_imagen_lista(image_id)

        else:
            enviar_whatsapp(numero, "Por ahora recibo mensajes de texto, notas de voz y fotos de listas 📝")
            return jsonify({"status": "ok"}), 200

        # ── Enviar a Claude ───────────────────────────────────
        respuesta_claude = procesar_con_claude(numero, texto_cliente)

        # ── Verificar si hay pedido confirmado ────────────────
        pedido = extraer_pedido_confirmado(respuesta_claude)
        if pedido:
            pedido["telefono"] = numero
            registrar_pedido_sheets(pedido)

        # ── Limpiar y enviar respuesta al cliente ─────────────
        respuesta_limpia = limpiar_respuesta(respuesta_claude)
        enviar_whatsapp(numero, respuesta_limpia)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print(f"❌ Error en webhook: {e}")
        return jsonify({"status": "error", "detail": str(e)}), 500


# ══════════════════════════════════════════════════════════════
# INTERFAZ WEB DE PRUEBAS
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Agente Dulcería - Pruebas</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto; padding: 20px; background: #f5f5f5; }
            h1 { color: #333; }
            #chat { background: white; border-radius: 12px; padding: 20px; height: 400px; overflow-y: auto; margin-bottom: 16px; border: 1px solid #ddd; }
            .msg-user { text-align: right; margin: 8px 0; }
            .msg-bot  { text-align: left;  margin: 8px 0; }
            .burbuja { display: inline-block; padding: 10px 14px; border-radius: 18px; max-width: 75%; white-space: pre-wrap; }
            .msg-user .burbuja { background: #25D366; color: white; }
            .msg-bot  .burbuja { background: #e9e9e9; color: #222; }
            #input-area { display: flex; gap: 10px; }
            #msg { flex: 1; padding: 12px; border-radius: 8px; border: 1px solid #ccc; font-size: 15px; }
            button { padding: 12px 20px; background: #25D366; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 15px; }
            button:hover { background: #1da851; }
        </style>
    </head>
    <body>
        <h1>🛒 Agente Vendedor - Distribuidora</h1>
        <p>Interfaz de pruebas (simula WhatsApp)</p>
        <div id="chat"></div>
        <div id="input-area">
            <input id="msg" type="text" placeholder="Escribe un mensaje..." onkeydown="if(event.key==='Enter') enviar()">
            <button onclick="enviar()">Enviar</button>
        </div>
        <script>
            const numero = "test_web_" + Math.random().toString(36).slice(2, 8);
            async function enviar() {
                const input = document.getElementById("msg");
                const texto = input.value.trim();
                if (!texto) return;
                agregar(texto, "user");
                input.value = "";
                const resp = await fetch("/test", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({numero, mensaje: texto})
                });
                const data = await resp.json();
                agregar(data.respuesta, "bot");
            }
            function agregar(texto, tipo) {
                const chat = document.getElementById("chat");
                const div = document.createElement("div");
                div.className = "msg-" + tipo;
                div.innerHTML = '<span class="burbuja">' + texto + '</span>';
                chat.appendChild(div);
                chat.scrollTop = chat.scrollHeight;
            }
        </script>
    </body>
    </html>
    """


@app.route("/test", methods=["POST"])
def test_bot():
    """Endpoint para la interfaz web de pruebas."""
    data = request.get_json()
    numero = data.get("numero", "test")
    mensaje = data.get("mensaje", "")
    respuesta = procesar_con_claude(numero, mensaje)
    respuesta_limpia = limpiar_respuesta(respuesta)
    return jsonify({"respuesta": respuesta_limpia})


# ══════════════════════════════════════════════════════════════
# INICIO
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
