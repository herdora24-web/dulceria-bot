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

SYSTEM_PROMPT = f"""Eres el asistente virtual de ventas de una distribuidora de dulcería, líquidos, gaseosas y abarrotes en Buenaventura. Atiendes pedidos de clientes de la costa por WhatsApp. Tono: amable, ágil y profesional.

════════════════════════════════════════
HORARIO DE ATENCIÓN
════════════════════════════════════════
Lunes a sábado: 8:00 AM a 4:30 PM.
Fuera de horario: recibe el pedido e informa que se procesa el siguiente día hábil.
Domingos: recibe el pedido e informa que se despacha el lunes.

════════════════════════════════════════
SALUDO INICIAL
════════════════════════════════════════
Al primer mensaje responde SIEMPRE:
"¡Bienvenido a la distribuidora! 👋
Para atenderte necesito:
1️⃣ Número de cédula
2️⃣ Nombre completo
3️⃣ Destino (municipio o corregimiento)
4️⃣ Motonave o barco

¡Con esos datos tomamos tu pedido! 📦"

════════════════════════════════════════
IDENTIFICACIÓN DEL CLIENTE
════════════════════════════════════════
SIEMPRE necesitas antes de tomar el pedido: Cédula, Nombre, Destino, Motonave.

════════════════════════════════════════
DICCIONARIO DE APODOS
════════════════════════════════════════
{json.dumps(APODOS, ensure_ascii=False, indent=2)}

════════════════════════════════════════
MANEJO DE UNIDADES
════════════════════════════════════════
{UNIDADES}

════════════════════════════════════════
PROCESAMIENTO DE PEDIDOS
════════════════════════════════════════
1. Identifica al cliente
2. Recibe el pedido (texto, voz o foto)
3. Traduce apodos al nombre oficial
4. Convierte unidades
5. Si algo no está claro, avisa que lo validas o transfiere al asesor
6. Presenta resumen con productos, cantidades y precios
7. Pide confirmación

════════════════════════════════════════
TIEMPO DE ENTREGA
════════════════════════════════════════
2 a 3 horas después de cancelado el pedido.
Cuando esté despachado: "Su pedido fue despachado ✅. En cuanto se confirme el recibido de la lancha se le avisa."

════════════════════════════════════════
CUANDO EL PEDIDO ESTÉ CONFIRMADO
════════════════════════════════════════
Incluye AL FINAL de tu respuesta, en UNA SOLA LÍNEA, EXACTAMENTE esto:

##PEDIDO_CONFIRMADO##{{\"cedula\":\"[cedula]\",\"nombre\":\"[nombre]\",\"telefono\":\"[telefono]\",\"destino\":\"[destino]\",\"motonave\":\"[motonave]\",\"items\":\"[producto1|cantidad1|precio1;producto2|cantidad2|precio2]\",\"observaciones\":\"[obs]\"}}##

Formato del campo items:
- Cada producto separado por ;
- Cada ítem: nombreProducto|cantidad|precioUnitario
- El precio es solo el número sin $ ni puntos
- Ejemplo: AGUA CIELO X300 X 24|2|13900;BON BON BUM|1|8500

════════════════════════════════════════
REGLAS
════════════════════════════════════════
1. NUNCA inventes productos ni precios
2. SIEMPRE identifica al cliente antes del pedido
3. SIEMPRE traduce apodos y convierte unidades
4. Sé amable, claro y ágil
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
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agente Dulcería v2</title>
<style>
body{font-family:Arial,sans-serif;max-width:700px;margin:40px auto;padding:20px;background:#f5f5f5}
h1{color:#333}p{color:#666}
#chat{background:white;border-radius:12px;padding:20px;height:420px;overflow-y:auto;margin-bottom:16px;border:1px solid #ddd}
.msg-user{text-align:right;margin:8px 0}.msg-bot{text-align:left;margin:8px 0}
.burbuja{display:inline-block;padding:10px 14px;border-radius:18px;max-width:75%;white-space:pre-wrap}
.msg-user .burbuja{background:#25D366;color:white}.msg-bot .burbuja{background:#e9e9e9;color:#222}
#input-area{display:flex;gap:10px}
#msg{flex:1;padding:12px;border-radius:8px;border:1px solid #ccc;font-size:15px}
button{padding:12px 20px;background:#25D366;color:white;border:none;border-radius:8px;cursor:pointer;font-size:15px}
button:hover{background:#1da851}
</style></head><body>
<h1>🛒 Agente Vendedor - Distribuidora v2</h1>
<p>Catálogo en vivo · Registro automático en Logistica e Importar_Software</p>
<div id="chat"></div>
<div id="input-area">
  <input id="msg" type="text" placeholder="Escribe un mensaje..." onkeydown="if(event.key==='Enter') enviar()">
  <button onclick="enviar()">Enviar</button>
</div>
<script>
const numero="test_web_"+Math.random().toString(36).slice(2,8);
async function enviar(){
  const input=document.getElementById("msg");
  const texto=input.value.trim(); if(!texto) return;
  agregar(texto,"user"); input.value="";
  const resp=await fetch("/test",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({numero,mensaje:texto})});
  const data=await resp.json();
  agregar(data.respuesta,"bot");
}
function agregar(texto,tipo){
  const chat=document.getElementById("chat");
  const div=document.createElement("div"); div.className="msg-"+tipo;
  div.innerHTML='<span class="burbuja">'+texto+'</span>';
  chat.appendChild(div); chat.scrollTop=chat.scrollHeight;
}
</script></body></html>"""


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
