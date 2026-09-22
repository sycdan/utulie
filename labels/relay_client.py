"""Native client for dan-pc: connects outbound to utulie's websocket relay
and drives the real B1 on incoming print jobs. Never containerized -- the
printer is a physical USB device on this machine, not reachable from htpc.

    python relay_client.py wss://utulie.wildharvesthomestead.com/labels/ws
"""
import asyncio
import json
import sys

import websockets
from niimprint import SerialTransport

from b1task import B1Printer
from render import render

URL = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8080/labels/ws"


async def handle(ws, msg):
    job_id = msg["job_id"]
    try:
        img, info = render(msg["id"], msg["media"], text=msg.get("text", ""))
        B1Printer(SerialTransport("COM3")).print_image(img.rotate(90, expand=True), density=5)
        print(f"printed {msg['id']} ({msg['media']})")
        await ws.send(json.dumps({"job_id": job_id, "ok": True}))
    except Exception as e:
        print(f"job {job_id} failed: {e}")
        await ws.send(json.dumps({"job_id": job_id, "ok": False, "error": str(e)}))


async def main():
    while True:
        try:
            async with websockets.connect(URL) as ws:
                print(f"connected to {URL}")
                async for raw in ws:
                    await handle(ws, json.loads(raw))
        except Exception as e:
            print(f"relay error: {e}; reconnecting in 5s")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
