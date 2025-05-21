# core/views.py

from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.conf import settings
from django.utils import timezone

from rest_framework import status, viewsets, mixins, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.reverse import reverse  

from drf_spectacular.utils import extend_schema, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from core.models import Workflow, Run
from .serializers import WorkflowSerializer, RunSerializer
from .permissions import IsActivePermission
from .mixins import OrgScopedMixin

import requests
import tempfile
from kfp import Client
import logging
import yaml

from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import OrgTokenObtainPairSerializer

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Temporary component descriptions and input metadata this will be removed after POC
# -----------------------------------------------------------------------------
COMPONENT_DESCRIPTIONS = {
    'comp-downloader': 'Downloads the source document from the provided URL.',
    'comp-transformer': 'Transforms the downloaded document into a standardized format (Markdown).',
    'comp-scriptwriter': 'Generates a podcast script from the processed document.',
    'comp-performer': 'Converts the podcast script into speech/audio using the specified voice profiles.',
}

def get_component_description(component_name):
    """
    Return a human-friendly description for the given component.
    Falls back to the raw component name if no description is found.
    """
    return COMPONENT_DESCRIPTIONS.get(component_name, component_name)

INPUT_METADATA = {
    'comp-downloader': {
        'document_url': {'required': True},
    },
    'comp-transformer': {
        'file_type': {'default_value': '.html'},
    },
    'comp-scriptwriter': {
        'cohost_name': {'default_value': 'Michael'},
        'host_name': {'default_value': 'Sarah'},
        'model': {'default_value': 'bartowski/Qwen2.5-7B-Instruct-GGUF/Qwen2.5-7B-Instruct-Q8_0.gguf'},
    },
    'comp-performer': {
        'audio_format': {'default_value': 'WAV'},
        'cohost_voice_profile': {'default_value': 'am_michael'},
        'host_voice_profile': {'default_value': 'af_sarah'},
        'model': {'default_value': 'hexgrad/Kokoro-82M'},
    },
}

def get_input_metadata(component_name, input_name):
    """
    Return a dict containing either 'required': True or
    'default_value': <value> for the given component input.
    """
    meta = INPUT_METADATA.get(component_name, {}).get(input_name, {})
    if 'default_value' in meta:
        return {'default_value': meta['default_value']}
    return {'required': True}

# -----------------------------------------------------------------------------
# Auth Serializers (for Swagger)
# -----------------------------------------------------------------------------

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

class TokenSerializer(serializers.Serializer):
    token = serializers.CharField()

# -----------------------------------------------------------------------------
# Workflow ViewSet
# -----------------------------------------------------------------------------

