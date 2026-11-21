# -*- coding: utf-8 -*-
"""Mesin hitung, penyimpanan data (SQLite), impor & ekspor Excel untuk Aplikasi Setoran.

Seluruh rumus meniru file Excel asli (APLKASI_SETORAN.xlsx).
Modul ini tidak bergantung pada tampilan sehingga bisa diuji terpisah.
"""
import json
import math
import os
import re
import sqlite3
import sys
from datetime import date, datetime

CHANNELS = ["D/0", "BRI", "MANDIRI", "MY PERTAMINA", "PT LEO", "PT TRIPATRA",
            "PT PDSI", "PT TIP", "PT TGI", "PT LERINDO", "MUTIARA",
            "CV ABADI JAYA", "LAINNYA"]
# Urutan & nama di panel ringkasan (sama dengan kolom S di Excel)
SUMMARY_ORDER = [(0, "D/0"), (2, "EDC MANDIRI"), (1, "EDC BRI"), (3, "MY PERTAMINA"),
                 (4, "PT LEO"), (5, "PT TRIPATRA"), (6, "PT PDSI"), (7, "PT TIP"),
                 (8, "PT TGI"), (9, "PT LERINDO"), (10, "MUTIARA"), (11, "CV ABADI"),
                 (12, "LAINNYA")]
N_BLOCKS = 4          # P1..P4
N_ROWS = 10           # baris isian per blok
N_COLS = len(CHANNELS)

# Posisi sel input di template Excel
BLOCK_TOP = [6, 22, 38, 54]      # baris isian pertama tiap blok
BLOCK_LAPORAN = ["Q5", "Q21", "Q37", "Q53"]
BLOCK_CASH = ["Q7", "Q23", "Q39", "Q55"]
CELL_TOTAL, CELL_GLOBAL = "T5", "T23"

# ---------------------------------------------------------------- jenis BBM
# Aturan kategori (UBAH DI SINI jika kebutuhan berubah):
#   P1       : kolom channel PT -> pilihan "92" atau "TURBO"
#   P2,P3,P4 : semua kolom otomatis "DEXLITE"; kolom MUTIARA -> pilihan "DEXLITE" / "SOLAR"
PT_CHANNELS = {"PT LEO", "PT TRIPATRA", "PT PDSI", "PT TIP", "PT TGI", "PT LERINDO"}
NO_FUEL_CHANNELS = {"D/0", "BRI", "MANDIRI", "MY PERTAMINA", "LAINNYA"}   # tanpa kategori BBM
FUEL_DEFAULT_PT = {"PT TIP": "TURBO"}      # pilihan awal P1; channel PT lain awalnya "92"
FUEL_ORDER = ["", "92", "TURBO", "DEXLITE", "SOLAR"]
SUMMARY_NAME = dict(SUMMARY_ORDER)


def fuel_options(block, col):
    """Daftar jenis BBM yang berlaku untuk sel (block 0..3, col 0..12).
    [] = tanpa kategori, 1 item = otomatis, 2 item = harus dipilih."""
    name = CHANNELS[col]
    if name in NO_FUEL_CHANNELS:          # satu kesatuan: tanpa kategori, tidak dipisah
        return []
    if block == 0:
        return ["92", "TURBO"] if name in PT_CHANNELS else []
    return ["DEXLITE", "SOLAR"] if name == "MUTIARA" else ["DEXLITE"]


def default_fuel(block, col):
    opts = fuel_options(block, col)
    if not opts:
        return ""
    if block == 0:
        want = FUEL_DEFAULT_PT.get(CHANNELS[col])
        if want in opts:
            return want
    return opts[0]


def effective_fuel(block, col, stored):
    """Jenis BBM yang berlaku: pilihan tersimpan bila sah, kalau tidak pakai bawaan."""
    return stored if stored in fuel_options(block, col) else default_fuel(block, col)


def label_channel(col, fuel):
    """'PT TRIPATRA' + '92' -> 'PT TRIPATRA (92)'."""
    name = SUMMARY_NAME.get(col, CHANNELS[col])
    return "%s (%s)" % (name, fuel) if fuel else name


