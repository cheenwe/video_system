"""服务器基础指标（CPU / 内存 / 磁盘），供管理端展示与告警。"""
from __future__ import annotations

import platform
import socket
from datetime import datetime
from typing import Any, Dict, List

# 磁盘使用率 ≥ 阈值时生成告警（百分比为已用空间占比）
DISK_WARN_PERCENT = 85.0
DISK_ALARM_PERCENT = 92.0
MEMORY_WARN_PERCENT = 90.0

_SKIP_FSTYPES = frozenset(
    {
        "tmpfs",
        "devtmpfs",
        "proc",
        "sysfs",
        "cgroup",
        "cgroup2",
        "pstore",
        "bpf",
        "tracefs",
        "fusectl",
        "mqueue",
        "securityfs",
        "devpts",
        "rpc_pipefs",
        "autofs",
    }
)


def _gb(n: int) -> float:
    return round(n / (1024**3), 2)


def collect_server_metrics() -> Dict[str, Any]:
    import psutil

    alerts: List[Dict[str, str]] = []

    cpu_percent = round(psutil.cpu_percent(interval=0.15), 1)
    cpu_count = psutil.cpu_count(logical=True) or 0
    loadavg: List[float] | None = None
    try:
        raw = psutil.getloadavg()
        loadavg = [round(x, 2) for x in raw]
    except (AttributeError, OSError):
        pass

    vm = psutil.virtual_memory()
    mem_pct = float(vm.percent)
    memory = {
        "total_gb": _gb(vm.total),
        "used_gb": _gb(vm.used),
        "available_gb": _gb(vm.available),
        "percent": round(mem_pct, 1),
    }
    if mem_pct >= MEMORY_WARN_PERCENT:
        alerts.append(
            {
                "level": "warn",
                "message": f"内存使用率较高（约 {mem_pct:.1f}%），请关注业务与备份占用。",
            }
        )

    disks: List[Dict[str, Any]] = []
    seen_mounts: set[str] = set()
    for part in psutil.disk_partitions(all=True):
        mp = part.mountpoint
        if not mp or mp in seen_mounts:
            continue
        if mp.startswith(("/proc", "/sys", "/dev")):
            continue
        fst = (part.fstype or "").lower()
        if fst in _SKIP_FSTYPES:
            continue
        try:
            usage = psutil.disk_usage(mp)
        except PermissionError:
            continue
        except OSError:
            continue
        if usage.total <= 0:
            continue
        pct = round(100.0 * usage.used / usage.total, 1)
        row = {
            "device": part.device or "",
            "mountpoint": mp,
            "fstype": part.fstype or "",
            "total_gb": _gb(usage.total),
            "used_gb": _gb(usage.used),
            "free_gb": _gb(usage.free),
            "percent": pct,
        }
        disks.append(row)
        seen_mounts.add(mp)

        if pct >= DISK_ALARM_PERCENT:
            alerts.append(
                {
                    "level": "error",
                    "message": f"磁盘「{mp}」空间紧张：已用约 {pct}%（剩余约 {row['free_gb']} GB），请尽快清理或扩容。",
                }
            )
        elif pct >= DISK_WARN_PERCENT:
            alerts.append(
                {
                    "level": "warn",
                    "message": f"磁盘「{mp}」使用率约 {pct}%，接近上限，建议预留空间。",
                }
            )

    disks.sort(key=lambda x: x["mountpoint"])

    boot_iso = None
    try:
        boot_iso = datetime.fromtimestamp(psutil.boot_time()).isoformat(timespec="seconds")
    except (AttributeError, OSError):
        pass

    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "cpu_percent": cpu_percent,
        "cpu_count_logical": cpu_count,
        "loadavg": loadavg,
        "memory": memory,
        "disks": disks,
        "alerts": alerts,
        "boot_time": boot_iso,
        "thresholds": {
            "disk_warn_percent": DISK_WARN_PERCENT,
            "disk_alarm_percent": DISK_ALARM_PERCENT,
            "memory_warn_percent": MEMORY_WARN_PERCENT,
        },
    }
