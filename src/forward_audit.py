"""V3.4 frozen-rule prospective tracking; no independent validation claim."""
from __future__ import annotations
import hashlib
from datetime import date
from pathlib import Path
import pandas as pd

FREEZE_ASOF = date(2026, 10, 19)
FIRST_FORWARD_DAY = date(2026, 10, 20)
FROZEN_SOURCE_BLOBS = {
    "src/strategy.py": "d79b8d7918f371f7a45afbdd2a6a4e22a2aa72fd",
    "src/validation.py": "41b66eeafecab50183ea72dfd1b8ffabac19fec1",
}


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def verify_frozen_rules(project_root: Path | None = None) -> dict:
    root = project_root or Path(__file__).resolve().parents[1]
    issues = []
    for path, expected in FROZEN_SOURCE_BLOBS.items():
        f = root / path
        if not f.exists():
            issues.append(f"{path}: missing")
        elif _git_blob_sha(f.read_bytes()) != expected:
            issues.append(f"{path}: changed after freeze")
    return {"rules_unchanged": not issues, "issues": issues,
            "freeze_asof": FREEZE_ASOF.isoformat(),
            "first_forward_day": FIRST_FORWARD_DAY.isoformat()}


def forward_signal_report(observations: pd.DataFrame, min_signals=100,
                          min_dates=20) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = ["訊號類型", "總訊號數", "完整5日訊號", "不同訊號日數",
            "5日平均報酬(%)", "5日平均超額(%)", "5日上漲比例(%)", "判定"]
    if observations.empty:
        return pd.DataFrame(columns=cols), observations.copy()
    required = {"day", "訊號類型", "5日狀態", "報酬5日", "超額5日"}
    missing = required.difference(observations.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    forward = observations.loc[
        (pd.to_datetime(observations["day"], errors="raise") >= pd.Timestamp(FIRST_FORWARD_DAY)) &
        observations["訊號類型"].isin(["蓄勢候選", "突破確認"])].copy()
    rows = []
    for kind, g in forward.groupby("訊號類型"):
        finished = g[(g["5日狀態"] == "完整") & g["報酬5日"].notna() & g["超額5日"].notna()]
        n, days = len(finished), finished["day"].nunique()
        enough = n >= min_signals and days >= min_dates
        rows.append({"訊號類型": kind, "總訊號數": len(g), "完整5日訊號": n,
                     "不同訊號日數": days,
                     "5日平均報酬(%)": round(float(finished["報酬5日"].mean())*100,2) if n else None,
                     "5日平均超額(%)": round(float(finished["超額5日"].mean())*100,2) if n else None,
                     "5日上漲比例(%)": round(float((finished["報酬5日"]>0).mean())*100,2) if n else None,
                     "判定": "樣本累積中；尚未驗證" if not enough else "描述性樣本達門檻；仍未完成正式樣本外驗證"})
    return pd.DataFrame(rows, columns=cols), forward
