"""功率预测接口：维护功率预测单，覆盖生成预测、登记偏差超标、复核预测等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.forecast import ForecastService

router = APIRouter(prefix="/api/forecast", tags=["功率预测"])

service = ForecastService()

LIST_FIELDS = ["预测单号", "所属场站", "预测日期", "预测出力", "实际出力", "预测偏差", "考核电量", "预测状态"]
STATUSES = ["待生成", "已生成", "偏差超标", "已复核"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按预测单号检索"),
    status: str | None = Query(default=None, description="待生成、已生成、偏差超标、已复核"),
    station: str | None = Query(default=None, description="按所属场站模糊检索"),
    start_date: str | None = Query(default=None, description="预测日期起（含），YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="预测日期止（含），YYYY-MM-DD"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按预测单号、状态、场站与预测日期范围过滤功率预测列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        station=station,
        start_date=start_date,
        end_date=end_date,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


# 注意：必须排在 /{entry_id} 之前，否则 /export 会被当成 entry_id 匹配而报参数错误。
@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按预测单号检索"),
    status: str | None = Query(default=None, description="待生成、已生成、偏差超标、已复核"),
    station: str | None = Query(default=None, description="按所属场站模糊检索"),
    start_date: str | None = Query(default=None, description="预测日期起（含），YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="预测日期止（含），YYYY-MM-DD"),
) -> dict[str, Any]:
    """按列表当前条件（单号、状态、场站、预测日期范围）导出待处理预测单。

    已复核的记录不导出，同一预测单号只保留一条；接口只读，不会改变列表里的记录。
    """
    items = service.export_entries(
        keyword=keyword,
        status=status,
        station=station,
        start_date=start_date,
        end_date=end_date,
    )
    return {"module": "forecast", "total": len(items), "fields": LIST_FIELDS, "items": items}


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
