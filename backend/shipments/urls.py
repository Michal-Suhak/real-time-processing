from django.urls import path, include
from rest_framework.routers import DefaultRouter

# TODO: Import views when implemented
# from .views import ShipmentViewSet, CarrierViewSet

router = DefaultRouter()
# TODO: Register viewsets when implemented
# router.register(r'carriers', CarrierViewSet)
# router.register(r'shipments', ShipmentViewSet)

urlpatterns = [
    path('', include(router.urls)),
]