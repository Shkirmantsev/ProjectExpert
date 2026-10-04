from __future__ import annotations
import asyncio, os

ENABLED=os.getenv("LITELLM_EXPOSE_ON_TAILSCALE","false").lower() in {"1","true","yes","on"}
HOST=os.environ["MAIN_TAILSCALE_IP"]
PORT=int(os.getenv("LITELLM_PORT","4000"))

async def pipe(reader,writer):
    try:
        while True:
            data=await reader.read(65536)
            if not data: break
            writer.write(data); await writer.drain()
    finally:
        writer.close()
        try: await writer.wait_closed()
        except Exception: pass

async def handle(r,w):
    try:
        ur,uw=await asyncio.open_connection("127.0.0.1",PORT)
    except Exception:
        w.close(); return
    await asyncio.gather(pipe(r,uw),pipe(ur,w))

async def main():
    if not ENABLED:
        print("LiteLLM Tailscale exposure disabled; set LITELLM_EXPOSE_ON_TAILSCALE=true to enable.")
        while True: await asyncio.sleep(3600)
    server=await asyncio.start_server(handle,HOST,PORT)
    print(f"LiteLLM Tailscale edge listening on {HOST}:{PORT}")
    async with server: await server.serve_forever()
asyncio.run(main())
