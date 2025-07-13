from django.urls import path, include
from rest_framework.routers import DefaultRouter

# TODO: Import views when implemented
# from .views import AlertViewSet, MetricViewSet, ReportViewSet

router = DefaultRouter()
# TODO: Register viewsets when implemented
# router.register(r'alerts', AlertViewSet)
# router.register(r'metrics', MetricViewSet)
# router.register(r'reports', ReportViewSet)

urlpatterns = [
    path('', include(router.urls)),
]