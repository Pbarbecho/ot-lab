"""Escenarios de la Práctica 1a (láminas 19-32 del Taller 2).

Cada escenario:
  board   -> sección "registers" que se escribe en ot-lab/modbus/server.json
             (claves = dirección pymodbus + 1, lámina 20; salvo el escenario 19-20
             que usa el JSON original para demostrar el desfase)
  labels  -> nombres de la topología por tabla (di, co, ir, hr) y dirección
  steps   -> pasos del reto; cada uno con sentencias de la sesión interactiva
             (c = ModbusTcpClient('172.28.0.30', port=5020), ya conectado)
  checks  -> comprobaciones opcionales por sentencia:
             i   índice de la sentencia dentro del paso
             out salida esperada en consola (repr)
             dir "TX" (Query) o "RX" (Response) y pdu = bytes PDU esperados en hex
Agregar un escenario = añadir un dict a SCENARIOS.
"""

U = ", device_id=1"

L_EJEMPLO = {
    "di": {0: {"label": "Pulsador"}},
    "co": {0: {"label": "LED", "icon": "led"}, 1: {"label": "Ventilador", "icon": "fan"}},
    "ir": {0: {"label": "Temperatura", "scale": 10, "unit": "°C"}, 1: {"label": "CO₂", "unit": "ppm"}},
    "hr": {0: {"label": "Consigna", "scale": 10, "unit": "°C"}, 1: {"label": "Umbral CO₂", "unit": "ppm"}},
}

L_BITS = {
    "di": {0: {"label": "Marcha"}, 1: {"label": "Paro"}, 2: {"label": "Emergencia"}, 3: {"label": "Puerta"}},
    "co": {0: {"label": "LED verde", "icon": "led", "color": "#39d98a"},
           1: {"label": "LED rojo", "icon": "led", "color": "#ff5a4f"},
           2: {"label": "Ventilador", "icon": "fan"}, 3: {"label": "Bomba", "icon": "pump"},
           4: {"label": "Sirena", "icon": "bell"}},
}

L_PALABRAS = {
    "ir": {0: {"label": "Temperatura", "scale": 10, "unit": "°C"}, 1: {"label": "Humedad", "scale": 10, "unit": "%"},
           2: {"label": "CO₂", "unit": "ppm"}, 3: {"label": "Presión", "unit": "hPa"}},
    "hr": {0: {"label": "Consigna T", "scale": 10, "unit": "°C"}, 1: {"label": "Consigna HR", "scale": 10, "unit": "%"},
           2: {"label": "Umbral CO₂", "unit": "ppm"}, 3: {"label": "Ventilador", "unit": "%"},
           4: {"label": "Modo", "unit": "1 = auto"}},
}

