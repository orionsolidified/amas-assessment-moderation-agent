#!/usr/bin/env bash
set -euo pipefail
: "${S3_ENDPOINT:?}" "${S3_ACCESS_KEY:?}" "${S3_SECRET_KEY:?}"
S3_REGION=${S3_REGION:-garage}
S3_BUCKET=${S3_BUCKET:-amas}
export AWS_ACCESS_KEY_ID=$S3_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$S3_SECRET_KEY AWS_DEFAULT_REGION=$S3_REGION
aws --endpoint-url "$S3_ENDPOINT" s3api head-bucket --bucket "$S3_BUCKET" 2>/dev/null || \
  aws --endpoint-url "$S3_ENDPOINT" s3api create-bucket --bucket "$S3_BUCKET"
for prefix in originals reports knowledge evals; do
  printf '' | aws --endpoint-url "$S3_ENDPOINT" s3 cp - "s3://$S3_BUCKET/$prefix/.keep"
done
if aws --endpoint-url "$S3_ENDPOINT" s3api put-bucket-lifecycle-configuration \
  --bucket "$S3_BUCKET" --lifecycle-configuration "file://$(dirname "$0")/s3-lifecycle.json"; then
  echo "Lifecycle configuration installed"
else
  echo "Object store does not support this lifecycle operation; enforce retention operationally." >&2
fi
aws --endpoint-url "$S3_ENDPOINT" s3 ls "s3://$S3_BUCKET/"
