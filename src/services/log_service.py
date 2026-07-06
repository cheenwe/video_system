"""操作日志：谁、何时、IP、做了什么。

`tag` 约定（与前端「操作日志」页 Tab 一致）：
- login：登录、登出、登录失败等认证轨迹
- operation：日常业务增改、生成报告、下载等业务动作
- audit：删除数据、系统配置变更、账号禁用/重置密码/改密、覆盖内置资源、触发安全限制等需重点留痕的动作
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from src.models.sys_log import SysLog


def log_action(
    db: Session,
    *,
    action: str,
    tag: str = "operation",
    result: str = "success",
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    ip: Optional[str] = None,
    request_id: Optional[str] = None,
    remark: Optional[str] = None,
) -> SysLog:
    log = SysLog(
        action=action,
        tag=tag,
        result=result,
        user_id=user_id,
        username=username,
        ip=ip,
        request_id=request_id,
        remark=remark,
    )
    db.add(log)
    db.commit()
    return log
