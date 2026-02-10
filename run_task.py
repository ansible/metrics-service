#!/usr/bin/env python
# ruff: noqa: E402, I001, T201
"""
Run tasks directly from the command line.

Usage:
    uv run ./run_task.py <task_name> [task_params_json]

Examples:
    uv run ./run_task.py collect_all_metrics
    uv run ./run_task.py collect_anonymous_metrics '{"database": "awx"}'
    uv run ./run_task.py cleanup_old_tasks '{"days_old": 7, "dry_run": true}'
    uv run ./run_task.py hello_world
"""

import json
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "metrics_service.settings")
import django

django.setup()

# Now we can import from the apps
from apps.tasks.tasks import TASK_FUNCTIONS, TASK_METADATA


def list_available_tasks():
    """Display all available tasks with their descriptions."""
    print("\nAvailable tasks:")
    print("=" * 80)

    # Group by category
    by_category = {}
    for task_name, metadata in TASK_METADATA.items():
        category = metadata.get("category", "Other")
        if category not in by_category:
            by_category[category] = []
        by_category[category].append((task_name, metadata))

    # Print by category
    for category in sorted(by_category.keys()):
        print(f"\n{category}:")
        print("-" * 80)
        for task_name, metadata in sorted(by_category[category]):
            description = metadata.get("description", "No description")
            print(f"  {task_name:30} - {description}")

    print("\n" + "=" * 80)
    print(f"Total: {len(TASK_FUNCTIONS)} tasks available")
    print("\nUsage: uv run ./run_task.py <task_name> [task_params_json]")


def show_task_help(task_name):
    """Show detailed help for a specific task."""
    if task_name not in TASK_METADATA:
        print(f"Error: Task '{task_name}' not found")
        return False

    metadata = TASK_METADATA[task_name]
    print(f"\nTask: {task_name}")
    print("=" * 80)
    print(f"Category: {metadata.get('category', 'Unknown')}")
    print(f"Description: {metadata.get('description', 'No description')}")

    params = metadata.get("parameters", {})
    if params:
        print("\nParameters:")
        for param_name, param_info in params.items():
            required = param_info.get("required", False)
            param_type = param_info.get("type", "any")
            default = param_info.get("default", "N/A")
            desc = param_info.get("description", "")
            req_str = " (required)" if required else f" (default: {default})"
            print(f"  {param_name} ({param_type}){req_str}")
            if desc:
                print(f"    {desc}")

    examples = metadata.get("examples", [])
    if examples:
        print("\nExamples:")
        for example in examples:
            name = example.get("name", "")
            data = example.get("data", {})
            data_str = json.dumps(data) if data else ""
            print(f"  {name}:")
            print(f"    uv run ./run_task.py {task_name} '{data_str}'")

    print("=" * 80)
    return True


def run_task(task_name, params=None):
    """Run a task with the given parameters."""
    if task_name not in TASK_FUNCTIONS:
        print(f"Error: Task '{task_name}' not found")
        print("\nUse 'uv run ./run_task.py' to see available tasks")
        return False

    # Parse parameters
    task_params = {}
    if params:
        try:
            task_params = json.loads(params)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON parameters: {e}")
            return False

    print(f"\nRunning task: {task_name}")
    if task_params:
        print(f"Parameters: {json.dumps(task_params, indent=2)}")
    print("-" * 80)

    try:
        # Get the task function
        task_function = TASK_FUNCTIONS[task_name]

        # Run the task
        result = task_function(**task_params)

        # Display result
        print("\nTask completed!")
        print("=" * 80)
        print("Result:")
        print(json.dumps(result, indent=2, default=str))
        print("=" * 80)

        return True

    except Exception as e:
        print(f"\nError running task: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        list_available_tasks()
        return 0

    task_name = sys.argv[1]

    # Handle help flags
    if task_name in ["-h", "--help", "help"]:
        if len(sys.argv) > 2:
            # Show help for specific task
            show_task_help(sys.argv[2])
        else:
            list_available_tasks()
        return 0

    # Get optional parameters
    params = sys.argv[2] if len(sys.argv) > 2 else None

    # Run the task
    success = run_task(task_name, params)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
