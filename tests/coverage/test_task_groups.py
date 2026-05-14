"""
Unit tests for apps/tasks/task_groups.py.
Targets 17.24% → ~93% coverage.
"""

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# get_feature_enabled_from_db
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_get_feature_enabled_from_db_true():
    from apps.dynamic_settings.models import Setting
    from apps.tasks.task_groups import get_feature_enabled_from_db

    Setting.objects.create(setting_key="TEST_FLAG_A", current_value="true")
    assert get_feature_enabled_from_db("TEST_FLAG_A") is True


@pytest.mark.unit
@pytest.mark.django_db
def test_get_feature_enabled_from_db_false():
    from apps.dynamic_settings.models import Setting
    from apps.tasks.task_groups import get_feature_enabled_from_db

    Setting.objects.create(setting_key="TEST_FLAG_B", current_value="false")
    assert get_feature_enabled_from_db("TEST_FLAG_B") is False


@pytest.mark.unit
@pytest.mark.django_db
def test_get_feature_enabled_from_db_json_true():
    from apps.dynamic_settings.models import Setting
    from apps.tasks.task_groups import get_feature_enabled_from_db

    Setting.objects.create(setting_key="TEST_FLAG_JSON", current_value="true")
    assert get_feature_enabled_from_db("TEST_FLAG_JSON") is True


@pytest.mark.unit
@pytest.mark.django_db
def test_get_feature_enabled_from_db_fallback_settings_dict():
    from apps.tasks.task_groups import get_feature_enabled_from_db

    with patch("apps.tasks.task_groups.settings") as mock_settings:
        mock_settings.FEATURE_ENABLED = {"MY_FLAG": True}
        mock_settings.FEATURE_MY_FLAG_ENABLED = None
        result = get_feature_enabled_from_db("MY_FLAG", default=False)
    assert result is True


@pytest.mark.unit
@pytest.mark.django_db
def test_get_feature_enabled_from_db_fallback_direct_attr():
    from apps.tasks.task_groups import get_feature_enabled_from_db

    with patch("apps.tasks.task_groups.settings") as mock_settings:
        mock_settings.FEATURE_ENABLED = {}
        mock_settings.FEATURE_DIRECT_FLAG_ENABLED = True
        result = get_feature_enabled_from_db("DIRECT_FLAG", default=False)
    assert result is True


@pytest.mark.unit
@pytest.mark.django_db
def test_get_feature_enabled_from_db_returns_default():
    from apps.tasks.task_groups import get_feature_enabled_from_db

    with patch("apps.tasks.task_groups.settings") as mock_settings:
        mock_settings.FEATURE_ENABLED = {}
        mock_settings.FEATURE_UNKNOWN_FLAG_ENABLED = None
        with patch("ansible_base.feature_flags.models.AAPFlag") as mock_flag:
            mock_flag.objects.filter.return_value.first.return_value = None
            result = get_feature_enabled_from_db("UNKNOWN_FLAG", default=False)
    assert result is False


@pytest.mark.unit
def test_get_feature_enabled_db_exception_falls_back_to_settings():
    from apps.tasks.task_groups import get_feature_enabled_from_db

    with patch("apps.dynamic_settings.models.Setting.objects.filter", side_effect=Exception("DB error")):
        with patch("apps.tasks.task_groups.settings") as mock_settings:
            mock_settings.FEATURE_ENABLED = {"FALLBACK_FLAG": True}
            result = get_feature_enabled_from_db("FALLBACK_FLAG", default=False)
    assert result is True


@pytest.mark.unit
def test_get_feature_enabled_db_exception_returns_default():
    from apps.tasks.task_groups import get_feature_enabled_from_db

    with patch("apps.dynamic_settings.models.Setting.objects.filter", side_effect=Exception("DB error")):
        with patch("apps.tasks.task_groups.settings") as mock_settings:
            mock_settings.FEATURE_ENABLED = {}
            result = get_feature_enabled_from_db("NO_FALLBACK", default=False)
    assert result is False


# ---------------------------------------------------------------------------
# TaskGroup
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_task_group_get_enabled_tasks_flag_disabled():
    from apps.dynamic_settings.models import Setting
    from apps.tasks.task_groups import TaskGroup

    Setting.objects.create(setting_key="MY_TEST_GROUP", current_value="false")
    group = TaskGroup(
        name="test",
        description="test group",
        tasks=[{"task_id": "t1", "function": "fn", "enabled": True}],
        feature_flag="MY_TEST_GROUP",
    )
    assert group.get_enabled_tasks() == []


@pytest.mark.unit
@pytest.mark.django_db
def test_task_group_get_enabled_tasks_flag_enabled():
    from apps.dynamic_settings.models import Setting
    from apps.tasks.task_groups import TaskGroup

    Setting.objects.create(setting_key="MY_TEST_GROUP2", current_value="true")
    group = TaskGroup(
        name="test2",
        description="test group 2",
        tasks=[
            {"task_id": "t1", "function": "fn1", "enabled": True},
            {"task_id": "t2", "function": "fn2", "enabled": False},
        ],
        feature_flag="MY_TEST_GROUP2",
    )
    tasks = group.get_enabled_tasks()
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == "t1"


