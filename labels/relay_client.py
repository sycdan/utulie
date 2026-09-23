"""Native client for dan-pc: connects outbound to utulie's websocket relay
and drives the real B1 on incoming print jobs. Never containerized -- the
printer is a physical USB device on this machine, not reachable from htpc.

    python relay_client.py wss://utulie.wildharvesthomestead.com/labels/ws
"""
import asyncio
import json
import socket
import sys

import websockets
from niimprint import SerialTransport

from b1task import B1Printer
from render import catalog, render

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
                # Say what this machine is and what stock it can render. The
                # server has no media list of its own -- whatever is reported
                # here is what the UI offers, so adding a stock size means
                # editing render.py and restarting, nothing else.
                await ws.send(json.dumps({
                    "hello": "relay",
                    "host": socket.gethostname(),
                    "media": catalog(),
                }))
                print(f"connected to {URL} as {socket.gethostname()}")
                async for raw in ws:
                    msg = json.loads(raw)
                    if "hello" in msg:
                        # A server too old to know the frame stays silent, so
                        # the ack is the only proof the stock list landed.
                        print(f"registered {len(catalog())} media")
                        continue
                    await handle(ws, msg)
        except Exception as e:
            print(f"relay error: {e}; reconnecting in 5s")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
