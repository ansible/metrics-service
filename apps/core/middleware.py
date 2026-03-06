"""Security middleware for the metrics service.

This module provides middleware to add security headers to HTTP responses.
"""


class SecurityHeadersMiddleware:
    """Middleware to add security headers to all HTTP responses.

    This middleware adds various security headers to protect against common web vulnerabilities:
    - Content Security Policy (CSP) to prevent XSS attacks
    - X-Content-Type-Options to prevent MIME type sniffing
    - X-Frame-Options to prevent clickjacking
    - X-XSS-Protection for legacy browser protection
    - Referrer-Policy to control referrer information leakage

    The CSP policy allows:
    - Scripts and styles from 'self' and Tailwind CDN
    - Inline scripts and styles (needed for dashboard functionality)
    - Images from 'self' and data: URIs
    - Fonts from 'self'
    - API connections to 'self'
    - Denies frame embedding
    """

    def __init__(self, get_response):
        """Initialize the middleware.

        Args:
            get_response: The next middleware or view in the chain
        """
        self.get_response = get_response

    def __call__(self, request):
        """Process the request and add security headers to the response.

        Args:
            request: The HTTP request object

        Returns:
            HttpResponse: The response with added security headers
        """
        response = self.get_response(request)

        # Content Security Policy (CSP)
        # Prevents XSS by controlling which resources can be loaded
        response["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )

        # X-Content-Type-Options
        # Prevents browsers from MIME-sniffing a response away from the declared content-type
        response["X-Content-Type-Options"] = "nosniff"

        # X-Frame-Options
        # Prevents clickjacking by not allowing the page to be embedded in frames
        response["X-Frame-Options"] = "DENY"

        # X-XSS-Protection
        # Enables XSS filtering in legacy browsers (modern browsers use CSP)
        response["X-XSS-Protection"] = "1; mode=block"

        # Referrer-Policy
        # Controls how much referrer information is shared
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions-Policy (formerly Feature-Policy)
        # Restricts which browser features and APIs can be used
        response["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        )

        return response
