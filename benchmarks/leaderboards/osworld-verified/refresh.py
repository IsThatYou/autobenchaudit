#!/usr/bin/env python3
"""Refresh the OSWorld-Verified leaderboard snapshot.

OSWorld is a computer-use / desktop-agent benchmark (HKU / XLANG). The
"Verified" 2025-07-28 release re-verifies a 361-task subset; the upstream
leaderboard is the XLSX on os-world.github.io plus trajectory zips on
HuggingFace.

Two sources, two granularities:

  1. Aggregate (all 139 submissions):
     https://os-world.github.io/static/data/osworld_verified_results.xlsx
     One row per submission (model × max-steps × config). Overall accuracy +
     per-category success counts for 10 app categories. Per-category cells
     are strings like "16.96/46" — numerator can be fractional because
     evaluators return partial credit in [0,1].

  2. Per-task (for submissions with trajectories):
     https://huggingface.co/datasets/xlangai/ubuntu_osworld_verified_trajs
     84 trajectory ZIPs (1-25 GB each) + a reference `all_result.json`.
     Each zip contains `<model>/<category>/<task_uuid>/result.txt` — a
     scalar score in [0,1]. We stream only these entries via HTTP Range
     requests to avoid downloading hundreds of GB.

Outputs:
  leaderboard.json           # 139 aggregate rows (XLSX)
  rows/<slug>.json           # per-row: metadata + per-category stats + per-task (if fetched)
  rows_index.json            # sorted summary, one line per row
  per_task_matrix.json       # {task_uuid: {slug: {score, category}}} for fetched zips
  tasks.json                 # canonical 361-task universe (category + uuid)

Usage:
  python refresh.py                        # aggregate only (XLSX, ~1s)
  python refresh.py --with-per-task        # also fetch per-task via ranged zip reads
  python refresh.py --with-per-task --only maestro_100steps  # one zip only (match substr)
  python refresh.py --workers 8
"""

from __future__ import annotations

import argparse
import ast
import datetime as _dt
import io
import json
import re
import struct
import sys
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent

XLSX_URL = "https://os-world.github.io/static/data/osworld_verified_results.xlsx"

HF_DATASET = "xlangai/ubuntu_osworld_verified_trajs"
HF_TREE_URL = f"https://huggingface.co/api/datasets/{HF_DATASET}/tree/main"
HF_RAW = f"https://huggingface.co/datasets/{HF_DATASET}/resolve/main"

CATEGORY_COLS = [
    "chrome",
    "gimp",
    "libreoffice_calc",
    "libreoffice_impress",
    "libreoffice_writer",
    "multi_apps",
    "os",
    "thunderbird",
    "vlc",
    "vs_code",
]


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _open(url: str, headers: dict | None = None, retries: int = 6):
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "osworld-leaderboard-refresh/1.0", **(headers or {})}
            )
            return urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                delay = min(60.0, 5.0 * (2**attempt))
                time.sleep(delay)
            else:
                time.sleep(1.5 * (attempt + 1))
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url}: {last_err}")


def fetch_bytes(url: str) -> bytes:
    with _open(url) as r:
        return r.read()


def fetch_json(url: str) -> object:
    return json.loads(fetch_bytes(url).decode("utf-8"))


# --------------------------------------------------------------------------- #
# Minimal stdlib XLSX reader (values only)
# --------------------------------------------------------------------------- #
def _xlsx_col(ref: str) -> int:
    """A1 -> 0; AA1 -> 26."""
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for c in letters:
        n = n * 26 + (ord(c) - ord("A") + 1)
    return n - 1


