"""Summarize the published phase-level overhead-press EMG workbook.

Research only: these seated exercise data do not validate the app's standing
press trajectory, inverse dynamics, or single-muscle force estimates.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path
from statistics import mean, stdev
from urllib.request import urlopen
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://zenodo.org/api/records/5744051/files/Raw%20data_new.xlsx/content"
PAPER_URL = "https://doi.org/10.3389/fphys.2022.825880"
EXPECTED_MD5 = "e8b6c718179c993b0817208341e84130"
WORKBOOK = ROOT / ".cache/research/overhead_press_emg_zenodo_5744051.xlsx"
OUTPUT = ROOT / "docs/data/overhead_press_emg_phase_summary.json"
NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
SHEETS = {
    "GranPettoraleClaveare%": "pectoralis_major_clavicular",
    "TricipiteCapoLaterale%": "triceps_brachii_lateral",
    "TrapezioSuperiore%": "upper_trapezius",
    "DeltoideAnteriore%": "anterior_deltoid",
    "DeltoideMedio%": "middle_deltoid",
    "DeltoidePosteriore%": "posterior_deltoid",
}
CONDITIONS = (
    "front_barbell_ascending", "front_barbell_descending",
    "back_barbell_ascending", "back_barbell_descending",
    "front_machine_ascending", "front_machine_descending",
    "back_machine_ascending", "back_machine_descending",
)


def get_workbook() -> bytes:
    if WORKBOOK.exists():
        data = WORKBOOK.read_bytes()
    else:
        with urlopen(SOURCE_URL, timeout=30) as response:
            data = response.read()
        WORKBOOK.parent.mkdir(parents=True, exist_ok=True)
        WORKBOOK.write_bytes(data)
    digest = hashlib.md5(data).hexdigest()
    if digest != EXPECTED_MD5:
        raise ValueError(f"Source workbook checksum changed: {digest}")
    return data


def read_source(data: bytes) -> dict[str, dict[str, list[float]]]:
    result = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        names = [sheet.attrib["name"] for sheet in workbook.findall(".//x:sheets/x:sheet", NS)]
        if set(names) != set(SHEETS):
            raise ValueError(f"Unexpected workbook sheets: {names}")
        for index, original_name in enumerate(names, start=1):
            sheet = ET.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml"))
            cells = {}
            for cell in sheet.findall(".//x:sheetData/x:row/x:c", NS):
                value = cell.find("x:v", NS)
                if value is not None and cell.attrib.get("t") != "s":
                    cells[cell.attrib["r"]] = float(value.text)
            columns = {}
            for column, condition in zip("ABCDEFGH", CONDITIONS):
                # Rows 2–9 are the eight participant averages; row 12 is the
                # published group mean, used below for a source integrity check.
                values = [cells[f"{column}{row}"] for row in range(2, 10)]
                if not all(math.isfinite(v) for v in values):
                    raise ValueError(f"Non-finite source data: {original_name} {column}")
                if abs(mean(values) - cells[f"{column}12"]) > 1e-8:
                    raise ValueError(f"Group mean mismatch: {original_name} {column}")
                columns[condition] = values
            result[SHEETS[original_name]] = columns
    return result


def describe(values: list[float]) -> dict:
    return {"mean_percent": round(mean(values), 3), "sd_percent": round(stdev(values), 3)}


def paired_difference(a: list[float], b: list[float]) -> dict:
    delta = [x - y for x, y in zip(a, b)]
    return {
        "mean_difference_percentage_points": round(mean(delta), 3),
        "sd_difference_percentage_points": round(stdev(delta), 3),
        "participants_positive": sum(v > 0 for v in delta),
        "participants_negative": sum(v < 0 for v in delta),
    }


def main() -> None:
    source = read_source(get_workbook())
    muscles = {}
    for muscle, columns in source.items():
        muscles[muscle] = {
            "conditions": {name: describe(values) for name, values in columns.items()},
            "comparisons": {
                "front_minus_back_barbell_ascending": paired_difference(
                    columns["front_barbell_ascending"], columns["back_barbell_ascending"]
                ),
                "front_minus_back_barbell_descending": paired_difference(
                    columns["front_barbell_descending"], columns["back_barbell_descending"]
                ),
                "front_barbell_ascending_minus_descending": paired_difference(
                    columns["front_barbell_ascending"], columns["front_barbell_descending"]
                ),
            },
        }
    summary = {
        "source": {"workbook_url": SOURCE_URL, "paper_url": PAPER_URL,
                   "zenodo_record": "https://zenodo.org/records/5744051",
                   "md5": EXPECTED_MD5, "license": "CC BY 4.0"},
        "measurement": "phase-averaged, normalized surface EMG RMS; percent of maximal voluntary excitation",
        "protocol": "8 male competitive bodybuilders; seated press with 80-degree backrest; 80% exercise-specific 1RM; 6 repetitions; 2-second ascending and descending phases",
        "participant_count": 8,
        "limitations": ["No frame-level kinematics", "No measured hand forces or support reactions",
                        "Seated protocol differs from app standing press", "EMG is not muscle force"],
        "muscles": muscles,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}: {len(muscles)} muscles, 8 participants each")
    for muscle, report in muscles.items():
        print(muscle, report["comparisons"]["front_minus_back_barbell_ascending"])


if __name__ == "__main__":
    main()
