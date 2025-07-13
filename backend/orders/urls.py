from django.urls import path, include
from rest_framework.routers import DefaultRouter

# TODO: Import views when implemented
# from .views import OrderViewSet, CustomerViewSet, PickingTaskViewSet

router = DefaultRouter()
# TODO: Register viewsets when implemented
# router.register(r'customers', CustomerViewSet)
# router.register(r'orders', OrderViewSet)
# router.register(r'picking-tasks', PickingTaskViewSet)

urlpatterns = [
    path('', include(router.urls)),
]