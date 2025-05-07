# core/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    WorkflowViewSet,
    WorkflowWebhookView,
    RunViewSet,
    OrgTokenObtainPairView,

)
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
router = DefaultRouter()
router.register(r'workflows', WorkflowViewSet, basename='workflows')

urlpatterns = [

    path('token/', OrgTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),

    # webhook (must come before the router)
    path(
        'workflows/webhook/<uuid:webhook_uuid>/',
        WorkflowWebhookView.as_view(),
        name='workflow-webhook'
    ),

    # this pulls in:
    #   GET    /workflows/
    #   GET    /workflows/{pk}/
    #   POST   /workflows/{pk}/run/         ← your custom action
    #   POST   /workflows/generate/
    path('', include(router.urls)),

    # nested runs (optional, for your runs list/retrieve)
    path(
        'workflows/<uuid:workflow_pk>/runs/',
        RunViewSet.as_view({'get': 'list'}),
        name='workflow-runs-list'
    ),
    path(
        'workflows/<uuid:workflow_pk>/runs/<uuid:pk>/',
        RunViewSet.as_view({'get': 'retrieve'}),
        name='workflow-runs-detail'
    ),
]
