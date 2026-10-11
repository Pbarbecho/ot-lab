"""
opcua-py · servidor OPC UA del laboratorio (asyncua)
GENERADO por el Explorador OPC UA (http://localhost:8600) a partir de opcua/modelo.json.
Si lo edita a mano, el editor lo sobrescribe al guardar: cambie el modelo, no este archivo.
"""
import asyncio
import math
import random

from asyncua import Server, ua


async def main():
    srv = Server()
    await srv.init()
    srv.set_endpoint('opc.tcp://0.0.0.0:4840/lab/')
    srv.set_server_name('Lab OPC UA Python')
    ns = await srv.register_namespace('http://lab.local')   # índice 2: el primero tras los de la norma
    objetos = srv.nodes.objects   # carpeta Objects (ns=0;i=85)

    # ── Tanque1 ─────────────────────────────────────────────────────
    tanque1 = await objetos.add_object(f"ns={ns};s=Tanque1", f"{ns}:Tanque1")
    tanque1_nivel = await tanque1.add_variable(f"ns={ns};s=Tanque1.Nivel", f"{ns}:Nivel", 0.0, ua.VariantType.Double)   # %
    tanque1_temperatura = await tanque1.add_variable(f"ns={ns};s=Tanque1.Temperatura", f"{ns}:Temperatura", 20.0, ua.VariantType.Double)   # °C
    tanque1_valvula = await tanque1.add_variable(f"ns={ns};s=Tanque1.Valvula", f"{ns}:Valvula", False, ua.VariantType.Boolean)
    await tanque1_valvula.set_writable()   # los clientes pueden escribirla

    # ── PLC1 ────────────────────────────────────────────────────────
    plc1 = await objetos.add_object(f"ns={ns};s=PLC1", f"{ns}:PLC1")
    plc1_temperatura = await plc1.add_variable(f"ns={ns};s=PLC1.Temperatura", f"{ns}:Temperatura", 23.5, ua.VariantType.Double)   # °C
    plc1_led = await plc1.add_variable(f"ns={ns};s=PLC1.LED", f"{ns}:LED", False, ua.VariantType.Boolean)
    await plc1_led.set_writable()   # los clientes pueden escribirla

    t = 0.0   # segundos desde el arranque
    async with srv:
        while True:
            # simulación: un valor nuevo cada 1000 ms
            await tanque1_nivel.write_value(50 + 30 * math.sin(2 * math.pi * t / 63))   # senoide
            await tanque1_temperatura.write_value(20 + 5 * math.cos(2 * math.pi * t / 94))   # cosenoide
            await plc1_temperatura.write_value(random.uniform(22, 26))   # ruido uniforme
            await asyncio.sleep(1)
            t += 1


asyncio.run(main())
