# core/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LoginView,
    LogoutView,
    WorkflowViewSet,
    WorkflowWebhookView,
    RunViewSet,
)

router = DefaultRouter()
router.register(r'workflows', WorkflowViewSet, basename='workflows')

urlpatterns = [
    # auth
    path('login/',  LoginView.as_view(),  name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),

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
