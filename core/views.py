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

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Auth Serializers (for Swagger)
# -----------------------------------------------------------------------------

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

class TokenSerializer(serializers.Serializer):
    token = serializers.CharField()


# -----------------------------------------------------------------------------
# Login / Logout
# -----------------------------------------------------------------------------

@extend_schema(
    request=LoginSerializer,
    responses={
        200: TokenSerializer,
        400: OpenApiResponse(description="Email and password required"),
        401: OpenApiResponse(description="Invalid credentials"),
    }
)
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        email = request.data.get('email')
        password = request.data.get('password')
        if not email or not password:
            return Response(
                {'detail': 'Please provide email and password.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        user = authenticate(request, email=email, password=password)
        if not user:
            return Response(
                {'detail': 'Invalid credentials.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key})


@extend_schema(
    responses={204: OpenApiResponse(description="Logout successful")}
)
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# -----------------------------------------------------------------------------
# Workflow ViewSet
# -----------------------------------------------------------------------------

class WorkflowViewSet(
    OrgScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    list/retrieve workflows in your org (super-admin sees all).
    """
    queryset = Workflow.objects.all()
    serializer_class = WorkflowSerializer
    permission_classes = [IsActivePermission]


    @extend_schema(
        request=WorkflowSerializer,
        responses={202: OpenApiResponse(description="Returns new workflow ID")}
    )
    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        """
        Create a Workflow and immediately POST to the Gardener API.
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

        payload = {
            "prompt": workflow.prompt,
            "webhook_url": (
                f"{settings.CALLBACK_BASE_URL}/api/v1/"
                f"workflows/webhook/{workflow.webhook_uuid}/"
            )
        }

        try:
            resp = requests.post(
                f"{settings.GARDENER_URL}/generate",
                json=payload,
                timeout=10
            )
            resp.raise_for_status()
        except requests.RequestException:
            workflow.status = Workflow.Status.FAILED
            workflow.save(update_fields=["status"])
            return Response(
                {"detail": "Failed to start generation job."},
                status=status.HTTP_502_BAD_GATEWAY
            )

        workflow.status = Workflow.Status.RUNNING
        workflow.save(update_fields=["status"])

        return Response({'id': workflow.id}, status=status.HTTP_202_ACCEPTED)


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
            run.save(update_fields=['kfp_run_id','status','started_at'])

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
# Gardener Webhook
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
