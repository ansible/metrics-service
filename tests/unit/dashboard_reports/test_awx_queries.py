from unittest.mock import MagicMock, patch

import pytest

from apps.dashboard_reports import awx_queries


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
        columns, data = awx_queries.fetch_data_from_db(
            "SELECT id, name FROM table", join_alias="", db_connection=db_conn, search_str=None, pk=None
        )
        assert columns == ["id", "name"]
        assert data == [(1, "X")]
        mock_exec.assert_called()

    @patch("apps.dashboard_reports.awx_queries.fetch_data_from_db")
    def test_fetch_id_name_success(self, mock_fetch):
        mock_fetch.return_value = (["id", "name"], [(3, "C")])
        result = awx_queries.fetch_id_name("SELECT id, name FROM t", error_msg="err", db_connection=MagicMock())
        assert result == [{"id": 3, "name": "C"}]

    @patch("apps.dashboard_reports.awx_queries.fetch_data_from_db")
    def test_fetch_id_name_error(self, mock_fetch):
        mock_fetch.side_effect = Exception("fail")
        with pytest.raises(Exception, match="fail"):
            awx_queries.fetch_id_name("SELECT id, name FROM t", error_msg="err", db_connection=MagicMock())

    @patch("apps.dashboard_reports.awx_queries.fetch_id_name")
    def test_fetch_organizations(self, mock_fetch):
        mock_fetch.return_value = [{"id": 1, "name": "Org"}]
        result = awx_queries.fetch_organizations(db_connection=MagicMock())
        assert result == [{"id": 1, "name": "Org"}]

    @patch("apps.dashboard_reports.awx_queries.fetch_id_name")
    def test_fetch_templates(self, mock_fetch):
        mock_fetch.return_value = [{"id": 2, "name": "Tpl"}]
        result = awx_queries.fetch_templates(db_connection=MagicMock())
        assert result == [{"id": 2, "name": "Tpl"}]

    @patch("apps.dashboard_reports.awx_queries.fetch_id_name")
    def test_fetch_projects(self, mock_fetch):
        mock_fetch.return_value = [{"id": 3, "name": "Prj"}]
        result = awx_queries.fetch_projects(db_connection=MagicMock())
        assert result == [{"id": 3, "name": "Prj"}]

    @patch("apps.dashboard_reports.awx_queries.fetch_id_name")
    def test_fetch_labels(self, mock_fetch):
        mock_fetch.return_value = [{"id": 4, "name": "Lbl"}]
        result = awx_queries.fetch_labels(db_connection=MagicMock())
        assert result == [{"id": 4, "name": "Lbl"}]
