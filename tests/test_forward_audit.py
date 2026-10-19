import hashlib
import pandas as pd
from src.forward_audit import forward_signal_report, _git_blob_sha, verify_frozen_rules


def test_forward_filter_excludes_research_period_and_immature():
    frame = pd.DataFrame([
        {"day":"2026-10-19", "訊號類型":"突破確認", "5日狀態":"完整", "報酬5日":1.0, "超額5日":1.0},
        {"day":"2026-10-20", "訊號類型":"突破確認", "5日狀態":"等待完整市場5日", "報酬5日":None, "超額5日":None},
        {"day":"2026-10-21", "訊號類型":"突破確認", "5日狀態":"完整", "報酬5日":.02, "超額5日":.01},
        {"day":"2026-10-22", "訊號類型":"一般合格股票", "5日狀態":"完整", "報酬5日":1.0, "超額5日":1.0},
    ])
    summary, forward = forward_signal_report(frame)
    assert len(forward) == 2
    assert summary.iloc[0]["完整5日訊號"] == 1
    assert summary.iloc[0]["5日平均報酬(%)"] == 2.0
    assert "尚未驗證" in summary.iloc[0]["判定"]


def test_no_forward_signals_are_not_success():
    summary, forward = forward_signal_report(pd.DataFrame())
    assert summary.empty and forward.empty


def test_freeze_detects_edits(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "strategy.py").write_text("modified")
    (tmp_path / "src" / "validation.py").write_text("modified")
    assert not verify_frozen_rules(tmp_path)["rules_unchanged"]


def test_git_blob_id_format():
    assert _git_blob_sha(b"hello\n") == hashlib.sha1(b"blob 6\0hello\n").hexdigest()
