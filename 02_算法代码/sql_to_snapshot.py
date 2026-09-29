"""数据接入适配器: 将比赛原始数据转换为标准 JSON snapshot。

支持输入格式:
    1. SQL 文件 (含 INSERT INTO 语句)
    2. CSV 文件目录 (每张表一个 .csv)
    3. Excel 文件 (.xlsx, 每个 Sheet 一张表)

输出:
    标准 14 表 JSON snapshot, 可被 data_loader.snapshot.load_json_snapshot() 直接消费。

表名别名映射 (自动处理):
    JBS_VOLTAGETYPE → JBS_ZD_VOLTAGETYPE  (date.sql 中的命名 vs 系统内部命名)

用法:
    # 从单个 SQL 文件导入 (含 INSERT, 或仅 DDL 自动合成演示数据)
    py -3 sql_to_snapshot.py --sql D:/secure_data/dianli/raw_data.sql -o snapshot.json

    # 从 SQL 目录导入 (官方数据集: 每张表一个 .sql, 自动合并去重)
    py -3 sql_to_snapshot.py --sql-dir D:/secure_data/dianli/sql/ -o snapshot.json

    # 从 CSV 目录导入
    py -3 sql_to_snapshot.py --csv-dir D:/secure_data/dianli/csv_export/ -o snapshot.json

    # 从 Excel 导入
    py -3 sql_to_snapshot.py --xlsx D:/secure_data/dianli/data.xlsx -o snapshot.json

    # 验证已有 snapshot
    py -3 sql_to_snapshot.py --validate data/snapshot.json

数据隔离:
    本脚本应在 DIANLI_DATA_ROOT 下操作, 输出也落在数据根。
    项目代码目录内不应出现真实比赛数据。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 表名别名映射: 赛方 SQL 命名 → 系统内部命名
# ---------------------------------------------------------------------------
TABLE_ALIASES: dict[str, str] = {
    "JBS_VOLTAGETYPE": "JBS_ZD_VOLTAGETYPE",
}

# 官方 14 表清单 (系统内部命名)
EXPECTED_TABLES = [
    "JBS_ZWSUBSTATION", "JBS_ZWEQUIPINFO", "JBS_ZWLINEEND",
    "JBS_ZWTERMINAL", "JBS_ZWMEA", "JBS_ZWSIGNAL",
    "JBS_PWFEEDERLINE", "JBS_PWROOM", "JBS_PWEQUIPINFO",
    "JBS_PWTERMINAL", "JBS_PWREAL",
    "JBS_ZD_OBJECT", "JBS_ZD_VOLTAGETYPE", "JBS_ZD_MEASTYPE",
]


def normalize_table_name(raw_name: str) -> str:
    """将原始表名归一化为系统内部命名。"""
    clean = raw_name.strip().strip('"').strip("'").upper()
    # 去掉 schema 前缀 (如 "EQUIP"."JBS_PWEQUIPINFO" → JBS_PWEQUIPINFO)
    if "." in clean:
        clean = clean.rsplit(".", 1)[-1].strip('"').strip("'")
    return TABLE_ALIASES.get(clean, clean)


# ---------------------------------------------------------------------------
# SQL 解析器
# ---------------------------------------------------------------------------
def _read_sql_text(sql_path: Path) -> str:
    """读取 SQL 文件, 自动检测编码 (比赛 date.sql 多为 GBK/达梦导出)。"""
    raw = sql_path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def parse_sql_file(sql_path: Path) -> dict[str, list[dict[str, Any]]]:
    """解析 SQL 文件中的 INSERT 语句, 返回 {表名: [行字典]}。

    统一走 data_loader.sql_importer.import_sql 解析（兼容多行 VALUES、
    缺失列名、GBK/UTF-8 编码探测）；若文件仅含 DDL（官方 date.sql 为
    CREATE TABLE + COMMENT, 无 INSERT）, 自动回退到 schema 合成模式
    生成最小样本数据。
    """
    from data_loader.sql_importer import import_sql

    content = _read_sql_text(sql_path)
    try:
        tables = import_sql(sql_path)
    except Exception as e:
        print(f"[WARN] SQL 解析失败: {e}", file=sys.stderr)
        return {}
    if "insert" not in content.lower():
        print("[INFO] SQL 无 INSERT 语句, 启用 schema 合成模式 (演示数据)", file=sys.stderr)
    return tables


# ---------------------------------------------------------------------------
# CSV 解析器
# ---------------------------------------------------------------------------
def parse_csv_dir(csv_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """解析 CSV 目录, 每个 .csv 文件名即表名。"""
    tables: dict[str, list[dict[str, Any]]] = {}
    for csv_file in sorted(csv_dir.glob("*.csv")):
        table_name = normalize_table_name(csv_file.stem)
        rows = []
        with open(csv_file, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
        if rows:
            tables[table_name] = rows
    return tables


# ---------------------------------------------------------------------------
# Excel 解析器
# ---------------------------------------------------------------------------
def parse_xlsx(xlsx_path: Path) -> dict[str, list[dict[str, Any]]]:
    """解析 Excel 文件, 每个 Sheet 名即表名。"""
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("[错误] 需要 openpyxl 库: pip install openpyxl", file=sys.stderr)
        sys.exit(1)

    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    tables: dict[str, list[dict[str, Any]]] = {}
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        table_name = normalize_table_name(sheet_name)
        rows_iter = ws.iter_rows(values_only=True)
        try:
            headers = [str(h).strip() if h else f"COL_{i}" for i, h in enumerate(next(rows_iter))]
        except StopIteration:
            continue
        rows = []
        for row_values in rows_iter:
            row = {h: v for h, v in zip(headers, row_values) if v is not None}
            if row:
                rows.append(row)
        if rows:
            tables[table_name] = rows
    wb.close()
    return tables


# ---------------------------------------------------------------------------
# 验证与输出
# ---------------------------------------------------------------------------
def validate_snapshot(tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    """验证 snapshot 完整性, 返回问题列表。"""
    issues = []
    for expected in EXPECTED_TABLES:
        if expected not in tables:
            issues.append(f"缺少表: {expected}")
        elif not tables[expected]:
            issues.append(f"表为空: {expected}")
    # 检查关键字段
    if "JBS_PWEQUIPINFO" in tables and tables["JBS_PWEQUIPINFO"]:
        first = tables["JBS_PWEQUIPINFO"][0]
        for field in ("EQUIP_ID", "EQUIP_TYPE", "FEEDER_ID"):
            if field not in first:
                issues.append(f"JBS_PWEQUIPINFO 缺少关键字段: {field}")
    return issues


def write_snapshot(tables: dict[str, list[dict[str, Any]]], output_path: Path) -> None:
    """写出标准 JSON snapshot。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"tables": tables}
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="比赛数据接入适配器: SQL/CSV/Excel → 标准 JSON snapshot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sql", type=Path, help="SQL 文件路径 (含 INSERT 语句)")
    group.add_argument("--sql-dir", type=Path, help="SQL 文件目录 (每表一个 .sql, 自动合并)")
    group.add_argument("--csv-dir", type=Path, help="CSV 文件目录 (每表一个 .csv)")
    group.add_argument("--xlsx", type=Path, help="Excel 文件 (每 Sheet 一张表)")
    group.add_argument("--validate", type=Path, help="验证已有 snapshot.json")

    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="输出 snapshot.json 路径 (默认: 当前目录/snapshot.json)")
    args = parser.parse_args()

    # 验证模式
    if args.validate:
        data = json.loads(args.validate.read_text(encoding="utf-8-sig"))
        tables = data.get("tables", data)
        issues = validate_snapshot(tables)
        if issues:
            print(f"[WARN] 发现 {len(issues)} 个问题:")
            for i in issues:
                print(f"  - {i}")
            sys.exit(1)
        else:
            total_rows = sum(len(v) for v in tables.values())
            print(f"[OK] snapshot 验证通过: {len(tables)} 表, {total_rows} 行")
            for name in EXPECTED_TABLES:
                count = len(tables.get(name, []))
                print(f"  {name}: {count} 行")
            sys.exit(0)

    # 导入模式
    if args.sql:
        if not args.sql.exists():
            print(f"[错误] SQL 文件不存在: {args.sql}", file=sys.stderr)
            sys.exit(1)
        print(f"[1/3] 解析 SQL: {args.sql}")
        tables = parse_sql_file(args.sql)
    elif args.sql_dir:
        if not args.sql_dir.is_dir():
            print(f"[错误] SQL 目录不存在: {args.sql_dir}", file=sys.stderr)
            sys.exit(1)
        sql_files = sorted(args.sql_dir.glob("*.sql"))
        if not sql_files:
            print(f"[错误] SQL 目录下没有 .sql 文件: {args.sql_dir}", file=sys.stderr)
            sys.exit(1)
        print(f"[1/3] 解析 SQL 目录: {args.sql_dir} ({len(sql_files)} 个文件)")
        try:
            from data_loader.sql_importer import import_sql_files
            tables = import_sql_files(sql_files)
        except Exception as e:
            print(f"[错误] SQL 目录批量解析失败: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.csv_dir:
        if not args.csv_dir.is_dir():
            print(f"[错误] CSV 目录不存在: {args.csv_dir}", file=sys.stderr)
            sys.exit(1)
        print(f"[1/3] 解析 CSV 目录: {args.csv_dir}")
        tables = parse_csv_dir(args.csv_dir)
    elif args.xlsx:
        if not args.xlsx.exists():
            print(f"[错误] Excel 文件不存在: {args.xlsx}", file=sys.stderr)
            sys.exit(1)
        print(f"[1/3] 解析 Excel: {args.xlsx}")
        tables = parse_xlsx(args.xlsx)
    else:
        parser.print_help()
        sys.exit(1)

    # 验证
    print(f"[2/3] 验证 ({len(tables)} 表)...")
    issues = validate_snapshot(tables)
    if issues:
        print(f"  [WARN] {len(issues)} 个问题 (非致命, 继续输出):")
        for i in issues:
            print(f"    - {i}")
    else:
        print("  [OK] 14 表完整")

    # 输出
    output = args.output or Path("snapshot.json")
    print(f"[3/3] 写出: {output}")
    write_snapshot(tables, output)
    total_rows = sum(len(v) for v in tables.values())
    print(f"  完成: {len(tables)} 表, {total_rows} 行 → {output.resolve()}")


if __name__ == "__main__":
    main()
