"""
S3Uploader — Uploads a PDF to S3 and returns a presigned URL valid for 7 days.

The presigned URL allows Slack users to download the report without needing
AWS credentials. It expires automatically after 7 days.
"""

from __future__ import annotations

import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# 7 days — long enough for async reviewers, short enough to avoid stale links
PRESIGNED_EXPIRY_SECONDS = 7 * 24 * 3600


class S3Uploader:
    def __init__(self, bucket: str) -> None:
        self.bucket = bucket
        self.s3 = boto3.client("s3")

    def upload(self, key: str, pdf_bytes: bytes) -> str:
        """
        Upload pdf_bytes to s3://bucket/key and return a presigned GET URL.

        Args:
            key:       S3 object key, e.g. "reports/experiment-abc123.pdf"
            pdf_bytes: Raw PDF content

        Returns:
            Presigned HTTPS URL (valid for 7 days)
        """
        logger.info("Uploading PDF to s3://%s/%s (%d bytes)", self.bucket, key, len(pdf_bytes))

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=pdf_bytes,
            ContentType="application/pdf",
            # Server-side encryption using the default S3-managed key
            ServerSideEncryption="AES256",
            # Prevent public access — only presigned URL holders can download
            ACL="private",
            Metadata={
                "generator": "chaos-platform-report-generator",
            },
        )
        logger.info("Upload complete: s3://%s/%s", self.bucket, key)

        presigned_url = self.s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=PRESIGNED_EXPIRY_SECONDS,
        )
        logger.info("Presigned URL generated (expires in %ds)", PRESIGNED_EXPIRY_SECONDS)
        return presigned_url
