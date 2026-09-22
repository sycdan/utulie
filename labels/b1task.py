"""B1 print task, per the NIIMBOT community protocol wiki.

niimprint implements the old D11/B21v1 task, which the B1 silently half-honours.
Differences: PrintStart is 7 bytes not 1, SetPageSize is 6 bytes not 4, bitmap
rows carry real black-pixel counts, and completion is a status poll not a sleep.
"""
import math, struct, time
from PIL import Image, ImageOps
from niimprint.packet import NiimbotPacket

PRINTHEAD_PIXELS = 384


def _counts(data: bytes):
    chunk = PRINTHEAD_PIXELS // 8 // 3          # 16
    total = sum(bin(b).count("1") for b in data)
    if len(data) <= chunk * 3:
        parts = [0, 0, 0]
        for i, b in enumerate(data):
            parts[min(i // chunk, 2)] += bin(b).count("1")
        return bytes(parts), total
    return bytes([0, total >> 8 & 0xFF, total & 0xFF]), total


class B1Printer:
    def __init__(self, transport):
        self.t = transport
        self.buf = bytearray()

    def _send(self, code, data):
        self.t.write(NiimbotPacket(code, data).to_bytes())

    def _xcv(self, code, data, respoffset=1, tries=6):
        want = code + respoffset
        self._send(code, data)
        for _ in range(tries):
            self.buf.extend(self.t.read(1024))
            while len(self.buf) > 4:
                n = self.buf[3] + 7
                if len(self.buf) < n:
                    break
                pkt = NiimbotPacket.from_bytes(self.buf[:n])
                del self.buf[:n]
                if pkt.type == want:
                    return pkt
        raise TimeoutError(f"no {want:#x} response to {code:#x}")

    # --- packets -----------------------------------------------------------
    def set_density(self, n):    return self._xcv(0x21, bytes([n]), 16)
    def set_label_type(self, n): return self._xcv(0x23, bytes([n]), 16)
    def print_start_7b(self, total_pages=1, page_color=0):
        return self._xcv(0x01, struct.pack(">HBBBBB", total_pages, 0, 0, 0, 0, page_color))
    def page_start(self):        return self._xcv(0x03, b"\x01")
    def set_page_size_6b(self, rows, cols, copies=1):
        return self._xcv(0x13, struct.pack(">HHH", rows, cols, copies))
    def page_end(self):          return self._xcv(0xE3, b"\x01")
    def print_end(self):         return bool(self._xcv(0xF3, b"\x01").data[0])

    def status(self):
        d = self._xcv(0xA3, b"\x01", respoffset=16).data
        page, pp, pf = struct.unpack(">HBB", d[:4])
        return page, pp, pf

    # --- image -------------------------------------------------------------
    def _rows(self, img):
        img = ImageOps.invert(img.convert("L")).convert("1")
        nbytes = math.ceil(img.width / 8)
        y = 0
        while y < img.height:
            bits = "".join("0" if img.getpixel((x, y)) == 0 else "1" for x in range(img.width))
            data = int(bits, 2).to_bytes(nbytes, "big")
            if not any(data):                       # blank -> coalesce into 0x84
                run = 1
                while y + run < img.height and run < 255:
                    nxt = "".join("0" if img.getpixel((x, y + run)) == 0 else "1"
                                  for x in range(img.width))
                    if int(nxt, 2):
                        break
                    run += 1
                yield NiimbotPacket(0x84, struct.pack(">HB", y, run))
                y += run
                continue
            parts, _ = _counts(data)
            yield NiimbotPacket(0x85, struct.pack(">H", y) + parts + b"\x01" + data)
            y += 1

    def print_image(self, img, density=5, label_type=1, timeout=20.0):
        self.set_density(density)
        self.set_label_type(label_type)
        self.print_start_7b(1, 0)
        self.page_start()
        self.set_page_size_6b(img.height, img.width, 1)
        for pkt in self._rows(img):
            self.t.write(pkt.to_bytes())
        self.page_end()
        t0 = time.time()
        while time.time() - t0 < timeout:
            page, pp, pf = self.status()
            if page >= 1 and pp >= 100 and pf >= 100:
                break
            time.sleep(0.2)
        else:
            raise TimeoutError(f"page never completed (last {page} {pp}% {pf}%)")
        while not self.print_end():
            time.sleep(0.1)
        return page, pp, pf
