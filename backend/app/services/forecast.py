"""功率预测业务规则：状态流转、字段校验、筛选口径与导出口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "forecast"
REQUIRED_FIELDS = ["预测单号", "所属场站", "预测日期"]
LIST_FIELDS = ["预测单号", "所属场站", "预测日期", "预测出力", "实际出力", "预测偏差", "考核电量", "预测状态"]
STATUS_ORDER = ["待生成", "已生成", "偏差超标", "已复核"]
ACTION_RULES = {"生成预测": "已生成", "登记偏差超标": "偏差超标", "复核预测": "已复核"}
NEGATIVE_ACTIONS = []
REVIEWED_STATUS = STATUS_ORDER[-1]


class ForecastService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        station: str | None = None,
        forecast_date: str | None = None,
        status: str | None = None,
        pending_only: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """按预测单号、所属场站、预测日期等条件取数。

        列表与导出共用这套口径，保证导出的就是当前条件下的同一批数据；
        同一预测单号只保留一条；pending_only 时已复核记录不进入待处理范围。
        """
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("预测单号", ""))]
        if station:
            rows = [row for row in rows if station in str(row.get("所属场站", ""))]
        if forecast_date:
            rows = [row for row in rows if forecast_date in str(row.get("预测日期", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if pending_only:
            rows = [row for row in rows if row.get("status") != REVIEWED_STATUS]
        rows = self._dedupe(rows)
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = [self._present(row) for row in rows[start:start + size]]
        return page_rows, total

    @staticmethod
    def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """同一预测单号只保留最早出现的一条，且不改动仓库里的原始记录。"""
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for row in rows:
            key = str(row.get("预测单号") or "")
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        return unique

    @staticmethod
    def _present(row: dict[str, Any]) -> dict[str, Any]:
        """投影成列表列：列齐全（缺字段补 None），预测状态取真实流转状态。"""
        item: dict[str, Any] = {"id": row.get("id")}
        for field in LIST_FIELDS:
            item[field] = row.get(field)
        item["预测状态"] = row.get("status")
        return item

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"功率预测单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于功率预测可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"功率预测单已{action}"
