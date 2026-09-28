"""Retain five synthetic deployment experiences in the configured Hindsight bank."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.hindsight_service import retain_deployment_experience

SEED_EXPERIENCES = [
    {
        "deployment_id": "DEP-025",
        "service": "Payment API",
        "environment": "Production",
        "changed_files": ["database.yml"],
        "change_summary": "Updated database connection configuration.",
        "result": "FAILED",
        "error": "Database connection timeout.",
        "root_cause": "Database connection pool size was too small.",
        "successful_fix": "Increased connection pool size from 10 to 30.",
        "lessons_learned": "Database configuration changes should validate connection pool settings before deployment.",
    },
    {
        "deployment_id": "DEP-031",
        "service": "Catalog API",
        "environment": "Production",
        "changed_files": ["redis.yml", "cache.py"],
        "change_summary": "Changed Redis endpoint and cache connection settings.",
        "result": "FAILED",
        "error": "Redis connection refused during startup.",
        "root_cause": "The service used the internal Redis hostname in a production network that required the managed endpoint.",
        "successful_fix": "Configured the production Redis endpoint and verified access from the application subnet.",
        "lessons_learned": "Validate Redis DNS and network reachability from the deployment environment.",
    },
    {
        "deployment_id": "DEP-034",
        "service": "Orders Worker",
        "environment": "Staging",
        "changed_files": ["deployment.yaml", "configmap.yaml"],
        "change_summary": "Updated Kubernetes environment variables for the worker.",
        "result": "FAILED",
        "error": "Pod entered CrashLoopBackOff after rollout.",
        "root_cause": "A required environment variable was misspelled, leaving the startup configuration invalid.",
        "successful_fix": "Corrected the variable name and verified the rendered pod environment before rollout.",
        "lessons_learned": "Validate required environment variable names and values in the rendered manifest.",
    },
    {
        "deployment_id": "DEP-038",
        "service": "Search API",
        "environment": "Production",
        "changed_files": ["gunicorn.conf.py", "Dockerfile"],
        "change_summary": "Adjusted application worker and thread configuration.",
        "result": "FAILED",
        "error": "API p95 latency increased under concurrent traffic.",
        "root_cause": "Worker threads were set too low for the blocking workload, increasing request queue time.",
        "successful_fix": "Raised the thread count based on load-test results and retained the previous value as rollback config.",
        "lessons_learned": "Use representative concurrency tests to validate worker and thread settings before production rollout.",
    },
    {
        "deployment_id": "DEP-041",
        "service": "Media Processor",
        "environment": "Production",
        "changed_files": ["docker-compose.yml", "cleanup.sh"],
        "change_summary": "Changed image retention and temporary-file handling.",
        "result": "FAILED",
        "error": "Container failed to write temporary files; node disk reached capacity.",
        "root_cause": "Old image layers and temporary artifacts were not removed, exhausting the node disk.",
        "successful_fix": "Removed unused images, enabled bounded log rotation, and added a pre-deploy disk-space check.",
        "lessons_learned": "Check available disk and image-cache growth before deployments that increase artifact usage.",
    },
]


def main() -> int:
    for experience in SEED_EXPERIENCES:
        result = retain_deployment_experience(experience)
        if getattr(result, "success", True) is False:
            print(f"Hindsight did not confirm storage for {experience['deployment_id']}.")
            return 1
        print(f"Stored {experience['deployment_id']} in Hindsight.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Unable to seed Hindsight memories: {exc}", file=sys.stderr)
        raise SystemExit(1)