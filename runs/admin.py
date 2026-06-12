from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from runs.models import AnalysisRun, Client, Profile, Tag


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0
    verbose_name_plural = "Client membership"


class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ("username", "email", "client_of", "is_staff", "is_active")

    @admin.display(description="Client")
    def client_of(self, obj):
        try:
            return obj.profile.client
        except Profile.DoesNotExist:
            return None


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(AnalysisRun)
class AnalysisRunAdmin(admin.ModelAdmin):
    """Read-only audit view of runs (use the app dashboard for day-to-day)."""

    list_display = ("id", "client", "status", "created_by", "created_at", "finished_at")
    list_filter = ("status", "client", "tags")
    search_fields = ("source_filename", "id")
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in AnalysisRun._meta.fields]

    def has_add_permission(self, request):
        return False
