"""Playwright E2E tests for Streamlit dashboard."""

import pytest


@pytest.mark.skip(reason="Streamlit server fixture needs manual setup")
def test_dashboard_homepage_loads(page, streamlit_server):
    """Test that the dashboard homepage loads successfully."""
    page.goto(streamlit_server)
    page.wait_for_selector("text=Stock KB 首页", timeout=10000)
    assert page.is_visible("text=Stock KB 首页")


@pytest.mark.skip(reason="Streamlit server fixture needs manual setup")
def test_watchlist_page_navigation(page, streamlit_server):
    """Test navigation to watchlist page."""
    page.goto(streamlit_server)
    page.click("text=关注清单")
    page.wait_for_selector("text=📁 关注清单", timeout=10000)
    assert page.is_visible("text=📁 关注清单")


@pytest.mark.skip(reason="Streamlit server fixture needs manual setup")
def test_stock_profile_page_loads(page, streamlit_server):
    """Test that stock profile page loads with data."""
    page.goto(f"{streamlit_server}/个股档案")
    page.wait_for_selector("text=📋 个股档案", timeout=10000)
    assert page.is_visible("text=📋 个股档案")
    # Should have stock selector
    assert page.is_visible("text=选择股票")
