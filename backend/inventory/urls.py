from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    SupplierViewSet, CategoryViewSet, LocationViewSet, ItemViewSet,
    StockLevelViewSet, InventoryMovementViewSet
)

router = DefaultRouter()
router.register(r'suppliers', SupplierViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'locations', LocationViewSet)
router.register(r'items', ItemViewSet)
router.register(r'stock-levels', StockLevelViewSet)
router.register(r'movements', InventoryMovementViewSet)

urlpatterns = [
    path('', include(router.urls)),
]