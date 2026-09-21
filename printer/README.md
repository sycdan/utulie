# printer

Drives a Niimbot B1 over USB serial and renders quid labels for it.

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
| `container-50x70` | 42.7 mm | 1.376 mm | 71 cm |

Module pitch quantizes to whole printer dots, so these are steps, not tunable.

Big bins take `container-50x70`; rounds are for containers too small or too
curved for a rectangle.

## Use

    python printlabel.py <quid> [media ...]

Defaults to every medium. The printer is on COM3 and must be awake -- USB
enumerates on bus power with the MCU asleep, so a dark printer answers nothing.
