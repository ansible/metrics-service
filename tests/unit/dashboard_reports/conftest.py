"""
Shared fixtures for dashboard_reports unit tests.
"""

from rest_framework.response import Response

from apps.dashboard_reports.viewsets.dashboard_report import require_date_range


class DummyView:
    """
    Dummy view class for testing the require_date_range decorator.
    Simulates a view with request and kwargs attributes.
    """

    def __init__(self):
        self.called = False
        self.last_args = None
        self.kwargs = {}

    @require_date_range
    def view(self, request, *args, **kwargs):
        self.called = True
        self.last_args = args
        self.kwargs = kwargs
        return Response({"success": True})
