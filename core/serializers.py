# core/serializers.py

from rest_framework import serializers
from core.models import Workflow, Run

class WorkflowSerializer(serializers.ModelSerializer):
    # only accept `prompt` on input, never return it
    prompt = serializers.CharField(write_only=True)
    # only return the S3 key, never accept it on input
    yaml_s3_key = serializers.CharField(read_only=True)

    class Meta:
        model = Workflow
        fields = [
            'id',
            'name',
            'prompt',
            'yaml_s3_key',
            'status',
            'webhook_uuid',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'webhook_uuid',
            'created_at',
            'updated_at',
        ]
        
class RunSerializer(serializers.ModelSerializer):
    # If you want the workflow ID in the output:
    workflow_id = serializers.UUIDField(source='workflow.id', read_only=True)

    class Meta:
        model = Run
        fields = [
            'id',
            'workflow_id',
            'kfp_run_id',
            'status',
            'started_at',
            'finished_at',
            'yaml_snapshot_s3_key',
        ]
        read_only_fields = fields