# Unit Tests Organization

This directory contains unit tests organized by application modules for better maintainability and clarity.

## Directory Structure

### `core/` - Core App Tests

Tests for the core application functionality:

- `test_core_models.py` - Core model tests (User, Organization, Team)
- `test_development_mode_permissions.py` - Development mode permission tests
- `test_metrics_service_command.py` - Unified metrics service command tests (includes init-service-id and init-default-settings)
- `test_metrics_service_helpers.py` - Metrics service helper function tests
- `test_mixins_comprehensive.py` - Comprehensive mixin tests
- `test_resource_api_comprehensive.py` - Resource API comprehensive tests

### `dashboard/` - Dashboard App Tests

Tests for the web dashboard functionality:

- `test_dashboard_views.py` - Dashboard view tests

### `tasks/` - Tasks App Tests

Tests for the background task system:

- `test_api_utils.py` - Task API utility tests
- `test_base_views_comprehensive.py` - Comprehensive base view tests
- `test_collector_integration.py` - Collector integration tests
- `test_dispatcherd_config.py` - Dispatcherd configuration tests
- `test_feature_enabled_db.py` - Feature enabled database tests
- `test_management_commands_coverage.py` - Management command coverage tests
- `test_mixins.py` - Task mixin tests
- `test_models.py` - Task model tests
- `test_run_dispatcherd_command.py` - Run dispatcherd command tests
- `test_run_task_scheduler_comprehensive.py` - Comprehensive task scheduler tests
- `test_services_output_formatter.py` - Service output formatter tests
- `test_task_groups.py` - Task group tests
- `test_tasks_api_views.py` - Task API view tests
- `test_tasks_collector_advanced.py` - Advanced task collector tests
- `test_tasks_collector_full_coverage.py` - Full coverage task collector tests
- `test_tasks_system.py` - Core task system tests
- `test_tasks_utils_comprehensive.py` - Comprehensive task utility tests
- `test_unified_scheduler.py` - Unified scheduler tests
- `test_v1_base_serializers.py` - V1 base serializer tests
- `test_v1_urls.py` - V1 URL tests

### `dynamic_settings/` - Dynamic Settings Tests

Tests for the dynamic settings system:

- `test_reload_config_command.py` - Reload configuration command tests

### `general/` - General/Integration Tests

Tests that span multiple apps or test general functionality:

- `test_additional_coverage.py` - Additional coverage tests
- `test_final_coverage.py` - Final coverage tests
- `test_health_metrics.py` - Health metrics tests
- `test_main_urls.py` - Main URL configuration tests (100% coverage)
- `test_main_urls_comprehensive.py` - Comprehensive main URL tests
- `test_models.py` - General model tests
- `test_urls_basic.py` - Basic URL configuration tests

### Root Level Tests

- `test_dynaconf_settings.py` - Dynaconf settings configuration tests

## Running Tests

### Run all unit tests:

```bash
python -m pytest tests/unit/
```

### Run tests for a specific app:

```bash
python -m pytest tests/unit/core/
python -m pytest tests/unit/dashboard/
python -m pytest tests/unit/dynamic_settings/
python -m pytest tests/unit/tasks/
python -m pytest tests/unit/general/
```

### Run specific test files:

```bash
python -m pytest tests/unit/core/test_core_models.py
python -m pytest tests/unit/tasks/test_tasks_system.py
python -m pytest tests/unit/general/test_main_urls.py
```

## Benefits of This Organization

1. **Clear Separation**: Tests are organized by the app they test
2. **Easy Navigation**: Developers can quickly find tests for specific functionality
3. **Maintainability**: Easier to maintain and update tests when code changes
4. **Scalability**: New apps can easily add their own test directories
5. **Parallel Development**: Teams can work on different app tests independently

## Test Coverage

The tests provide comprehensive coverage of:

- Model functionality and validation
- API endpoints and serialization
- Permission systems and access control
- Background task processing and scheduling
- Task collectors and metrics collection
- Management commands and CLI tools
- Dynamic settings and feature flags
- Dispatcherd configuration and integration
- Utility functions and mixins
- URL routing and configuration
- Dashboard views and interfaces

### Main URLs Test (`test_main_urls.py`)

The `test_main_urls.py` file provides comprehensive testing for the main URL configuration (`metrics_service/urls.py`) with 100% code coverage:

**Test Categories:**

- **File Content Tests**: Verify the actual content and structure of the URLs file
- **Import Tests**: Test that all required imports are available and functional
- **URL Resolution Tests**: Test that URLs can be resolved correctly
- **Mock Tests**: Test functionality with mocked dependencies
- **Edge Case Tests**: Test file permissions, encoding, syntax, and error conditions
- **Integration Tests**: Test with full Django setup and settings

**Coverage Areas:**

- File existence and readability
- Import statement validation
- URL pattern structure verification
- Django URL resolution functionality
- File syntax and encoding validation
- Debug/production mode compatibility
- Multi-line import handling
- File permissions and encoding

This test ensures that the main URL configuration is properly structured and functional across different environments.
