"""Validation wrapper around a snapshot of the official input tables."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .object_dictionary import normalize_dataset_types
from .schema import REQUIRED_TABLES, TABLE_SCHEMAS, value_errors


@dataclass(frozen=True)
class OfficialDataset:
    tables: Mapping[str, Sequence[Mapping[str, Any]]]

    def missing_tables(self) -> tuple[str, ...]:
        return tuple(name for name in REQUIRED_TABLES if name not in self.tables)

    def field_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        for table_name, rows in self.tables.items():
            schema = TABLE_SCHEMAS.get(table_name)
            if schema is None or not rows:
                continue
            fields = set(rows[0])
            missing = set(schema.required_fields) - fields
            if missing:
                errors.append(f"{table_name}: missing {', '.join(sorted(missing))}")
        return tuple(errors)

    def validate(self) -> None:
        errors = [f"missing table: {name}" for name in self.missing_tables()]
        errors.extend(self.field_errors())
        if errors:
            raise ValueError("; ".join(errors))

    def normalized(self) -> "OfficialDataset":
        """返回预处理后的数据集。

        预处理步骤（按答疑要求）：
        1. EQUIP_TYPE 按 JBS_ZD_OBJECT 归一（D8）
        2. Bug#42: JBS_PWREAL 按 TRAN_ID+DATA_DATE 去重（Q8）
        3. Bug#42: EQUIP_TYPE=1312 修正为 1321（Q7）
        4. 官方 0821 数据库更新脚本（数据库更新脚本20260821.txt）行级变更，
           确定性且幂等应用（原始数据集文件保持不动）：
           - DELETE JBS_PWTERMINAL WHERE ID IN ('TMP00062787','TMP00063385')
           - UPDATE JBS_ZWTERMINAL SET CONNECTIVITYNODE_ID='109000054006023'
             WHERE EQUIP_ID='TMP00048726'
           （该脚本的另两条——ZWEQUIPINFO 1312→1321、PWREAL 按
           TRAN_ID+DATA_DATE 去重——已由步骤 2/3 等价覆盖：本数据集
           PWEQUIPINFO 无 1312 行；keep-first 与官方 MIN(ROWID) 同序。）
        """
        tables = normalize_dataset_types(self.tables)
        # Bug#42: PWREAL 去重
        pwreal = tables.get("JBS_PWREAL", [])
        if pwreal:
            seen = set()
            deduped = []
            for r in pwreal:
                key = (str(r.get("TRAN_ID", "")), str(r.get("DATA_DATE", "")))
                if key not in seen:
                    seen.add(key)
                    deduped.append(r)
            tables["JBS_PWREAL"] = deduped
        # Bug#42: 1312→1321 修正
        for tbl in ("JBS_PWEQUIPINFO", "JBS_ZWEQUIPINFO"):
            rows = tables.get(tbl, [])
            if rows:
                fixed = []
                for r in rows:
                    if str(r.get("EQUIP_TYPE", "")) == "1312":
                        r = dict(r)
                        r["EQUIP_TYPE"] = "1321"
                    fixed.append(r)
                tables[tbl] = fixed
        # 官方 0821 更新脚本: DELETE JBS_PWTERMINAL WHERE ID IN (...)
        _pwterm = tables.get("JBS_PWTERMINAL")
        if _pwterm:
            tables["JBS_PWTERMINAL"] = [
                r for r in _pwterm
                if str(r.get("ID")) not in ("TMP00062787", "TMP00063385")
            ]
        # 官方 0821 更新脚本: UPDATE JBS_ZWTERMINAL SET CONNECTIVITYNODE_ID
        _zwterm = tables.get("JBS_ZWTERMINAL")
        if _zwterm:
            fixed = []
            for r in _zwterm:
                if (str(r.get("EQUIP_ID")) == "TMP00048726"
                        and str(r.get("CONNECTIVITYNODE_ID")) != "109000054006023"):
                    r = dict(r)
                    r["CONNECTIVITYNODE_ID"] = "109000054006023"
                fixed.append(r)
            tables["JBS_ZWTERMINAL"] = fixed
        return OfficialDataset(tables)
