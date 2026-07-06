"""运行环境变量（.env）API 模型"""
from __future__ import annotations

from pydantic import BaseModel, Field


class RuntimeEnvItem(BaseModel):
    key: str
    value: str
    readonly: bool = False
    description: str = ""
    example: str = ""


class RuntimeEnvListOut(BaseModel):
    items: list[RuntimeEnvItem]
    path: str
    full_example_env: str = ""
    hint: str = Field(
        default="修改后部分项需重启进程方生效（如 PORT）。PORT 仅可查看，保存时以服务器当前 .env 为准。"
    )


class RuntimeEnvPutBody(BaseModel):
    """键为大写环境变量名，值为字符串（与 .env 一致）。"""

    data: dict[str, str] = Field(default_factory=dict)
