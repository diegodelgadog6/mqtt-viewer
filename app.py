# time_with_lapse.py — C3 (visor MQTT + web para ESP32 y Raspberry)
from flask import Flask, jsonify, render_template_string
import locale
import paho.mqtt.client as mqtt
from collections import deque
import time

app = Flask(__name__)

# --- Configuración opcional de idioma ---
for loc in ('es_ES.UTF-8', 'es_MX.UTF-8'):
    try:
        locale.setlocale(locale.LC_TIME, loc)
        break
    except:
        pass

# ======= CONFIGURA AQUÍ =======
BROKER_HOST = "test.mosquitto.org"   # broker público
BROKER_PORT = 1883
TOPIC1 = "data/Raspy"                # publica la Raspberry
TOPIC2 = "data/ESP32"                # publica el Arduino
ULTIMOS_N = 50                       # cuántos mensajes mostrar (histórico general)
# ==========================================

mensajes = deque(maxlen=ULTIMOS_N)
ultimo_por_topic = {TOPIC1: None, TOPIC2: None}  # <<-- guardamos el último de cada topic

# --- Conexión MQTT ---
def on_connect(client, userdata, flags, rc):
    print("✅ MQTT conectado (rc=%s)" % rc)
    client.subscribe(TOPIC1)
    client.subscribe(TOPIC2)
    print(f"📡 Suscrito a: {TOPIC1} y {TOPIC2}")

def on_message(client, userdata, msg):
    payload = msg.payload.decode(errors="ignore")
    marca = time.strftime("%H:%M:%S")
    registro = {"ts": marca, "topic": msg.topic, "msg": payload}
    mensajes.appendleft(registro)
    if msg.topic in ultimo_por_topic:
        # siempre mantenemos el último de cada topic
        ultimo_por_topic[msg.topic] = {"ts": marca, "msg": payload}
    print(f"RX[{msg.topic}]: {payload}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER_HOST, BROKER_PORT, 60)
client.loop_start()

# --- Página principal (http://localhost:5000) ---
@app.route('/')
def index():
    html = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>📡 C3 – Visor MQTT</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; text-align: center; }
            button {
                padding: 10px 18px; font-size: 16px; border: 0; border-radius: 8px;
                background: #3498db; color: #fff; cursor: pointer; margin: 6px 8px;
            }
            button:hover { background: #2980b9; }
            #resultado { white-space: pre-line; font-size: 16px; color: #2c3e50; margin-top: 16px; }
            code { background: #f3f3f3; padding: 2px 6px; border-radius: 6px; }
            .row { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; }
        </style>
    </head>
    <body>
        <h2>📡 Mensajes MQTT recibidos</h2>
        <p>Broker: <code>{{host}}</code> · Topics: <code>{{t1}}</code>, <code>{{t2}}</code></p>

        <div class="row">
            <!-- Botón original (opcional: sigue trayendo el histórico cada 3s) -->
            <button onclick="toggleUpdate()">⏯️ Iniciar / Detener histórico</button>

            <!-- NUEVOS: lecturas puntuales por topic -->
            <button onclick="leerUnaVez('{{t1}}')">🟢 Leer solo {{t1}}</button>
            <button onclick="leerUnaVez('{{t2}}')">🟠 Leer solo {{t2}}</button>
        </div>

        <div id="resultado">Esperando actualización… (usa cualquiera de los botones)</div>

        <script>
            let intervalo = null;

            async function obtenerMensajes() {
                const res = await fetch('/api/mqtt');
                const data = await res.json();
                const lines = (data.mensajes || []).map(
                    m => `${m.ts} — ${m.topic}: ${m.msg}`
                );
                document.getElementById('resultado').innerText =
                    lines.length ? lines.join("\\n") : "Sin mensajes aún…";
            }

            function toggleUpdate() {
                if (intervalo) {
                    clearInterval(intervalo);
                    intervalo = null;
                    document.getElementById('resultado').innerText += "\\n⏸️ Histórico detenido";
                } else {
                    obtenerMensajes();
                    intervalo = setInterval(obtenerMensajes, 3000);
                }
            }

            // === NUEVO: lectura "solo una vez" del último mensaje de un topic ===
            async function leerUnaVez(topic) {
                const res = await fetch('/api/peek?topic=' + encodeURIComponent(topic));
                const data = await res.json();
                // data = { ts, topic, msg } o {}
                if (data && data.msg !== undefined) {
                    document.getElementById('resultado').innerText =
                        `${data.ts} — ${topic}: ${data.msg}`;
                } else {
                    document.getElementById('resultado').innerText =
                        "No hay lectura disponible todavía para " + topic;
                }
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(
        html,
        host=f"{BROKER_HOST}:{BROKER_PORT}",
        t1=TOPIC1,
        t2=TOPIC2
    )

# --- Endpoints ---
@app.route('/api/mqtt')
def get_mqtt():
    # histórico general (igual que antes)
    return jsonify({"mensajes": list(mensajes)})

@app.route('/api/peek')
def api_peek():
    # devuelve SOLO la lectura "del momento" (última conocida) del topic pedido
    from flask import request
    topic = request.args.get('topic')
    if topic in ultimo_por_topic and ultimo_por_topic[topic]:
        return jsonify({"ts": ultimo_por_topic[topic]["ts"],
                        "topic": topic,
                        "msg": ultimo_por_topic[topic]["msg"]})
    return jsonify({})  # si aún no ha llegado nada de ese topic

if __name__ == '__main__':
    import os
    # Railway asigna el puerto automáticamente
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)