def _grid_get(grid, r, c, default=""):
    try:
        v = grid[r][c]
    except (IndexError, TypeError, KeyError):
        return default
    return default if v is None else v


# ---------------------------------------------------------------- utilitas
def excel_round_1000(x):
    """ROUND(x, -3) ala Excel (pembulatan setengah menjauhi nol)."""
    if x == 0:
        return 0
    s = 1 if x > 0 else -1
    return s * int(math.floor(abs(x) / 1000.0 + 0.5)) * 1000


def parse_money(text):
    """'1.234.567' / 'Rp 1,234,567' / '-500' -> int. Kosong -> 0."""
    if text is None:
        return 0
    if isinstance(text, (int, float)):
        return int(round(text))
    t = str(text).strip()
    if not t:
        return 0
    neg = t.startswith("-") or t.startswith("(")
    digits = re.sub(r"\D", "", t)
    if not digits:
        return 0
    v = int(digits)
    return -v if neg else v


def fmt_money(v, rp=False):
    """12345678 -> '12.345.678' (format Indonesia)."""
    if v is None:
        v = 0
    s = "{:,}".format(int(v)).replace(",", ".")
    return ("Rp " + s) if rp else s


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name):
    base = getattr(sys, "_MEIPASS", app_dir())
    return os.path.join(base, name)


DATA_DIR_OVERRIDE = None     # diisi oleh versi Android (App.user_data_dir)


def data_dir():
    if DATA_DIR_OVERRIDE:
        os.makedirs(DATA_DIR_OVERRIDE, exist_ok=True)
        return DATA_DIR_OVERRIDE
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "AplikasiSetoran")
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------- data kosong
def empty_record():
    return {
        "total": 0,           # T5  (TOTAL)
        "total_global": 0,    # T23 (TOTAL GLOBAL)
        "blocks": [
            {"laporan": 0, "cash": 0,
             "rows": [[0] * N_COLS for _ in range(N_ROWS)],
             "fuel": [[""] * N_COLS for _ in range(N_ROWS)],   # pilihan BBM per sel
             "note": [[""] * N_COLS for _ in range(N_ROWS)]}   # keterangan teks per sel
            for _ in range(N_BLOCKS)
        ],
    }


# ---------------------------------------------------------------- perhitungan
LAINNYA_COL = CHANNELS.index("LAINNYA")


def _collect_detail(bi, b, detail):
    """Kumpulkan per (channel, jenis BBM): jumlah + daftar isian berketerangan.
    Isian berketerangan tidak digabung: tiap isian jadi baris sendiri tepat di bawah
    baris channelnya, sedangkan baris channel hanya memuat isian yang tanpa keterangan."""
    for r in range(N_ROWS):
        for c in range(N_COLS):
            v = b["rows"][r][c]
            if not v:
                continue
            f = effective_fuel(bi, c, _grid_get(b.get("fuel"), r, c))
            n = str(_grid_get(b.get("note"), r, c)).strip() if c == LAINNYA_COL else ""
            g = detail.setdefault((c, f), {"amount": 0, "items": []})
            if n:                      # berketerangan -> baris sendiri, tidak masuk jumlah channel
                g["items"].append({"note": n, "amount": v})
                continue
            g["amount"] += v


def _ordered_detail(detail):
    """[(kolom, jenis BBM, jumlah, [isian berketerangan])] urut sesuai ringkasan."""
    pos = {ci: i for i, (ci, _) in enumerate(SUMMARY_ORDER)}
    keys = sorted(detail, key=lambda k: (
        pos.get(k[0], 99), FUEL_ORDER.index(k[1]) if k[1] in FUEL_ORDER else 99))
    return [(c, f, detail[(c, f)]["amount"], detail[(c, f)]["items"])
            for c, f in keys if detail[(c, f)]["amount"] or detail[(c, f)]["items"]]