def read_xlsx(xlsx_bytes: bytes) -> list[list]:
    """Return sheet1 as a list of rows; cells are str / int / float / None."""
    NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        shared: list[str] = []
        try:
            ss_xml = z.read("xl/sharedStrings.xml")
            for si in ET.fromstring(ss_xml).findall("s:si", NS):
                # Flatten any rich-text runs into a single string.
                parts = [t.text or "" for t in si.iter("{%s}t" % NS["s"])]
                shared.append("".join(parts))
        except KeyError:
            pass
        sheet_xml = z.read("xl/worksheets/sheet1.xml")

    rows: list[list] = []
    for row_el in ET.fromstring(sheet_xml).iter("{%s}row" % NS["s"]):
        row: list = []
        for c in row_el.findall("s:c", NS):
            ref = c.get("r")
            col = _xlsx_col(ref) if ref else len(row)
            while len(row) <= col:
                row.append(None)
            t = c.get("t")
            v = c.find("s:v", NS)
            is_ = c.find("s:is", NS)
            if t == "s" and v is not None:
                row[col] = shared[int(v.text)]
            elif t == "inlineStr" and is_ is not None:
                row[col] = "".join(x.text or "" for x in is_.iter("{%s}t" % NS["s"]))
            elif t == "b" and v is not None:
                row[col] = v.text == "1"
            elif v is not None:
                s = v.text
                try:
                    row[col] = int(s)
                except Exception:
                    try:
                        row[col] = float(s)
                    except Exception:
                        row[col] = s
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Parse aggregate leaderboard from XLSX
# --------------------------------------------------------------------------- #
def _parse_cat_cell(s) -> tuple[float | None, int | None]:
    """'16.96/46' -> (16.96, 46). Accepts numbers or None too."""
    if s is None or s == "":
        return None, None
    if isinstance(s, (int, float)):
        return float(s), None
    m = re.match(r"\s*([0-9]*\.?[0-9]+)\s*/\s*([0-9]+)\s*$", str(s))
    if not m:
        return None, None
    return float(m.group(1)), int(m.group(2))


def _slugify(*parts: str) -> str:
    joined = "_".join(str(p) for p in parts if p not in (None, ""))
    return re.sub(r"[^A-Za-z0-9._-]+", "_", joined).strip("_") or "unknown"


