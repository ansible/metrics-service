"""
URL configuration for dynamic_settings app.

This file defines URL patterns specific to this app. It is automatically loaded
by the platform-service-framework when the app is registered and discovered via
the LOADED_APPS mechanism.

## LOADED_APPS Mechanism

The framework dynamically discovers and loads URL patterns from apps:

1. **App registration**: Apps must be added to the `project_applications` list
   in `apps/settings.py` (e.g., "apps.myapp").

2. **Discovery**: At runtime, the framework filters `INSTALLED_APPS` for entries
   that start with "apps." and have a corresponding directory in the apps folder.

3. **LOADED_APPS population**: The filtered list becomes `settings.LOADED_APPS`,
   preserving the order defined in `project_applications`.

4. **URL loading**: The framework imports each app's urls.py and appends any
   `urlpatterns` to the main URL configuration. If this file doesn't exist or
   has no urlpatterns, the app is silently skipped.

## Controlling URL Loading Order

Django uses first-match routing, so loading order determines which pattern
handles a request when multiple patterns could match.

**Example conflict**: If both `apps.core` and `apps.api` define a pattern for
`api/v1/users/`, only the first-loaded app's pattern will handle requests.
The other pattern becomes unreachable.

You have two options to control this:

### Option 1: Reorder apps in `project_applications`

The URL loading order follows the order in `project_applications` in
`apps/settings.py`. Reordering apps there changes their URL loading order.

- If `project_applications = ["apps.core", "apps.api"]`, core's URLs load first
- If two apps define the same URL pattern, the first one in the list wins

**Trade-offs**:
- Changing app order affects settings loading order (each app's settings.py
  is loaded in this order)
- This changes URL loading order for ALL URLs in the app - you cannot load
  a single URL from app B before app A while keeping the rest of app B after

Use this when you want to change the overall priority of an entire app.

### Option 2: Use `apps/urls.py`

The `apps/urls.py` file loads BEFORE all individual app URL patterns, giving
you a way to define URLs that are independent of app order. This provides
finer control:

- Add a single high-priority URL without reordering apps
- Define URLs that don't belong to any specific app
- Override patterns from any app regardless of app order

Use this for service-level customizations, cross-app endpoints, or when you
need a specific URL to take priority without changing app order.

## Full URL Loading Order

1. Django Ansible Base URLs (DAB)
2. Dynamic API root view overrides
3. Cross-app/custom URL patterns (apps/urls.py) <-- use this for priority URLs
4. >>> Individual app URL patterns (this file, order from project_applications) <<<
5. Debug/development URLs

## Best Practices

- Use versioned paths for API endpoints: path("api/v1/...", ...)
- Use descriptive names for reverse URL lookups: name="resource-list"
- Keep URL patterns focused on this app's domain
- For cross-app or priority URLs, use apps/urls.py instead

"""

from django.urls import include, path

app_name = "dynamic_settings"

urlpatterns = [
    path("api/v1/settings/", include("apps.dynamic_settings.v1.urls", namespace="v1")),
]
