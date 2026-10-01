"""功率预测业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "forecast"
REQUIRED_FIELDS = ["预测单号", "所属场站", "预测日期"]
STATUS_ORDER = ["待生成", "已生成", "偏差超标", "已复核"]
ACTION_RULES = {"生成预测": "已生成", "登记偏差超标": "偏差超标", "复核预测": "已复核"}
NEGATIVE_ACTIONS = []

# 列表与导出共用一套列口径，保证导出文件列与页面一致（考核电量不能缺）。
LIST_FIELDS = ["预测单号", "所属场站", "预测日期", "预测出力", "实际出力", "预测偏差", "考核电量", "预测状态"]
NUMBER_FIELD = "预测单号"
STATION_FIELD = "所属场站"
DATE_FIELD = "预测日期"
REVIEWED_STATUS = STATUS_ORDER[-1]


class ForecastService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        station: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._query_rows(
            keyword=keyword,
            status=status,
            station=station,
            start_date=start_date,
            end_date=end_date,
        )
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def export_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        station: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """按列表当前条件导出待处理预测单。

        - 与列表同一套取数口径（预测单号、场站、预测日期范围、状态）；
        - 已复核的记录不再进入待处理导出范围；
        - 同一预测单号只保留第一条；
        - 每条都按列表列补齐字段（含考核电量），缺值留空；
        - 只读，不改动仓库里的任何记录。
        """
        rows = self._query_rows(
            keyword=keyword,
            status=status,
            station=station,
            start_date=start_date,
            end_date=end_date,
        )
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            if row.get("status") == REVIEWED_STATUS:
                continue
            number = str(row.get(NUMBER_FIELD) or "").strip()
            # 预测单号理论上必填；没有单号时用 id 兜底，避免空号互相吞并。
            key = number or f"__id__{row.get('id', id(row))}"
            if key in seen:
                continue
            seen.add(key)
            items.append({field: self._cell(row.get(field)) for field in LIST_FIELDS})
        return items

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

    def _query_rows(
        self,
        *,
        keyword: str | None,
        status: str | None,
        station: str | None,
        start_date: str | None,
        end_date: str | None,
    ) -> list[dict[str, Any]]:
        """列表与导出共用的筛选口径：单号关键字 + 状态 + 场站 + 预测日期闭区间。"""
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get(NUMBER_FIELD, ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if station:
            rows = [row for row in rows if station in str(row.get(STATION_FIELD, ""))]
        # 预测日期统一为 YYYY-MM-DD，字符串比较即日期比较。
        if start_date:
            rows = [row for row in rows if str(row.get(DATE_FIELD, "")) >= start_date]
        if end_date:
            rows = [row for row in rows if str(row.get(DATE_FIELD, "")) <= end_date]
        return rows

    @staticmethod
    def _cell(value: Any) -> Any:
        return "" if value is None else value
