# labels

Drives a Niimbot B1 over USB serial and renders quid labels for it. Optional:
the rest of utulie works with this directory deleted entirely -- nothing in
`api/` imports it. `pip install -r labels/requirements.txt`, native only,
never containerized (the printer is a physical USB device).

`niimprint` speaks the old D11/B21v1 print task. The B1 accepts those commands,
acknowledges them, and half-honours them -- pages above ~190 rows are silently
cut. `b1task.py` implements the B1 task instead, mirroring niimbluelib's
`src/print_tasks/B1PrintTask.ts`:

- `PrintStart` is 7 bytes (total pages, page colour), not 1
- `SetPageSize` is 6 bytes (rows, cols, copies), not 4
- bitmap rows carry real black-pixel counts per printhead third, not zeros
- blank rows go as `PrintEmptyRow` 0x84 runs
- completion is a `PrintStatus` 0xa3 poll, not a fixed sleep

If B1 firmware moves, diff against that file.

## Media

Payload is `HTTPS://QRGU.ID/<26-char crockford quid>`, 42 alphanumeric chars, at
error-correction L. The scheme is mandatory -- a bare `QRGU.ID/...` decodes but
iOS offers a web search rather than a link. EC L keeps the payload inside QR
version 2; at EC M it spills to version 3 and costs a whole dot of module pitch.
The quid is never truncated: every shorter payload lands on the same module count.

| media | QR | module | measured read |
| --- | --- | --- | --- |
| `item-50x30` | 27.2 mm | 0.876 mm | 47 cm |
| `container-50x50-round` | 32.7 mm | 1.126 mm | 48 cm, on a curved surface |
| `container-40x70` | 38.8 mm | 1.251 mm | not yet measured |

Module pitch quantizes to whole printer dots, so these are steps, not tunable.

Big bins take `container-40x70`; rounds are for containers too small or too
curved for a rectangle.

Media dimensions are the *stock*, measured, not the printhead. The 70 mm stock
was first assumed to be 50 mm wide and calibrated against the full 376-dot
printhead; it is actually 41.3 mm (2 5/8 x 1 5/8 in), so that label printed
~5 dots wider than the label on each side. It scanned -- the overhang came out
of the quiet zone, not the data -- and read at 71 cm, but that geometry is not
reproducible and the entry has been corrected to fit the stock.

## Use

    python printlabel.py <quid> [media ...]

Defaults to every medium. The printer is on COM3 and must be awake -- USB
enumerates on bus power with the MCU asleep, so a dark printer answers nothing.

## Relay client (spike)

`relay_client.py` connects outbound to utulie's `/labels/ws` websocket and
drives the B1 on incoming jobs, so `POST /things/{id}/print` from the phone
reaches the printer without a manual `printlabel.py` step:

    python relay_client.py wss://utulie.wildharvesthomestead.com/labels/ws

One client at a time -- the physical printer only exists in one place.
Reconnects on drop; a job sent with nobody connected just fails. No queue,
no auth on the socket yet -- see kb/01a0c748-94d0-7ebf-8403-297632c22a83.md
for what a real version needs.
