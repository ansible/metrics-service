from unittest.mock import MagicMock, patch

import pytest

from apps.dashboard_reports import awx_queries
from apps.dashboard_reports.awx_queries import AWXQuery


@pytest.mark.unit
class TestAWXQueries:
    def test_build_where_clause_none(self):
        clause, params = awx_queries._build_where_clause("", None, None)
        assert clause == ""
        assert params == []

    def test_build_where_clause_search(self):
        clause, params = awx_queries._build_where_clause("x.", "foo", None)
        assert clause == " WHERE x.name ilike %s ESCAPE '\\\\'"
        assert params == ["%foo%"]

    def test_build_where_clause_pk(self):
        clause, params = awx_queries._build_where_clause("y.", None, 42)
        assert clause == " WHERE y.id = %s"
        assert params == [42]

    def test_build_where_clause_both(self):
        clause, params = awx_queries._build_where_clause("z.", "bar", 7)
        assert clause == " WHERE z.name ilike %s ESCAPE '\\\\' AND z.id = %s"
        assert params == ["%bar%", 7]

    def test_format_id_name_rows(self):
        rows = [(1, "A"), (2, "B")]
        result = awx_queries.format_id_name_rows(rows)
        assert result == [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]

    @patch("apps.dashboard_reports.awx_queries._execute_db_query")
    def test_fetch_data_from_db(self, mock_exec):
        mock_exec.return_value = (["id", "name"], [(1, "X")])
        db_conn = MagicMock()
        rows, total = awx_queries.fetch_data_from_db(
            AWXQuery.ORGANIZATIONS, join_alias="", db_connection=db_conn, search_str=None, pk=None
        )
        assert rows == [(1, "X")]
        assert total == 1  # len(rows) when no limit
        mock_exec.assert_called()

    @patch("apps.dashboard_reports.awx_queries._execute_db_query")
    @patch("apps.dashboard_reports.awx_queries._execute_count_query")
    def test_fetch_data_from_db_with_limit(self, mock_count, mock_exec):
        mock_count.return_value = 42
        mock_exec.return_value = (["id", "name"], [(1, "X"), (2, "Y")])
        db_conn = MagicMock()
        rows, total = awx_queries.fetch_data_from_db(
            AWXQuery.ORGANIZATIONS,
            join_alias="",
            db_connection=db_conn,
            search_str=None,
            pk=None,
            limit=10,
            offset=0,
        )
        assert rows == [(1, "X"), (2, "Y")]
        assert total == 42
        mock_count.assert_called_once()
        mock_exec.assert_called_once()

    @patch("apps.dashboard_reports.awx_queries.fetch_data_from_db")
    def test_fetch_id_name_success(self, mock_fetch):
        mock_fetch.return_value = ([(3, "C")], 1)
        items, total = awx_queries.fetch_id_name(AWXQuery.ORGANIZATIONS, error_msg="err", db_connection=MagicMock())
        assert items == [{"id": 3, "name": "C"}]
        assert total == 1

    @patch("apps.dashboard_reports.awx_queries.fetch_data_from_db")
    def test_fetch_id_name_error(self, mock_fetch):
        mock_fetch.side_effect = Exception("fail")
        with pytest.raises(Exception, match="fail"):
            awx_queries.fetch_id_name(AWXQuery.ORGANIZATIONS, error_msg="err", db_connection=MagicMock())

    @patch("apps.dashboard_reports.awx_queries.fetch_id_name")
    def test_fetch_organizations(self, mock_fetch):
        mock_fetch.return_value = ([{"id": 1, "name": "Org"}], 1)
        items, total = awx_queries.fetch_organizations(db_connection=MagicMock())
        assert items == [{"id": 1, "name": "Org"}]
        assert total == 1

    @patch("apps.dashboard_reports.awx_queries.fetch_id_name")
    def test_fetch_templates(self, mock_fetch):
        mock_fetch.return_value = ([{"id": 2, "name": "Tpl"}], 1)
        items, total = awx_queries.fetch_templates(db_connection=MagicMock())
        assert items == [{"id": 2, "name": "Tpl"}]
        assert total == 1

    @patch("apps.dashboard_reports.awx_queries.fetch_id_name")
    def test_fetch_projects(self, mock_fetch):
        mock_fetch.return_value = ([{"id": 3, "name": "Prj"}], 1)
        items, total = awx_queries.fetch_projects(db_connection=MagicMock())
        assert items == [{"id": 3, "name": "Prj"}]
        assert total == 1

    @patch("apps.dashboard_reports.awx_queries.fetch_id_name")
    def test_fetch_labels(self, mock_fetch):
        mock_fetch.return_value = ([{"id": 4, "name": "Lbl"}], 1)
        items, total = awx_queries.fetch_labels(db_connection=MagicMock())
        assert items == [{"id": 4, "name": "Lbl"}]
        assert total == 1
