# core/serializers.py

from rest_framework import serializers
from core.models import Workflow, Run
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class WorkflowSerializer(serializers.ModelSerializer):

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
    workflow_id     = serializers.UUIDField(source='workflow.id', read_only=True)
    artifact_url    = serializers.SerializerMethodField()

    class Meta:
        model           = Run
        fields          = [
            'id', 
            'workflow_id',
            'kfp_run_id',
            'status',
            'started_at',
            'finished_at',
            'yaml_snapshot_s3_key',
            'run_url',
            'artifact_s3_key',
            'artifact_url'
        ]
        read_only_fields= fields

    def get_artifact_url(self, obj: Run) -> str | None:
        return obj.get_assigned_artifact_url()

class OrgTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        # Get the standard token (refresh + access)
        token = super().get_token(user)

        # Add custom claims
        # Make sure your CustomUser has an .org relation
        token['org_id'] = str(user.org.id)       # e.g. UUIDField
        token['org_name'] = user.org.name        # optional human-readable

        return token