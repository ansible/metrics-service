"""Django view that serves the BI Connector admin page."""

from django.views.generic import TemplateView


class BiAdminView(TemplateView):
    """Serve the BI Connector admin React SPA at /bi-admin/.

    No login is required at the Django level — authentication is performed
    in-page via a username/password form that sets Basic auth headers on
    every API request.
    """

    template_name = "bi_connector/admin.html"