def parse_leaderboard(rows: list[list]) -> list[dict]:
    # Normalize header row — XLSX may carry trailing None cells.
    hdr = [str(h) if h is not None else "" for h in rows[0]]
    idx = {h: i for i, h in enumerate(hdr) if h}
    out: list[dict] = []
    slug_counts: dict[str, int] = {}
    for r in rows[1:]:
        if not any(c is not None and str(c).strip() for c in r):
            continue
        model = r[idx["Model"]]
        inst = r[idx["Institution"]]
        max_steps = r[idx["Max steps"]]
        date = r[idx["Date"]]
        if hasattr(date, "isoformat"):
            date = date.isoformat()[:10]
        elif isinstance(date, (int, float)):
            # Excel serial date → ISO. Anchor at 1899-12-30 to match Excel's
            # "1900 leap year" bug for serials after 1900-03-01.
            date = (_dt.date(1899, 12, 30) + _dt.timedelta(days=int(date))).isoformat()
        success_rate = r[idx["Success rate"]]
        if isinstance(success_rate, str):
            try:
                success_rate = float(success_rate.strip().rstrip("%"))
            except ValueError:
                success_rate = None
        success_total = r[idx["Success/Total"]]
        succ_num, succ_den = _parse_cat_cell(success_total)
        base_slug = _slugify(inst, model, f"{max_steps}steps" if max_steps else "")
        # Multi-rollout runs collide on (model × steps); disambiguate with _r2, _r3…
        n = slug_counts.get(base_slug, 0) + 1
        slug_counts[base_slug] = n
        slug = base_slug if n == 1 else f"{base_slug}_r{n}"
        cats = {}
        for cat in CATEGORY_COLS:
            n, d = _parse_cat_cell(r[idx[cat]])
            cats[cat] = {"success": n, "total": d}
        out.append(
            {
                "slug": slug,
                "model": model,
                "institution": inst,
                "paper_link": r[idx["PaperLink"]],
                "paper_authors": r[idx["PaperAuthors"]],
                "approach_type": r[idx["Approach type"]],
                "max_steps": max_steps,
                "a11y_tree_used": r[idx["Additional a11y tree used"]],
                "additional_coding_action": r[idx["Additional coding-based action"]],
                "multiple_rollout": r[idx["Multiple rollout"]],
                "date": date,
                "success_rate": success_rate,
                "success_total_raw": success_total,
                "success_count": succ_num,
                "total_tasks": succ_den,
                "per_category": cats,
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Task universe from all_result.json (Python-literal, not JSON)
# --------------------------------------------------------------------------- #
def fetch_task_universe() -> list[dict]:
    raw = fetch_bytes(f"{HF_RAW}/all_result.json").decode("utf-8")
    data = ast.literal_eval(raw)
    tasks: list[dict] = []
    for cat, uuid_scores in data.items():
        if not isinstance(uuid_scores, dict):
            continue
        for uuid, score in uuid_scores.items():
            tasks.append({"task_id": uuid, "category": cat})
    tasks.sort(key=lambda t: (t["category"], t["task_id"]))
    return tasks


# --------------------------------------------------------------------------- #
# Ranged HTTP file (file-like for zipfile.ZipFile)
# --------------------------------------------------------------------------- #
class RangedHTTPFile(io.RawIOBase):
    """File-like wrapper around an HTTP resource that supports Range requests.

    To keep zipfile's central-directory parse cheap, we prefetch the last
    TRAILER_SIZE bytes on construction and serve any read that falls inside
    that window from the local buffer. Large central directories fit
    comfortably (ours max out around 120 KiB for the 25 GB zips).
    """

    TRAILER_SIZE = 2 * 1024 * 1024  # 2 MiB is plenty for OSWorld zips

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._pos = 0
        # First probe: Range: bytes=0-0 → Content-Range tells us total size.
        with _open(self.url, headers={"Range": "bytes=0-0"}) as r:
            cr = r.headers.get("Content-Range", "")
            m = re.match(r"bytes\s+\d+-\d+/(\d+)", cr)
            if m:
                self.size = int(m.group(1))
            else:
                self.size = int(r.headers.get("Content-Length") or 0)
        # Prefetch the trailer.
        trailer_start = max(0, self.size - self.TRAILER_SIZE)
        with _open(self.url, headers={"Range": f"bytes={trailer_start}-{self.size - 1}"}) as r:
            self._trailer = r.read()
        self._trailer_start = trailer_start

    def readable(self) -> bool: return True
    def seekable(self) -> bool: return True

    def seek(self, pos: int, whence: int = 0) -> int:
        if whence == 0: self._pos = pos
        elif whence == 1: self._pos += pos
        elif whence == 2: self._pos = self.size + pos
        return self._pos

    def tell(self) -> int: return self._pos

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.size - self._pos
        if n == 0 or self._pos >= self.size:
            return b""
        end = min(self._pos + n - 1, self.size - 1)
        # Serve from the trailer buffer when possible.
        if self._pos >= self._trailer_start:
            lo = self._pos - self._trailer_start
            hi = end + 1 - self._trailer_start
            buf = self._trailer[lo:hi]
            self._pos += len(buf)
            return buf
        with _open(self.url, headers={"Range": f"bytes={self._pos}-{end}"}) as r:
            buf = r.read()
        self._pos += len(buf)
        return buf

    def readall(self) -> bytes: return self.read(-1)


# --------------------------------------------------------------------------- #
# Remote zip extract: pull only result.txt entries
# --------------------------------------------------------------------------- #
# ZIP layout:
#   [local_header + compressed_data] x N entries
#   [central directory] x N entries
#   [EOCD] (22 bytes + optional ZIP64 extra)
#
# We parse zipfile's central directory once (one ranged read of the trailer),
# then for each result.txt entry we issue exactly ONE range request covering
# the local header + compressed data, parse the header inline, and decompress.

def _http_range(url: str, start: int, end: int) -> bytes:
    with _open(url, headers={"Range": f"bytes={start}-{end}"}) as r:
        return r.read()


def _range_fetch_entry(url: str, info: zipfile.ZipInfo) -> bytes:
    """Fetch + decompress one zip entry in a single HTTP request.

    Local file header: 30 bytes fixed + filename + extra.
    The *true* extra length is only in the local header (central directory's
    extra may differ), so we upper-bound with filename length from central dir
    plus a generous 4 KiB for local extra.
    """
    hdr_upper = 30 + len(info.filename.encode()) + 4096
    blob = _http_range(
        url,
        info.header_offset,
        info.header_offset + hdr_upper + info.compress_size - 1,
    )
    if blob[:4] != b"PK\x03\x04":
        raise RuntimeError(f"bad local header signature for {info.filename}")
    fn_len, extra_len = struct.unpack("<HH", blob[26:30])
    data_off = 30 + fn_len + extra_len
    compressed = blob[data_off : data_off + info.compress_size]
    if info.compress_type == zipfile.ZIP_STORED:
        return compressed
    if info.compress_type == zipfile.ZIP_DEFLATED:
        import zlib
        return zlib.decompress(compressed, -15)
    raise RuntimeError(f"unsupported compress_type {info.compress_type}")


def extract_result_txts(zip_url: str, inner_workers: int = 6) -> dict[str, float]:
    """Return {task_uuid: score} for every result.txt in the remote zip.

    Strategy:
      1. zipfile parses the central directory (fetches the trailer only).
      2. We filter for result.txt entries.
      3. A thread pool issues one ranged HTTP fetch per entry.

    Roughly O(# result.txt) HTTP requests, well under the naive zipfile path.
    """
    f = RangedHTTPFile(zip_url)
    out: dict[str, float] = {}
    with zipfile.ZipFile(f) as zf:
        targets = [
            i for i in zf.infolist()
            if i.filename.endswith("/result.txt") or i.filename.endswith("result.txt")
        ]

        def _one(info: zipfile.ZipInfo):
            parts = info.filename.strip("/").split("/")
            if len(parts) < 2:
                return None
            uuid = parts[-2]
            try:
                body = _range_fetch_entry(zip_url, info).decode("utf-8", errors="replace").strip()
            except Exception:
                return None
            try:
                return uuid, float(body) if body else 0.0
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=inner_workers) as ex:
            for res in ex.map(_one, targets):
                if res is not None:
                    out[res[0]] = res[1]
    return out


def enumerate_zips() -> list[dict]:
    files = fetch_json(HF_TREE_URL)
    zips = []
    for f in files:
        if f.get("type") == "file" and f["path"].endswith(".zip"):
            zips.append(
                {
                    "filename": f["path"],
                    "size": f.get("size", 0),
                    "url": f"{HF_RAW}/{urllib.parse.quote(f['path'])}",
                    "slug": _slugify(f["path"].replace(".zip", "")),
                }
            )
    return zips


def fetch_all_per_task(
    zips: list[dict], workers: int, only: str | None
) -> dict[str, dict[str, float]]:
    """Return {zip_slug: {task_uuid: score}}."""
    cache_dir = HERE / "_per_task_cache"
    cache_dir.mkdir(exist_ok=True)
    if only:
        zips = [z for z in zips if only in z["filename"]]
    print(f"  [per-task] processing {len(zips)} zips")
    out: dict[str, dict[str, float]] = {}

    # Resume: load cached results.
    for z in zips:
        p = cache_dir / f"{z['slug']}.json"
        if p.exists():
            try:
                out[z["slug"]] = json.loads(p.read_text())
            except Exception:
                pass

    todo = [z for z in zips if z["slug"] not in out]
    if not todo:
        print(f"  [per-task] all {len(zips)} cached")
        return out

    def work(z):
        t0 = time.time()
        scores = extract_result_txts(z["url"])
        dt = time.time() - t0
        (cache_dir / f"{z['slug']}.json").write_text(json.dumps(scores))
        return z, scores, dt

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(work, z): z for z in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            z = futs[fut]
            try:
                _, scores, dt = fut.result()
            except Exception as e:
                print(f"  [per-task] FAIL {z['filename']}: {e}")
                continue
            out[z["slug"]] = scores
            print(
                f"  [per-task] [{i}/{len(todo)}] {z['filename']} -> "
                f"{len(scores)} task scores ({dt:.1f}s)"
            )
    return out


# --------------------------------------------------------------------------- #
# Match XLSX rows to trajectory zips (best-effort)
# --------------------------------------------------------------------------- #
def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def attach_per_task(
    entries: list[dict],
    tasks: list[dict],
    per_zip: dict[str, dict[str, float]],
    zips: list[dict],
) -> None:
    """Record a best-guess `trajectory_zip` slug on each leaderboard row.

    We do NOT embed the per-task array in row files — that lives in
    `per_task_matrix.json` keyed by zip slug, so unmatched zips are still
    queryable. Rows just carry a pointer.

    Matching rule: model substring match on zip filename, constrained to
    zips whose filename contains the row's step count. Falls back to
    step-less zips when nothing else fits.
    """
    zip_index = {z["slug"]: z for z in zips}
    matched = 0
    for e in entries:
        steps = e["max_steps"]
        model_n = _norm(e["model"])
        step_tag = f"{steps}step"
        best = None
        for slug, z in zip_index.items():
            fname = z["filename"].lower()
            if step_tag not in fname:
                continue
            if model_n and model_n in _norm(z["filename"]):
                if best is None or len(z["filename"]) < len(best["filename"]):
                    best = z
        if best is None:
            # Try step-less filenames (e.g. results_hippo_agent.zip)
            for slug, z in zip_index.items():
                fname = z["filename"].lower()
                if re.search(r"\d+step", fname):
                    continue
                if model_n and model_n in _norm(z["filename"]):
                    if best is None or len(z["filename"]) < len(best["filename"]):
                        best = z
        if best is None:
            continue
        if best["slug"] not in per_zip:
            continue
        e["trajectory_zip"] = best["filename"]
        e["trajectory_zip_slug"] = best["slug"]
        matched += 1
    print(f"  [attach] matched {matched} / {len(entries)} leaderboard rows to zips")


# --------------------------------------------------------------------------- #
# Write outputs
# --------------------------------------------------------------------------- #
def write_rows_files(entries: list[dict]) -> None:
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)
    for e in entries:
        (rows_dir / f"{e['slug']}.json").write_text(json.dumps(e, indent=2))


