"""
Unit tests for apps/dashboard_reports/awx_queries.py.
Targets 28.79% → ~90% coverage.
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _build_where_clause
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_build_where_clause_no_filters():
    from apps.dashboard_reports.awx_queries import _build_where_clause

    clause, params = _build_where_clause("", None, None)
    assert clause == ""
    assert params == []


@pytest.mark.unit
def test_build_where_clause_with_search():
    from apps.dashboard_reports.awx_queries import _build_where_clause

    clause, params = _build_where_clause("ujt.", "my-template", None)
    assert "WHERE" in clause
    assert "ilike" in clause
    assert params[0] == "%my-template%"


@pytest.mark.unit
def test_build_where_clause_with_pk():
    from apps.dashboard_reports.awx_queries import _build_where_clause

    clause, params = _build_where_clause("", None, 42)
    assert "WHERE" in clause
    assert 42 in params


@pytest.mark.unit
def test_build_where_clause_with_both():
    from apps.dashboard_reports.awx_queries import _build_where_clause

    clause, params = _build_where_clause("", "search", 5)
    assert "WHERE" in clause
    assert "AND" in clause
    assert len(params) == 2


@pytest.mark.unit
def test_build_where_clause_escapes_special_chars():
    from apps.dashboard_reports.awx_queries import _build_where_clause

    clause, params = _build_where_clause("", "my%project_name", None)
    # % and _ should be escaped
    assert "\\%" in params[0] or r"\%" in params[0]


# ---------------------------------------------------------------------------
# _execute_db_query
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_execute_db_query():
    from apps.dashboard_reports.awx_queries import _execute_db_query

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.description = [("id",), ("name",)]
    mock_cursor.fetchall.return_value = [(1, "test"), (2, "test2")]
    mock_conn.cursor.return_value = mock_cursor

    columns, data = _execute_db_query(mock_conn, "SELECT id, name FROM test", [])
    assert columns == ["id", "name"]
    assert data == [(1, "test"), (2, "test2")]


# ---------------------------------------------------------------------------
# _execute_count_query
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_execute_count_query():
    from apps.dashboard_reports.awx_queries import _execute_count_query

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.return_value = (42,)
    mock_conn.cursor.return_value = mock_cursor

    count = _execute_count_query(mock_conn, "SELECT COUNT(*) FROM test", [])
    assert count == 42


# ---------------------------------------------------------------------------
# format_id_name_rows
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_format_id_name_rows():
    from apps.dashboard_reports.awx_queries import format_id_name_rows

    rows = [(1, "org1"), (2, "org2")]
    result = format_id_name_rows(rows)
    assert result == [{"id": 1, "name": "org1"}, {"id": 2, "name": "org2"}]


@pytest.mark.unit
def test_format_id_name_rows_empty():
    from apps.dashboard_reports.awx_queries import format_id_name_rows

    result = format_id_name_rows([])
    assert result == []


# ---------------------------------------------------------------------------
# fetch_data_from_db — with and without limit
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_fetch_data_from_db_without_limit():
    from apps.dashboard_reports.awx_queries import AWXQuery, fetch_data_from_db

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.description = [("id",), ("name",)]
    mock_cursor.fetchall.return_value = [(1, "org1"), (2, "org2")]
    mock_conn.cursor.return_value = mock_cursor

    data, total = fetch_data_from_db(AWXQuery.ORGANIZATIONS, db_connection=mock_conn)
    assert total == 2
    assert len(data) == 2


@pytest.mark.unit
def test_fetch_data_from_db_with_limit():
    from apps.dashboard_reports.awx_queries import AWXQuery, fetch_data_from_db

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    # First call: COUNT, returns 10
    # Second call: actual data
    mock_cursor.fetchone.return_value = (10,)
    mock_cursor.fetchall.return_value = [(1, "org1")]
    mock_cursor.description = [("id",), ("name",)]
    mock_conn.cursor.return_value = mock_cursor

    data, total = fetch_data_from_db(
        AWXQuery.ORGANIZATIONS, db_connection=mock_conn, limit=5, offset=0
    )
    assert total == 10


# ---------------------------------------------------------------------------
# fetch_organizations, fetch_templates, fetch_projects, fetch_labels
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_fetch_organizations():
    from apps.dashboard_reports.awx_queries import fetch_organizations

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.description = [("id",), ("name",)]
    mock_cursor.fetchall.return_value = [(1, "Default")]
    mock_conn.cursor.return_value = mock_cursor

    items, total = fetch_organizations(db_connection=mock_conn)
    assert items == [{"id": 1, "name": "Default"}]


@pytest.mark.unit
def test_fetch_templates():
    from apps.dashboard_reports.awx_queries import fetch_templates

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.description = [("id",), ("name",)]
    mock_cursor.fetchall.return_value = [(5, "My Template")]
    mock_conn.cursor.return_value = mock_cursor

    items, total = fetch_templates(db_connection=mock_conn)
    assert items == [{"id": 5, "name": "My Template"}]


@pytest.mark.unit
def test_fetch_id_name_raises_on_db_error():
    """When DB query fails, fetch_id_name logs and re-raises."""
    from apps.dashboard_reports.awx_queries import AWXQuery, fetch_id_name

    mock_conn = MagicMock()
    mock_conn.cursor.side_effect = Exception("DB error")

    with pytest.raises(Exception, match="DB error"):
        fetch_id_name(AWXQuery.ORGANIZATIONS, db_connection=mock_conn, error_msg="fail")


@pytest.mark.unit
def test_awxquery_enum_values():
    from apps.dashboard_reports.awx_queries import AWXQuery

    assert "SELECT" in AWXQuery.ORGANIZATIONS.value
    assert "SELECT" in AWXQuery.TEMPLATES.value
    assert "SELECT" in AWXQuery.PROJECTS.value
    assert "SELECT" in AWXQuery.LABELS.value