SCENARIOS = [
    # ------------------------------------------------------------------ 19-20
    {
        "id": "offset",
        "title": "server.json original · desfase +1",
        "slides": "19–20",
        "intro": "JSON original con claves desde «0». pymodbus pide la dirección 0 y el servidor "
                 "entrega la clave «1»: el 1234 de la clave «0» es inalcanzable.",
        "board": {
            "discreteInput": {"0": True, "1": False},
            "coils": {"0": False, "1": True},
            "holdingRegister": {"0": 1234, "1": 25, "2": 72},
            "inputRegister": {"0": 999},
        },
        "labels": {
            "di": {0: {"label": "DI 0"}, 1: {"label": "DI 1"}},
            "co": {0: {"label": "Coil 0"}, 1: {"label": "Coil 1"}},
            "ir": {0: {"label": "IR 0"}},
            "hr": {0: {"label": "HR 0"}, 1: {"label": "HR 1"}, 2: {"label": "HR 2"}},
        },
        "steps": [
            {"label": "Leer 3 holding desde 0 (FC 03)",
             "stmts": [f"c.read_holding_registers(0, count=3{U}).registers"],
             "checks": [{"i": 0, "out": "[25, 72, 0]"}],
             "note": "Claves «1», «2» y un hueco: el 1234 de «0» no aparece."},
            {"label": "Leer coils y DI desde 0",
             "stmts": [f"c.read_coils(0, count=2{U}).bits[:2]",
                       f"c.read_discrete_inputs(0, count=2{U}).bits[:2]"],
             "checks": [{"i": 0, "out": "[True, False]"}, {"i": 1, "out": "[False, False]"}],
             "note": "address=0 lee la clave «1»: también desplazado en las tablas de bits."},
        ],
    },
    # ------------------------------------------------------------------ 21-29
    {
        "id": "ejemplo",
        "title": "PLC del ejemplo · coils y registros",
        "slides": "21–29",
        "intro": "Pulsador (DI 0), LED y ventilador (coils 0-1), temperatura y CO₂ (IR 0-1), "
                 "consigna y umbral (HR 0-1). Claves = dirección + 1.",
        "board": {
            "discreteInput": {"1": True},
            "coils": {"1": False, "2": False},
            "inputRegister": {"1": 235, "2": 612},
            "holdingRegister": {"1": 260, "2": 800},
        },
        "labels": L_EJEMPLO,
        "steps": [
            {"label": "Lámina 22 · leer LED y ventilador (FC 01)",
             "stmts": [f"c.read_coils(0, count=2{U}).bits[:2]"],
             "checks": [{"i": 0, "out": "[False, False]", "dir": "RX", "pdu": "01 01 00"}]},
            {"label": "Lámina 22 · LED ON (FC 05)",
             "stmts": [f"c.write_coil(0, True{U})"],
             "checks": [{"i": 0, "dir": "TX", "pdu": "05 00 00 FF 00"}],
             "note": "En la trama viaja FF 00 (ON) o 00 00 (OFF)."},
            {"label": "Lámina 23 · reto: LED + ventilador en UNA trama (FC 15)",
             "stmts": [f"c.write_coils(0, [True, True]{U})",
                       f"c.read_coils(0, count=2{U}).bits[:2]"],
             "checks": [{"i": 0, "dir": "TX", "pdu": "0F 00 00 00 02 01 03"},
                        {"i": 1, "out": "[True, True]"}],
             "note": "Prediga el byte de datos antes de enviar: 0000 0011 = 0x03 (coil 0 = bit menos significativo)."},
            {"label": "Lámina 28 · ¿dónde viajan los True/False? (FC 01)",
             "stmts": [f"c.read_coils(0, count=2{U}).bits[:2]"],
             "checks": [{"i": 0, "dir": "RX", "pdu": "01 01 03"}],
             "note": "La Query solo pide (00 00 00 02); los valores viajan en la Response."},
            {"label": "Lámina 22 · leer pulsador (FC 02)",
             "stmts": [f"c.read_discrete_inputs(0, count=1{U}).bits[0]"],
             "checks": [{"i": 0, "out": "True"}],
             "note": "Discrete input: lo fija el campo, el maestro solo lo lee."},
            {"label": "Apagar LED y ventilador (FC 15)",
             "stmts": [f"c.write_coils(0, [False, False]{U})"]},
            {"label": "Lámina 29 · leer medidas (FC 04) y parámetros (FC 03)",
             "stmts": [f"c.read_input_registers(0, count=2{U}).registers",
                       f"c.read_holding_registers(0, count=2{U}).registers"],
             "checks": [{"i": 0, "out": "[235, 612]"}, {"i": 1, "out": "[260, 800]"}],
             "note": "235 = 23,5 °C (×10) · 612 ppm · consigna 26,0 °C · umbral 800 ppm."},
            {"label": "Lámina 29 · consigna a 28,0 °C (FC 06)",
             "stmts": [f"c.write_register(0, 280{U})"],
             "checks": [{"i": 0, "dir": "TX", "pdu": "06 00 00 01 18"}]},
            {"label": "Lámina 29 · consigna + umbral en una trama (FC 16)",
             "stmts": [f"c.write_registers(0, [280, 1000]{U})",
                       f"c.read_holding_registers(0, count=2{U}).registers"],
             "checks": [{"i": 0, "dir": "TX", "pdu": "10 00 00 00 02 04 01 18 03 E8"},
                        {"i": 1, "out": "[280, 1000]"}]},
        ],
    },
    # --------------------------------------------------------------------- 30
    {
        "id": "bits",
        "title": "Reto · tablero con varios bits",
        "slides": "30",
        "intro": "Cuatro entradas y cinco salidas: leer en bloque, cambiar una y cambiar varias "
                 "de golpe (parada de emergencia en una sola trama).",
        "board": {
            "discreteInput": {"1": True, "2": False, "3": False, "4": True},
            "coils": {"1": True, "2": False, "3": False, "4": False, "5": False},
        },
        "labels": L_BITS,
        "steps": [
            {"label": "Paso 2 · leer las 4 entradas (FC 02, count=4)",
             "stmts": [f"c.read_discrete_inputs(0, count=4{U}).bits[:4]"],
             "checks": [{"i": 0, "out": "[True, False, False, True]", "dir": "RX", "pdu": "02 01 09"}],
             "note": "Pulsado: Marcha; Puerta abierta. Byte 0000 1001 = 0x09 (DI 0 = bit menos significativo)."},
            {"label": "Paso 3 · leer los 5 coils (FC 01, count=5)",
             "stmts": [f"c.read_coils(0, count=5{U}).bits[:5]"],
             "checks": [{"i": 0, "out": "[True, False, False, False, False]", "dir": "RX", "pdu": "01 01 01"}]},
            {"label": "Paso 4 · arrancar la bomba (FC 05, coil 3)",
             "stmts": [f"c.write_coil(3, True{U})",
                       f"c.read_coils(0, count=5{U}).bits[:5]"],
             "checks": [{"i": 0, "dir": "TX", "pdu": "05 00 03 FF 00"},
                        {"i": 1, "out": "[True, False, False, True, False]"}]},
            {"label": "Paso 5 · parada de emergencia en UNA trama (FC 15)",
             "stmts": [f"c.write_coils(0, [False, True, True, False, True]{U})",
                       f"c.read_coils(0, count=5{U}).bits[:5]"],
             "checks": [{"i": 0, "dir": "TX", "pdu": "0F 00 00 00 05 01 16"},
                        {"i": 1, "out": "[False, True, True, False, True]", "dir": "RX", "pdu": "01 01 16"}],
             "note": "Predicción: verde OFF, rojo ON, ventilador ON, bomba OFF, sirena ON → 1 0110 = 0x16."},
        ],
    },
    # --------------------------------------------------------------------- 31
    {
        "id": "palabras",
        "title": "Reto · tablero con varias palabras",
        "slides": "31",
        "intro": "Cuatro medidas y cinco parámetros: leer en bloque, cambiar uno, «modo verano» "
                 "en una sola trama y valores fuera de rango.",
        "board": {
            "inputRegister": {"1": 235, "2": 480, "3": 612, "4": 1013},
            "holdingRegister": {"1": 260, "2": 500, "3": 800, "4": 40, "5": 0},
        },
        "labels": L_PALABRAS,
        "steps": [
            {"label": "Paso 2 · leer las 4 medidas (FC 04, count=4)",
             "stmts": [f"c.read_input_registers(0, count=4{U}).registers"],
             "checks": [{"i": 0, "out": "[235, 480, 612, 1013]",
                         "dir": "RX", "pdu": "04 08 00 EB 01 E0 02 64 03 F5"}],
             "note": "23,5 °C · 48,0 % · 612 ppm · 1013 hPa. Respuesta: 1 + 1 + 2·4 = 10 bytes."},
            {"label": "Paso 3 · leer los 5 parámetros (FC 03, count=5)",
             "stmts": [f"c.read_holding_registers(0, count=5{U}).registers"],
             "checks": [{"i": 0, "out": "[260, 500, 800, 40, 0]"}]},
            {"label": "Paso 4 · ventilador a 75 % (FC 06, HR 3)",
             "stmts": [f"c.write_register(3, 75{U})",
                       f"c.read_holding_registers(0, count=5{U}).registers"],
             "checks": [{"i": 0, "dir": "TX", "pdu": "06 00 03 00 4B"},
                        {"i": 1, "out": "[260, 500, 800, 75, 0]"}]},
            {"label": "Paso 5 · «modo verano» en UNA trama (FC 16)",
             "stmts": [f"c.write_registers(0, [240, 550, 1000, 60, 1]{U})",
                       f"c.read_holding_registers(0, count=5{U}).registers"],
             "checks": [{"i": 0, "dir": "TX", "pdu": "10 00 00 00 05 0A 00 F0 02 26 03 E8 00 3C 00 01"},
                        {"i": 1, "out": "[240, 550, 1000, 60, 1]"}],
             "note": "Predicción: 10 bytes de datos, PDU de 16 bytes (1+2+2+1+10)."},
            {"label": "Paso 6 · valor > 65535 (FC 06)",
             "stmts": [f"c.write_register(2, 70000{U})"],
             "note": "¿Quién se queja? pymodbus: struct.error al codificar; la trama nunca sale."},
            {"label": "Paso 6 · valor negativo (FC 06)",
             "stmts": [f"c.write_register(0, -5{U})"]},
            {"label": "Paso 6 · cinco valores desde HR 3 (desborda a HR 7)",
             "stmts": [f"c.write_registers(3, [1, 2, 3, 4, 5]{U})",
                       f"c.read_holding_registers(0, count=8{U}).registers"],
             "checks": [{"i": 1, "out": "[240, 550, 1000, 1, 2, 3, 4, 5]"}],
             "note": "El esclavo no se queja: initializeUndefinedRegisters crea HR 5-7."},
        ],
    },
    # --------------------------------------------------------------------- 32
    {
        "id": "captura",
        "title": "Reto · captura completa (9 peticiones)",
        "slides": "32",
        "intro": "Los dos tableros cargados a la vez. Ejecute todos los pasos: la tabla de la "
                 "lámina 32 (FC, dónde van los datos, PDU y valor) se llena sola en la captura.",
        "board": {
            "discreteInput": {"1": True, "2": False, "3": False, "4": True},
            "coils": {"1": True, "2": False, "3": False, "4": False, "5": False},
            "inputRegister": {"1": 235, "2": 480, "3": 612, "4": 1013},
            "holdingRegister": {"1": 260, "2": 500, "3": 800, "4": 40, "5": 0},
        },
        "labels": {**L_BITS, **L_PALABRAS},
        "steps": [
            {"label": "Las 9 peticiones de las láminas 30 y 31",
             "stmts": [f"c.read_discrete_inputs(0, count=4{U}).bits[:4]",
                       f"c.read_coils(0, count=5{U}).bits[:5]",
                       f"c.write_coil(3, True{U})",
                       f"c.write_coils(0, [False, True, True, False, True]{U})",
                       f"c.read_input_registers(0, count=4{U}).registers",
                       f"c.read_holding_registers(0, count=5{U}).registers",
                       f"c.write_register(3, 75{U})",
                       f"c.write_registers(0, [240, 550, 1000, 60, 1]{U})",
                       f"c.write_registers(3, [1, 2, 3, 4, 5]{U})"],
             "checks": [{"i": 0, "dir": "RX", "pdu": "02 01 09"},
                        {"i": 1, "dir": "RX", "pdu": "01 01 01"},
                        {"i": 2, "dir": "TX", "pdu": "05 00 03 FF 00"},
                        {"i": 3, "dir": "TX", "pdu": "0F 00 00 00 05 01 16"},
                        {"i": 4, "dir": "RX", "pdu": "04 08 00 EB 01 E0 02 64 03 F5"},
                        {"i": 5, "dir": "RX", "pdu": "03 0A 01 04 01 F4 03 20 00 28 00 00"},
                        {"i": 6, "dir": "TX", "pdu": "06 00 03 00 4B"},
                        {"i": 7, "dir": "TX", "pdu": "10 00 00 00 05 0A 00 F0 02 26 03 E8 00 3C 00 01"},
                        {"i": 8, "dir": "TX", "pdu": "10 00 03 00 05 0A 00 01 00 02 00 03 00 04 00 05"}],
             "note": "Lecturas: datos en la Response. Escrituras: en la Query. Una excepción vendría como FC 0x90."},
        ],
    },
    # ------------------------------------------------------------------ 33-36
    {
        "id": "openplc",
        "kind": "openplc",
        "title": "OpenPLC · sondeo y lógica",
        "slides": "33–36",
        "intro": "El maestro ya no es Python: es el runtime de OpenPLC, que sondea los tableros de las "
                 "láminas 30–31 cada 100 ms y aplica una lógica de umbrales (tableros.st). "
                 "La tabla de la lámina 36 se llena en vivo desde la captura.",
        "board": {
            "discreteInput": {"1": True, "2": False, "3": False, "4": False},
            "coils": {"1": False, "2": False, "3": False, "4": False, "5": False},
            "inputRegister": {"1": 235, "2": 480, "3": 612, "4": 1013},
            "holdingRegister": {"1": 260, "2": 500, "3": 800, "4": 40, "5": 0},
        },
        "labels": {
            **L_BITS,
            "ir": L_PALABRAS["ir"],
            "hr": {**L_PALABRAS["hr"],
                   5: {"label": "Estado PLC", "unit": "bits"}, 6: {"label": "Exceso T", "scale": 10, "unit": "°C"},
                   7: {"label": "Ciclos PLC"}},
        },
        "program": "tableros.st",
        "logic": [
            {"out": ["co", 1], "text": "LED rojo = temperatura (IR 0) > consigna T (HR 0)  o  emergencia"},
            {"out": ["co", 2], "text": "Ventilador = CO₂ (IR 2) > umbral CO₂ (HR 2)  o  alarma de temperatura"},
            {"out": ["co", 0], "text": "LED verde = marcha y no paro y no emergencia y sin alarma"},
            {"out": ["co", 3], "text": "Bomba = marcha y no paro y no emergencia y puerta cerrada (DI 3 = 0)"},
            {"out": ["co", 4], "text": "Sirena = emergencia (DI 2)"},
        ],
        "steps": [],
    },
]
