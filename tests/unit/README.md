# Unit Tests Organization

This directory contains unit tests organized by application modules for better maintainability and clarity.

## Directory Structure

### `core/` - Core App Tests

Tests for the core application functionality:

- `test_access_control_mixin.py` - Access control mixin tests
- `test_core_models.py` - Core model tests (User, Organization, Team)
- `test_core_permissions.py` - Permission system tests
- `test_core_utils.py` - Utility function tests
- `test_init_service_id_command.py` - ServiceID initialization command tests
- `test_metrics_service_command.py` - Unified metrics service command tests
- `test_system_auditor_permissions.py` - System auditor permission tests

### `api/` - API App Tests

Tests for the REST API functionality:

- `test_api_views.py` - Basic API view tests
- `test_api_views_coverage.py` - API view coverage tests
- `test_api_views_extended.py` - Extended API view tests
- `test_base_views_complete.py` - Base view complete tests
- `test_base_views_comprehensive.py` - Comprehensive base view tests
- `test_tasks_api_comprehensive.py` - Task API comprehensive tests

### `dashboard/` - Dashboard App Tests

Tests for the web dashboard functionality:

- `test_dashboard_views.py` - Dashboard view tests

### `tasks/` - Tasks App Tests

Tests for the background task system:

- `test_task_system.py` - Core task system tests
- `test_task_management_extended.py` - Extended task management tests
- `test_tasks_utils.py` - Task utility function tests
- `test_tasks_views_extended.py` - Extended task view tests

### `general/` - General/Integration Tests

Tests that span multiple apps or test general functionality:

- `test_additional_coverage.py` - Additional coverage tests
- `test_final_coverage.py` - Final coverage tests
- `test_main_urls.py` - Main URL configuration tests (100% coverage)
- `test_models.py` - General model tests
- `test_models_extended.py` - Extended model tests
- `test_urls_basic.py` - Basic URL configuration tests

## Running Tests

### Run all unit tests:

```bash
python -m pytest tests/unit/
```

### Run tests for a specific app:

```bash
python -m pytest tests/unit/core/
python -m pytest tests/unit/api/
python -m pytest tests/unit/dashboard/
python -m pytest tests/unit/tasks/
python -m pytest tests/unit/general/
```

### Run specific test files:

```bash
python -m pytest tests/unit/core/test_core_models.py
python -m pytest tests/unit/api/test_api_views.py
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
- Background task processing
- Management commands
- Utility functions
- URL routing and configuration

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
