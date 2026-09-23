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
| `50x30` | 27.2 mm | 0.876 mm | 47 cm |
| `50x50-round` | 32.7 mm | 1.126 mm | 48 cm, on a curved surface |
| `40x70` | 38.8 mm | 1.251 mm | not yet measured |

Module pitch quantizes to whole printer dots, so these are steps, not tunable.

A key names the stock and nothing else. What a size is *for* is a guess about
the thing being labelled, not a property of the label, so it lives in `suits`
-- a hint the UI uses to pre-select, never a restriction. Big bins take
`40x70`; rounds are for containers too small or too curved for a rectangle.

## Text budget

Caption text is word-wrapped across `max_lines` and the font is the largest
size whose wrapping fits. Explicit newlines stay hard breaks, so a caller that
asked for three lines gets three; exceeding `max_lines` that way raises.

Width is never enforced -- no layout refuses on width, each shrinks the font
to fit, down to 8 px (~1 mm), which prints and cannot be read. So `max_chars`
is advisory: the whole-caption length that still clears a 2 mm cap height once
wrapped. Past it you still get a label, just a worse one than the quid default
you would have got for free.

Text keeps `MARGIN` dots of quiet edge. Drawn any closer it reads as having
run off the label even when the dots are on it, because the stock feeds with
more registration slack than that.

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

On connect it announces its hostname and `catalog()`. The server keeps no
media list of its own, so adding a stock size means editing `MEDIA` and
`TEXT_LIMITS` here and restarting the relay -- nothing on the server, no
redeploy. The server acks; a server too old to understand the frame stays
silent, which is why the ack exists.

One client at a time -- the physical printer only exists in one place.
Reconnects on drop; a job sent with nobody connected just fails. No queue,
no auth on the socket yet -- see kb/01a0c748-94d0-7ebf-8403-297632c22a83.md
for what a real version needs.

### Running it without thinking about it

dan-pc registers it as a scheduled task at logon, so nothing has to be
started before printing:

    $py = "$env:LOCALAPPDATA\Programs\Python\Python314\pythonw.exe"
    $me = "$env:USERDOMAIN\$env:USERNAME"
    Register-ScheduledTask -TaskName utulie-print-relay -Force `
      -Action (New-ScheduledTaskAction -Execute $py `
         -Argument "relay_client.py wss://utulie.wildharvesthomestead.com/labels/ws" `
         -WorkingDirectory "C:\Users\Dan\mi\workspace\utulie\labels") `
      -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $me) `
      -Principal (New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive) `
      -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable `
         -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
         -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew)

`pythonw`, so there is no window; `ExecutionTimeLimit 0`, because the default
kills a task after three days and this is meant to outlive that.

No window also means no output, which is what `relay.cmd` is for: run it in a
terminal to watch the relay connect and report jobs, or to find out why it is
not running. Stop the task first -- one client at a time.

The server side says whether it has a client: `/health` reports `printer`
alongside `ok`, and a thing's page says "Print client offline" next to the
print button rather than waiting for a 503. `ok` deliberately stays true with
no relay -- it is the container healthcheck, and an unplugged printer is not
the service being down.
