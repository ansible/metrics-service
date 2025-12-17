from dynaconf import Validator

validators = [
    Validator(
        "ALLOW_SHARED_RESOURCE_CUSTOM_ROLES",
        eq=False,
        messages={"operations": "ALLOW_SHARED_RESOURCE_CUSTOM_ROLES must be False in production."},
    ),
]
