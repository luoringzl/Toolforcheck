from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import AppConfig, ReviewPreset
from .pipeline import run


BG = "#F3F6FA"
CARD = "#FFFFFF"
NAVY = "#173B63"
BLUE = "#1677FF"
TEXT = "#1F2D3D"
MUTED = "#64748B"
BORDER = "#DCE5EF"
PALE_BLUE = "#EAF3FF"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("核验工具")
        self.geometry("1000x790")
        self.minsize(900, 700)
        self.configure(background=BG)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(Path.cwd() / "核验报告.xlsx"))
        self.audit_mode_var = tk.StringVar(value="预审")
        self.student_var = tk.BooleanVar(value=False)
        self.graduated_var = tk.BooleanVar(value=False)
        self.working_var = tk.BooleanVar(value=False)
        self.education_var = tk.StringVar(value="自动判断")
        self.work_history_var = tk.StringVar(value="自动判断")
        self.status_var = tk.StringVar(value="准备就绪")
        self.material_vars = {
            name: tk.BooleanVar(value=False)
            for name in (
                "工作证明",
                "工作年限承诺书",
                "学信网材料",
                "企业信息截图",
                "职业技能等级认定承诺书",
                "其他材料",
            )
        }
        self._configure_style()
        self._build()

    def _configure_style(self) -> None:
        self.option_add("*Font", ("Microsoft YaHei UI", 10))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("App.TFrame", background=BG)
        style.configure("Header.TFrame", background=NAVY)
        style.configure("HeaderTitle.TLabel", background=NAVY, foreground="white", font=("Microsoft YaHei UI", 20, "bold"))
        style.configure("HeaderSub.TLabel", background=NAVY, foreground="#D8E8FA", font=("Microsoft YaHei UI", 10))
        style.configure("Card.TFrame", background=CARD, relief="flat")
        style.configure("CardTitle.TLabel", background=CARD, foreground=TEXT, font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("CardText.TLabel", background=CARD, foreground=TEXT)
        style.configure("Hint.TLabel", background=PALE_BLUE, foreground="#285A8A", padding=(12, 8))
        style.configure("Status.TLabel", background=BG, foreground=MUTED)
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 11, "bold"), foreground="white", background=BLUE, padding=(18, 10))
        style.map("Primary.TButton", background=[("active", "#0F63D8"), ("disabled", "#9EBCE0")])
        style.configure("Secondary.TButton", foreground=NAVY, background="#E8EEF5", padding=(12, 7))
        style.map("Secondary.TButton", background=[("active", "#D7E3EF")])
        style.configure("TEntry", padding=7, fieldbackground="white")
        style.configure("TCombobox", padding=6, fieldbackground="white")
        style.configure("TProgressbar", background=BLUE, troughcolor="#DCE7F3", bordercolor="#DCE7F3")

    def _card(self, parent: tk.Widget) -> ttk.Frame:
        outer = tk.Frame(parent, background=BORDER, padx=1, pady=1)
        inner = ttk.Frame(outer, style="Card.TFrame", padding=16)
        inner.pack(fill="both", expand=True)
        return outer, inner

    def _file_row(self, parent: ttk.Frame, label: str, var: tk.StringVar, command, row: int) -> None:
        ttk.Label(parent, text=label, style="CardText.TLabel").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=(14, 10), pady=6)
        ttk.Button(parent, text="选择", command=command, style="Secondary.TButton").grid(row=row, column=2, pady=6)

    def _check(self, parent: tk.Widget, text: str, variable: tk.BooleanVar, row: int, column: int) -> tk.Checkbutton:
        check = tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            background=CARD,
            activebackground=CARD,
            foreground=TEXT,
            selectcolor="white",
            highlightthickness=0,
            bd=0,
            anchor="w",
            padx=0,
            pady=3,
        )
        check.grid(row=row, column=column, sticky="w", padx=(0, 22))
        return check

    def _build(self) -> None:
        header = ttk.Frame(self, style="Header.TFrame", padding=(28, 18))
        header.pack(fill="x")
        ttk.Label(header, text="核验工具", style="HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(header, text="完全离线运行 · 批量核验人员材料 · 文件不会上传", style="HeaderSub.TLabel").pack(anchor="w", pady=(3, 0))

        main = ttk.Frame(self, style="App.TFrame", padding=(24, 18, 24, 20))
        main.pack(fill="both", expand=True)

        file_outer, file_card = self._card(main)
        file_outer.pack(fill="x")
        file_card.columnconfigure(1, weight=1)
        ttk.Label(file_card, text="1  文件与审核设置", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self._file_row(file_card, "人员总文件夹", self.input_var, self._input, 1)
        self._file_row(file_card, "Excel 输出位置", self.output_var, self._output, 2)
        ttk.Label(file_card, text="审核模式", style="CardText.TLabel").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Combobox(file_card, textvariable=self.audit_mode_var, values=("预审", "正式审核"), state="readonly", width=22).grid(row=3, column=1, sticky="w", padx=(14, 10), pady=6)

        preset_outer, preset_card = self._card(main)
        preset_outer.pack(fill="x", pady=(14, 0))
        preset_card.columnconfigure(0, weight=1)
        preset_card.columnconfigure(1, weight=1)
        ttk.Label(preset_card, text="2  批次辅助判断（可选）", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            preset_card,
            text="以下设置应用于本次批次全部人员。勾选或选择后作为人工预设；保持默认则全部由工具根据材料自动判断。",
            style="Hint.TLabel",
            wraplength=880,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 12))

        person = tk.Frame(preset_card, background=CARD)
        person.grid(row=2, column=0, sticky="nsew", padx=(0, 24))
        material = tk.Frame(preset_card, background=CARD)
        material.grid(row=2, column=1, sticky="nsew")

        tk.Label(person, text="人员情况", bg=CARD, fg=NAVY, font=("Microsoft YaHei UI", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self._check(person, "高校在校生", self.student_var, 1, 0)
        self._check(person, "已毕业", self.graduated_var, 1, 1)
        self._check(person, "已工作", self.working_var, 1, 2)
        tk.Label(person, text="最高学历", bg=CARD, fg=TEXT).grid(row=2, column=0, sticky="w", pady=(9, 4))
        ttk.Combobox(
            person,
            textvariable=self.education_var,
            values=("自动判断", "初中", "高中", "中职", "高职", "本科", "研究生"),
            state="readonly",
            width=18,
        ).grid(row=3, column=0, sticky="w", padx=(0, 16))
        tk.Label(person, text="工作经历", bg=CARD, fg=TEXT).grid(row=2, column=1, sticky="w", pady=(9, 4))
        ttk.Combobox(
            person,
            textvariable=self.work_history_var,
            values=("自动判断", "无", "1份", "2份及以上"),
            state="readonly",
            width=18,
        ).grid(row=3, column=1, columnspan=2, sticky="w")

        tk.Label(material, text="强制要求的条件材料", bg=CARD, fg=NAVY, font=("Microsoft YaHei UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        for index, (name, variable) in enumerate(self.material_vars.items()):
            self._check(material, name, variable, 1 + index // 2, index % 2)
        tk.Label(material, text="勾选＝必须提交；未勾选＝按人员情况自动判断", bg=CARD, fg=MUTED, font=("Microsoft YaHei UI", 9)).grid(row=4, column=0, columnspan=2, sticky="w", pady=(7, 0))

        action = ttk.Frame(main, style="App.TFrame")
        action.pack(fill="x", pady=(14, 10))
        self.start = ttk.Button(action, text="开始批量核验", command=self._start, style="Primary.TButton")
        self.start.pack(side="left")
        self.progress = ttk.Progressbar(action, mode="indeterminate", length=220)
        self.progress.pack(side="left", padx=16)
        ttk.Label(action, textvariable=self.status_var, style="Status.TLabel").pack(side="left")

        log_outer, log_card = self._card(main)
        log_outer.pack(fill="both", expand=True)
        ttk.Label(log_card, text="运行记录", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        self.log = tk.Text(
            log_card,
            height=8,
            state="disabled",
            wrap="word",
            background="#F8FAFC",
            foreground="#334155",
            insertbackground=TEXT,
            relief="flat",
            padx=12,
            pady=10,
            font=("Microsoft YaHei UI", 9),
        )
        self.log.pack(fill="both", expand=True)

    def _input(self) -> None:
        if path := filedialog.askdirectory():
            self.input_var.set(path)

    def _output(self) -> None:
        if path := filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel 工作簿", "*.xlsx")]):
            self.output_var.set(path)

    def _append(self, text: str) -> None:
        self.after(0, lambda: self._append_ui(text))

    def _append_ui(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.status_var.set(text)

    def _validate_presets(self) -> bool:
        if self.student_var.get() and self.graduated_var.get():
            messagebox.showerror("预设冲突", "“高校在校生”和“已毕业”不能同时选择。")
            return False
        if self.student_var.get() and self.education_var.get() in {"初中", "高中", "中职"}:
            messagebox.showerror("预设冲突", "高校在校生的最高学历层次应选择高职、本科或研究生，或保持自动判断。")
            return False
        if self.working_var.get() and self.work_history_var.get() == "无":
            messagebox.showerror("预设冲突", "已选择“已工作”，工作经历不能同时选择“无”。")
            return False
        if self.graduated_var.get() and self.work_history_var.get() == "无":
            messagebox.showerror("预设冲突", "按当前核验规则，已毕业人员必须填写至少一段工作经历。")
            return False
        return True

    def _review_preset(self) -> ReviewPreset:
        education = "" if self.education_var.get() == "自动判断" else self.education_var.get()
        work_history = "" if self.work_history_var.get() == "自动判断" else self.work_history_var.get()
        required = tuple(name for name, variable in self.material_vars.items() if variable.get())
        return ReviewPreset(
            is_college_student=self.student_var.get(),
            is_graduated=self.graduated_var.get(),
            is_working=self.working_var.get(),
            education_level=education,
            work_history=work_history,
            forced_required_materials=required,
        )

    def _start(self) -> None:
        if not self.input_var.get() or not Path(self.input_var.get()).is_dir():
            messagebox.showerror("错误", "请选择有效的人员总文件夹。")
            return
        if not self._validate_presets():
            return
        # Tk变量只在主线程读取，避免后台核验线程访问Tk解释器。
        self._run_input = Path(self.input_var.get())
        self._run_output = Path(self.output_var.get())
        self._run_cfg = AppConfig(
            audit_mode=self.audit_mode_var.get(),
            review_preset=self._review_preset(),
        )
        self.start.configure(state="disabled")
        self.status_var.set("正在准备核验……")
        self.progress.start(10)
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            run(self._run_input, self._run_output, cfg=self._run_cfg, progress=self._append)
            self.after(0, lambda: self.status_var.set("核验完成"))
            self.after(0, lambda: messagebox.showinfo("完成", "批量核验完成，Excel 报告已生成。"))
        except Exception as exc:
            self._append(f"错误：{exc}")
            self.after(0, lambda: messagebox.showerror("处理失败", str(exc)))
        finally:
            self.after(0, self.progress.stop)
            self.after(0, lambda: self.start.configure(state="normal"))


def main() -> None:
    App().mainloop()
