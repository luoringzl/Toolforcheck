from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run


def main():
    p = argparse.ArgumentParser(description="核验工具：完全离线的人事材料批量核验")
    p.add_argument("input", type=Path, help="人员总文件夹")
    p.add_argument("--output", type=Path, default=Path("核验报告.xlsx"))
    args = p.parse_args()
    run(args.input, args.output, progress=print)


if __name__ == "__main__":
    main()
