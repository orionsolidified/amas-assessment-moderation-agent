# Object storage

## Local demonstration profile

The Compose stack uses Garage in single-node mode with persistent Docker volumes. It automatically creates the configured access key and default bucket.

This mode provides S3-compatible behavior for a workshop demonstration. It has no replication and should not be treated as institutional high availability.

## Object layout

```text
originals/{tenant}/{case_id}/{artifact_type}/{sha256}-{filename}
reports/{tenant}/{case_id}/v{report_version}-{sha256}.json
knowledge/...
evals/...
```

## Setup against a generic S3-compatible service

Configure `deploy/.env`, install an AWS-compatible CLI, then run:

```bash
set -a
source deploy/.env
set +a
./storage/setup_s3.sh
```

The script:

- creates the bucket when absent;
- creates logical prefixes;
- attempts to install the lifecycle policy;
- lists the resulting bucket.

Some S3-compatible services do not implement lifecycle APIs identically. In that case, enforce retention through the platform's native policy or an operational job.

## IAM policy

`storage/s3-iam-policy.json` restricts access to the AMAS bucket and expected prefixes. Replace the literal bucket name if `S3_BUCKET` differs from `amas`.

Use separate credentials for:

- intake/report archival read-write access;
- backup administration;
- read-only audit access, if needed.

## Production controls

- private network endpoint where available;
- TLS certificate validation;
- server-side encryption with institution-managed keys where required;
- object versioning or immutability for canonical reports;
- access logging;
- replication and tested recovery;
- lifecycle rules based on approved retention;
- alerts for public-access policy changes;
- no browser exposure of S3 credentials.

## Integrity verification

PostgreSQL stores SHA-256 hashes and storage keys. Periodically sample objects, recompute hashes, and compare them with database records. Report archives are canonical JSON serialized with sorted keys before hashing.
