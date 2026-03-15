from rest_framework.permissions import BasePermission

from api.models import Church, ChurchAdmin


def _get_church_id_from_view(view):
    kwargs = getattr(view, "kwargs", {}) or {}
    return kwargs.get("church_id") or kwargs.get("pk")

class IsAuthenticatedUser(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, "role", None) == "SADMIN"

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, "role", None) == "ADMIN"

class IsChurchAdmin(BasePermission):
    """Permission to check if user is a church admin (OWNER or ADMIN role) for the specific church"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # SuperAdmin has all access
        if getattr(request.user, "role", None) == "SADMIN":
            return True

        # If church_id is in URL, verify access specifically for that church
        church_id = _get_church_id_from_view(view)
        if church_id:
            return ChurchAdmin.objects.filter(
                user=request.user,
                church_id=church_id,
                role__in=["OWNER", "ADMIN"]
            ).exists()

        # Fallback: Check if user has at least one church admin role (general access)
        return ChurchAdmin.objects.filter(
            user=request.user,
            role__in=["OWNER", "ADMIN"]
        ).exists()
    
    def has_object_permission(self, request, view, obj):
        # SuperAdmin has all access
        if getattr(request.user, "role", None) == "SADMIN":
            return True
        
        # Determine the church related to the object
        church = obj if isinstance(obj, Church) else getattr(obj, 'church', None)
        
        if not church:
            return False
            
        # Check if user is admin of this specific church
        return ChurchAdmin.objects.filter(
            user=request.user,
            church=church,
            role__in=["OWNER", "ADMIN"]
        ).exists()

def is_church_admin(user, church):
    return ChurchAdmin.objects.filter(
        user=user,
        church=church,
        role__in=["OWNER", "ADMIN"]
    ).exists()

def user_is_church_admin(user, church):
    return user.role == "SADMIN" or \
           ChurchAdmin.objects.filter(church=church, user=user).exists()

def user_is_church_owner(user, church):
    # SuperAdmin a toujours accès
    if user.role == "SADMIN":
        return True

    # Vérifier si l'utilisateur est OWNER dans ChurchAdmin
    return ChurchAdmin.objects.filter(
        user=user,
        church=church,
        role__in=["OWNER"]
    ).exists()

class IsChurchOwnerOrAdmin(BasePermission):
    """Permission to check if user is church owner or admin"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # SuperAdmin has all access
        if getattr(request.user, "role", None) == "SADMIN":
            return True

        church_id = _get_church_id_from_view(view)
        filters = {
            "user": request.user,
            "role__in": ["OWNER", "ADMIN"],
        }
        if church_id:
            filters["church_id"] = church_id
        return ChurchAdmin.objects.filter(**filters).exists()
    
    def has_object_permission(self, request, view, obj):
        # SuperAdmin has all access
        if getattr(request.user, "role", None) == "SADMIN":
            return True
        # Check if user is admin/owner of the church
        church = obj.church if hasattr(obj, 'church') else obj
        return ChurchAdmin.objects.filter(
            user=request.user,
            church=church,
            role__in=["OWNER", "ADMIN"]
        ).exists()

class IsTestimonyOwner(BasePermission):
    """Permission to check if user is the testimony owner or church admin"""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # SuperAdmin has all access
        if getattr(request.user, "role", None) == "SADMIN":
            return True
        # Testimony owner can edit
        if obj.created_by == request.user:
            return True
        # Church admin/owner can edit
        return ChurchAdmin.objects.filter(
            user=request.user,
            church=obj.church,
            role__in=["OWNER", "ADMIN"]
        ).exists()
