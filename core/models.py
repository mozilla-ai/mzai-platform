# core/models.py
import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _


class Org(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class CustomUserManager(BaseUserManager):
    """
    Custom user manager where email is the unique identifier
    instead of usernames.
    """
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, org=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('role', CustomUser.Role.ORG_USER)
        # Org is required for regular users
        if org is None:
            raise ValueError('Regular users must be assigned an org')
        extra_fields['org'] = org
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', CustomUser.Role.SUPER_ADMIN)
        # Superusers have no org
        extra_fields['org'] = None

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        if extra_fields.get('role') != CustomUser.Role.SUPER_ADMIN:
            raise ValueError('Superuser must have role=SUPER_ADMIN.')

        return self._create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    # Remove username field
    username = None
    email = models.EmailField(_('email address'), unique=True)

    # Manager
    objects = CustomUserManager()

    # Override groups and permissions to avoid reverse accessor clashes
    groups = models.ManyToManyField(
        Group,
        related_name='customuser_set',
        blank=True,
        verbose_name=_('groups'),
        help_text=_(
            'The groups this user belongs to. A user will get all permissions '
            'granted to each of their groups.'
        ),
        related_query_name='user'
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name='customuser_set',
        blank=True,
        verbose_name=_('user permissions'),
        help_text=_(
            'Specific permissions for this user.'
        ),
        related_query_name='user'
    )

    # Additional fields
    display_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    org = models.ForeignKey(
        Org,
        on_delete=models.PROTECT,
        related_name='users',
        null=True,
        blank=True,
        help_text=_('Organization this user belongs to (not required for super-admins).')
    )

    class Role(models.TextChoices):
        SUPER_ADMIN = 'SUPER_ADMIN', 'Super Admin'
        ORG_USER = 'ORG_USER', 'Org User'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.ORG_USER
    )

    # Use email as the unique identifier
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.display_name or self.email


class Workflow(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        FAILED = 'FAILED', 'Failed'
        READY = 'READY', 'Ready'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        Org,
        on_delete=models.CASCADE,
        related_name='workflows'
    )
    name = models.CharField(max_length=255)
    prompt = models.TextField()
    yaml_s3_key = models.CharField(max_length=1024, blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING
    )
    webhook_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.status})"


class Run(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        SUCCEEDED = 'SUCCEEDED', 'Succeeded'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name='runs'
    )
    kfp_run_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    yaml_snapshot_s3_key = models.CharField(max_length=1024, blank=True)

    def __str__(self):
        return f"Run {self.id} - {self.status}"