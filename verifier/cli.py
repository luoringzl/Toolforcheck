from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run


def main():
    p = argparse.ArgumentParser(description="完全离线的人事材料批量核验工具")
    p.add_argument("input", type=Path, help="人员总文件夹")
    p.add_argument("--output", type=Path, default=Path("核验报告.xlsx"))
    p.add_argument("--company-registry", default=None, help="本地工商企业全称名录 CSV/XLSX")
    args = p.parse_args()
    run(args.input, args.output, args.company_registry, progress=print)


if __name__ == "__main__":
    main()

