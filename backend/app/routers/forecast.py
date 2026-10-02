"""功率预测接口：维护功率预测单，覆盖生成预测、登记偏差超标、复核预测等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.forecast import ForecastService, LIST_FIELDS

router = APIRouter(prefix="/api/forecast", tags=["功率预测"])

service = ForecastService()

STATUSES = ["待生成", "已生成", "偏差超标", "已复核"]
EXPORT_SIZE = 10000


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按预测单号检索"),
    station: str | None = Query(default=None, description="按所属场站检索"),
    forecast_date: str | None = Query(default=None, description="按预测日期检索"),
    status: str | None = Query(default=None, description="待生成、已生成、偏差超标、已复核"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按预测单号、所属场站、预测日期与状态过滤功率预测列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        station=station,
        forecast_date=forecast_date,
        status=status,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按预测单号检索"),
    station: str | None = Query(default=None, description="按所属场站检索"),
    forecast_date: str | None = Query(default=None, description="按预测日期检索"),
) -> dict[str, Any]:
    """按当前筛选条件（预测单号、所属场站、预测日期）导出待处理清单。

    与列表同一套取数口径；同一预测单号只留一条；已复核的记录不再进入导出范围；
    导出是只读操作，不会改动任何记录。
    """
    items, total = service.list_entries(
        keyword=keyword,
        station=station,
        forecast_date=forecast_date,
        pending_only=True,
        page=1,
        size=EXPORT_SIZE,
    )
    # 导出列与列表保持一致，去掉 id 等内部字段。
    export_items = [{field: row.get(field) for field in LIST_FIELDS} for row in items]
    return {"module": "forecast", "total": total, "columns": LIST_FIELDS, "items": export_items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条功率预测单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"功率预测单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条功率预测单，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="功率预测单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条功率预测单执行生成预测、登记偏差超标、复核预测；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
