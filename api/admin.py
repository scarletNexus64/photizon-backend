from django.contrib import admin
from .models import (
    Church, ChurchAdmin, Subscription, SubscriptionPlan, Notification,
    Content, Category, BookOrder, Ticket, Payment,
    ServiceConfiguration, User, Commission, ChurchCommission,
    Donation, DonationCategory, Receipt,
    Testimony, ChurchCollaboration, Programme, ProgrammeMember
)

# =====================================================
# GESTION DES UTILISATEURS (Fonctionnalité 2)
# =====================================================

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "name", "email", "role", "current_church", "city", "country", "is_active", "is_staff", "created_at")
    search_fields = ("phone_number", "name", "email", "city", "country")
    list_filter = ("role", "is_active", "is_staff", "is_superuser", "country")
    readonly_fields = ("id", "created_at", "updated_at", "last_login")

    fieldsets = (
        ("Informations de base", {
            "fields": ("phone_number", "name", "email", "picture_url")
        }),
        ("Rôle et église", {
            "fields": ("role", "current_church")
        }),
        ("Localisation", {
            "fields": ("address", "city", "country", "longitude", "latitude")
        }),
        ("Permissions", {
            "fields": ("is_active", "is_staff", "is_superuser"),
            "classes": ("collapse",)
        }),
        ("Informations système", {
            "fields": ("id", "created_at", "updated_at", "last_login"),
            "classes": ("collapse",)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('current_church')

# =====================================================
# GESTION DES ÉGLISES (Fonctionnalité 1)
# =====================================================

@admin.register(Church)
class ChurchAdminAdmin(admin.ModelAdmin):
    list_display = ("title","code","owner","status","is_verified","members_count","created_at")
    search_fields = ("title","code","owner__phone_number")
    list_filter = ("status","is_verified","country","city")
    readonly_fields = ("code","slug","created_at","members_count","admins_count","profile_views")

    fieldsets = (
        ("Informations de base", {
            "fields": ("title","slug","owner","status","lang","description")
        }),
        ("Branding", {
            "fields": ("logo_url","primary_color","secondary_color"),
            "classes": ("collapse",)
        }),
        ("Contact", {
            "fields": ("email","phone_number_1","phone_number_2","phone_number_3","phone_number_4","website","whatsapp_phone"),
            "classes": ("collapse",)
        }),
        ("Réseaux sociaux", {
            "fields": ("facebook_url","instagram_url","youtube_url","tiktok_url"),
            "classes": ("collapse",)
        }),
        ("Localisation", {
            "fields": ("city","country","longitude","latitude")
        }),
        ("Relations", {
            "fields": ("parent",)
        }),
        ("Paramètres", {
            "fields": ("is_public","is_verified","look_actuality","seats")
        }),
        ("Statistiques", {
            "fields": ("members_count","admins_count","profile_views"),
            "classes": ("collapse",)
        }),
        ("Informations système", {
            "fields": ("code","created_at","updated_at"),
            "classes": ("collapse",)
        }),
    )

@admin.register(ChurchAdmin)
class ChurchAdminInline(admin.ModelAdmin):
    list_display = ("church","user","role","created_at")
    search_fields = ("church__title","user__phone_number")
    list_filter = ("role","church")
    readonly_fields = ("created_at",)

# =====================================================
# ABONNEMENTS SAAS (Fonctionnalité 1)
# =====================================================

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("display_name", "name", "price", "currency", "duration_days", "is_active", "order")
    list_filter = ("is_active", "has_chat", "has_programmes", "has_analytics")
    search_fields = ("name", "display_name", "description")
    ordering = ("order", "price")

    fieldsets = (
        ("Informations de base", {
            "fields": ("name", "display_name", "description", "order", "is_active")
        }),
        ("Prix et validité", {
            "fields": ("price", "currency", "duration_days")
        }),
        ("Limites", {
            "fields": ("max_members", "max_contents", "max_storage_gb")
        }),
        ("Fonctionnalités", {
            "fields": ("has_chat", "has_programmes", "has_analytics", "has_custom_branding", "features")
        }),
    )

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("church", "get_plan_display", "subscription_plan", "is_active", "started_at", "expires_at")
    list_filter = ("plan", "is_active", "subscription_plan")
    search_fields = ("church__title",)

    def get_plan_display(self, obj):
        return obj.get_plan_name()
    get_plan_display.short_description = "Plan actuel"

# =====================================================
# GESTION DES CONTENUS (Fonctionnalité 3)
# =====================================================

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name","slug")
    search_fields = ("name","slug")
    readonly_fields = ("slug",)

@admin.register(Content)
class ContentAdmin(admin.ModelAdmin):
    list_display = ("title","type","church","created_by","published","get_status_display","is_paid","price","start_at","created_at")
    search_fields = ("title","slug","church__title","created_by__phone_number")
    list_filter = ("type","published","is_paid","is_public","delivery_type","church","created_at")
    readonly_fields = ("id","slug","created_at","updated_at","tickets_sold")
    date_hierarchy = "created_at"

    fieldsets = (
        ("Informations de base", {
            "fields": ("church","type","title","slug","description","cover_image_url","category","created_by")
        }),
        ("Médias", {
            "fields": ("audio_url","video_url","file"),
            "classes": ("collapse",)
        }),
        ("Événement", {
            "fields": ("start_at","end_at","location","capacity","tickets_sold","allow_ticket_sales"),
            "classes": ("collapse",)
        }),
        ("Tarification", {
            "fields": ("is_paid","price","currency","delivery_type","phone")
        }),
        ("Billetterie Multi-Niveaux", {
            "fields": ("has_ticket_tiers","classic_price","classic_quantity","vip_price","vip_quantity","premium_price","premium_quantity"),
            "classes": ("collapse",),
            "description": "Pour les événements avec plusieurs types de billets"
        }),
        ("Coming Soon", {
            "fields": ("planned_release_date",),
            "classes": ("collapse",),
            "description": "Date de publication programmée"
        }),
        ("Visibilité", {
            "fields": ("published","is_public")
        }),
        ("Métadonnées", {
            "fields": ("metadata",),
            "classes": ("collapse",)
        }),
    )

    def get_status_display(self, obj):
        return obj.get_status()
    get_status_display.short_description = "Statut"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('church','created_by','category')

# =====================================================
# PROGRAMMES (Fonctionnalité 4)
# =====================================================

class ProgrammeMemberInline(admin.TabularInline):
    model = ProgrammeMember
    extra = 0
    readonly_fields = ("joined_at",)
    fields = ("user","joined_at")
    can_delete = True

@admin.register(Programme)
class ProgrammeAdmin(admin.ModelAdmin):
    list_display = ("title","church","status","start_date","end_date","is_public","get_member_count_display","created_at")
    search_fields = ("title","description","church__title")
    list_filter = ("status","is_public","start_date","church")
    readonly_fields = ("id","created_at","updated_at","duration_in_days")
    filter_horizontal = ("content_items",)
    inlines = [ProgrammeMemberInline]
    date_hierarchy = "start_date"

    fieldsets = (
        ("Informations de base", {
            "fields": ("church","title","description","cover_image_url","created_by")
        }),
        ("Dates", {
            "fields": ("start_date","end_date","duration_in_days")
        }),
        ("Statut et visibilité", {
            "fields": ("status","is_public")
        }),
        ("Contenu introductif (Coming Soon)", {
            "fields": ("intro_video_url","intro_document_url"),
            "classes": ("collapse",),
            "description": "Accessible avant le démarrage"
        }),
        ("Contenus du programme", {
            "fields": ("content_items",),
        }),
    )

    def get_member_count_display(self, obj):
        return obj.get_member_count()
    get_member_count_display.short_description = "Membres"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('church','created_by')

# =====================================================
# TÉMOIGNAGES (Fonctionnalité 6)
# =====================================================

@admin.register(Testimony)
class TestimonyAdmin(admin.ModelAdmin):
    list_display = ("get_title_display","user","church","type","status","is_public","views_count","created_at")
    search_fields = ("user__phone_number","church__title","title","text_content")
    list_filter = ("type","status","is_public","church","created_at")
    readonly_fields = ("id","created_at","updated_at","approved_at","views_count")
    date_hierarchy = "created_at"

    fieldsets = (
        ("Informations de base", {
            "fields": ("church","user","type","title")
        }),
        ("Contenu", {
            "fields": ("text_content","audio_url","duration")
        }),
        ("Modération", {
            "fields": ("status","is_public","approved_by","approved_at","rejection_reason")
        }),
        ("Statistiques", {
            "fields": ("views_count",),
            "classes": ("collapse",)
        }),
    )

    def get_title_display(self, obj):
        return obj.title if obj.title else f"Témoignage #{str(obj.id)[:8]}"
    get_title_display.short_description = "Titre"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('church','user','approved_by')

    actions = ['approve_testimonies','reject_testimonies']

    def approve_testimonies(self, request, queryset):
        count = 0
        for testimony in queryset.filter(status="PENDING"):
            testimony.approve(request.user)
            count += 1
        self.message_user(request, f"{count} témoignage(s) approuvé(s)")
    approve_testimonies.short_description = "✅ Approuver les témoignages"

    def reject_testimonies(self, request, queryset):
        count = queryset.filter(status="PENDING").update(
            status="REJECTED",
            rejection_reason="Rejeté en masse par l'administrateur"
        )
        self.message_user(request, f"{count} témoignage(s) rejeté(s)")
    reject_testimonies.short_description = "❌ Rejeter les témoignages"

# =====================================================
# COMMISSIONS ET GROUPES (Fonctionnalité 7)
# =====================================================

class ChurchCommissionInline(admin.TabularInline):
    model = ChurchCommission
    extra = 1
    fields = ("church","user","role")
    autocomplete_fields = ["user","church"]

@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = ("name","eng_name","created_at")
    search_fields = ("name","eng_name","description")
    readonly_fields = ("id","created_at")
    inlines = [ChurchCommissionInline]

    fieldsets = (
        ("Informations de base", {
            "fields": ("name","eng_name","logo","description")
        }),
    )

# =====================================================
# COLLABORATIONS (Fonctionnalité 11)
# =====================================================

@admin.register(ChurchCollaboration)
class ChurchCollaborationAdmin(admin.ModelAdmin):
    list_display = ("initiator_church","target_church","collaboration_type","status","start_date","created_at")
    search_fields = ("initiator_church__title","target_church__title")
    list_filter = ("collaboration_type","status","created_at")
    readonly_fields = ("id","created_at","updated_at","accepted_at","rejected_at")
    date_hierarchy = "created_at"

    fieldsets = (
        ("Informations", {
            "fields": ("initiator_church","target_church","collaboration_type","created_by")
        }),
        ("Dates", {
            "fields": ("start_date",)
        }),
        ("Statut", {
            "fields": ("status","accepted_by","accepted_at","rejected_at")
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('initiator_church','target_church','created_by','accepted_by')

    actions = ['accept_collaborations','reject_collaborations']

    def accept_collaborations(self, request, queryset):
        count = 0
        for collab in queryset.filter(status="PENDING"):
            collab.accept(request.user)
            count += 1
        self.message_user(request, f"{count} collaboration(s) acceptée(s)")
    accept_collaborations.short_description = "✅ Accepter les collaborations"

    def reject_collaborations(self, request, queryset):
        count = 0
        for collab in queryset.filter(status="PENDING"):
            collab.reject()
            count += 1
        self.message_user(request, f"{count} collaboration(s) rejetée(s)")
    reject_collaborations.short_description = "❌ Rejeter les collaborations"

# =====================================================
# GESTION FINANCIÈRE (Fonctionnalité 12)
# =====================================================

@admin.register(DonationCategory)
class DonationCategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name","description")

@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ("user","church","category","amount","currency","gateway","withdrawed","created_at")
    search_fields = ("user__phone_number","church__title","gateway_transaction_id")
    list_filter = ("gateway","withdrawed","category","church","created_at")
    readonly_fields = ("id","created_at","confirmed_at")
    date_hierarchy = "created_at"

    fieldsets = (
        ("Informations", {
            "fields": ("user","church","category","amount","currency")
        }),
        ("Paiement", {
            "fields": ("gateway","gateway_transaction_id","withdrawed")
        }),
        ("Message du donateur", {
            "fields": ("message",),
            "classes": ("collapse",)
        }),
        ("Métadonnées", {
            "fields": ("metadata",),
            "classes": ("collapse",)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user','church','category')

@admin.register(BookOrder)
class BookOrderAdmin(admin.ModelAdmin):
    list_display = ("id","user","content","quantity","total_price","delivery_type","is_ticket","shipped","created_at")
    list_filter = ("is_ticket","payment_gateway","delivery_type","shipped","created_at")
    search_fields = ("user__phone_number","content__title","payment_transaction_id")
    readonly_fields = ("id","total_price","created_at")
    date_hierarchy = "created_at"

    fieldsets = (
        ("Commande", {
            "fields": ("user","content","quantity","total_price","is_ticket","ticket_tier")
        }),
        ("Livraison", {
            "fields": ("delivery_type","shipped","delivered_at"),
        }),
        ("Adresse de livraison", {
            "fields": ("delivery_recipient_name","delivery_phone","delivery_address_line1","delivery_address_line2","delivery_city","delivery_postal_code","delivery_country","shipping_method","shipping_cost"),
            "classes": ("collapse",)
        }),
        ("Paiement", {
            "fields": ("payment_gateway","payment_transaction_id","withdrawed")
        }),
    )

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id","content","user","status","price","issued_at")
    search_fields = ("id","user__phone_number","content__title")
    list_filter = ("status","issued_at")
    readonly_fields = ("id","issued_at","price")
    date_hierarchy = "issued_at"

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id","user","church","amount","currency","gateway","status","gateway_transaction_id","created_at")
    search_fields = ("user__phone_number","gateway_transaction_id","church__title")
    list_filter = ("gateway","status","created_at")
    readonly_fields = ("id","created_at","updated_at")
    date_hierarchy = "created_at"

@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ("church","content","amount","issued_at")
    search_fields = ("church__title","content__title","description")
    list_filter = ("church","issued_at")
    readonly_fields = ("id","issued_at","created_at")
    date_hierarchy = "issued_at"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('church','content')

# =====================================================
# NOTIFICATIONS (Fonctionnalité 13)
# =====================================================

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user","title","type","channel","sent","created_at")
    search_fields = ("user__phone_number","title","message")
    list_filter = ("type","channel","sent","created_at")
    readonly_fields = ("created_at","sent_at")
    date_hierarchy = "created_at"

# =====================================================
# CONFIGURATION DES SERVICES
# =====================================================

@admin.register(ServiceConfiguration)
class ServiceConfigurationAdmin(admin.ModelAdmin):
    list_display = ("service_type", "is_active", "get_status", "updated_at")
    list_filter = ("service_type", "is_active")
    search_fields = ("service_type",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Configuration Générale", {
            "fields": ("service_type", "is_active", "config")
        }),
        ("Mode Maintenance", {
            "fields": ("maintenance_message",),
            "classes": ("collapse",),
            "description": "Configuration du mode maintenance"
        }),
        ("WhatsApp API", {
            "fields": (
                "whatsapp_api_token",
                "whatsapp_phone_number_id",
                "whatsapp_api_version",
                "whatsapp_template_name",
                "whatsapp_language"
            ),
            "classes": ("collapse",),
            "description": "Configuration de l'API WhatsApp (Meta/Facebook)"
        }),
        ("Nexaah SMS API", {
            "fields": (
                "nexaah_base_url",
                "nexaah_send_endpoint",
                "nexaah_credits_endpoint",
                "nexaah_user",
                "nexaah_password",
                "nexaah_sender_id"
            ),
            "classes": ("collapse",),
            "description": "Configuration de l'API Nexaah SMS"
        }),
        ("FreeMoPay Payment Gateway", {
            "fields": (
                "freemopay_base_url",
                "freemopay_app_key",
                "freemopay_secret_key",
                "freemopay_callback_url",
                "freemopay_init_payment_timeout",
                "freemopay_status_check_timeout",
                "freemopay_token_timeout",
                "freemopay_token_cache_duration",
                "freemopay_max_retries",
                "freemopay_retry_delay"
            ),
            "classes": ("collapse",),
            "description": "Configuration de l'API FreeMoPay"
        }),
        ("Préférences de Notification", {
            "fields": ("default_notification_channel",),
            "classes": ("collapse",),
        }),
    )

    def get_status(self, obj):
        if obj.is_active:
            if obj.is_configured():
                return "✅ Configuré et actif"
            else:
                return "⚠️ Actif mais mal configuré"
        return "❌ Inactif"
    get_status.short_description = "Statut"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        if obj.is_active and not obj.is_configured():
            errors = []
            if obj.service_type == 'whatsapp':
                errors = obj.validate_whatsapp_config()
            elif obj.service_type == 'nexaah_sms':
                errors = obj.validate_nexaah_config()
            elif obj.service_type == 'freemopay':
                errors = obj.validate_freemopay_config()

            if errors:
                from django.contrib import messages
                messages.warning(
                    request,
                    f"Service activé mais incomplet : {', '.join(errors)}"
                )
