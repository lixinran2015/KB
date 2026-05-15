import os
import tempfile

from packages.engines.report_engine import ReportEngine


def test_report_generation():
    engine = ReportEngine()
    md = engine.generate(stock_code="300308.SZ", segment="光模块", report_period="2024Q1")
    assert "300308.SZ" in md
    assert "中际旭创" in md
    assert "评分卡" in md


def test_manual_slot_preserved():
    engine = ReportEngine()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "300308.SZ.md")

        # First generation
        md1 = engine.generate(
            stock_code="300308.SZ",
            segment="光模块",
            report_period="2024Q1",
            output_path=output_path,
        )
        assert "MANUAL_SLOT" in md1

        # Simulate user adding manual notes in the slot
        md1 = md1.replace(
            "<!-- 在此区域手动添加分析笔记，不会被自动覆盖 -->",
            "<!-- 在此区域手动添加分析笔记，不会被自动覆盖 -->\n\n我的手动分析笔记",
        )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md1)

        # Re-generate
        md2 = engine.generate(
            stock_code="300308.SZ",
            segment="光模块",
            report_period="2024Q1",
            output_path=output_path,
        )

        assert "我的手动分析笔记" in md2
