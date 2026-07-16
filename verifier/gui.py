from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .pipeline import run
from .config import AppConfig


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("核验工具")
        self.geometry("820x560")
        self.minsize(720, 480)
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(Path.cwd() / "核验报告.xlsx"))
        self.registry_var = tk.StringVar()
        self.audit_mode_var = tk.StringVar(value="预审")
        self._build()

    def _row(self, parent, label, var, command, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=8)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=10)
        ttk.Button(parent, text="选择", command=command).grid(row=row, column=2)

    def _build(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="核验工具 · 完全离线 · 文件不会上传", font=("Microsoft YaHei UI", 16, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 15))
        self._row(frame, "人员总文件夹（内含姓名文件夹）", self.input_var, self._input, 1)
        self._row(frame, "Excel输出位置", self.output_var, self._output, 2)
        self._row(frame, "企业全称名录（可选）", self.registry_var, self._registry, 3)
        ttk.Label(frame, text="审核模式").grid(row=4, column=0, sticky="w", pady=8)
        ttk.Combobox(frame, textvariable=self.audit_mode_var, values=("预审", "正式审核"), state="readonly").grid(row=4, column=1, sticky="ew", padx=10)
        note = "身份证照片模糊、严重反光或严重旋转时直接退回；企业简称直接退回。未提供企业名录时，形式完整的名称仍需人工确认。"
        ttk.Label(frame, text=note, wraplength=740, foreground="#7A3E00").grid(row=5, column=0, columnspan=3, sticky="w", pady=10)
        self.start = ttk.Button(frame, text="开始批量核验", command=self._start)
        self.start.grid(row=6, column=0, columnspan=3, sticky="ew", pady=10)
        self.log = tk.Text(frame, height=16, state="disabled", wrap="word")
        self.log.grid(row=7, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(7, weight=1)

    def _input(self):
        if p := filedialog.askdirectory(): self.input_var.set(p)
    def _output(self):
        if p := filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")]): self.output_var.set(p)
    def _registry(self):
        if p := filedialog.askopenfilename(filetypes=[("企业名录", "*.xlsx *.csv")]): self.registry_var.set(p)
    def _append(self, text):
        self.after(0, lambda: self._append_ui(text))
    def _append_ui(self, text):
        self.log.configure(state="normal"); self.log.insert("end", text + "\n"); self.log.see("end"); self.log.configure(state="disabled")
    def _start(self):
        if not self.input_var.get() or not Path(self.input_var.get()).is_dir():
            messagebox.showerror("错误", "请选择有效的人员总文件夹"); return
        self.start.configure(state="disabled")
        threading.Thread(target=self._worker, daemon=True).start()
    def _worker(self):
        try:
            cfg = AppConfig(audit_mode=self.audit_mode_var.get())
            run(Path(self.input_var.get()), Path(self.output_var.get()), self.registry_var.get() or None, cfg=cfg, progress=self._append)
            self.after(0, lambda: messagebox.showinfo("完成", "批量核验完成，Excel报告已生成"))
        except Exception as e:
            self._append(f"错误：{e}")
            self.after(0, lambda: messagebox.showerror("处理失败", str(e)))
        finally:
            self.after(0, lambda: self.start.configure(state="normal"))


def main():
    App().mainloop()
