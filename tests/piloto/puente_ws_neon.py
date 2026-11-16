"""Puente de PRUEBA: TCP local -> WebSocket seguro de Neon (wss://<endpoint>/v2), que transporta el protocolo de
PostgreSQL por el puerto 443. Solo existe porque este contenedor no puede abrir el puerto 5432; Render conecta directo.
Uso: python puente_ws.py <host_endpoint> <puerto_local>"""
import asyncio, ssl, sys
import websockets

HOST, PORT = sys.argv[1], int(sys.argv[2])
CTX = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")


async def tubo(reader, writer):
    try:
        async with websockets.connect(f"wss://{HOST}/v2?address={HOST}:5432", ssl=CTX, max_size=None,
                                      compression=None, open_timeout=30) as ws:
            async def subir():
                while data := await reader.read(65536):
                    await ws.send(data)
                await ws.close()

            async def bajar():
                async for msg in ws:
                    writer.write(msg if isinstance(msg, bytes) else msg.encode()); await writer.drain()

            await asyncio.gather(subir(), bajar())
    except Exception as e:
        print("puente:", type(e).__name__, str(e)[:120], flush=True)
    finally:
        writer.close()


async def main():
    srv = await asyncio.start_server(tubo, "127.0.0.1", PORT)
    print("escuchando", PORT, flush=True)
    async with srv:
        await srv.serve_forever()

asyncio.run(main())