def build_rows_index(entries: list[dict]) -> list[dict]:
    out = []
    for e in entries:
        out.append(
            {
                "slug": e["slug"],
                "model": e["model"],
                "institution": e["institution"],
                "max_steps": e["max_steps"],
                "date": e["date"],
                "success_rate": e["success_rate"],
                "total_tasks": e["total_tasks"],
                "success_count": e["success_count"],
                "trajectory_zip": e.get("trajectory_zip"),
                "trajectory_zip_slug": e.get("trajectory_zip_slug"),
            }
        )
    out.sort(key=lambda r: -(r["success_rate"] or 0))
    return out


def build_leaderboard(entries: list[dict]) -> dict:
    light = [dict(e) for e in entries]
    light.sort(key=lambda r: -(r["success_rate"] or 0))
    return {
        "source_xlsx": XLSX_URL,
        "source_trajectories": f"https://huggingface.co/datasets/{HF_DATASET}",
        "benchmark": "osworld-verified",
        "num_entries": len(light),
        "scoring_note": (
            "pass@1 by default; 'Multiple rollout' flag marks opt-in multi-trial. "
            "Scores are floats in [0,1] (partial credit allowed)."
        ),
        "entries": light,
    }


def build_per_task_matrix(
    per_zip: dict[str, dict[str, float]],
    tasks: list[dict],
    zips: list[dict],
    entries: list[dict],
) -> dict:
    """Matrix keyed by task_uuid → {col_slug: {score, ...}}.

    Columns use the leaderboard row slug when a zip is mapped to one (or more)
    rows via `trajectory_zip_slug`, so `matrix[task][row.slug]` resolves
    directly. Zips with no row match fall back to the zip slug so their data
    stays addressable. Each cell carries `trajectory_zip_slug` so the zip
    identity is always recoverable.
    """
    task_cat = {t["task_id"]: t["category"] for t in tasks}

    rows_for_zip: dict[str, list[str]] = defaultdict(list)
    for e in entries:
        zslug = e.get("trajectory_zip_slug")
        if zslug:
            rows_for_zip[zslug].append(e["slug"])

    matrix: dict[str, dict[str, dict]] = defaultdict(dict)
    for zslug, scores in per_zip.items():
        col_keys = rows_for_zip.get(zslug) or [zslug]
        for uuid, score in scores.items():
            cell = {
                "score": score,
                "n_trials": 1,
                "n_success": 1 if score >= 1.0 else 0,
                "category": task_cat.get(uuid),
                "trajectory_zip_slug": zslug,
            }
            for col in col_keys:
                matrix[uuid][col] = cell
    return {
        "tasks": [
            {"task_id": t["task_id"], "category": t["category"]} for t in tasks
        ],
        "task_category": task_cat,
        "zips": sorted(
            [
                {
                    "slug": z["slug"],
                    "filename": z["filename"],
                    "num_tasks_scored": len(per_zip.get(z["slug"], {})),
                }
                for z in zips
                if z["slug"] in per_zip
            ],
            key=lambda z: z["filename"],
        ),
        "note": (
            "Cells are float scores in [0,1] (OSWorld evaluators return partial "
            "credit). n_success is binarised at score>=1.0. Columns are keyed "
            "by leaderboard row slug when a zip maps to one or more rows via "
            "`trajectory_zip_slug`; zips with no matching row keep their zip "
            "slug. Each cell carries `trajectory_zip_slug` for zip-level "
            "analysis."
        ),
        "matrix": dict(matrix),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--with-per-task", action="store_true",
                    help="Also fetch per-task results from trajectory zips on HF "
                         "(streams ~200KB/zip via HTTP Range; ~84 zips)")
    ap.add_argument("--only", default=None,
                    help="When --with-per-task: substring filter on zip filename")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    print("=" * 72)
    print("OSWorld-Verified leaderboard refresh")
    print(f"  output: {HERE}")
    print("=" * 72)

    print("[1/4] fetching XLSX leaderboard")
    xlsx = fetch_bytes(XLSX_URL)
    rows = read_xlsx(xlsx)
    entries = parse_leaderboard(rows)
    print(f"       {len(entries)} submission rows")

    print("[2/4] fetching canonical task universe (all_result.json)")
    tasks = fetch_task_universe()
    print(f"       {len(tasks)} tasks across {len({t['category'] for t in tasks})} categories")
    (HERE / "tasks.json").write_text(json.dumps(
        {"num_tasks": len(tasks), "tasks": tasks}, indent=2
    ))

    per_zip: dict[str, dict[str, float]] = {}
    zips: list[dict] = []
    if args.with_per_task:
        print("[3/4] fetching per-task scores via ranged zip reads")
        zips = enumerate_zips()
        per_zip = fetch_all_per_task(zips, args.workers, args.only)
        attach_per_task(entries, tasks, per_zip, zips)
    else:
        print("[3/4] --with-per-task not set; skipping per-task fetch")

    print("[4/4] writing outputs")
    write_rows_files(entries)
    (HERE / "leaderboard.json").write_text(
        json.dumps(build_leaderboard(entries), indent=2)
    )
    matched_zip_slugs = {
        e["trajectory_zip_slug"] for e in entries if e.get("trajectory_zip_slug")
    }
    unreferenced_zips = sorted(
        z["filename"] for z in (zips or [])
        if z["slug"] in (per_zip or {}) and z["slug"] not in matched_zip_slugs
    )
    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(entries),
                "num_matched_to_zip": sum(1 for e in entries if e.get("trajectory_zip")),
                "num_tasks": len(tasks),
                "num_zips_with_per_task": len(per_zip or {}),
                "unreferenced_zips": unreferenced_zips,
                "rows": build_rows_index(entries),
            },
            indent=2,
        )
    )
    if args.with_per_task:
        (HERE / "per_task_matrix.json").write_text(
            json.dumps(build_per_task_matrix(per_zip, tasks, zips, entries), indent=2)
        )

    print()
    print("done. outputs:")
    for f in ("leaderboard.json", "rows_index.json", "per_task_matrix.json", "tasks.json"):
        p = HERE / f
        if p.exists():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
    n_rows = len(list((HERE / "rows").glob("*.json")))
    print(f"  rows/  ({n_rows} files)")


if __name__ == "__main__":
    main()
