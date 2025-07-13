"""
Test configuration and fixtures for the warehouse management system
"""
import pytest
from django.contrib.auth.models import User, Group
from django.test import Client
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker):
    """
    Database setup for tests
    """
    with django_db_blocker.unblock():
        # Create user groups
        Group.objects.get_or_create(name='admin')
        Group.objects.get_or_create(name='worker')


@pytest.fixture
def api_client():
    """
    DRF API client
    """
    return APIClient()


@pytest.fixture
def admin_user(db):
    """
    Create admin user
    """
    user = User.objects.create_user(
        username='admin',
        email='admin@warehouse.com',
        password='admin123',
        is_staff=True
    )
    admin_group = Group.objects.get(name='admin')
    user.groups.add(admin_group)
    return user


@pytest.fixture
def worker_user(db):
    """
    Create worker user
    """
    user = User.objects.create_user(
        username='worker',
        email='worker@warehouse.com',
        password='worker123'
    )
    worker_group = Group.objects.get(name='worker')
    user.groups.add(worker_group)
    return user


@pytest.fixture
def regular_user(db):
    """
    Create regular user (no special groups)
    """
    return User.objects.create_user(
        username='user',
        email='user@warehouse.com',
        password='user123'
    )


@pytest.fixture
def admin_client(api_client, admin_user):
    """
    API client authenticated as admin
    """
    refresh = RefreshToken.for_user(admin_user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return api_client


@pytest.fixture
def worker_client(api_client, worker_user):
    """
    API client authenticated as worker
    """
    refresh = RefreshToken.for_user(worker_user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return api_client


@pytest.fixture
def user_client(api_client, regular_user):
    """
    API client authenticated as regular user
    """
    refresh = RefreshToken.for_user(regular_user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return api_client


@pytest.fixture
def unauthenticated_client():
    """
    Unauthenticated API client
    """
    return APIClient()