def calculate(rec):
    """Hitung semua angka turunan persis seperti rumus Excel."""
    out = {"blocks": []}
    ch_sum = [0] * N_COLS
    minus_total = 0
    detail = {}
    for bi, b in enumerate(rec["blocks"]):
        col_tot = [sum(r[c] for r in b["rows"]) for c in range(N_COLS)]
        app_total = sum(col_tot)                          # D18 / D34 / D50 / D66
        total_setoran = app_total + b["cash"]             # Q9
        minus = excel_round_1000(b["laporan"] - total_setoran)   # Q8
        setoran_akhir = total_setoran + minus             # Q11
        out["blocks"].append({
            "col_totals": col_tot, "app_total": app_total,
            "total_setoran": total_setoran, "minus": minus,
            "setoran_akhir": setoran_akhir,
        })
        for c in range(N_COLS):
            ch_sum[c] += col_tot[c]
        _collect_detail(bi, b, detail)
        minus_total += minus
    t20 = excel_round_1000(rec["total"] - sum(ch_sum))    # T20
    tera = rec["total_global"] + minus_total - t20        # T24
    out.update({
        "channel_sums": ch_sum,
        "channel_detail": _ordered_detail(detail),   # [(kolom, jenis BBM, jumlah, isian berketerangan)]
        "cash_total": t20,
        "minus_total": minus_total,
        "tera": tera,
        "global_akhir": rec["total_global"] - tera,       # T26
        "total_akhir": rec["total_global"] - tera + minus_total,   # T27
    })
    return out


# ---------------------------------------------------------------- KALKULATOR PAS
# Tujuan: membuat MINUS = 0 (setoran pas dengan LAPORAN HARIAN) di tiap blok.
#   minus = ROUND(laporan - (total aplikasi + cash), -3)  ->  pas bila selisih < 500
PAS_TOLERANSI = 500
DENOMS = [100000, 50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100]


def block_status(rec, bi):
    """Ringkasan pas/tidak pas satu blok.
    selisih  = laporan - total setoran   (+ kurang setoran, - kelebihan setoran)
    cash_pas = cash yang dibutuhkan agar selisih = 0 (negatif = aplikasi sudah melebihi laporan)"""
    b = rec["blocks"][bi]
    app_total = sum(sum(r) for r in b["rows"])
    total = app_total + b["cash"]
    selisih = b["laporan"] - total
    return {"laporan": b["laporan"], "app_total": app_total, "cash": b["cash"],
            "total_setoran": total, "selisih": selisih,
            "pas": abs(selisih) < PAS_TOLERANSI,
            "cash_pas": b["laporan"] - app_total}


def pecahan_total(counts):
    """{100000: 3, 50000: 2} -> 400000"""
    return sum(int(d) * int(n) for d, n in counts.items() if n)


def pecahan_breakdown(amount):
    """Rincian pecahan (serakah) untuk nominal tertentu: [(pecahan, jumlah lembar)]."""
    amount = max(0, int(amount))
    out = []
    for d in DENOMS:
        n, amount = divmod(amount, d)
        if n:
            out.append((d, n))
    if amount:
        out.append((1, amount))      # sisa di bawah 100 (receh)
    return out


def cari_penyebab(rec, bi, max_size=3, limit=8):
    """Cari isian yang kemungkinan jadi penyebab KELEBIHAN setoran (total > laporan):
    kombinasi 1..max_size isian (termasuk cash) yang jumlahnya sama dengan kelebihan,
    mis. isian dobel / terinput di blok yang salah. Mengembalikan daftar kombinasi,
    tiap kombinasi = [(keterangan, nominal)]. Kosong bila setoran sudah pas / kurang."""
    from itertools import combinations
    st = block_status(rec, bi)
    gap = -st["selisih"]
    if gap < PAS_TOLERANSI:
        return []
    b = rec["blocks"][bi]
    items = []
    for r in range(N_ROWS):
        for c in range(N_COLS):
            v = b["rows"][r][c]
            if v > 0:
                f = effective_fuel(bi, c, _grid_get(b.get("fuel"), r, c))
                items.append(("%s baris %d" % (label_channel(c, f), r + 1), v))
    if b["cash"] > 0:
        items.append(("SETORAN CASH", b["cash"]))
    for tol in (0, PAS_TOLERANSI - 1):
        hasil = []
        for k in range(1, max_size + 1):
            for combo in combinations(items, k):
                if abs(sum(v for _, v in combo) - gap) <= tol:
                    hasil.append(list(combo))
                    if len(hasil) >= limit:
                        return hasil
        if hasil:
            return hasil
    return []


