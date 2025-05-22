from django.db import models
import uuid
from core.models.workflow import Workflow
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.conf import settings
import requests
import boto3
from botocore.client import Config as BotoConfig
import mimetypes
import logging

logger = logging.getLogger(__name__)

class Run(models.Model):
    class Status(models.TextChoices):
        PENDING   = 'PENDING',   'Pending'
        RUNNING   = 'RUNNING',   'Running'
        SUCCEEDED = 'SUCCEEDED', 'Succeeded'
        FAILED    = 'FAILED',    'Failed'

    id                   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow             = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='runs')
    kfp_run_id           = models.CharField(max_length=255, blank=True)
    status               = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    started_at           = models.DateTimeField(null=True, blank=True)
    finished_at          = models.DateTimeField(null=True, blank=True)
    yaml_snapshot_s3_key = models.CharField(max_length=1024, blank=True)
    run_url              = models.CharField(max_length=1024, blank=True)
    artifact_s3_key      = models.CharField(max_length=1024, blank=True, null=True)

    def __str__(self):
        return f"Run {self.id} - {self.status}"

    def fetch_and_archive_artifact(
        self,
        step_name: str = "performer",
        artifact_name: str = "podcast",
    ) -> str | None:
        from core.kfp_utils import find_artifact_uri

        download_url = find_artifact_uri(
            run_id=self.kfp_run_id,
            step_name=step_name,
            artifact_name=artifact_name,
        )
        if not download_url:
            return None

        resp = requests.get(download_url)
        resp.raise_for_status()
        content = resp.content

        # Determine extension
        content_type = resp.headers.get('Content-Type', 'application/octet-stream')
        ext = mimetypes.guess_extension(content_type) or ''
        key = f"runs/{self.id}/{artifact_name}{ext}"

        # Upload with content type
        bucket = getattr(settings, 'AWS_S3_BUCKET_NAME', None) or getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
        s3 = boto3.client(
            's3',
            endpoint_url=getattr(settings, 'AWS_S3_ENDPOINT_URL', None),
            region_name=getattr(settings, 'AWS_S3_REGION_NAME', None),
            aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
            aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
            config=BotoConfig(signature_version='s3v4')
        )
        try:
            s3.put_object(Bucket=bucket, Key=key, Body=content, ContentType=content_type)
        except Exception as e:
            logger.error("S3 upload failed: %s", e)
            default_storage.save(key, ContentFile(content))

        self.artifact_s3_key = key
        self.save(update_fields=['artifact_s3_key'])
        return key

    def get_assigned_artifact_url(self, expires_in: int = 3600) -> str | None:
        if not self.artifact_s3_key:
            return None
        try:
            from django.core.files.storage import default_storage
            from botocore.client import Config as BotoConfig
            # determine bucket
            bucket = getattr(default_storage, 'bucket_name', None) or getattr(settings, 'AWS_S3_BUCKET_NAME', None) or getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
            # boto3 client
            s3 = boto3.client(
                's3',
                endpoint_url=getattr(settings, 'AWS_S3_ENDPOINT_URL', None),
                region_name=getattr(settings, 'AWS_S3_REGION_NAME', None),
                aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
                aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
                config=BotoConfig(signature_version='s3v4')
            )
            return s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': self.artifact_s3_key},
                ExpiresIn=expires_in
            )
        except Exception as e:
            logger.error("Presign failed: %s", e)
            try:
                return default_storage.url(self.artifact_s3_key)
            except Exception:
                return None