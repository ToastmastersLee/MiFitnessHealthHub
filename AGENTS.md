# MiFitnessHealthHub working rules

- Read README.md and docs/BRIDGE_EVALUATION.md before changing the integration.
- Use synthetic data only in tests, fixtures, screenshots and reports.
- Do not read real account credentials or health records into an agent session without the user's specific authorization.
- Keep data/, work/, exports/, private/, databases and .env out of Git. Do not force-add ignored files.
- The bridge is an optional external dependency. Do not copy its connector source into this project.
- No automatic login, remote creation, push, telemetry or scheduled-task registration.
- Preserve the distinction between synthetic pipeline tests and Band 9 live compatibility.
- Run pytest and ruff after functional changes. Keep failure messages free of input values.
