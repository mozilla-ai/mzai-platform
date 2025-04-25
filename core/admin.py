# core/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import Org, CustomUser, Workflow, Run

@admin.register(Org)
class OrgAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('email', 'display_name', 'org', 'role', 'is_active')
    list_filter = ('role', 'is_active', 'org')
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('display_name',)}),
        (_('Organization'), {'fields': ('org',)}),
        (_('Permissions'), {
            'fields': (
                'role', 'is_active', 'is_staff', 
                'is_superuser', 'groups', 'user_permissions'
            )
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 'display_name', 'org', 
                'role', 'password1', 'password2',
                'is_active', 'is_staff'
            )
        }),
    )
    search_fields = ('email', 'display_name')
    filter_horizontal = ('groups', 'user_permissions',)

@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ('name','id','org', 'status', 'created_at', 'updated_at','webhook_uuid','yaml_s3_key')
    list_filter  = ('status', 'org')
    search_fields= ('name', 'prompt', 'webhook_uuid')

@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ('id', 'workflow', 'status', 'started_at', 'finished_at')
    list_filter  = ('status', 'workflow__org')
    search_fields= ('kfp_run_id',)
