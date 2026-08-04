# Authentication & Request Flow

All external requests to metrics-service are routed through AAP Gateway, which validates the OAuth2 session and injects a signed JWT (`X-DAB-JW-TOKEN`) before forwarding to the service. Inside metrics-service, `ServicePrefixMiddleware` strips the `/api/metrics/` path prefix, then `JWTAuthentication` (from `django-ansible-base`) validates the JWT signature against `ANSIBLE_BASE_JWT_KEY` and gets-or-creates a local `User` object. DRF permission classes (`IsSystemAdminOrAuditor`) gate access before any ViewSet logic runs; a background `initial_resource_sync` task keeps the local identity store in sync with Gateway's resource registry.

```mermaid
sequenceDiagram
    participant C as Client (browser / BI tool)
    participant GW as AAP Gateway (OAuth2 + Envoy)
    participant NGINX as Nginx (metrics-service)
    participant MW as ServicePrefixMiddleware
    participant AUTH as JWTAuthentication (DAB)
    participant PERM as RBAC / Permission check
    participant VIEW as Django ViewSet
    participant DB as metrics-service PostgreSQL

    C->>GW: GET /api/metrics/v1/dashboard_reports/report/
    GW->>GW: Validate OAuth2 session
    GW->>NGINX: Forward + X-DAB-JW-TOKEN header
    NGINX->>MW: HTTP request
    MW->>MW: Strip /api/metrics prefix → /api/
    MW->>AUTH: Forward to Django URL routing
    AUTH->>AUTH: Verify JWT signature (ANSIBLE_BASE_JWT_KEY)
    AUTH->>AUTH: Extract user claims (username, roles, orgs)
    AUTH->>DB: get_or_create local User
    AUTH->>VIEW: request.user = User
    VIEW->>PERM: check_permissions() → IsSystemAdminOrAuditor
    PERM-->>VIEW: allowed (or 403)
    VIEW->>DB: QuerySet.filter(...)
    DB-->>VIEW: results
    VIEW-->>C: 200 JSON response

    Note over GW,AUTH: Resource sync (background, init task)
    GW->>AUTH: /api/v1/resource-registry/ (X-ANSIBLE-SERVICE-AUTH)
    AUTH->>DB: sync Users / Orgs / Teams / RBAC roles
```
