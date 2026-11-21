# -*- coding: utf-8 -*-
"""Aplikasi Setoran - versi Android (Kivy) + Kalkulator Pas.

Semua perhitungan memakai logic.py (sama dengan versi desktop / Excel).
File ini hanya tampilan.
"""
import os
import shutil
from datetime import date, datetime, timedelta

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.utils import get_color_from_hex as hx

import logic as L

Window.softinput_mode = "below_target"

C = dict(bg="#F1F4F9", head="#10243E", card="#FFFFFF", line="#D5DCE8", text="#1E2A3B",
         muted="#8190A5", accent="#2563EB", ok="#168A4A", bad="#C62828", warn="#B7791F",
         calc="#EAF0FA", note="#FFF4CC")
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
FS = sp(15)


# ------------------------------------------------------------------ widget kecil
def paint(widget, color, radius=8):
    with widget.canvas.before:
        Color(*hx(color))
        rect = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[dp(radius)])
    widget.bind(pos=lambda w, v: setattr(rect, "pos", v),
                size=lambda w, v: setattr(rect, "size", v))
    return rect


def lbl(text="", bold=False, color="text", halign="left", size=None, **kw):
    w = Label(text=text, bold=bold, color=hx(C.get(color, color)), font_size=size or FS,
              halign=halign, valign="middle", **kw)
    w.bind(size=lambda s, v: setattr(s, "text_size", v))
    return w


def btn(text, cb, kind="ghost", **kw):
    bg, fg = {"primary": (C["accent"], "#FFFFFF"), "ghost": ("#E3E9F4", C["text"]),
              "ok": (C["ok"], "#FFFFFF"), "danger": ("#FBE4E4", C["bad"]),
              "dark": (C["head"], "#FFFFFF")}[kind]
    kw.setdefault("size_hint_y", None)
    kw.setdefault("height", dp(46))
    b = Button(text=text, background_normal="", background_color=hx(bg), color=hx(fg),
               font_size=FS, bold=True, **kw)
    b.bind(on_release=lambda *_: cb())
    return b


def vbox(**kw):
    b = BoxLayout(orientation="vertical", size_hint_y=None, **kw)
    b.bind(minimum_height=b.setter("height"))
    return b


def scroll_of(content):
    sv = ScrollView(do_scroll_x=False, bar_width=dp(3))
    sv.add_widget(content)
    return sv


class MoneyInput(TextInput):
    """Isian rupiah: angka saja, tampil 1.234.567 saat tidak diedit."""

    def __init__(self, value=0, on_value=None, **kw):
        kw.setdefault("font_size", FS)
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(46))
        super().__init__(multiline=False, input_filter="int", input_type="number",
                         halign="right", write_tab=False, padding=[dp(10), dp(12)], **kw)
        self._cb, self._silent = on_value, False
        self.set_value(value)
        self.bind(focus=self._focus, text=self._changed)

    @property
    def value(self):
        return L.parse_money(self.text)

    def set_value(self, v):
        self._silent = True
        self.text = L.fmt_money(v) if v else ""
        self._silent = False

    def _focus(self, _, f):
        if f:
            v = self.value
            self._silent = True
            self.text = str(v) if v else ""
            self._silent = False
            Clock.schedule_once(lambda dt: self.select_all(), 0.1)
        else:
            self.set_value(self.value)

    def _changed(self, _, t):
        if not self._silent and self._cb:
            self._cb(self.value)


class Row(ButtonBehavior, BoxLayout):
    """Baris putih yang bisa ditekan: tulisan kiri + angka kanan."""

    def __init__(self, left, right, on_press_cb=None, bg="card", right_color="text", **kw):
        super().__init__(size_hint_y=None, height=dp(48), padding=[dp(12), 0], **kw)
        paint(self, C[bg])
        self.lb_left = lbl(left)
        self.lb_right = lbl(right, bold=True, halign="right", color=right_color)
        self.add_widget(self.lb_left)
        self.add_widget(self.lb_right)
        if on_press_cb:
            self.bind(on_release=lambda *_: on_press_cb())


def kv_row(left, right, bold=False, color="text"):
    r = BoxLayout(size_hint_y=None, height=dp(34))
    r.add_widget(lbl(left, bold=bold))
    r.add_widget(lbl(right, bold=True, halign="right", color=color))
    return r


def rp(v):
    return "Rp " + L.fmt_money(v)


def popup(title, content, size=(0.94, 0.9)):
    p = Popup(title=title, content=content, size_hint=size, auto_dismiss=False,
              title_size=sp(16))
    p.open()
    return p


def info(title, msg):
    box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
    box.add_widget(lbl(msg, valign="top"))
    p = popup(title, box, (0.88, 0.4))
    box.add_widget(btn("OK", p.dismiss, "primary"))


def confirm(msg, yes, yes_text="Ya", no_text="Batal", extra=None):
    box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
    box.add_widget(lbl(msg, valign="top"))
    p = popup("Konfirmasi", box, (0.88, 0.42))
    row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
    row.add_widget(btn(no_text, p.dismiss))
    if extra:
        row.add_widget(btn(extra[0], lambda: (p.dismiss(), extra[1]()), "danger"))
    row.add_widget(btn(yes_text, lambda: (p.dismiss(), yes()), "primary"))
    box.add_widget(row)