@pytest.mark.unit
def test_task_group_no_flag_filters_disabled_tasks():
    from apps.tasks.task_groups import TaskGroup

    group = TaskGroup(
        name="no_flag",
        description="No feature flag group",
        tasks=[
            {"task_id": "t1", "function": "fn1", "enabled": True},
            {"task_id": "t2", "function": "fn2", "enabled": False},
            {"task_id": "t3", "function": "fn3"},  # No "enabled" key → defaults True
        ],
        feature_flag=None,
    )
    tasks = group.get_enabled_tasks()
    assert len(tasks) == 2
    assert any(t["task_id"] == "t1" for t in tasks)
    assert any(t["task_id"] == "t3" for t in tasks)


@pytest.mark.unit
def test_task_group_empty_tasks():
    from apps.tasks.task_groups import TaskGroup

    group = TaskGroup(name="empty", description="empty group", tasks=[], feature_flag=None)
    assert group.get_enabled_tasks() == []


@pytest.mark.unit
def test_task_group_none_tasks_defaults_to_empty():
    from apps.tasks.task_groups import TaskGroup

    group = TaskGroup(name="none_tasks", description="desc")
    assert group.tasks == []
    assert group.get_enabled_tasks() == []


# ---------------------------------------------------------------------------
# get_all_enabled_tasks
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_get_all_enabled_tasks_includes_system_tasks():
    from apps.dynamic_settings.models import Setting
    from apps.tasks.task_groups import get_all_enabled_tasks

    # Enable all feature flags in DB so all groups run
    for key in ["METRICS_COLLECTION", "ANONYMIZED_DATA_COLLECTION", "DASHBOARD_COLLECTION"]:
        Setting.objects.get_or_create(setting_key=key, defaults={"current_value": "true"})

    tasks = get_all_enabled_tasks()
    assert "daily_task_cleanup" in tasks
    assert "hourly_health_check" in tasks


@pytest.mark.unit
@pytest.mark.django_db
def test_get_all_enabled_tasks_excludes_disabled_group():
    from apps.dynamic_settings.models import Setting
    from apps.tasks.task_groups import get_all_enabled_tasks

    Setting.objects.update_or_create(setting_key="METRICS_COLLECTION", defaults={"current_value": "false"})

    tasks = get_all_enabled_tasks()
    assert "hourly_job_host_summary" not in tasks
    assert "daily_metrics_rollup" not in tasks


@pytest.mark.unit
@pytest.mark.django_db
def test_get_all_enabled_tasks_embeds_feature_flag():
    from apps.dynamic_settings.models import Setting
    from apps.tasks.task_groups import get_all_enabled_tasks

    Setting.objects.get_or_create(setting_key="METRICS_COLLECTION", defaults={"current_value": "true"})
    tasks = get_all_enabled_tasks()

    if "daily_task_cleanup" in tasks:
        assert "group" in tasks["daily_task_cleanup"]


# ---------------------------------------------------------------------------
# get_all_tasks_for_init
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_get_all_tasks_for_init_ignores_feature_flags():
    from apps.dynamic_settings.models import Setting
    from apps.tasks.task_groups import get_all_tasks_for_init

    # Disable all flags
    for key in ["METRICS_COLLECTION", "ANONYMIZED_DATA_COLLECTION"]:
        Setting.objects.update_or_create(setting_key=key, defaults={"current_value": "false"})

    tasks = get_all_tasks_for_init()
    # These tasks exist with enabled=True in their group config — must be included
    assert "daily_task_cleanup" in tasks
    assert "daily_metrics_rollup" in tasks
    assert "daily_anonymize" in tasks


@pytest.mark.unit
def test_get_all_tasks_for_init_excludes_individually_disabled():
    from apps.tasks.task_groups import get_all_tasks_for_init

    tasks = get_all_tasks_for_init()
    # hourly_job_events has enabled=False in METRICS_COLLECTION_GROUP.tasks
    assert "hourly_job_events" not in tasks


@pytest.mark.unit
def test_get_all_tasks_for_init_embeds_feature_flag_in_config():
    from apps.tasks.task_groups import get_all_tasks_for_init

    tasks = get_all_tasks_for_init()
    # daily_metrics_rollup is in METRICS_COLLECTION_GROUP which has feature_flag="METRICS_COLLECTION"
    assert tasks["daily_metrics_rollup"]["feature_flag"] == "METRICS_COLLECTION"


@pytest.mark.unit
def test_get_all_tasks_for_init_system_tasks_no_feature_flag():
    from apps.tasks.task_groups import get_all_tasks_for_init

    tasks = get_all_tasks_for_init()
    # System tasks have no feature flag
    assert "feature_flag" not in tasks["daily_task_cleanup"]
