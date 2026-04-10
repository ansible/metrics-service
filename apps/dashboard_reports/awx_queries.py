import logging
from typing import Any

logger = logging.getLogger(__name__)


def _build_where_clause(join_alias: str, search_str: str | None, pk: Any) -> tuple[str, list[Any]]:
    """Build WHERE clause and parameters for SQL query."""
    where_clauses = []
    params = []
    if search_str:
        where_clauses.append(f"{join_alias}name ilike %s")
        params.append("%" + search_str + "%")
    if pk:
        where_clauses.append(f"{join_alias}id = %s")
        params.append(pk)
    clause = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    return clause, params


def _execute_db_query(db_connection, query: str, params: list[Any]) -> tuple[list[str], list[Any]]:
    """Execute SQL query and return columns and data."""
    with db_connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        data = cursor.fetchall()
    return columns, data


def fetch_data_from_db(base_query: str, join_alias: str = "", **kwargs: Any) -> tuple[list[Any], Any]:
    db_connection = kwargs.get("db_connection")
    search_str = kwargs.get("search_str")
    pk = kwargs.get("pk")
    # Build WHERE clause and params
    where_clause, params = _build_where_clause(join_alias, search_str, pk)
    query = base_query + where_clause + f" ORDER BY {join_alias}name"
    # Execute query and return results
    columns, data = _execute_db_query(db_connection, query, params)
    return columns, data


def format_id_name_rows(rows: list[Any]) -> list[dict[str, Any]]:
    """Format rows as list of dicts with 'id' and 'name' keys."""
    return [{"id": row[0], "name": row[1]} for row in rows]


def fetch_id_name(query: str, join_alias: str = "", error_msg: str = "", **kwargs) -> list[dict[str, Any]]:
    try:
        _, rows = fetch_data_from_db(query, join_alias=join_alias, **kwargs)
    except Exception:
        logger.exception(error_msg)
        raise
    return format_id_name_rows(rows)


def fetch_organizations(*args, **kwargs) -> list[dict[str, Any]]:
    """Fetch organizations from DB."""
    query = "SELECT id, name FROM main_organization"
    return fetch_id_name(query, error_msg="Error fetching organizations from AWX database", **kwargs)


def fetch_templates(*args, **kwargs) -> list[dict[str, Any]]:
    """Fetch job templates from DB."""
    query = (
        "SELECT ujt.id, ujt.name "
        "FROM main_unifiedjobtemplate ujt "
        "JOIN main_jobtemplate jt on jt.unifiedjobtemplate_ptr_id = ujt.id"
    )
    return fetch_id_name(query, join_alias="ujt.", error_msg="Error fetching job templates from AWX database", **kwargs)


def fetch_projects(*args, **kwargs) -> list[dict[str, Any]]:
    """Fetch projects from DB."""
    query = (
        "SELECT ujt.id, "
        "ujt.name FROM main_unifiedjobtemplate ujt "
        "JOIN main_project pj on pj.unifiedjobtemplate_ptr_id = ujt.id"
    )
    return fetch_id_name(query, join_alias="ujt.", error_msg="Error fetching projects from AWX database", **kwargs)


def fetch_labels(*args, **kwargs) -> list[dict[str, Any]]:
    """Fetch labels from DB."""
    query = "SELECT id, name FROM main_label"
    return fetch_id_name(query, error_msg="Error fetching labels from AWX database", **kwargs)
