from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """
    Permission for admin users only.
    Full access to all operations including user management, system configuration,
    and sensitive operations like deleting records.
    """
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        return request.user.is_superuser or (
            hasattr(request.user, 'groups') and 
            request.user.groups.filter(name='admin').exists()
        )


class IsWorker(BasePermission):
    """
    Permission for worker users.
    Access to day-to-day warehouse operations like inventory movements,
    order processing, and shipment handling.
    """
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        return request.user.is_superuser or (
            hasattr(request.user, 'groups') and 
            request.user.groups.filter(name__in=['admin', 'worker']).exists()
        )


class IsAdminOrWorker(BasePermission):
    """
    Permission for both admin and worker users.
    Most warehouse operations should use this permission.
    """
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        return request.user.is_superuser or (
            hasattr(request.user, 'groups') and 
            request.user.groups.filter(name__in=['admin', 'worker']).exists()
        )


class IsAdminOrReadOnly(BasePermission):
    """
    Read access for all authenticated users.
    Write access only for admin users.
    Used for configuration endpoints like suppliers, categories, locations.
    """
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Read access for all authenticated users
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        
        # Write access only for admins
        return request.user.is_superuser or (
            hasattr(request.user, 'groups') and 
            request.user.groups.filter(name='admin').exists()
        )


class IsWorkerOrReadOnly(BasePermission):
    """
    Read access for all authenticated users.
    Write access for workers and admins.
    Used for operational endpoints like inventory movements, orders.
    """
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Read access for all authenticated users
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        
        # Write access for workers and admins
        return request.user.is_superuser or (
            hasattr(request.user, 'groups') and 
            request.user.groups.filter(name__in=['admin', 'worker']).exists()
        )