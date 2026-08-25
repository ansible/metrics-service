"""
Management command to load service ingest schemas from YAML files.

Reads all YAML files from schemas/service_ingest/<service>/<event>.yaml
and creates/updates ServiceDefinition records.

This command is idempotent and safe to run multiple times. It upserts
based on (service_name, event_name) unique constraint.
"""

import logging
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from jsonschema import Draft7Validator, ValidationError as JsonSchemaValidationError

from apps.service_ingest.models import ServiceDefinition
from apps.service_ingest.rollup import infer_rollup_config

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Load service ingest schemas from YAML files into ServiceDefinition table."""

    help = "Load service ingest schemas from schemas/service_ingest/ into the database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema-dir",
            type=str,
            default=None,
            help="Path to schemas directory (default: PROJECT_ROOT/schemas/service_ingest)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate schemas without saving to database",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed output for each schema",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        verbose = options["verbose"]

        # Determine schema directory
        if options["schema_dir"]:
            schema_dir = Path(options["schema_dir"])
        else:
            schema_dir = Path(settings.BASE_DIR) / "schemas" / "service_ingest"

        if not schema_dir.exists():
            raise CommandError(f"Schema directory not found: {schema_dir}")

        self.stdout.write(f"Loading schemas from: {schema_dir}")

        # Find all YAML files
        yaml_files = sorted(list(schema_dir.glob("*/*.yaml")) + list(schema_dir.glob("*/*.yml")))

        if not yaml_files:
            self.stdout.write(self.style.WARNING("No schema files found"))
            return

        created_count = 0
        updated_count = 0
        error_count = 0

        for yaml_path in yaml_files:
            try:
                schema_data = self._load_and_validate_yaml(yaml_path)

                if verbose:
                    self.stdout.write(f"  Processing: {yaml_path.relative_to(schema_dir)}")

                if not dry_run:
                    created = self._upsert_schema(schema_data, verbose)
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                else:
                    self.stdout.write(
                        f"    [DRY RUN] Would upsert: {schema_data['service_name']}/{schema_data['event_name']}"
                    )

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"  Error in {yaml_path.name}: {e}")
                )
                if verbose:
                    logger.exception(f"Failed to process {yaml_path}")

        # Summary
        self.stdout.write("")
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"Dry run complete: validated {len(yaml_files)} files")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Loaded {len(yaml_files)} schemas: "
                    f"{created_count} created, {updated_count} updated, {error_count} errors"
                )
            )

    def _load_and_validate_yaml(self, yaml_path: Path) -> dict:
        """Load YAML file and validate required fields."""
        with yaml_path.open() as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("Schema file must contain a YAML object (dict)")

        # Validate required fields
        required = [
            "service_name",
            "event_name",
            "display_name",
            "version",
            "segment_event_name",
            "payload_schema",
        ]
        missing = [f for f in required if f not in data]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        # Validate JSON Schema
        payload_schema = data["payload_schema"]
        if not isinstance(payload_schema, dict):
            raise ValueError("payload_schema must be a JSON object (dict)")

        try:
            Draft7Validator.check_schema(payload_schema)
        except JsonSchemaValidationError as e:
            raise ValueError(f"Invalid JSON Schema: {e.message}")

        # Validate rollup_config if present
        if "rollup_config" in data and data["rollup_config"]:
            self._validate_rollup_config(data["rollup_config"])

        return data

    def _validate_rollup_config(self, config: dict):
        """Validate explicit rollup config structure."""
        from apps.service_ingest.rollup import KNOWN_STRATEGIES

        if not isinstance(config, dict):
            raise ValueError("rollup_config must be a dict")

        strategy = config.get("strategy")
        if strategy and strategy not in KNOWN_STRATEGIES:
            raise ValueError(f"Unknown rollup strategy: {strategy}")

        for key in ["group_by", "stats_fields", "identifier_fields"]:
            if key in config and not isinstance(config[key], list):
                raise ValueError(f"rollup_config.{key} must be a list")

    def _upsert_schema(self, data: dict, verbose: bool) -> bool:
        """Create or update ServiceDefinition. Returns True if created."""
        rollup_config = data.get("rollup_config") or {}

        # Auto-infer rollup config if not provided
        if not rollup_config:
            rollup_config = infer_rollup_config(data["payload_schema"])
            if verbose:
                self.stdout.write(
                    f"    Auto-inferred rollup config: {rollup_config['strategy']}"
                )

        definition, created = ServiceDefinition.objects.update_or_create(
            service_name=data["service_name"],
            event_name=data["event_name"],
            defaults={
                "display_name": data["display_name"],
                "version": data["version"],
                "segment_event_name": data["segment_event_name"],
                "payload_schema": data["payload_schema"],
                "rollup_config": rollup_config,
                "validate_payload": data.get("validate_payload", False),
                "active": True,
            },
        )

        if verbose:
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"    {action}: {definition}"))

        return created
