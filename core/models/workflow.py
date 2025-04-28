from django.db import models
import uuid
from .org import Org
class Workflow(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        FAILED = 'FAILED', 'Failed'
        READY = 'READY', 'Ready'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        Org,
        on_delete=models.CASCADE,
        related_name='workflows'
    )
    name = models.CharField(max_length=255)
    prompt = models.TextField()
    yaml_s3_key = models.CharField(max_length=1024, blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING
    )
    webhook_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.status})"
