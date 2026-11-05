# Testing the metrics_service sosreport plugin

The plugin is a single file, `metrics_service.py`. It is not packaged in the
metrics-service wheel (`pyproject.toml` only ships `metrics_service*` and
`apps*`); distribution into the container/operator image is an OS packaging
step. Test it by copying it onto a host that has `sos` installed.

## Local test procedure

```bash
# 1. Install the plugin where sos discovers plugins.
sudo cp tools/sosreport/metrics_service.py /usr/lib/python3.*/site-packages/sos/report/plugins/

# 2. Confirm sos sees it.
sudo sos report --list-plugins | grep metrics_service

# 3. Run only this plugin and keep the report in a scrap directory.
sudo sos report --only-plugins metrics_service --batch --tmp-dir /tmp/sos-test
```

If `metrics-service` is not on `root`'s `PATH` (for example a container image),
add a wrapper or run sos from the service's virtualenv.

## Expected assertions

After the report is extracted:

1. The plugin's directory exists in the report:
   `sosreport-*/sos_commands/metrics_service/` and
   `sosreport-*/etc/ansible-automation-platform/metrics_service/`.
2. The forbidden Segment key is absent:
   `test ! -e sosreport-*/etc/ansible-automation-platform/metrics/segment-write-key`
3. No secret values survive in collected settings overrides:
   ```bash
   grep -rE "SECRET_KEY|PASSWORD|RESOURCE_SERVER__SECRET_KEY|SEGMENT_WRITE_KEY" \
       sosreport-*/etc/ansible-automation-platform/metrics_service/ \
     | grep -v '\*\*\*\*\*\*\*\*'
   ```
   This should produce no output. Assignments are replaced with `********`
   regardless of spacing or quote style (`KEY='...'`, `KEY = "..."`,
   `KEY = '''...'''`).
4. The dry-run manifest was captured under
   `sosreport-*/sos_commands/metrics_service/` (the
   `metrics-service support-bundle --dry-run` command output), and no tarball
   was written into the report.

## Notes

- `support-bundle --dry-run` is used so sosreport never writes a bundle file.
- Logs are emitted to stdout rather than `/var/log/metrics-service`, so the
  plugin intentionally does not collect a log directory. The platform collects
  container/service stdout separately.
