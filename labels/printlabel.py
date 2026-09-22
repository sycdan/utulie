import sys
from niimprint import SerialTransport
from b1task import B1Printer
from render import render, MEDIA

quid = sys.argv[1]
names = sys.argv[2:] or list(MEDIA)
p = B1Printer(SerialTransport("COM3"))
for n in names:
    img, info = render(quid, n)
    print(n, info["side_mm"], "mm QR,", info["module_mm"], "mm/module ->",
          p.print_image(img.rotate(90, expand=True), density=5))