class WorkflowViewSet(
    OrgScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Workflow.objects.all()
    serializer_class = WorkflowSerializer
    permission_classes = [IsActivePermission]

    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        """
        Create a Workflow in PENDING state, synchronously call Composer,
        save the YAML, mark READY (or FAILED), then redirect to details.
        """
        if request.user.org is None:
            return Response(
                {'detail': 'You must belong to an organization to generate workflows.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        workflow = serializer.save(
            org=request.user.org,
            status=Workflow.Status.PENDING
        )

        try:
            resp = requests.post(
                settings.WORKFLOW_COMPOSER_URL,
                params={'prompt': workflow.prompt},
                timeout=30
            )
            resp.raise_for_status()
            yaml_str = resp.text

            key = f'mzai-platform-workflows/{workflow.id}.yaml'
            default_storage.save(key, ContentFile(yaml_str.encode('utf-8')))

            workflow.yaml_s3_key = key
            workflow.status = Workflow.Status.READY
            workflow.save(update_fields=['yaml_s3_key', 'status'])

        except requests.RequestException as e:
            # mark FAILED on network/HTTP errors
            workflow.status = Workflow.Status.FAILED
            workflow.save(update_fields=['status'])
            return Response(
                {'detail': f'Failed to generate workflow: {e}'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as e:
            # mark FAILED on any parsing/storage error
            workflow.status = Workflow.Status.FAILED
            workflow.save(update_fields=['status'])
            return Response(
                {'detail': f'Error processing workflow output: {e}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        details_url = reverse(
            'workflows-detail',        
            kwargs={'pk': workflow.id},
            request=request
        )

        return Response(status=status.HTTP_303_SEE_OTHER, headers={'Location': details_url})

    def retrieve(self, request, pk=None):
        """
        Returns:
        {
            <all WorkflowSerializer fields...>,
            "json": {
                "workflowId": ...,
                "description": ...,
                "steps": [ ... ]
            }
        }
        """
        workflow = self.get_object()
        # 1. serialize all the metadata
        meta_serializer = self.get_serializer(workflow)
        metadata = meta_serializer.data

        # 2. if not ready, short-circuit
        if workflow.status != Workflow.Status.READY:
            return Response(
                {'detail': 'Workflow not ready yet.'},
                status=status.HTTP_200_OK
            )

        # 3. load & parse YAML just like before
        try:
            raw = default_storage.open(workflow.yaml_s3_key).read().decode('utf-8')
            spec = yaml.safe_load(raw)
        except Exception as e:
            return Response(
                {'detail': f'Error loading workflow spec: {e}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        executors = spec.get('deploymentSpec', {}).get('executors', {})
        executor_images = {
            label: defs.get('container', {}).get('image')
            for label, defs in executors.items()
        }

        # 4. build the “inner” JSON exactly as before
        inner = {
            'workflowId': workflow.id,
            'description': spec.get('pipelineInfo', {}).get('description', ''),
            'steps': []
        }

        tasks = spec.get('root', {}).get('dag', {}).get('tasks', {})
        components = spec.get('components', {})

        for name, task in tasks.items():
            comp_name = task.get('componentRef', {}).get('name')
            executor_label = components.get(comp_name, {}).get('executorLabel')
            image = executor_images.get(executor_label)

            step = {
                'id': name,
                'description': get_component_description(comp_name),
                'inputs': [],
                'image': image
            }

            for param in task.get('inputs', {}).get('parameters', {}):
                meta = get_input_metadata(comp_name, param)
                step['inputs'].append({
                    'name': param,
                    'type': 'string',
                    **meta
                })

            inner['steps'].append(step)

        # 5. wrap it all together under the "json" key
        envelope = {
            **metadata,
            'json': inner
        }

        return Response(envelope, status=status.HTTP_200_OK)

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={202: OpenApiResponse(description="Returns new run ID")}
    )
    @action(detail=True, methods=['post'], url_path='run')
    def run(self, request, pk=None):
        """
        Launch a READY workflow on Kubeflow Pipelines:
         - Creates Run (PENDING)
         - Downloads YAML
         - Submits to KFP
         - Updates Run (RUNNING)
        """
        workflow = self.get_object()
        if workflow.status != Workflow.Status.READY:
            return Response(
                {"detail": "Workflow must be READY to run."},
                status=status.HTTP_400_BAD_REQUEST
            )

        run = Run.objects.create(
            workflow=workflow,
            status=Run.Status.PENDING,
            yaml_snapshot_s3_key=workflow.yaml_s3_key,
        )

        try:
            blob = default_storage.open(workflow.yaml_s3_key).read()
        except Exception:
            run.status = Run.Status.FAILED
            run.save(update_fields=['status'])
            return Response(
                {"detail": "Could not fetch YAML from storage."},
                status=status.HTTP_502_BAD_GATEWAY
            )

        with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False) as tmp:
            tmp.write(blob)
            tmp_path = tmp.name

        pipeline_params = request.data or {}
        logger.exception(f" submitting run with this pipeline params {pipeline_params}")
        try:
            client = Client(
                host=settings.KFP_API_URL,
                existing_token=settings.KFP_AUTH_TOKEN
            )
            exp = client.create_experiment('mzai-platform-poc')
            full_name = getattr(exp, 'name', '')
            if '/' in full_name:
                exp_id = full_name.rsplit('/', 1)[-1]
            else:
                exp_id = getattr(exp, 'id', None) or getattr(exp, 'experiment_id', None)

            res = client.run_pipeline(
                experiment_id=exp_id,
                job_name=f"run-{run.id}",
                pipeline_package_path=tmp_path,
                params=pipeline_params,
            )

            run.kfp_run_id = getattr(res, 'id', None) or getattr(res, 'run_id', None)
            run.status     = Run.Status.RUNNING
            run.started_at = timezone.now()
            base = settings.KFP_API_URL.rstrip('/')
            run.run_url = f"{base}/#/runs/details/{run.kfp_run_id}"
            run.save(update_fields=['kfp_run_id','status','started_at','run_url'])

        except Exception as e:
            logger.exception(f"Error submitting run {run.id} to KFP")
            run.status = Run.Status.FAILED
            run.save(update_fields=['status'])
            return Response(
                {"detail": f"Failed to submit to Kubeflow: {e}"},
                status=status.HTTP_502_BAD_GATEWAY
            )

        return Response({"id": str(run.id)}, status=status.HTTP_202_ACCEPTED)


# -----------------------------------------------------------------------------
# Workflow Composer Webhook - currently not used 
# -----------------------------------------------------------------------------

class WorkflowWebhookView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=OpenApiTypes.BINARY,
        responses={200: OpenApiResponse(description="Webhook received")}
    )
    def post(self, request, webhook_uuid):
        workflow = get_object_or_404(Workflow, webhook_uuid=webhook_uuid)

        status_str = request.headers.get('X-Workflow-Status') or request.query_params.get('status')
        if status_str not in Workflow.Status.values:
            return Response({'detail':'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        workflow.status = status_str

        if request.content_type in ('application/x-yaml','text/yaml'):
            yaml_str = request.body.decode('utf-8')
        else:
            return Response(
                {'detail':'Content-Type must be application/x-yaml'},
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
            )

        if status_str == Workflow.Status.READY:
            key = f'workflows/{workflow.id}.yaml'
            default_storage.save(key, ContentFile(yaml_str.encode()))
            workflow.yaml_s3_key = key

        workflow.save(update_fields=['status','yaml_s3_key'])
        return Response(status=status.HTTP_200_OK)


# -----------------------------------------------------------------------------
# Run ViewSet (nested)
# -----------------------------------------------------------------------------

class RunViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    """
    list/retrieve runs for a given workflow (nested route).
    """
    serializer_class = RunSerializer
    permission_classes = [IsAuthenticated, IsActivePermission]

    @extend_schema(exclude=True)
    def get_queryset(self):
        user = self.request.user
        workflow_pk = self.kwargs['workflow_pk']
        qs = Run.objects.filter(workflow_id=workflow_pk)
        if user.org is not None:
            qs = qs.filter(workflow__org=user.org)
        return qs
    def retrieve(self, request, *args, **kwargs):
        run = self.get_object()

        # 1) Pull live .state from KFP
        try:
            kfp = Client(
                host=settings.KFP_API_URL,
                existing_token=settings.KFP_AUTH_TOKEN
            )
            # v2 SDK returns V2beta1Run directly
            kfp_run = kfp.get_run(run.kfp_run_id)
            new_state = kfp_run.state.upper()
        except Exception:
            logger.exception("Failed to fetch KFP run %s", run.kfp_run_id)
            new_state = run.status

        # 2) If it’s changed—and hit a terminal state—update DB
        if new_state != run.status:
            run.status = new_state
            if new_state in (Run.Status.SUCCEEDED, Run.Status.FAILED):
                run.finished_at = timezone.now()
            run.save(update_fields=['status', 'finished_at'])

        # 3) Now return the usual serializer response
        return super().retrieve(request, *args, **kwargs)

class OrgTokenObtainPairView(TokenObtainPairView):
    serializer_class = OrgTokenObtainPairSerializer
