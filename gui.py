"""gui.py -- tkinter front-end for greek_srt. Run: python gui.py"""

from __future__ import annotations

import ctypes
import json
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from greek_srt import Action, FileReport, Target, convert, scan
from greek_srt.fileio import count_temp_files

APP_NAME = "Greek SRT Converter"
CHECKED = "\u2611"      # BALLOT BOX WITH CHECK
UNCHECKED = "\u2610"    # BALLOT BOX
SETTINGS = Path(os.environ.get("APPDATA", Path.home())) / "GreekSrtConverter" / "settings.json"


def enable_dpi_awareness() -> None:
    """MUST be called before tkinter.Tk() is constructed."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def pick_mono_font(root: tk.Misc) -> str:
    available = set(tkfont.families(root))
    for family in ("Consolas", "Courier New", "Lucida Console"):
        if family in available:
            return family
    return tkfont.nametofont("TkFixedFont").actual("family")


def row_text(report: FileReport) -> tuple[str, list[str], bool]:
    """-> (status text, extra tags, ticked-and-toggleable)."""
    if report.action is Action.UNREADABLE:
        return f"unreadable - {report.error}", ["bad"], False
    if report.action is Action.ALREADY_TARGET:
        return "already target", ["skip"], False
    if report.action is Action.NEEDS_REVIEW:
        return (f"NEEDS REVIEW - {report.loss_ratio:.0%} of non-ASCII lost",
                ["review"], False)
    if report.dropped_count:
        return f"{report.dropped_count} chars stripped (!)", ["warn"], True
    if report.encoding == "utf-8-sig" and report.target is Target.UTF_8 and report.time_offset_ms == 0:
        return "will convert (BOM removed)", [], True
    if report.time_offset_ms != 0:
        sec = report.time_offset_ms / 1000.0
        return f"will convert (shift {sec:+.1f}s)", [], True
    return "will convert", [], True


class ConverterApp(ttk.Frame):
    def __init__(self, master: tk.Tk, initial_folder: str = "") -> None:
        super().__init__(master, padding=0)
        self.root: tk.Tk = master
        self.settings = load_settings()
        self.queue: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self._after_id: str | None = None
        self.checked: dict[str, bool] = {}
        self.reports: dict[str, FileReport] = {}
        self.recent_folders: list[str] = self.settings.get("recent_folders", [])

        if initial_folder and os.path.isdir(initial_folder):
            self.settings["last_folder"] = initial_folder
            self._add_recent_folder(initial_folder)

        self.mono = pick_mono_font(master)
        self.pack(fill="both", expand=True)
        self._build()
        self._init_style()
        master.protocol("WM_DELETE_WINDOW", self.on_close)

    def _add_recent_folder(self, folder: str) -> None:
        folder = os.path.normpath(folder)
        if folder in self.recent_folders:
            self.recent_folders.remove(folder)
        self.recent_folders.insert(0, folder)
        self.recent_folders = self.recent_folders[:10]
        if hasattr(self, "folder_combo"):
            self.folder_combo.configure(values=self.recent_folders)

    # ------------------------------------------------------------- style & theme
    def _init_style(self) -> None:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        base = tkfont.nametofont("TkDefaultFont")
        self.row_height = base.metrics("linespace") + 10
        style.configure("Treeview", rowheight=self.row_height)
        style.configure("Treeview.Heading", padding=(6, 4))
        style.configure("TButton", padding=(10, 4))
        self._apply_theme()

    def _apply_theme(self) -> None:
        dark = self.dark_var.get()
        style = ttk.Style()
        base = tkfont.nametofont("TkDefaultFont")

        bg_color = "#1e1e1e" if dark else "#f0f0f0"
        fg_color = "#d4d4d4" if dark else "#111111"
        text_bg = "#2d2d2d" if dark else "#ffffff"
        tree_bg = "#252526" if dark else "#ffffff"
        stripe_bg = "#2a2d32" if dark else "#f5f7fa"
        warn_fg = "#e5c07b" if dark else "#b35c00"
        bad_fg = "#e06c75" if dark else "#c02626"
        skip_fg = "#7f848e" if dark else "#8a8a8a"

        self.root.configure(background=bg_color)
        self.preview.configure(background=text_bg, foreground=fg_color, insertbackground=fg_color)
        self.status.configure(background=bg_color, foreground=fg_color)

        if dark:
            style.configure("Treeview", background=tree_bg, foreground=fg_color, fieldbackground=tree_bg)
            style.configure("Treeview.Heading", background="#333333", foreground="#ffffff")
        else:
            style.configure("Treeview", background="#ffffff", foreground="#111111", fieldbackground="#ffffff")

        self.tree.tag_configure("stripe", background=stripe_bg)
        self.tree.tag_configure("warn", foreground=warn_fg)
        self.tree.tag_configure("skip", foreground=skip_fg)
        self.tree.tag_configure("bad", foreground=bad_fg)
        self.tree.tag_configure(
            "review", foreground=bad_fg,
            font=(base.actual("family"), base.actual("size"), "bold"))

    # ------------------------------------------------------------- widgets
    def _build(self) -> None:
        base = tkfont.nametofont("TkDefaultFont")

        # Top bar: Folder picking with Combobox
        top = ttk.Frame(self, padding=(12, 10, 12, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Folder:").grid(row=0, column=0, sticky="w")
        self.folder_var = tk.StringVar(value=self.settings.get("last_folder", ""))
        self.folder_combo = ttk.Combobox(top, textvariable=self.folder_var, values=self.recent_folders)
        self.folder_combo.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(top, text="Browse\u2026", command=self.browse).grid(row=0, column=2)
        self.recurse_var = tk.BooleanVar(value=bool(self.settings.get("recurse", False)))
        ttk.Checkbutton(top, text="Recurse", variable=self.recurse_var,
                        onvalue=True, offvalue=False).grid(row=0, column=3, padx=(12, 0))
        top.columnconfigure(1, weight=1)

        # Mode and Time Shift bar
        mode = ttk.Frame(self, padding=(12, 4))
        mode.pack(fill="x")
        ttk.Label(mode, text="Mode:").pack(side="left")
        self.target_var = tk.StringVar(value=self.settings.get("target", "utf-8"))
        ttk.Radiobutton(mode, text="UTF-8", variable=self.target_var,
                        value="utf-8").pack(side="left", padx=(8, 0))
        ttk.Radiobutton(mode, text="Greek ISO-8859-7", variable=self.target_var,
                        value="iso-8859-7").pack(side="left", padx=(10, 0))

        ttk.Label(mode, text="Time Shift:").pack(side="left", padx=(16, 0))
        self.offset_var = tk.StringVar(value="0.0")
        ttk.Entry(mode, textvariable=self.offset_var, width=6).pack(side="left", padx=(4, 0))
        ttk.Label(mode, text="s").pack(side="left")

        # Preset buttons for time offset
        for label, val in [("-2s", "-2.0"), ("-0.5s", "-0.5"), ("0s", "0.0"), ("+0.5", "+0.5"), ("+2s", "+2.0")]:
            ttk.Button(mode, text=label, width=4,
                       command=lambda v=val: self.offset_var.set(v)).pack(side="left", padx=1)

        self.scan_btn = ttk.Button(mode, text="Scan", command=self.start_scan)
        self.scan_btn.pack(side="right")

        # Main Table (Treeview)
        mid = ttk.Frame(self, padding=(12, 6))
        mid.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(mid, columns=("sel", "file", "encoding", "status"),
                                 show="headings", selectmode="browse", height=8)
        self.tree.heading("sel", text=CHECKED, command=self.toggle_all)
        self.tree.heading("file", text="File", anchor="w")
        self.tree.heading("encoding", text="Detected", anchor="w")
        self.tree.heading("status", text="Status", anchor="w")
        glyph_w = max(base.measure(CHECKED), base.measure(UNCHECKED)) + 22
        self.tree.column("sel", width=glyph_w, minwidth=glyph_w, stretch=False, anchor="center")
        self.tree.column("file", width=280, minwidth=140, anchor="w")
        self.tree.column("encoding", width=140, minwidth=90, anchor="w")
        self.tree.column("status", width=260, minwidth=120, anchor="w")
        bar = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        bar.grid(row=0, column=1, sticky="ns")
        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)

        self.tree.bind("<Button-1>", self.on_tree_click, add="+")
        self.tree.bind("<space>", self.on_space)
        self.root.bind("<Control-a>", lambda e: self.select_all_keyboard())
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # Subtitle Preview Pane
        pane = ttk.LabelFrame(self, text="Preview", padding=(8, 6))
        pane.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        self.preview = tk.Text(pane, height=9, wrap="none", undo=False,
                               font=(self.mono, 10), background="#ffffff",
                               foreground="#111111", relief="solid", borderwidth=1,
                               spacing1=1, spacing3=1, padx=6, pady=4)
        pv = ttk.Scrollbar(pane, orient="vertical", command=self.preview.yview)
        ph = ttk.Scrollbar(pane, orient="horizontal", command=self.preview.xview)
        self.preview.configure(yscrollcommand=pv.set, xscrollcommand=ph.set)
        self.preview.grid(row=0, column=0, sticky="nsew")
        pv.grid(row=0, column=1, sticky="ns")
        ph.grid(row=1, column=0, sticky="ew")
        pane.rowconfigure(0, weight=1)
        pane.columnconfigure(0, weight=1)
        self.preview.configure(state="disabled")

        # Bottom Bar: Controls, Options, Progress
        bottom = ttk.Frame(self, padding=(12, 0, 12, 10))
        bottom.pack(fill="x")
        self.backup_var = tk.BooleanVar(value=bool(self.settings.get("backup", True)))
        ttk.Checkbutton(bottom, text="Backup originals", variable=self.backup_var,
                        onvalue=True, offvalue=False).pack(side="left")

        self.dark_var = tk.BooleanVar(value=bool(self.settings.get("dark_mode", False)))
        ttk.Checkbutton(bottom, text="Dark Theme", variable=self.dark_var,
                        command=self._apply_theme, onvalue=True, offvalue=False).pack(side="left", padx=(12, 0))

        self.convert_btn = ttk.Button(bottom, text="Convert 0 selected",
                                      state="disabled", command=self.start_convert)
        self.convert_btn.pack(side="right")
        self.cancel_btn = ttk.Button(bottom, text="Cancel", state="disabled",
                                     command=self.cancel.set)
        self.cancel_btn.pack(side="right", padx=(0, 8))
        self.progress = ttk.Progressbar(bottom, mode="determinate", length=180)
        self.progress.pack(side="right", padx=(0, 10))

        self.status = ttk.Label(self.root, text="Ready", relief="sunken",
                                anchor="w", padding=(8, 3))
        self.status.pack(fill="x", side="bottom")

    # ------------------------------------------------------------- folder
    def browse(self) -> None:
        seed = self.folder_var.get().strip() or self.settings.get("last_folder", "")
        if not seed or not os.path.isdir(seed):
            seed = os.path.expanduser("~")
        chosen = filedialog.askdirectory(
            parent=self.root,
            title="Choose the folder containing your .srt files",
            initialdir=seed, mustexist=True)
        if not chosen:            # Cancel returns "" (empty str), never None
            return
        norm = os.path.normpath(chosen)
        self.folder_var.set(norm)
        self._add_recent_folder(norm)
        self.settings["last_folder"] = norm
        save_settings(self.settings)

    # ------------------------------------------------------------- checkbox
    def _toggleable(self, iid: str) -> bool:
        report = self.reports.get(iid)
        return report is not None and report.writable

    def on_tree_click(self, event: tk.Event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "separator" or region == "heading" or region != "cell":
            return None
        if self.tree.identify_column(event.x) != "#1":
            return None
        row = self.tree.identify_row(event.y)
        if not row:
            return None
        if self._toggleable(row):
            self.set_checked(row, not self.checked.get(row, False))
        return "break"

    def on_space(self, _event: tk.Event) -> str:
        for iid in self.tree.selection():
            if self._toggleable(iid):
                self.set_checked(iid, not self.checked.get(iid, False))
        return "break"

    def select_all_keyboard(self) -> str:
        self.toggle_all()
        return "break"

    def set_checked(self, iid: str, value: bool) -> None:
        self.checked[iid] = value
        self.tree.set(iid, "sel", CHECKED if value else UNCHECKED)
        self.refresh_convert_button()

    def toggle_all(self) -> None:
        rows = [i for i in self.tree.get_children("")
                if self.reports[i].action is Action.CONVERT]
        if not rows:
            return
        new_value = not all(self.checked.get(i, False) for i in rows)
        for iid in rows:
            self.checked[iid] = new_value
            self.tree.set(iid, "sel", CHECKED if new_value else UNCHECKED)
        self.tree.heading("sel", text=CHECKED if new_value else UNCHECKED)
        self.refresh_convert_button()

    def refresh_convert_button(self) -> None:
        n = sum(1 for i in self.tree.get_children("") if self.checked.get(i))
        self.convert_btn.configure(text=f"Convert {n} selected",
                                   state="normal" if n else "disabled")

    # ------------------------------------------------------------- preview
    def on_tree_select(self, _event: tk.Event | None = None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        report = self.reports.get(sel[0])
        if report is None:
            return
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")

        content = []
        if report.lossy:
            changes_desc = ", ".join(
                f"{c.char!r}->{c.replacement!r} ({c.count}x)" if not c.dropped else f"{c.char!r} dropped ({c.count}x)"
                for c in report.lossy[:5]
            )
            content.append(f"--- Character Folding Details ({len(report.lossy)} types): {changes_desc} ---\n")

        if report.time_offset_ms != 0:
            content.append(f"--- Timing Shift Applied: {report.time_offset_ms / 1000.0:+.2f} seconds ---\n")

        content.extend(report.preview)
        self.preview.insert("1.0", "\n".join(content))
        self.preview.configure(state="disabled")
        self.preview.yview_moveto(0.0)

    # ------------------------------------------------------------- workers
    def _set_busy(self, busy: bool) -> None:
        self.scan_btn.configure(state="disabled" if busy else "normal")
        self.cancel_btn.configure(state="normal" if busy else "disabled")
        if busy:
            self.convert_btn.configure(state="disabled")
        else:
            self.refresh_convert_button()

    def _get_time_offset_ms(self) -> int:
        try:
            val = float(self.offset_var.get().strip())
            return int(round(val * 1000))
        except ValueError:
            return 0

    def start_scan(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        folder = self.folder_var.get().strip()
        if not os.path.isdir(folder):
            messagebox.showerror(APP_NAME, "Pick an existing folder first.", parent=self.root)
            return
        self._add_recent_folder(folder)
        self.tree.delete(*self.tree.get_children(""))
        self.checked.clear()
        self.reports.clear()
        self.cancel.clear()
        self._set_busy(True)
        self.status.configure(text="Scanning\u2026")
        time_offset_ms = self._get_time_offset_ms()
        self._spawn(self._scan_worker,
                    (folder, self.recurse_var.get(), Target(self.target_var.get()), time_offset_ms))

    def start_convert(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        chosen = [(i, self.reports[i]) for i in self.tree.get_children("")
                  if self.checked.get(i)]
        if not chosen:
            return
        risky = sum(1 for _, r in chosen if r.action is Action.NEEDS_REVIEW)
        extra = f"\n\n{risky} file(s) are flagged NEEDS REVIEW." if risky else ""
        if not messagebox.askyesno(
                APP_NAME,
                f"Overwrite {len(chosen)} file(s) in place?\n\n"
                f"Backups: {'ON' if self.backup_var.get() else 'OFF'}{extra}",
                parent=self.root):
            return
        self._row_by_path = {r.path: i for i, r in chosen}
        self.cancel.clear()
        self._set_busy(True)
        self._spawn(self._convert_worker,
                    ([r for _, r in chosen], self.backup_var.get()))

    def _spawn(self, fn, args: tuple) -> None:
        def runner() -> None:
            try:
                fn(*args)
            except Exception as exc:
                self.queue.put(("error", repr(exc)))
            finally:
                self.queue.put(("finished", None))
        self.worker = threading.Thread(target=runner, daemon=True, name="srt-worker")
        self.worker.start()
        self._schedule_pump()

    def _schedule_pump(self) -> None:
        self._after_id = self.root.after(50, self._pump)

    def _pump(self) -> None:
        """Runs on the Tk main thread. The ONLY place widgets get touched."""
        self._after_id = None
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                self._handle(kind, payload)
        except queue.Empty:
            pass
        if (self.worker is not None and self.worker.is_alive()) or not self.queue.empty():
            self._schedule_pump()

    def _handle(self, kind: str, payload) -> None:
        if kind == "progress":
            done, total, name = payload
            self.progress.configure(maximum=max(total, 1), value=done)
            self.status.configure(text=f"{done}/{total}  {name}")
        elif kind == "row":
            self._insert_row(payload)
        elif kind == "result":
            self._apply_result(payload)
        elif kind == "done":
            self.status.configure(text=payload)
        elif kind == "error":
            self.status.configure(text="Error")
            messagebox.showerror(APP_NAME, str(payload), parent=self.root)
        elif kind == "finished":
            self.worker = None
            self._set_busy(False)

    def _insert_row(self, report: FileReport) -> None:
        n = len(self.tree.get_children(""))
        tags: list[str] = ["stripe"] if n % 2 else []
        status, extra, ticked = row_text(report)
        tags.extend(extra)
        enc = (f"{report.encoding} ({report.confidence.value})"
               if report.encoding else "-")
        iid = self.tree.insert("", "end",
                               values=(CHECKED if ticked else UNCHECKED,
                                       report.path.name, enc, status),
                               tags=tuple(tags))
        self.checked[iid] = ticked
        self.reports[iid] = report
        self.refresh_convert_button()

    def _apply_result(self, result) -> None:
        iid = getattr(self, "_row_by_path", {}).get(result.path)
        if iid is None:
            return
        if result.ok and result.status == "converted":
            text = f"converted (backup: {result.backup})"
        elif result.ok:
            text = "unchanged"
        else:
            text = f"FAILED [{result.code}] {result.error}"
        self.tree.set(iid, "status", text)
        self.tree.set(iid, "sel", UNCHECKED)
        self.checked[iid] = False
        self.refresh_convert_button()

    # ------------------------------------------------------------- core calls
    def _scan_worker(self, folder: str, recurse: bool, target: Target, time_offset_ms: int) -> None:
        def on_progress(p) -> None:
            self.queue.put(("progress", (p.done, p.total, p.path.name)))
            self.queue.put(("row", p.report))
        reports = scan(folder, recursive=recurse, target=target, time_offset_ms=time_offset_ms,
                       on_progress=on_progress, cancel=self.cancel)
        leftovers = count_temp_files(Path(folder), recursive=recurse)
        note = f"; {leftovers} leftover temp file(s) from an interrupted run" if leftovers else ""
        verb = "Cancelled after" if self.cancel.is_set() else "Scanned"
        self.queue.put(("done", f"{verb} {len(reports)} file(s){note}"))

    def _convert_worker(self, reports: list[FileReport], backup: bool) -> None:
        def on_progress(p) -> None:
            self.queue.put(("progress", (p.done, p.total, p.path.name)))
            self.queue.put(("result", p.result))
        results = convert(reports, backup=backup,
                          on_progress=on_progress, cancel=self.cancel)
        ok = sum(1 for r in results if r.ok)
        bad = len(results) - ok
        self.queue.put(("done", f"Converted {ok} file(s), {bad} failed"))

    # ------------------------------------------------------------- shutdown
    def on_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askokcancel(
                    APP_NAME, "A job is still running. Stop it and quit?", parent=self.root):
                return
        self.cancel.set()                                  # 1. tell worker to stop
        if self._after_id is not None:                     # 2. kill pending after()
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if self.worker is not None:                        # 3. wait for it
            self.worker.join(timeout=5.0)
        self.settings.update(last_folder=self.folder_var.get().strip(),
                             recent_folders=self.recent_folders,
                             recurse=self.recurse_var.get(),
                             target=self.target_var.get(),
                             backup=self.backup_var.get(),
                             dark_mode=self.dark_var.get())
        save_settings(self.settings)
        self.root.destroy()                                # 4. only now destroy


def main() -> None:
    enable_dpi_awareness()          # BEFORE Tk()
    root = tk.Tk()
    root.title(APP_NAME)
    root.minsize(800, 580)

    def report_exception(exc, val, tb):
        import traceback
        messagebox.showerror(APP_NAME,
                             "".join(traceback.format_exception(exc, val, tb))[-1500:])
    root.report_callback_exception = report_exception

    initial_folder = sys.argv[1] if len(sys.argv) > 1 else ""
    ConverterApp(root, initial_folder=initial_folder)
    root.mainloop()


if __name__ == "__main__":
    main()
