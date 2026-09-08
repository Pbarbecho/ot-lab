import asyncio, math
from asyncua import Server

async def main():
    srv = Server()
    await srv.init()
    srv.set_endpoint("opc.tcp://0.0.0.0:4840/lab/")
    srv.set_server_name("Lab OPC UA Python")
    ns = await srv.register_namespace("http://lab.local")
    obj = await srv.nodes.objects.add_object(ns, "Tanque1")
    nivel = await obj.add_variable(ns, "Nivel", 0.0)
    temp  = await obj.add_variable(ns, "Temperatura", 20.0)
    valv  = await obj.add_variable(ns, "Valvula", False)
    await valv.set_writable()
    t = 0
    async with srv:
        while True:
            t += 1
            await nivel.write_value(50 + 30 * math.sin(t / 10))
            await temp.write_value(20 + 5 * math.cos(t / 15))
            await asyncio.sleep(1)

asyncio.run(main())
