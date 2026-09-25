"""Fetch the University of Denver's CC BY 4.0 Visible Human Male final STLs.

Source: https://digitalcommons.du.edu/visiblehuman/2/
The archive stays in .cache/ so large research inputs are not bundled into the app.
"""

from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener
from zipfile import ZipFile

PAGE = "https://digitalcommons.du.edu/visiblehuman/2/"
URL = "https://digitalcommons.du.edu/cgi/viewcontent.cgi?filename=10&article=1000&context=visiblehuman&type=additional"
ARCHIVE = Path(__file__).resolve().parents[1] / ".cache" / "vhm-final-stl.zip"
EXPECTED_BYTES = 139_572_345
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": PAGE,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

ARCHIVE.parent.mkdir(exist_ok=True)
if not ARCHIVE.exists() or ARCHIVE.stat().st_size != EXPECTED_BYTES:
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    opener.open(Request(PAGE, headers=HEADERS), timeout=60).read(2048)
    with opener.open(Request(URL, headers=HEADERS), timeout=120) as response, ARCHIVE.open("wb") as output:
        while chunk := response.read(1 << 20):
            output.write(chunk)
    print(f"Downloaded {ARCHIVE.stat().st_size:,} bytes to {ARCHIVE}")
else:
    print(f"Using existing {ARCHIVE}")

with ZipFile(ARCHIVE) as source:
    relevant = [name for name in source.namelist() if name.lower().endswith('.stl') and
                any(key in name.lower() for key in ('femur', 'tibia', 'vastus', 'gluteus', 'gastrocnemius'))]
    print(f"Archive contains {len(source.namelist())} entries; selected examples:")
    for name in relevant[:25]:
        print(name)