# ------------------------------------------------------------------ popup isian channel
class ChannelPopup:
    """Isi sampai 10 nominal untuk satu channel pada satu blok."""

    def __init__(self, app, bi, col):
        self.app, self.bi, self.col = app, bi, col
        b = app.rec["blocks"][bi]
        self.is_lain = col == L.LAINNYA_COL
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        grid = vbox(spacing=dp(6))
        self.amount, self.fuel, self.note = [], [], []
        opts = L.fuel_options(bi, col)
        for r in range(L.N_ROWS):
            row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            row.add_widget(lbl(str(r + 1), color="muted", size_hint_x=None, width=dp(24)))
            mi = MoneyInput(b["rows"][r][col], on_value=lambda v: self._sum())
            self.amount.append(mi)
            row.add_widget(mi)
            if len(opts) > 1:
                sp_ = Spinner(text=L.effective_fuel(bi, col, L._grid_get(b["fuel"], r, col)),
                              values=opts, size_hint_x=None, width=dp(100), font_size=FS)
                self.fuel.append(sp_)
                row.add_widget(sp_)
            elif len(opts) == 1:
                self.fuel.append(None)
                row.add_widget(lbl(opts[0], color="muted", halign="center",
                                   size_hint_x=None, width=dp(80), size=sp(12)))
            else:
                self.fuel.append(None)
            if self.is_lain:
                ti = TextInput(text=str(L._grid_get(b["note"], r, col)), multiline=False,
                               hint_text="Keterangan", font_size=sp(13),
                               size_hint_x=0.8, padding=[dp(8), dp(12)])
                self.note.append(ti)
                row.add_widget(ti)
            grid.add_widget(row)
        box.add_widget(scroll_of(grid))
        self.total = lbl("", bold=True, halign="right", size_hint_y=None, height=dp(30))
        box.add_widget(self.total)
        foot = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        self.pop = popup(L.SUMMARY_NAME.get(col, L.CHANNELS[col]) + "  -  %s%d" % ("P", bi + 1),
                         box)
        foot.add_widget(btn("Batal", self.pop.dismiss))
        foot.add_widget(btn("Simpan", self._ok, "primary"))
        box.add_widget(foot)
        self._sum()

    def _sum(self):
        self.total.text = "Total: " + rp(sum(m.value for m in self.amount))

    def _ok(self):
        b = self.app.rec["blocks"][self.bi]
        for r in range(L.N_ROWS):
            b["rows"][r][self.col] = self.amount[r].value
            f = self.fuel[r].text if self.fuel and self.fuel[r] is not None else ""
            b["fuel"][r][self.col] = f
            if self.is_lain:
                b["note"][r][self.col] = self.note[r].text.strip()
        self.pop.dismiss()
        self.app.mark_dirty()
        self.app.refresh_block()