def _eval_node(node):
    import ast
    from fractions import Fraction
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Fraction(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _eval_node(node.operand)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        a, b = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if b == 0:
            raise ValueError("Dibagi nol")
        return a / b
    raise ValueError("Rumus tidak valid")


def calc_eval(expr):
    """Hitung rumus ala kalkulator. Format Indonesia: titik = pemisah ribuan, koma = desimal.
    Mendukung + - x * / : ( ) dan persen ('10%' = 0,1). Hasil berupa Fraction (tepat)."""
    import ast
    t = str(expr).strip()
    if not t:
        raise ValueError("Kosong")
    t = t.replace("\u00d7", "*").replace("x", "*").replace("X", "*")
    t = t.replace("\u00f7", "/").replace(":", "/")
    t = t.replace(".", "").replace(",", ".").replace(" ", "")
    t = re.sub(r"(\d+(?:\.\d+)?)%", r"(\1/100)", t)
    t = re.sub(r"(\d)\(", r"\1*(", t)           # 5(3+2) -> 5*(3+2)
    t = re.sub(r"\)(\d|\()", r")*\1", t)         # (1+2)3 -> (1+2)*3
    try:
        tree = ast.parse(t, mode="eval")
    except SyntaxError:
        raise ValueError("Rumus tidak valid")
    return _eval_node(tree)


def fmt_calc(v):
    """Fraction -> teks Indonesia (bulat: 1.234.567 ; pecahan: 1.234,56)."""
    from fractions import Fraction
    v = Fraction(v)
    if v.denominator == 1:
        return fmt_money(int(v))
    x = round(float(v), 2)
    neg = x < 0
    ip, fp = ("%.2f" % abs(x)).split(".")
    s = fmt_money(int(ip)) + "," + fp.rstrip("0")
    s = s.rstrip(",")
    return ("-" + s) if neg else s


# ---------------------------------------------------------------- database
class Store:
    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), "setoran.db")
        self.con = sqlite3.connect(self.path)
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS setoran ("
            " tanggal TEXT NOT NULL, shift INTEGER NOT NULL, data TEXT NOT NULL,"
            " updated TEXT NOT NULL, PRIMARY KEY (tanggal, shift))")
        self.con.commit()

    def save(self, tgl, shift, rec):
        self.con.execute(
            "INSERT OR REPLACE INTO setoran VALUES (?,?,?,?)",
            (tgl.isoformat(), int(shift), json.dumps(rec),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self.con.commit()

    def load(self, tgl, shift):
        r = self.con.execute("SELECT data FROM setoran WHERE tanggal=? AND shift=?",
                             (tgl.isoformat(), int(shift))).fetchone()
        return _normalize(json.loads(r[0])) if r else None

    def delete(self, tgl, shift):
        self.con.execute("DELETE FROM setoran WHERE tanggal=? AND shift=?",
                         (tgl.isoformat(), int(shift)))
        self.con.commit()

    def exists(self, tgl, shift):
        return self.con.execute("SELECT 1 FROM setoran WHERE tanggal=? AND shift=?",
                                (tgl.isoformat(), int(shift))).fetchone() is not None

    def list_all(self):
        """[(date, shift, updated, data)] terbaru dulu."""
        rows = self.con.execute(
            "SELECT tanggal, shift, updated, data FROM setoran "
            "ORDER BY tanggal DESC, shift DESC").fetchall()
        return [(date.fromisoformat(t), s, u, _normalize(json.loads(d)))
                for t, s, u, d in rows]

    def close(self):
        self.con.close()


def _normalize(rec):
    """Pastikan struktur lengkap (jaga-jaga data lama/rusak)."""
    base = empty_record()
    base["total"] = int(rec.get("total", 0))
    base["total_global"] = int(rec.get("total_global", 0))
    for i, b in enumerate(rec.get("blocks", [])[:N_BLOCKS]):
        base["blocks"][i]["laporan"] = int(b.get("laporan", 0))
        base["blocks"][i]["cash"] = int(b.get("cash", 0))
        for r, row in enumerate(b.get("rows", [])[:N_ROWS]):
            for c, v in enumerate(row[:N_COLS]):
                base["blocks"][i]["rows"][r][c] = int(v or 0)
        for r in range(N_ROWS):          # data lama tanpa BBM/keterangan -> kosong
            for c in range(N_COLS):
                base["blocks"][i]["fuel"][r][c] = str(_grid_get(b.get("fuel"), r, c))
                if c == LAINNYA_COL:     # keterangan hanya untuk kolom LAINNYA
                    base["blocks"][i]["note"][r][c] = str(_grid_get(b.get("note"), r, c))
    return base


# ---------------------------------------------------------------- Excel
def _num(v):
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(round(v))
    return parse_money(v)


def read_workbook(path):
    """Baca file Excel format lama -> [(date|None, shift, rec, nama_sheet)]."""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True)
    hasil = []
    for ws in wb.worksheets:
        if str(ws["G3"].value or "").strip().upper() != "SETORAN APLIKASI":
            continue            # bukan sheet setoran
        tgl = ws["B2"].value
        if isinstance(tgl, datetime):
            tgl = tgl.date()
        elif not isinstance(tgl, date):
            tgl = None
        m = re.search(r"(\d+)", str(ws["C2"].value or ""))
        shift = int(m.group(1)) if m else 1
        rec = empty_record()
        rec["total"] = _num(ws[CELL_TOTAL].value)
        rec["total_global"] = _num(ws[CELL_GLOBAL].value)
        for i in range(N_BLOCKS):
            b = rec["blocks"][i]
            b["laporan"] = _num(ws[BLOCK_LAPORAN[i]].value)
            b["cash"] = _num(ws[BLOCK_CASH[i]].value)
            for r in range(N_ROWS):
                for c in range(N_COLS):
                    b["rows"][r][c] = _num(ws.cell(BLOCK_TOP[i] + r, 2 + c).value)
        hasil.append((tgl, shift, rec, ws.title))
    return hasil


def _cell_comment(bi, c, fuel, note):
    parts = []
    if len(fuel_options(bi, c)) > 1:
        parts.append("BBM: " + effective_fuel(bi, c, fuel))
    if note:
        parts.append(note)
    return "\n".join(parts)


def export_workbook(path, items):
    """Tulis ke Excel memakai template asli (rumus & tampilan tetap).
    items = [(date, shift, rec)] -> satu sheet per tanggal+shift."""
    from openpyxl import load_workbook
    from openpyxl.comments import Comment
    wb = load_workbook(resource_path("template_setoran.xlsx"))
    tpl = wb.worksheets[0]
    used = set()
    for tgl, shift, rec in items:
        ws = wb.copy_worksheet(tpl)
        nama = "%s S%d" % (tgl.strftime("%d-%m-%Y"), shift)
        base, n = nama, 2
        while nama in used:
            nama = "%s (%d)" % (base, n)
            n += 1
        used.add(nama)
        ws.title = nama[:31]
        ws["B2"] = datetime(tgl.year, tgl.month, tgl.day)
        ws["C2"] = "SHIFT %d" % shift
        ws[CELL_TOTAL] = rec["total"]
        ws[CELL_GLOBAL] = rec["total_global"]
        for i in range(N_BLOCKS):
            b = rec["blocks"][i]
            ws[BLOCK_LAPORAN[i]] = b["laporan"]
            ws[BLOCK_CASH[i]] = b["cash"]
            for r in range(N_ROWS):
                for c in range(N_COLS):
                    v = b["rows"][r][c]
                    cell = ws.cell(BLOCK_TOP[i] + r, 2 + c)
                    cell.value = v if v else None
                    if v:      # jenis BBM (bila ada pilihan) & keterangan -> komentar sel
                        txt = _cell_comment(i, c, _grid_get(b.get("fuel"), r, c),
                                            str(_grid_get(b.get("note"), r, c)).strip()
                                            if c == LAINNYA_COL else "")
                        if txt:
                            try:
                                cell.comment = Comment(txt, "Aplikasi Setoran")
                            except Exception:
                                pass
    wb.remove(tpl)
    wb.save(path)
