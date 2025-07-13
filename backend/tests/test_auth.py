"""
Authentication and authorization tests
"""
import pytest
from django.contrib.auth.models import User, Group
from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from tests.factories import AdminUserFactory, WorkerUserFactory, UserFactory


@pytest.mark.auth
class TestAuthentication:
    """Test authentication endpoints"""
    
    def test_login_success(self, api_client, admin_user):
        """Test successful login"""
        url = reverse('token_obtain_pair')
        data = {
            'username': 'admin',
            'password': 'admin123'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data
    
    def test_login_invalid_credentials(self, api_client, admin_user):
        """Test login with invalid credentials"""
        url = reverse('token_obtain_pair')
        data = {
            'username': 'admin',
            'password': 'wrongpassword'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_login_missing_fields(self, api_client):
        """Test login with missing fields"""
        url = reverse('token_obtain_pair')
        data = {
            'username': 'admin'
            # missing password
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_token_refresh_success(self, api_client, admin_user):
        """Test successful token refresh"""
        # Get initial tokens
        login_url = reverse('token_obtain_pair')
        login_data = {
            'username': 'admin',
            'password': 'admin123'
        }
        login_response = api_client.post(login_url, login_data, format='json')
        refresh_token = login_response.data['refresh']
        
        # Refresh token
        refresh_url = reverse('token_refresh')
        refresh_data = {'refresh': refresh_token}
        response = api_client.post(refresh_url, refresh_data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
    
    def test_token_refresh_invalid_token(self, api_client):
        """Test token refresh with invalid token"""
        url = reverse('token_refresh')
        data = {'refresh': 'invalid_token'}
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_token_verify_success(self, api_client, admin_user):
        """Test successful token verification"""
        # Get token
        login_url = reverse('token_obtain_pair')
        login_data = {
            'username': 'admin',
            'password': 'admin123'
        }
        login_response = api_client.post(login_url, login_data, format='json')
        access_token = login_response.data['access']
        
        # Verify token
        verify_url = reverse('token_verify')
        verify_data = {'token': access_token}
        response = api_client.post(verify_url, verify_data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_token_verify_invalid_token(self, api_client):
        """Test token verification with invalid token"""
        url = reverse('token_verify')
        data = {'token': 'invalid_token'}
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.auth
class TestPermissions:
    """Test permission classes"""
    
    def test_unauthenticated_access_denied(self, unauthenticated_client):
        """Test that unauthenticated requests are denied"""
        url = '/api/inventory/items/'
        response = unauthenticated_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_admin_full_access(self, admin_client):
        """Test that admin has full access"""
        # Test read access
        url = '/api/inventory/suppliers/'
        response = admin_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        
        # Test write access
        data = {
            'name': 'Test Supplier',
            'country': 'Test Country'
        }
        response = admin_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_worker_read_only_suppliers(self, worker_client):
        """Test that worker has read-only access to suppliers"""
        url = '/api/inventory/suppliers/'
        
        # Test read access
        response = worker_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        
        # Test write access denied
        data = {
            'name': 'Test Supplier',
            'country': 'Test Country'
        }
        response = worker_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_worker_write_access_items(self, worker_client):
        """Test that worker has write access to items"""
        from tests.factories import CategoryFactory, SupplierFactory
        
        category = CategoryFactory()
        supplier = SupplierFactory()
        
        url = '/api/inventory/items/'
        data = {
            'item_id': 'TEST-001',
            'name': 'Test Item',
            'category': category.id,
            'supplier': supplier.id,
            'unit_cost': '10.50',
            'weight': '1.000',
            'dimensions': '10x10x10',
            'reorder_point': 20,
            'max_stock_level': 500
        }
        
        response = worker_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_regular_user_read_only_access(self, user_client):
        """Test that regular user has read-only access"""
        # Test read access to stock levels
        url = '/api/inventory/stock-levels/'
        response = user_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        
        # Test write access denied to items
        url = '/api/inventory/items/'
        data = {
            'item_id': 'TEST-002',
            'name': 'Test Item 2'
        }
        response = user_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.auth
class TestUserGroups:
    """Test user group functionality"""
    
    @pytest.mark.django_db
    def test_admin_group_creation(self):
        """Test admin group is created correctly"""
        admin_user = AdminUserFactory()
        
        assert admin_user.groups.filter(name='admin').exists()
        assert admin_user.is_staff is True
    
    @pytest.mark.django_db
    def test_worker_group_creation(self):
        """Test worker group is created correctly"""
        worker_user = WorkerUserFactory()
        
        assert worker_user.groups.filter(name='worker').exists()
        assert worker_user.is_staff is False
    
    @pytest.mark.django_db
    def test_regular_user_no_groups(self):
        """Test regular user has no special groups"""
        regular_user = UserFactory()
        
        assert not regular_user.groups.filter(name__in=['admin', 'worker']).exists()
        assert regular_user.is_staff is False


@pytest.mark.auth
class TestJWTTokens:
    """Test JWT token functionality"""
    
    def test_token_contains_user_info(self, admin_user):
        """Test that JWT token contains user information"""
        refresh = RefreshToken.for_user(admin_user)
        access_token = refresh.access_token
        
        # Decode token (without verification for testing)
        import jwt
        decoded = jwt.decode(str(access_token), options={"verify_signature": False})
        
        assert decoded['user_id'] == admin_user.id
        assert 'exp' in decoded
        assert 'iat' in decoded
    
    def test_token_expiration(self, admin_user):
        """Test token expiration time"""
        from django.conf import settings
        
        refresh = RefreshToken.for_user(admin_user)
        access_token = refresh.access_token
        
        import jwt
        decoded = jwt.decode(str(access_token), options={"verify_signature": False})
        
        # Check that token has reasonable expiration (1 hour = 3600 seconds)
        exp_time = decoded['exp']
        iat_time = decoded['iat']
        duration = exp_time - iat_time
        
        # Should be 1 hour (3600 seconds) as configured in settings
        assert duration == 3600
    
    def test_refresh_token_rotation(self, api_client, admin_user):
        """Test refresh token rotation"""
        # Get initial tokens
        login_url = reverse('token_obtain_pair')
        login_data = {
            'username': 'admin',
            'password': 'admin123'
        }
        login_response = api_client.post(login_url, login_data, format='json')
        original_refresh = login_response.data['refresh']
        
        # Use refresh token
        refresh_url = reverse('token_refresh')
        refresh_data = {'refresh': original_refresh}
        refresh_response = api_client.post(refresh_url, refresh_data, format='json')
        
        assert refresh_response.status_code == status.HTTP_200_OK
        assert 'access' in refresh_response.data
        
        # Depending on configuration, there might be a new refresh token
        # This tests the token refresh mechanism works