# ------------------------------------------------------------------ aplikasi
class SetoranApp(App):
    title = "Aplikasi Setoran"

    # ---------- siklus hidup
    def build(self):
        L.DATA_DIR_OVERRIDE = self.user_data_dir
        self.store = L.Store()
        self.tgl, self.shift = date.today(), 1
        self.rec, self.dirty, self.cur_block = L.empty_record(), False, 0
        self.calc_block, self.expr = 0, ""
        Window.clearcolor = hx(C["bg"])

        root = BoxLayout(orientation="vertical")
        root.add_widget(self._topbar())
        self.sm = ScreenManager(transition=NoTransition())
        for name, builder in (("input", self._build_input), ("ringkasan", self._build_summary),
                              ("kalkulator", self._build_calc), ("riwayat", self._build_history),
                              ("menu", self._build_menu)):
            s = Screen(name=name)
            s.add_widget(builder())
            self.sm.add_widget(s)
        root.add_widget(self.sm)
        root.add_widget(self._navbar())
        self.load_current(first=True)
        return root

    def on_start(self):
        try:                                   # izin penyimpanan (hanya di Android)
            from android.permissions import Permission, request_permissions
            request_permissions([Permission.READ_EXTERNAL_STORAGE,
                                 Permission.WRITE_EXTERNAL_STORAGE])
        except Exception:
            pass

    def on_pause(self):
        if self.dirty:                         # jangan sampai data hilang saat app ditutup
            self.save()
        return True

    def on_stop(self):
        try:
            self.store.close()
        except Exception:
            pass

    # ---------- bilah atas & bawah
    def _topbar(self):
        bar = BoxLayout(size_hint_y=None, height=dp(96), orientation="vertical",
                        padding=[dp(8), dp(6)], spacing=dp(4))
        paint(bar, C["head"], 0)
        r1 = BoxLayout(spacing=dp(6))
        r1.add_widget(btn("<", lambda: self.shift_day(-1), "ghost", width=dp(42), size_hint_x=None))
        self.ti_date = TextInput(text=self.tgl.strftime("%d/%m/%Y"), multiline=False,
                                 font_size=FS, halign="center", padding=[dp(6), dp(12)],
                                 size_hint_y=None, height=dp(46))
        self.ti_date.bind(on_text_validate=lambda *_: self.change_date())
        r1.add_widget(self.ti_date)
        r1.add_widget(btn(">", lambda: self.shift_day(1), "ghost", width=dp(42), size_hint_x=None))
        self.sp_shift = Spinner(text="Shift 1", values=["Shift 1", "Shift 2", "Shift 3"],
                                size_hint=(None, None), size=(dp(96), dp(46)), font_size=FS)
        self.sp_shift.bind(text=lambda *_: self.change_date())
        r1.add_widget(self.sp_shift)
        bar.add_widget(r1)
        r2 = BoxLayout(spacing=dp(6))
        self.lb_status = lbl("", color="#FFFFFF", bold=True, size=sp(13))
        r2.add_widget(self.lb_status)
        r2.add_widget(btn("Buka", self.change_date, "ghost", width=dp(70), size_hint_x=None,
                          height=dp(34)))
        r2.add_widget(btn("SIMPAN", self.save, "ok", width=dp(100), size_hint_x=None,
                          height=dp(34)))
        bar.add_widget(r2)
        return bar

    def _navbar(self):
        bar = BoxLayout(size_hint_y=None, height=dp(54))
        paint(bar, C["head"], 0)
        self.nav = {}
        for key, text in (("input", "Input"), ("ringkasan", "Ringkasan"),
                          ("kalkulator", "Kalkulator"), ("riwayat", "Riwayat"), ("menu", "Menu")):
            b = Button(text=text, background_normal="", background_color=(0, 0, 0, 0),
                       color=hx("#B8C6DC"), font_size=sp(13), bold=True)
            b.bind(on_release=lambda w, k=key: self.go(k))
            self.nav[key] = b
            bar.add_widget(b)
        return bar

    def go(self, name):
        self.sm.current = name
        for k, b in self.nav.items():
            b.color = hx("#FFFFFF" if k == name else "#B8C6DC")
        if name == "ringkasan":
            self.refresh_summary()
        elif name == "kalkulator":
            self.refresh_calc()
        elif name == "riwayat":
            self.refresh_history()
        elif name == "input":
            self.refresh_block()

    # ---------- data: buka / simpan
    def mark_dirty(self):
        self.dirty = True
        self.set_status()

    def set_status(self):
        if self.dirty:
            self.lb_status.text = "* BELUM DISIMPAN"
        elif self.store.exists(self.tgl, self.shift):
            self.lb_status.text = "Tersimpan  -  %s" % HARI[self.tgl.weekday()]
        else:
            self.lb_status.text = "Data baru  -  %s" % HARI[self.tgl.weekday()]

    def load_current(self, first=False):
        self.rec = self.store.load(self.tgl, self.shift) or L.empty_record()
        self.dirty = False
        self.ti_date.text = self.tgl.strftime("%d/%m/%Y")
        self.sp_shift.text = "Shift %d" % self.shift
        self.set_status()
        if not first:
            self.go(self.sm.current)
        else:
            self.go("input")

    def _parse_date(self):
        t = self.ti_date.text.strip()
        for f in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(t, f).date()
            except ValueError:
                pass
        return None

    def change_date(self):
        d = self._parse_date()
        sh = int(self.sp_shift.text.split()[-1])
        if d is None:
            info("Tanggal salah", "Tulis tanggal seperti 21/11/2026.")
            self.ti_date.text = self.tgl.strftime("%d/%m/%Y")
            return
        if (d, sh) == (self.tgl, self.shift):
            return

        def do():
            self.tgl, self.shift = d, sh
            self.load_current()

        def back():
            self.ti_date.text = self.tgl.strftime("%d/%m/%Y")
            self.sp_shift.text = "Shift %d" % self.shift

        if self.dirty:
            confirm("Ada perubahan yang belum disimpan.", lambda: (self.save(), do()),
                    yes_text="Simpan", no_text="Batal",
                    extra=("Buang", do))
            back()
        else:
            do()

    def shift_day(self, n):
        d = self._parse_date() or self.tgl
        self.ti_date.text = (d + timedelta(days=n)).strftime("%d/%m/%Y")
        self.change_date()

    def save(self):
        self.store.save(self.tgl, self.shift, self.rec)
        self.dirty = False
        self.set_status()

    # ================================================================== INPUT
    def _build_input(self):
        root = BoxLayout(orientation="vertical", spacing=dp(4), padding=[dp(6), dp(6)])
        tabs = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        self.tab_btn = []
        for i in range(L.N_BLOCKS):
            b = Button(text="P%d" % (i + 1), background_normal="", font_size=FS, bold=True)
            b.bind(on_release=lambda w, i=i: self.pick_block(i))
            self.tab_btn.append(b)
            tabs.add_widget(b)
        root.add_widget(tabs)
        self.block_box = vbox(spacing=dp(6), padding=[0, dp(4)])
        root.add_widget(scroll_of(self.block_box))
        self._build_block_widgets()
        return root

    def pick_block(self, i):
        self.cur_block = i
        self.calc_block = i
        self.refresh_block()

    def _build_block_widgets(self):
        bb = self.block_box
        bb.clear_widgets()
        self.in_laporan = MoneyInput(on_value=self._on_laporan)
        self.in_cash = MoneyInput(on_value=self._on_cash)
        r = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        r.add_widget(lbl("LAPORAN HARIAN", bold=True))
        r.add_widget(self.in_laporan)
        bb.add_widget(r)
        r = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        r.add_widget(lbl("SETORAN CASH", bold=True))
        r.add_widget(self.in_cash)
        bb.add_widget(r)
        bb.add_widget(btn("PAS-KAN CASH OTOMATIS", self.auto_pas_cash, "primary"))
        bb.add_widget(lbl("Channel (tekan untuk mengisi nominal)", color="muted", size=sp(12),
                          size_hint_y=None, height=dp(24)))
        self.ch_rows = []
        for c in range(L.N_COLS):
            row = Row(L.SUMMARY_NAME.get(c, L.CHANNELS[c]), "0",
                      on_press_cb=lambda c=c: ChannelPopup(self, self.cur_block, c))
            self.ch_rows.append(row)
            bb.add_widget(row)
        self.tot_box = vbox(padding=[dp(12), dp(8)], spacing=dp(2))
        paint(self.tot_box, C["calc"])
        bb.add_widget(self.tot_box)
        bb.add_widget(btn("Buka Kalkulator Pas", lambda: self.go("kalkulator"), "dark"))

    def _on_laporan(self, v):
        self.rec["blocks"][self.cur_block]["laporan"] = v
        self.mark_dirty()
        self.refresh_block(skip_inputs=True)

    def _on_cash(self, v):
        self.rec["blocks"][self.cur_block]["cash"] = v
        self.mark_dirty()
        self.refresh_block(skip_inputs=True)

    def auto_pas_cash(self):
        st = L.block_status(self.rec, self.cur_block)
        if st["cash_pas"] < 0:
            info("Tidak bisa dipaskan",
                 "Isian aplikasi sudah lebih besar %s dari laporan.\n"
                 "Buka Kalkulator > Pas-kan untuk mencari isian yang kemungkinan dobel/salah."
                 % rp(-st["cash_pas"]))
            return
        self.rec["blocks"][self.cur_block]["cash"] = st["cash_pas"]
        self.mark_dirty()
        self.refresh_block()

    def refresh_block(self, skip_inputs=False):
        bi = self.cur_block
        b = self.rec["blocks"][bi]
        if not skip_inputs:
            self.in_laporan.set_value(b["laporan"])
            self.in_cash.set_value(b["cash"])
        res = L.calculate(self.rec)
        for i, tb in enumerate(self.tab_btn):
            st = L.block_status(self.rec, i)
            mark = "" if not (st["laporan"] or st["app_total"]) else (" OK" if st["pas"] else " !")
            tb.text = "P%d%s" % (i + 1, mark)
            on = i == bi
            tb.background_color = hx(C["accent"] if on else "#DCE3F0")
            tb.color = hx("#FFFFFF" if on else C["text"])
        bl = res["blocks"][bi]
        for c, row in enumerate(self.ch_rows):
            n = sum(1 for r in range(L.N_ROWS) if b["rows"][r][c])
            tot = bl["col_totals"][c]
            row.lb_right.text = ("%s  (%dx)" % (L.fmt_money(tot), n)) if tot else "0"
            row.lb_right.color = hx(C["text"] if tot else C["muted"])
        st = L.block_status(self.rec, bi)
        t = self.tot_box
        t.clear_widgets()
        t.add_widget(kv_row("TOTAL SETORAN APLIKASI", rp(bl["app_total"])))
        t.add_widget(kv_row("TOTAL SETORAN", rp(bl["total_setoran"]), True))
        t.add_widget(kv_row("MINUS", rp(bl["minus"]), True,
                            "ok" if bl["minus"] == 0 else "bad"))
        t.add_widget(kv_row("SETORAN AKHIR", rp(bl["setoran_akhir"]), True))
        msg, col = self.pas_message(st)
        t.add_widget(lbl(msg, bold=True, color=col, size_hint_y=None, height=dp(34),
                         halign="center"))

    @staticmethod
    def pas_message(st):
        if st["pas"]:
            return "SETORAN PAS (OK)", "ok"
        if st["selisih"] > 0:
            return "KURANG %s" % rp(st["selisih"]), "bad"
        return "LEBIH %s" % rp(-st["selisih"]), "warn"

    # ================================================================== RINGKASAN
    def _build_summary(self):
        root = vbox(spacing=dp(6), padding=dp(8))
        self.in_total = MoneyInput(on_value=self._on_total)
        self.in_global = MoneyInput(on_value=self._on_global)
        r = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        r.add_widget(lbl("TOTAL", bold=True))
        r.add_widget(self.in_total)
        root.add_widget(r)
        r = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        r.add_widget(lbl("TOTAL GLOBAL", bold=True))
        r.add_widget(self.in_global)
        root.add_widget(r)
        root.add_widget(lbl("Isi dua angka ini dari laporan harian. Sisanya dihitung otomatis.",
                            color="muted", size=sp(12), size_hint_y=None, height=dp(34)))
        self.sum_out = vbox(spacing=dp(4))
        root.add_widget(self.sum_out)
        return scroll_of(root)

    def _on_total(self, v):
        self.rec["total"] = v
        self.mark_dirty()
        self.refresh_summary(skip_inputs=True)

    def _on_global(self, v):
        self.rec["total_global"] = v
        self.mark_dirty()
        self.refresh_summary(skip_inputs=True)

    def _section(self, title):
        self.sum_out.add_widget(lbl(title, bold=True, color="accent", size_hint_y=None,
                                    height=dp(36)))

    def refresh_summary(self, skip_inputs=False):
        if not skip_inputs:
            self.in_total.set_value(self.rec["total"])
            self.in_global.set_value(self.rec["total_global"])
        res = L.calculate(self.rec)
        o = self.sum_out
        o.clear_widgets()
        self._section("Rekap Per Channel (P1 - P4)")
        if not res["channel_detail"]:
            o.add_widget(lbl("Belum ada channel yang terisi", color="muted",
                             size_hint_y=None, height=dp(30)))
        for c, f, amount, items in res["channel_detail"]:
            if amount or not items:
                o.add_widget(kv_row(L.label_channel(c, f), rp(amount)))
            for it in items:
                r = kv_row("    " + it["note"], rp(it["amount"]))
                paint(r, C["note"], 4)
                o.add_widget(r)
        self._section("Hasil Perhitungan")
        for text, val, bold in (("TOTAL (setelah dikurangi aplikasi)", res["cash_total"], False),
                                ("MINUS TOTAL", res["minus_total"], False),
                                ("PROFIT", res["tera"], False),
                                ("GLOBAL AKHIR", res["global_akhir"], False),
                                ("TOTAL AKHIR", res["total_akhir"], True)):
            o.add_widget(kv_row(text, rp(val), bold))
        self._section("Rincian per Blok")
        for i, bl in enumerate(res["blocks"]):
            b = self.rec["blocks"][i]
            card = vbox(padding=[dp(10), dp(6)], spacing=dp(1))
            paint(card, C["card"])
            card.add_widget(lbl("P%d" % (i + 1), bold=True, size_hint_y=None, height=dp(28)))
            card.add_widget(kv_row("Laporan harian", rp(b["laporan"])))
            card.add_widget(kv_row("Setoran cash", rp(b["cash"])))
            card.add_widget(kv_row("Setoran aplikasi", rp(bl["app_total"])))
            card.add_widget(kv_row("Total setoran", rp(bl["total_setoran"])))
            card.add_widget(kv_row("Minus", rp(bl["minus"]), True,
                                   "ok" if bl["minus"] == 0 else "bad"))
            card.add_widget(kv_row("Setoran akhir", rp(bl["setoran_akhir"]), True))
            o.add_widget(card)
            o.add_widget(BoxLayout(size_hint_y=None, height=dp(4)))

    # ================================================================== KALKULATOR
    def _build_calc(self):
        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))
        top = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.mode_btn = {}
        for key, text in (("pas", "PAS-KAN SETORAN"), ("biasa", "KALKULATOR")):
            b = Button(text=text, background_normal="", font_size=sp(14), bold=True)
            b.bind(on_release=lambda w, k=key: self.set_calc_mode(k))
            self.mode_btn[key] = b
            top.add_widget(b)
        root.add_widget(top)
        self.calc_holder = BoxLayout()
        root.add_widget(self.calc_holder)
        self.calc_mode = "pas"
        self._build_pas_view()
        self._build_keypad_view()
        return root

    def set_calc_mode(self, m):
        self.calc_mode = m
        self.refresh_calc()

    def refresh_calc(self):
        self.calc_holder.clear_widgets()
        for k, b in self.mode_btn.items():
            on = k == self.calc_mode
            b.background_color = hx(C["accent"] if on else "#DCE3F0")
            b.color = hx("#FFFFFF" if on else C["text"])
        if self.calc_mode == "pas":
            self.calc_holder.add_widget(self.pas_view)
            self.sp_blok.text = "P%d" % (self.calc_block + 1)
            self.refresh_pas()
        else:
            self.calc_holder.add_widget(self.keypad_view)
            self.show_expr()

    # ---------- Pas-kan setoran
    def _build_pas_view(self):
        content = vbox(spacing=dp(6), padding=[0, dp(4)])
        r = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        r.add_widget(lbl("Pilih blok", bold=True))
        self.sp_blok = Spinner(text="P1", values=["P1", "P2", "P3", "P4"], font_size=FS)
        self.sp_blok.bind(text=self._pick_calc_block)
        r.add_widget(self.sp_blok)
        content.add_widget(r)
        self.pas_info = vbox(padding=[dp(12), dp(8)], spacing=dp(2))
        paint(self.pas_info, C["calc"])
        content.add_widget(self.pas_info)
        self.pas_actions = vbox(spacing=dp(6))
        content.add_widget(self.pas_actions)
        content.add_widget(lbl("Hitung uang tunai (pecahan)", bold=True, color="accent",
                               size_hint_y=None, height=dp(36)))
        self.denom_in, self.denom_sub = {}, {}
        for d in L.DENOMS[:7]:                      # 100.000 s/d 1.000 (receh lewat kolom lain)
            row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            row.add_widget(lbl(L.fmt_money(d), bold=True, size_hint_x=0.9))
            ti = TextInput(multiline=False, input_filter="int", input_type="number",
                           hint_text="lembar", halign="center", font_size=FS,
                           padding=[dp(6), dp(11)])
            ti.bind(text=lambda *_: self.refresh_denoms())
            self.denom_in[d] = ti
            row.add_widget(ti)
            sub = lbl("0", halign="right", color="muted")
            self.denom_sub[d] = sub
            row.add_widget(sub)
            content.add_widget(row)
        r = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        r.add_widget(lbl("Receh / lainnya", bold=True, size_hint_x=0.9))
        self.denom_extra = MoneyInput(on_value=lambda v: self.refresh_denoms())
        r.add_widget(self.denom_extra)
        r.add_widget(lbl("", size_hint_x=0.8))
        content.add_widget(r)
        self.denom_result = vbox(spacing=dp(4))
        content.add_widget(self.denom_result)
        self.pas_view = scroll_of(content)

    def _pick_calc_block(self, _, text):
        self.calc_block = int(text[1]) - 1
        self.refresh_pas()

    def refresh_pas(self):
        bi = self.calc_block
        st = L.block_status(self.rec, bi)
        i = self.pas_info
        i.clear_widgets()
        i.add_widget(kv_row("LAPORAN HARIAN", rp(st["laporan"]), True))
        i.add_widget(kv_row("Total aplikasi", rp(st["app_total"])))
        i.add_widget(kv_row("Setoran cash", rp(st["cash"])))
        i.add_widget(kv_row("Total setoran", rp(st["total_setoran"]), True))
        msg, col = self.pas_message(st)
        i.add_widget(lbl(msg, bold=True, color=col, size=sp(20), halign="center",
                         size_hint_y=None, height=dp(44)))
        a = self.pas_actions
        a.clear_widgets()
        if st["pas"]:
            a.add_widget(lbl("Minus = 0. Tidak ada yang perlu diubah.", color="ok",
                             size_hint_y=None, height=dp(30)))
        elif st["cash_pas"] >= 0:
            a.add_widget(lbl("Agar pas, cash yang dibutuhkan:", color="muted",
                             size_hint_y=None, height=dp(26)))
            a.add_widget(lbl(rp(st["cash_pas"]), bold=True, size=sp(22), halign="center",
                             size_hint_y=None, height=dp(40)))
            a.add_widget(btn("ISI CASH = %s" % rp(st["cash_pas"]),
                             lambda: self.apply_cash(st["cash_pas"]), "primary"))
        else:
            a.add_widget(lbl("Total setoran melebihi laporan %s. Cash tidak bisa diturunkan "
                             "lagi (isian aplikasi saja sudah lebih besar %s dari laporan). "
                             "Kemungkinan penyebab - isian yang jumlahnya sama dengan "
                             "kelebihan:" % (rp(-st["selisih"]), rp(-st["cash_pas"])),
                             color="bad", size_hint_y=None, height=dp(110)))
            cands = L.cari_penyebab(self.rec, bi)
            if not cands:
                a.add_widget(lbl("Tidak ditemukan kombinasi yang cocok. Periksa ulang laporan "
                                 "harian atau nominal yang terlalu besar.", color="muted",
                                 size_hint_y=None, height=dp(60)))
            for combo in cands:
                card = vbox(padding=[dp(10), dp(6)])
                paint(card, C["note"])
                for name, v in combo:
                    card.add_widget(kv_row(name, rp(v)))
                a.add_widget(card)
        self.refresh_denoms()

    def apply_cash(self, v):
        self.rec["blocks"][self.calc_block]["cash"] = v
        self.mark_dirty()
        self.refresh_pas()

    def refresh_denoms(self):
        if not hasattr(self, "denom_result") or not self.denom_in:
            return
        counts = {}
        for d, ti in self.denom_in.items():
            n = L.parse_money(ti.text)
            counts[d] = n
            self.denom_sub[d].text = L.fmt_money(d * n) if n else "0"
        total = L.pecahan_total(counts) + self.denom_extra.value
        st = L.block_status(self.rec, self.calc_block)
        o = self.denom_result
        o.clear_widgets()
        o.add_widget(kv_row("TOTAL UANG TUNAI", rp(total), True))
        need = st["cash_pas"]
        if need >= 0 and not st["pas"]:
            diff = total - need
            if abs(diff) < L.PAS_TOLERANSI:
                o.add_widget(lbl("OK - sama dengan cash yang dibutuhkan", bold=True, color="ok",
                                 size_hint_y=None, height=dp(30)))
            else:
                o.add_widget(lbl(("KURANG %s dari cash yang dibutuhkan" % rp(-diff)) if diff < 0
                                 else ("LEBIH %s dari cash yang dibutuhkan" % rp(diff)),
                                 bold=True, color="bad" if diff < 0 else "warn",
                                 size_hint_y=None, height=dp(30)))
            o.add_widget(lbl("Pecahan untuk %s:  %s" % (rp(need), ",  ".join(
                "%s x%d" % (L.fmt_money(d), n) for d, n in L.pecahan_breakdown(need))),
                color="muted", size=sp(12), size_hint_y=None, height=dp(48)))
        o.add_widget(btn("PAKAI TOTAL INI SEBAGAI CASH", lambda: self.apply_cash(total), "ghost"))

    # ---------- kalkulator biasa
    def _build_keypad_view(self):
        v = BoxLayout(orientation="vertical", spacing=dp(6))
        disp = BoxLayout(orientation="vertical", padding=[dp(12), dp(8)], spacing=dp(2),
                         size_hint_y=None, height=dp(110))
        paint(disp, C["head"])
        self.lb_expr = lbl("", color="#B8C6DC", halign="right", size=sp(18), size_hint_y=None,
                           height=dp(36))
        self.lb_res = lbl("0", color="#FFFFFF", halign="right", bold=True, size=sp(32),
                          size_hint_y=None, height=dp(56))
        disp.add_widget(self.lb_expr)
        disp.add_widget(self.lb_res)
        v.add_widget(disp)
        keys = [["C", "(", ")", "÷"], ["7", "8", "9", "×"], ["4", "5", "6", "-"],
                ["1", "2", "3", "+"], ["0", "000", ",", "DEL"]]
        grid = GridLayout(cols=4, spacing=dp(5))
        for row in keys:
            for k in row:
                kind = "dark" if k in ("÷", "×", "-", "+") else "ghost"
                if k == "C":
                    kind = "danger"
                b = btn(k, lambda k=k: self.key(k), kind, size_hint_y=1)
                b.font_size = sp(22)
                grid.add_widget(b)
        v.add_widget(grid)
        v.add_widget(btn("=   HITUNG", lambda: self.key("="), "primary"))
        tools = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        tools.add_widget(btn("ISI KE CASH", lambda: self.send_result("cash"), "ok"))
        tools.add_widget(btn("ISI KE LAPORAN", lambda: self.send_result("laporan"), "ghost"))
        v.add_widget(tools)
        self.keypad_view = v

    def key(self, k):
        if k == "C":
            self.expr = ""
        elif k == "DEL":
            self.expr = self.expr[:-1]
        elif k == "=":
            try:
                self.expr = L.fmt_calc(L.calc_eval(self.expr))
            except ValueError:
                info("Rumus salah", "Periksa kembali rumusnya.")
        else:
            self.expr += k
        self.show_expr()

    def show_expr(self):
        self.lb_expr.text = self.expr
        try:
            self.lb_res.text = L.fmt_calc(L.calc_eval(self.expr)) if self.expr else "0"
        except (ValueError, ZeroDivisionError):
            self.lb_res.text = "..." if self.expr else "0"

    def send_result(self, target):
        try:
            val = L.calc_eval(self.expr)
        except ValueError:
            info("Belum ada hasil", "Hitung dulu rumusnya.")
            return
        v = int(round(val))
        b = self.rec["blocks"][self.calc_block]
        b[target] = max(0, v)
        self.mark_dirty()
        info("Terisi", "%s P%d diisi %s" % ("Cash" if target == "cash" else "Laporan harian",
                                             self.calc_block + 1, rp(b[target])))

    # ================================================================== RIWAYAT
    def _build_history(self):
        self.hist_box = vbox(spacing=dp(6), padding=dp(8))
        return scroll_of(self.hist_box)

    def refresh_history(self):
        hb = self.hist_box
        hb.clear_widgets()
        items = self.store.list_all()
        if not items:
            hb.add_widget(lbl("Belum ada data tersimpan", color="muted", size_hint_y=None,
                              height=dp(40)))
        for tgl, shift, upd, rec in items:
            res = L.calculate(rec)
            card = vbox(padding=[dp(10), dp(6)], spacing=dp(1))
            paint(card, C["card"])
            card.add_widget(lbl("%s %s  -  Shift %d" % (HARI[tgl.weekday()],
                                                       tgl.strftime("%d/%m/%Y"), shift),
                                bold=True, size_hint_y=None, height=dp(30)))
            card.add_widget(kv_row("Laporan harian", rp(sum(b["laporan"] for b in rec["blocks"]))))
            card.add_widget(kv_row("Minus total", rp(res["minus_total"]), False,
                                   "ok" if res["minus_total"] == 0 else "bad"))
            card.add_widget(kv_row("Profit", rp(res["tera"])))
            card.add_widget(kv_row("Total akhir", rp(res["total_akhir"]), True))
            card.add_widget(lbl("Diubah " + upd, color="muted", size=sp(11), size_hint_y=None,
                                height=dp(22)))
            r = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
            r.add_widget(btn("Buka", lambda t=tgl, s=shift: self.open_history(t, s), "primary",
                             height=dp(40)))
            r.add_widget(btn("Hapus", lambda t=tgl, s=shift: self.delete_history(t, s), "danger",
                             height=dp(40)))
            card.add_widget(r)
            hb.add_widget(card)

    def open_history(self, t, s):
        def do():
            self.tgl, self.shift = t, s
            self.load_current()
            self.go("input")
        if self.dirty:
            confirm("Ada perubahan yang belum disimpan.", lambda: (self.save(), do()),
                    yes_text="Simpan", extra=("Buang", do))
        else:
            do()

    def delete_history(self, t, s):
        def do():
            self.store.delete(t, s)
            if (t, s) == (self.tgl, self.shift):
                self.rec, self.dirty = L.empty_record(), False
                self.set_status()
            self.refresh_history()
        confirm("Hapus data %s Shift %d?" % (t.strftime("%d/%m/%Y"), s), do, yes_text="Hapus")

    # ================================================================== MENU
    def _build_menu(self):
        box = vbox(spacing=dp(8), padding=dp(12))
        for text, cb, kind in (("Ekspor Excel (tanggal ini)", self.export_current, "primary"),
                               ("Ekspor Excel (semua data)", self.export_all, "ghost"),
                               ("Impor dari Excel", self.import_excel, "ghost"),
                               ("Backup Data", self.backup, "ghost"),
                               ("Kosongkan Data Ini", self.clear_current, "danger")):
            box.add_widget(btn(text, cb, kind))
        self.lb_path = lbl("", color="muted", size=sp(12), size_hint_y=None, height=dp(80))
        box.add_widget(self.lb_path)
        return scroll_of(box)

    def out_dir(self):
        for base in ("/storage/emulated/0/Documents", os.path.join(self.user_data_dir, "export")):
            d = os.path.join(base, "AplikasiSetoran")
            try:
                os.makedirs(d, exist_ok=True)
                t = os.path.join(d, ".t")
                open(t, "w").close()
                os.remove(t)
                return d
            except Exception:
                continue
        return self.user_data_dir

    def _do_export(self, items, name):
        try:
            path = os.path.join(self.out_dir(), name)
            L.export_workbook(path, items)
            self.lb_path.text = "Tersimpan di:\n" + path
            info("Ekspor berhasil", path)
        except Exception as e:
            info("Ekspor gagal", "%s\n\nPastikan file template_setoran.xlsx ikut di dalam app." % e)

    def export_current(self):
        self._do_export([(self.tgl, self.shift, self.rec)],
                        "Setoran_%s_S%d.xlsx" % (self.tgl.strftime("%Y%m%d"), self.shift))

    def export_all(self):
        items = [(t, s, r) for t, s, u, r in reversed(self.store.list_all())]
        if not items:
            info("Kosong", "Belum ada data tersimpan.")
            return
        self._do_export(items, "Setoran_semua_%s.xlsx" % datetime.now().strftime("%Y%m%d_%H%M"))

    def import_excel(self):
        start = self.out_dir()
        for p in ("/storage/emulated/0/Download", start):
            if os.path.isdir(p):
                start = p
                break
        box = BoxLayout(orientation="vertical", spacing=dp(6))
        fc = FileChooserListView(path=start, filters=["*.xlsx", "*.xlsm"])
        box.add_widget(fc)
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        pop = popup("Pilih file Excel", box)

        def go_import():
            if not fc.selection:
                return
            pop.dismiss()
            try:
                found = L.read_workbook(fc.selection[0])
            except Exception as e:
                info("Gagal membaca", str(e))
                return
            ok = 0
            for tgl, shift, rec, _ in found:
                if tgl:
                    self.store.save(tgl, shift, rec)
                    ok += 1
            self.load_current()
            info("Impor selesai", "%d sheet diimpor, %d dilewati (tanpa tanggal)." %
                 (ok, len(found) - ok))

        row.add_widget(btn("Batal", pop.dismiss))
        row.add_widget(btn("Impor", go_import, "primary"))
        box.add_widget(row)

    def backup(self):
        try:
            dst = os.path.join(self.out_dir(), "setoran_backup_%s.db" %
                               datetime.now().strftime("%Y%m%d_%H%M"))
            shutil.copy2(self.store.path, dst)
            self.lb_path.text = "Backup tersimpan di:\n" + dst
            info("Backup berhasil", dst)
        except Exception as e:
            info("Backup gagal", str(e))

    def clear_current(self):
        def do():
            self.rec = L.empty_record()
            self.mark_dirty()
            self.go(self.sm.current)
        confirm("Kosongkan semua isian untuk %s Shift %d?\n(belum menghapus dari riwayat "
                "sebelum Anda tekan SIMPAN)" % (self.tgl.strftime("%d/%m/%Y"), self.shift),
                do, yes_text="Kosongkan")


if __name__ == "__main__":
    SetoranApp().run()
