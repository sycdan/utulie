"""Label renderer. Canvas is (feed, head) pre-rotation; head runs across the 384-dot bar."""
import qrcode
from qrcode.constants import ERROR_CORRECT_L
from PIL import Image, ImageDraw, ImageFont

DPMM = 203 / 25.4                       # 7.992 dots per mm
CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
BASE = "HTTPS://QRGU.ID/"   # scheme required: iOS treats a bare domain as a search term

MEDIA = {                               # feed x head, in dots
    "item-50x30":            dict(feed=240, head=376, shape="rect"),
    "container-50x50-round": dict(feed=390, head=376, shape="round"),
    "container-40x70":       dict(feed=533, head=330, shape="rect-tall"),
}

# How much caller-supplied `text` each medium's layout can actually hold.
# These mirror the line counts the quid-fragment default already uses for
# that shape -- that default was tuned to fit, so it doubles as the proven
# capacity. Exceeding it is refused rather than silently clipped off-canvas.
TEXT_LIMITS = {
    "item-50x30":            dict(max_lines=3, note="beside the QR, short (feed) axis"),
    "container-50x50-round": dict(max_lines=1, note="below the QR, chord-width limited"),
    "container-40x70":       dict(max_lines=2, note="beside the QR, across the short (head) axis"),
}


def b32(quid: str) -> str:
    n = int(quid.replace("-", ""), 16)
    s = "".join(CROCKFORD[(n >> (5 * i)) & 31] for i in range(26))[::-1]
    return s


def font(px):
    return ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", px)


def qr_block(payload, budget, border=4):
    """Largest QR that fits `budget` dots, returned with its module pitch."""
    q = qrcode.QRCode(error_correction=ERROR_CORRECT_L, border=border)
    q.add_data(payload)
    q.make(fit=True)
    mods = q.modules_count + 2 * border
    px = budget // mods
    img = q.make_image(fill_color="black", back_color="white").convert("1")
    side = px * mods
    return img.resize((side, side), Image.NEAREST), side, px, mods


def render(quid, media, text=""):
    """`text`, if given, replaces the printed quid fragment with caller-supplied
    lines (split on literal newlines -- no auto-wrap). The QR still always
    carries the quid; `text` only changes what a human reads off the label."""
    m = MEDIA[media]
    if text and text.count("\n") + 1 > TEXT_LIMITS[media]["max_lines"]:
        raise ValueError(f"{media} fits at most {TEXT_LIMITS[media]['max_lines']} "
                          f"line(s) of text ({TEXT_LIMITS[media]['note']})")
    feed, head = m["feed"], m["head"]
    payload = BASE + b32(quid)
    c = Image.new("1", (feed, head), 1)
    d = ImageDraw.Draw(c)
    g = quid.split("-")

    if m["shape"] == "rect-tall":
        # QR is bound by the printhead (376 dots), not the 70 mm feed.
        # Text lines run along head, so each is drawn flat and rotated in.
        qr, side, px, mods = qr_block(payload, head - 8, border=3)
        c.paste(qr, (6, (head - side) // 2))
        lines = text.split("\n") if text else [f"{g[0]}-{g[1]}-{g[2]}", f"{g[3]}-{g[4]}"]
        fs = 48
        while fs > 8 and max(d.textlength(t, font=font(fs)) for t in lines) > head - 20:
            fs -= 1
        f = font(fs)
        x = 6 + side + 14
        for t in reversed(lines):   # feed order flips under the print rotation
            w = int(d.textlength(t, font=f)) + 4
            strip = Image.new("1", (w, fs + 8), 1)
            ImageDraw.Draw(strip).text((2, 0), t, font=f, fill=0)
            strip = strip.rotate(-90, expand=True)
            c.paste(strip, (x, (head - w) // 2))
            x += strip.width + 6
    elif m["shape"] == "rect":
        # QR fills the short (feed) axis; full quid beside it, split on group boundaries
        qr, side, px, mods = qr_block(payload, feed - 4, border=3)
        c.paste(qr, (2, 2))
        x0 = side + 8
        lines = text.split("\n") if text else [f"{g[0]}-{g[1]}", f"{g[2]}-{g[3]}", g[4]]
        fs = 30
        while fs > 8:
            f = font(fs)
            if (max(d.textlength(t, font=f) for t in lines) <= feed - 8
                    and len(lines) * (fs + 3) <= head - x0 - 4):
                break
            fs -= 1
        f = font(fs)
        for i, t in enumerate(lines):
            d.text((4, x0 + i * (fs + 3)), t, font=f, fill=0)
    else:
        # r is the label circle (50 mm), not the printhead band
        r = 195                      # 2 mm of registration slack off the 200-dot radius
        qr, side, px, mods = qr_block(int(r * 2 ** 0.5), 0) if False else             qr_block(payload, int(r * 2 ** 0.5), border=2)
        cx, cy = feed // 2, head // 2
        top = cy - side // 2 - 18
        c.paste(qr, (cx - side // 2, top))
        lines = [text] if text else [g[4]]    # one line only: the chord below is narrow
        fs = 30
        y = top + side + 8
        while fs > 8:
            f = font(fs)
            half = (r ** 2 - max(0, y + fs - cy) ** 2) ** 0.5
            if d.textlength(lines[0], font=f) <= 2 * half - 12:
                break
            fs -= 1
        f = font(fs)
        w = d.textlength(lines[0], font=f)
        d.text(((feed - w) / 2, y), lines[0], font=f, fill=0)
    mm = side / DPMM
    return c, dict(media=media, side_px=side, side_mm=round(mm, 1),
                   module_px=px, module_mm=round(px / DPMM, 3), modules=mods,
                   font_px=fs, payload=payload)


if __name__ == "__main__":
    import sys, json
    quid = sys.argv[1]
    for name in MEDIA:
        img, info = render(quid, name)
        img.save(f"out-{name}.png")
        print(json.dumps(info))
