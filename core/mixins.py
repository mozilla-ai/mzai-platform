class OrgScopedMixin:
    """
    Mixin to limit queryset to the current user's org for org-scoped models.
    Usage: Inherit this mixin in your viewsets before GenericViewSet.
    """
    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # Super-admins see all
        if hasattr(user, 'role') and user.role == user.Role.SUPER_ADMIN:
            return qs
        # Otherwise filter by org
        return qs.filter(org=user.org)
