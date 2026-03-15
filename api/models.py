from django.db import models, transaction, IntegrityError
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from django.db.models import F, Sum
from django.apps import apps
import uuid
# -----------------------------------------------------
# Church Model (défini en premier pour éviter les erreurs)
# -----------------------------------------------------

class Church(models.Model):

    STATUS_CHOICES = (
        ("PENDING", "En attente"),
        ("APPROVED", "Approuvée"),
        ("REJECTED", "Rejetée"),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    class Meta:
        indexes = [
        models.Index(fields=["status"]),
        models.Index(fields=["country", "city"]),
        models.Index(fields=["is_public"]),
       ]
    # Identification
    code = models.BigIntegerField(
        null=True,
        blank=True,
        unique=True,
        editable=False,
        default=1
    )
    title = models.CharField(max_length=100, unique=True, db_index=True)
    slug = models.SlugField(blank=True,max_length=120)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    lang = models.CharField(default="fr")

    # Description & branding
    description = models.TextField(blank=True)
    logo_url = models.URLField(max_length=500, blank=True, null=True)
    primary_color = models.CharField(max_length=20, default="#1A73E8")
    secondary_color = models.CharField(max_length=20, default="#FFFFFF")

    # Contact info
    email = models.EmailField(blank=True, null=True)
    # Support up to four phone numbers for an eglise
    phone_number_1 = models.CharField(max_length=20, blank=True, null=True)
    phone_number_2 = models.CharField(max_length=20, blank=True, null=True)
    phone_number_3 = models.CharField(max_length=20, blank=True, null=True)
    phone_number_4 = models.CharField(max_length=20, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    whatsapp_phone = models.TextField(max_length=500, blank=True, null=True)
    doc_url = models.URLField(max_length=500, default="")

    # Social media
    tiktok_url = models.URLField(blank=True, null=True)
    instagram_url = models.URLField(blank=True, null=True)
    youtube_url = models.URLField(blank=True, null=True)
    facebook_url = models.URLField(blank=True, null=True)

    # Location
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    longitude = models.FloatField(default=0.0)
    latitude = models.FloatField(default=0.0)

    # Stats
    members_count = models.PositiveIntegerField(default=0)
    admins_count = models.PositiveIntegerField(default=0)
    profile_views = models.PositiveIntegerField(default=0)

    # Seats & operations
    seats = models.PositiveIntegerField(default=0)
    is_public = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    look_actuality = models.BooleanField(default=False)

    # Subscription SaaS
    is_active_subscription = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    # Later FK added from User model
    # owner = ...
    parent = models.ForeignKey(
    "self",
    on_delete=models.CASCADE,
    null=True,
    blank=True,
    related_name="sub_churches"
    )
    
    @property
    def phone_number(self):
        """Cached property for first non-empty phone number."""
        if hasattr(self, '_cached_phone_number'):
            return self._cached_phone_number
        
        for n in (self.phone_number_1, self.phone_number_2, self.phone_number_3, self.phone_number_4):
            if n:
                self._cached_phone_number = n
                return n
        self._cached_phone_number = None
        return None

    def phone_numbers(self):
        """Return a list of non-empty phone numbers."""
        return [n for n in (self.phone_number_1, self.phone_number_2, self.phone_number_3, self.phone_number_4) if n]

    def save(self, *args, **kwargs):
        # Always update slug from title if title has changed or slug is missing
        if self.title:
            new_slug = slugify(self.title)
            if self.slug != new_slug:
                self.slug = new_slug
        
        if self._state.adding and not self.code:
            existing = Church.objects.filter(code__isnull=False).order_by('-code').values_list('code', flat=True).first()
            self.code = (existing + 1) if existing else 1
        
        # Save with retry logic for IntegrityError (concurrency)
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                return 
            except IntegrityError:
                if attempt == max_attempts - 1:
                    raise
                existing = Church.objects.filter(code__isnull=False).order_by('-code').values_list('code', flat=True).first()
                self.code = (existing + 1) if existing else 1
    def __str__(self):
        return self.title


# -----------------------------------------------------
# User Manager
# -----------------------------------------------------

class UserManager(BaseUserManager):
    def create_user(self, phone_number, **extra_fields):
        if not phone_number:
            raise ValueError("Le numéro de téléphone doit être fourni")

        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_unusable_password()   # pas de mot de passe pour OTP WhatsApp
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")

        return self.create_user(phone_number, **extra_fields)


# -----------------------------------------------------
# User Model
# -----------------------------------------------------

class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=50, unique=True, db_index=True)
    picture_url = models.URLField(blank=True, null=True)
    notification_preferences = models.JSONField(default=dict, blank=True)
    ROLE_CHOICES = [
        ("SADMIN", "Sadmin"),
        ("USER", "User"),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="USER", db_index=True)

    # un user peut appartenir à une église → ForeignKey
    current_church = models.ForeignKey(
        Church,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members"
    )
    longitude = models.FloatField(default=0.0)
    latitude = models.FloatField(default=0.0)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=250, blank=True)
    email = models.CharField(max_length=250, blank=True,unique=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # indispensable pour l'admin Django
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []
    objects = UserManager()
    def __str__(self):
        return f"{self.phone_number} ({self.role})"


# -----------------------------------------------------
# Ajout du owner *après* la définition du User
# -----------------------------------------------------

Church.add_to_class(
    "owner",
    models.ForeignKey(
        User,
            on_delete=models.SET_NULL,
        related_name="owners_church",
        null=True,
        blank=True
    )
)

class Content(models.Model):
    TYPE_CHOICES = [
        ("ARTICLE", "Article"),
        ("AUDIO", "Audio"),
        ("EVENT", "Event"),
        ("VIDEO", "Video"),
        ("POST", "Short"),
        ("BOOK", "Book"),
        ("STORY", "Story")
    ]

    DELIVERY_CHOICES = [
        ("DIGITAL", "Numérique"),
        ("PHYSICAL", "Physique"),
    ]

    church = models.ForeignKey("Church", on_delete=models.CASCADE)
    delivery_type = models.CharField(max_length=20, choices=DELIVERY_CHOICES, default="DIGITAL")
    
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, db_index=True)
     
    title = models.CharField(max_length=250)
    phone = models.CharField(max_length=250,null=True, blank=True)
    slug = models.SlugField()
    description = models.TextField(blank=True)
    cover_image_url = models.URLField(blank=True, null=True)

    # For media (optional fields depending on type)
    audio_url = models.URLField(blank=True, null=True)
    video_url = models.URLField(blank=True, null=True)
    file = models.URLField(blank=True, null=True)

    # Event-specific fields
    start_at = models.DateTimeField(null=True, blank=True, db_index=True)
    end_at = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=250, blank=True)
    is_paid = models.BooleanField(default=False)
    is_public = models.BooleanField(default=False)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, default="XAF")
    # Flexibility
    metadata = models.JSONField(default=dict)

    # Event/ticketing fields
    capacity = models.PositiveIntegerField(null=True, blank=True)
    tickets_sold = models.PositiveIntegerField(default=0)
    allow_ticket_sales = models.BooleanField(default=False)

    category = models.ForeignKey("Category", on_delete=models.SET_NULL, null=True)

    created_by = models.ForeignKey("User", on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    published = models.BooleanField(default=True)
    
    # Coming Soon Management
    planned_release_date = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Date prévue de publication (Coming Soon)"
    )

    # Ticket tiers stored directly on Content (prix et quantités par type)
    # Exemple: classic, vip, premium
    has_ticket_tiers = models.BooleanField(default=False)
    classic_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    classic_quantity = models.PositiveIntegerField(null=True, blank=True)
    vip_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    vip_quantity = models.PositiveIntegerField(null=True, blank=True)
    premium_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    premium_quantity = models.PositiveIntegerField(null=True, blank=True)


    # dans class Content
   
    def save(self, *args, **kwargs):
        # auto-generate slug if missing
        if not self.slug and self.title:
            self.slug = slugify(self.title)[:120]

        # validate ticket counts vs capacity
        # existing tickets_sold vs capacity check
        if self.capacity is not None and self.tickets_sold is not None:
            if self.tickets_sold > self.capacity:
                raise ValidationError("tickets_sold cannot exceed capacity")

        # If ticket tiers are used, ensure their total quantity does not exceed overall capacity
        if getattr(self, "has_ticket_tiers", False) and self.capacity is not None:
            total_tier_qty = 0
            for f in ("classic_quantity", "vip_quantity", "premium_quantity"):
                v = getattr(self, f, None)
                if v:
                    total_tier_qty += int(v)
            if total_tier_qty > self.capacity:
                raise ValidationError("Sum of tier quantities exceeds content capacity")

        super().save(*args, **kwargs)

    def available_tickets(self):
        """Return remaining tickets (None means unlimited/not set)."""
        if self.capacity is None:
            return None
        return max(0, self.capacity - (self.tickets_sold or 0))
    
    def is_coming_soon(self):
        """Vérifier si le contenu est 'Coming Soon'"""
        if self.planned_release_date and self.published:
            return timezone.now() < self.planned_release_date
        return False
    
    def get_status(self):
        """Retourner le statut du contenu"""
        if not self.published:
            return "DRAFT"
        elif self.is_coming_soon():
            return "COMING_SOON"
        else:
            return "PUBLISHED"

    def __str__(self):
        return f"{self.type} - {self.title}"

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["start_at"]), models.Index(fields=["-created_at"])]
  
class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True)

class ContentTag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.ForeignKey(Content, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)

class Playlist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(Church, on_delete=models.CASCADE)
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    cover_image_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

class PlaylistItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE)
    content = models.ForeignKey(Content, on_delete=models.CASCADE)
    position = models.PositiveIntegerField(default=0)

class ContentView(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.ForeignKey(Content, on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(auto_now_add=True)

class ContentLike(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.ForeignKey(Content, on_delete=models.CASCADE)
    liked_at = models.DateTimeField(auto_now_add=True)

class Comment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.ForeignKey(Content, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)

class OTP(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=20, unique=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    last_sent_at = models.DateTimeField(auto_now=True)
    session_id = models.UUIDField(default=uuid.uuid4)

    def is_expired(self):
        from django.conf import settings
        expiration = settings.OTP_EXPIRATION_SECONDS
        return (timezone.now() - self.last_sent_at).total_seconds() > expiration

    def can_resend(self):
        from django.conf import settings
        cooldown = settings.OTP_SEND_COOLDOWN_SECONDS
        return (timezone.now() - self.last_sent_at).total_seconds() > cooldown

class ChurchAdmin(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ROLE_CHOICES = [
        ("OWNER", "Owner"),
        ("ADMIN", "Admin"),
        ("MODERATOR", "Moderator"),
        ("PASTOR", "Pastor"),
    ]

    church = models.ForeignKey("Church", on_delete=models.CASCADE, related_name="admins")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="church_roles")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="ADMIN")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("church", "user")

    def __str__(self):
        return f"{self.user.phone_number} @ {self.church.title} ({self.role})"

class SubscriptionPlan(models.Model):
    """Plans de souscription configurables dans l'admin"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=100, unique=True, help_text="Nom du plan (ex: FREE, STARTER, PRO)")
    display_name = models.CharField(max_length=100, help_text="Nom d'affichage (ex: Gratuit, Démarrage, Pro)")

    # Prix et devise
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Prix du plan")
    currency = models.CharField(max_length=10, default="XAF")

    # Validité
    duration_days = models.PositiveIntegerField(default=30, help_text="Durée de validité en jours")

    # Limites et fonctionnalités
    max_members = models.PositiveIntegerField(null=True, blank=True, help_text="Nombre maximum de membres (null = illimité)")
    max_contents = models.PositiveIntegerField(null=True, blank=True, help_text="Nombre maximum de contenus (null = illimité)")
    max_storage_gb = models.PositiveIntegerField(null=True, blank=True, help_text="Stockage maximum en GB (null = illimité)")

    # Fonctionnalités booléennes
    has_chat = models.BooleanField(default=True, help_text="Accès au chat")
    has_programmes = models.BooleanField(default=True, help_text="Accès aux programmes")
    has_analytics = models.BooleanField(default=False, help_text="Accès aux statistiques avancées")
    has_custom_branding = models.BooleanField(default=False, help_text="Personnalisation avancée")

    # Description et metadata
    description = models.TextField(blank=True, help_text="Description du plan")
    features = models.JSONField(default=list, blank=True, help_text="Liste des fonctionnalités")

    # Statut
    is_active = models.BooleanField(default=True, help_text="Plan disponible à l'achat")

    # Ordre d'affichage
    order = models.PositiveIntegerField(default=0, help_text="Ordre d'affichage")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'price']
        verbose_name = "Plans"
        verbose_name_plural = "Plans"

    def __str__(self):
        return f"{self.display_name} ({self.price} {self.currency})"

class Subscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    PLAN_CHOICES = [
        ("FREE", "Free"),
        ("STARTER", "Starter"),
        ("PRO", "Pro"),
        ("PREMUIM", "Premium"),
    ]

    church = models.OneToOneField("Church", on_delete=models.CASCADE, related_name="subscription")

    # Nouveau: Plan configurable (prioritaire si défini)
    subscription_plan = models.ForeignKey(
        "SubscriptionPlan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscriptions",
        help_text="Plans"
    )

    # Ancien: Plan hardcodé (pour compatibilité arrière)
    plan = models.CharField(max_length=30, choices=PLAN_CHOICES, default="FREE")

    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    # gateway data
    gateway = models.CharField(max_length=50, blank=True, null=True)  # e.g. stripe, mobilemoney
    gateway_subscription_id = models.CharField(max_length=200, blank=True, null=True)

    def get_plan_name(self):
        """Retourne le nom du plan (subscription_plan en priorité)"""
        if self.subscription_plan:
            return self.subscription_plan.name
        return self.plan

    def get_plan_price(self):
        """Retourne le prix du plan (cherche dans SubscriptionPlan en priorité)"""
        if self.subscription_plan:
            return self.subscription_plan.price
            
        # Fallback: chercher par le nom du plan (STARTER, PRO, etc.)
        try:
            # On utilise apps.get_model pour éviter les imports circulaires si nécessaire
            plan_obj = apps.get_model("api", "SubscriptionPlan").objects.filter(name=self.plan, is_active=True).first()
            if plan_obj:
                return plan_obj.price
        except Exception:
            pass

        # Prix hardcodés en dernier recours pour compatibilité historique
        PLAN_PRICES = {
            "STARTER": 10000.00,
            "PRO": 30000.00,
            "PREMIUM": 50000.00,
        }
        return PLAN_PRICES.get(self.plan, 0)

    def __str__(self):
        plan_name = self.subscription_plan.display_name if self.subscription_plan else self.plan
        return f"{self.church.title} - {plan_name}"

# Extend Notification to hold channel info + send status
class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    NOTIF_TYPES = [
        ('OTP', 'Code OTP'),
        ('DOC_REQUEST', 'Demande de documents'),
        ('DOC_VALIDATED', 'Documents validés'),
        ('ACCOUNT_APPROVED', 'Compte activé'),
        ('INFO', 'Information'),
        ('WARNING', 'Avertissement'),
        ('ERROR', 'Erreur'),
        ("SUCCESS","Success")
    ]

    CHANNEL_CHOICES = [
        ("IN_APP", "In App"),
        ("WHATSAPP", "WhatsApp"),
        ("EMAIL", "Email")
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=255)
    message = models.TextField()
    eng_message = models.TextField(default="")
    eng_title = models.TextField(default="")
    type = models.CharField(max_length=20, choices=NOTIF_TYPES)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="IN_APP")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)  # store payload / gateway response

    def mark_sent(self, response_meta=None):
        self.sent = True
        self.sent_at = timezone.now()
        if response_meta:
            self.meta = response_meta
        self.save()

    def __str__(self):
        # safer if user might not have phone_number set
        phone = getattr(self.user, "phone_number", str(self.user.pk))
        return f"{phone} • {self.title}"

class Commission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    eng_name = models.CharField(max_length=255, unique=True,default="")
    logo = models.URLField(null=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class ChurchCommission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ROLE_CHOICES = [
        ("MEMBER", "Member"),
        ("LEADER", "Leader"),
        ("ASSISTANT", "Assistant"),
    ]

    church = models.ForeignKey("Church", on_delete=models.CASCADE, related_name="church_commissions")
    commission = models.ForeignKey("Commission", on_delete=models.CASCADE, related_name="church_links")
    user = models.ForeignKey("User", on_delete=models.CASCADE, related_name="church_commissions")

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="MEMBER")

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("church", "commission", "user")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Sync Church.owner if role is OWNER
        if self.role == "OWNER":
            church = self.church
            if church.owner != self.user:
                church.owner = self.user
                # Use update_fields to avoid re-running Church.save() logic
                from api.models import Church
                Church.objects.filter(pk=church.pk).update(owner=self.user)

    def __str__(self):
        return f"{self.user.phone_number} → {self.commission.name} @ {self.church.title}"

class Deny(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey("Church", on_delete=models.CASCADE, related_name="denied_members")
    user = models.ForeignKey("User", on_delete=models.CASCADE, related_name="denied_in_churches")
    reason = models.TextField(blank=True)
    denied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("church", "user")

    def __str__(self):
        return f"{self.user.phone_number} denied from {self.church.title}"
    
class DonationCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

  # Une catégorie par église

    def __str__(self):
        return f"{self.name}"
    
class Donation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    PAYMENT_GATEWAYS = [
        ("MOMO", "Mobile Money"),
        ("OM", "Orange Money"),
        ("CARD", "Carte Bancaire"),
        ("CASH", "Cash"),
        ("OTHER", "Autre"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="donations")
    church = models.ForeignKey(Church, on_delete=models.CASCADE, related_name="donations")
    category = models.ForeignKey(DonationCategory, on_delete=models.SET_NULL, null=True)
    withdrawed = models.BooleanField(default=False) 
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="XAF")

    gateway = models.CharField(max_length=20, choices=PAYMENT_GATEWAYS, default="CASH")
    gateway_transaction_id = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    message = models.TextField(blank=True)  # message du donateur (optionnel)
    metadata = models.JSONField(default=dict, blank=True)  # données techniques du paiement
    confirmed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.phone_number} → {self.amount} {self.currency} ({self.category})"


class Payment(models.Model):
    """Unified payment record for orders and donations (for admin reconciliation).

    - Can be linked to a BookOrder or a Donation (or both/none for manual entries).
    - Stores gateway metadata and who processed the payment in the admin.
    """

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SUCCESS", "Successful"),
        ("FAILED", "Failed"),
        ("REFUNDED", "Refunded"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    church = models.ForeignKey(Church, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    order = models.ForeignKey("BookOrder", on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    donation = models.ForeignKey("Donation", on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="XAF")

    GATEWAY_CHOICES = [
        ("MOMO", "Mobile Money"),
        ("OM", "Orange Money"),
        ("CARD", "Card"),
        ("CASH", "Cash"),
        ("OTHER", "Other"),
    ]
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES, default="MOMO")
    gateway_transaction_id = models.CharField(max_length=200, blank=True, null=True, db_index=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING", db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    # Admin who reconciled/created this payment (if any)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="processed_payments")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["gateway_transaction_id"]), models.Index(fields=["status"])]

    def __str__(self):
        who = self.user.phone_number if self.user else (self.church.title if self.church else str(self.id))
        return f"Payment {self.id} — {who} — {self.amount} {self.currency} ({self.status})"

class BookOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    PAYMENT_CHOICES = [
        ("MOMO", "Mobile Money"),
        ("OM", "Orange Money"),
        ("CARD", "Carte Bancaire"),
        ("CASH", "Cash"),
        ("OTHER", "Autre"),
    ]
    DELIVERY_CHOICES = [
        ("DIGITAL", "Numérique"),
        ("PHYSICAL", "Physique"),
    ]
    user = models.ForeignKey("User", on_delete=models.CASCADE, related_name="book_orders")
    content = models.ForeignKey("Content", on_delete=models.CASCADE, related_name="book_orders")
    delivery_type = models.CharField(max_length=20, choices=DELIVERY_CHOICES, default="DIGITAL")
    
    quantity = models.PositiveIntegerField(default=1)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    withdrawed = models.BooleanField(default=False) 
    payment_gateway = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default="CASH")
    payment_transaction_id = models.CharField(max_length=200, blank=True, null=True)
    
    shipped = models.BooleanField(default=False)
    delivered_at = models.DateTimeField(null=True, blank=True)

    # Optional delivery information for physical goods
    delivery_recipient_name = models.CharField(max_length=250, blank=True, null=True)
    delivery_address_line1 = models.CharField(max_length=250, blank=True, null=True)
    delivery_address_line2 = models.CharField(max_length=250, blank=True, null=True)
    delivery_city = models.CharField(max_length=150, blank=True, null=True)
    delivery_postal_code = models.CharField(max_length=50, blank=True, null=True)
    delivery_country = models.CharField(max_length=150, blank=True, null=True)
    delivery_phone = models.CharField(max_length=50, blank=True, null=True)
    shipping_method = models.CharField(max_length=100, blank=True, null=True)
    shipping_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    # flag to indicate this order purchases tickets for an event
    is_ticket = models.BooleanField(default=False)
    # optional: which ticket type (if ticket types are used)
    # Backwards-compatible: keep FK but prefer `ticket_tier` which reads tiers from Content
    ticket_type = models.ForeignKey("TicketType", on_delete=models.SET_NULL, null=True, blank=True)
    # New: choose a tier stored on Content directly: CLASSIC, VIP or PREMIUM
    TIER_CHOICES = [("CLASSIC", "Classic"), ("VIP", "VIP"), ("PREMIUM", "Premium")]
    ticket_tier = models.CharField(max_length=20, choices=TIER_CHOICES, null=True, blank=True)

    def save(self, *args, **kwargs):
        # Vérifie la disponibilité des tickets si c'est une commande de billets.
        # On utilise une transaction + select_for_update pour éviter la sur-vente.
        with transaction.atomic():
            # lock related rows
            if self.is_ticket:
                # Prefer explicit ticket_type FK if present, else use ticket_tier info on content
                if getattr(self, "ticket_type_id", None):
                    # lock the ticket type row
                    tt = TicketType.objects.select_for_update().get(pk=self.ticket_type_id)
                    if tt.quantity is not None and tt.quantity < (self.quantity or 0):
                        raise ValidationError("Not enough tickets available for the selected ticket type")
                elif getattr(self, "ticket_tier", None):
                    # lock the content row and check tier availability
                    c = Content.objects.select_for_update().get(pk=self.content_id)
                    tier = (self.ticket_tier or "").upper()
                    qty_field = {
                        "CLASSIC": "classic_quantity",
                        "VIP": "vip_quantity",
                        "PREMIUM": "premium_quantity",
                    }.get(tier)
                    if qty_field:
                        avail = getattr(c, qty_field)
                        if avail is not None and avail < (self.quantity or 0):
                            raise ValidationError("Not enough tickets available for the selected tier")
                else:
                    # lock the content row and check overall capacity
                    c = Content.objects.select_for_update().get(pk=self.content_id)
                    if c.capacity is not None and (c.capacity - (c.tickets_sold or 0)) < (self.quantity or 0):
                        raise ValidationError("Not enough tickets available for this event")

            # Calcul automatique du prix total
            unit_price = 0
            try:
                # Determine unit price from ticket_type FK, or ticket_tier on content, or content.price
                if self.is_ticket and getattr(self, "ticket_type", None):
                    unit_price = self.ticket_type.price or 0
                elif getattr(self, "ticket_tier", None) and getattr(self, "content", None):
                    tier = (self.ticket_tier or "").upper()
                    unit_price = {
                        "CLASSIC": (self.content.classic_price or 0),
                        "VIP": (self.content.vip_price or 0),
                        "PREMIUM": (self.content.premium_price or 0),
                    }.get(tier, 0)
                elif getattr(self, "content", None) and self.content.price:
                    unit_price = self.content.price
            except Exception:
                unit_price = 0
            self.total_price = (self.quantity or 0) * (unit_price or 0)
            super().save(*args, **kwargs)

    def issue_tickets(self, payment_transaction_id=None, buyer=None):
        """
        Atomically issue tickets for this order after payment confirmation.
        Returns list of created Ticket instances.
        """
        if not self.is_ticket:
            raise ValidationError("This order is not a ticket order")

        Ticket = apps.get_model("api", "Ticket")
        TicketType = apps.get_model("api", "TicketType")
        ContentModel = apps.get_model("api", "Content")

        with transaction.atomic():
            # Lock and validate availability
            if self.ticket_type_id:
                tt = TicketType.objects.select_for_update().get(pk=self.ticket_type_id)
                if tt.quantity is not None and tt.quantity < (self.quantity or 0):
                    raise ValidationError("Not enough tickets available for the selected ticket type")
            else:
                c = ContentModel.objects.select_for_update().get(pk=self.content_id)
                if c.capacity is not None and (c.capacity - (c.tickets_sold or 0)) < (self.quantity or 0):
                    raise ValidationError("Not enough tickets available for this event")

            # compute unit price
            unit_price = 0
            if self.ticket_type_id:
                tt = TicketType.objects.get(pk=self.ticket_type_id)
                unit_price = tt.price or 0
            else:
                c = ContentModel.objects.get(pk=self.content_id)
                unit_price = c.price or 0

            # create tickets
            tickets = []
            content_obj = ContentModel.objects.get(pk=self.content_id)
            buyer_user = buyer or self.user
            for _ in range(self.quantity or 0):
                t = Ticket.objects.create(
                    content=content_obj,
                    order=self,
                    ticket_type=(tt if getattr(self, "ticket_type_id", None) else None),
                    user=buyer_user,
                    price=unit_price,
                )
                tickets.append(t)

            # decrement stock and increment sold counters
            # If using ticket_type FK, decrement its quantity
            if self.ticket_type_id and tt.quantity is not None:
                TicketType.objects.filter(pk=tt.pk).update(quantity=F('quantity') - (self.quantity or 0))
            # If using ticket_tier stored on content, decrement the corresponding content tier quantity
            elif getattr(self, "ticket_tier", None):
                tier = (self.ticket_tier or "").upper()
                qty_field = {
                    "CLASSIC": "classic_quantity",
                    "VIP": "vip_quantity",
                    "PREMIUM": "premium_quantity",
                }.get(tier)
                if qty_field:
                    ContentModel.objects.filter(pk=self.content_id).update(**{
                        qty_field: F(qty_field) - (self.quantity or 0)
                    })

            # Always increment tickets_sold counter
            ContentModel.objects.filter(pk=self.content_id).update(tickets_sold=F('tickets_sold') + (self.quantity or 0))

            # update order with payment transaction id if provided
            if payment_transaction_id:
                self.payment_transaction_id = payment_transaction_id
                # update without re-running availability checks via queryset
                BookOrder = apps.get_model("api", "BookOrder")
                BookOrder.objects.filter(pk=self.pk).update(payment_transaction_id=payment_transaction_id)

            return tickets

    def __str__(self):
        return f"{self.user.phone_number} - {self.content.title} ({self.delivery_type}) x{self.quantity}"

class TicketType(models.Model):
    """Category / tariff for an event (e.g. CLASSIQUE, VIP)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.ForeignKey("Content", on_delete=models.CASCADE, related_name="ticket_types")
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    # quantity=None means unlimited
    quantity = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["name"]), models.Index(fields=["-created_at"])]

    class Meta:
        unique_together = ("content", "name")

    def __str__(self):
        return f"{self.content.title} — {self.name} ({self.price})"

    def available(self):
        """Return remaining tickets for this type (None means unlimited), taking into account active reservations."""
        if self.quantity is None:
            return None
        
        # Tickets already issued
        sold = Ticket.objects.filter(ticket_type=self).count()
        
        # Tickets currently reserved (not expired)
        reserved = TicketReservation.objects.filter(
            ticket_type=self, 
            expires_at__gt=timezone.now()
        ).aggregate(sum=Sum('quantity'))['sum'] or 0
        
        return max(0, self.quantity - sold - reserved)

class TicketReservation(models.Model):
    """Temporary reservation to hold tickets during payment window."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("User", on_delete=models.SET_NULL, null=True, blank=True)
    content = models.ForeignKey("Content", on_delete=models.CASCADE)
    ticket_type = models.ForeignKey("TicketType", on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    reserved_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["expires_at"])]

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def __str__(self):
        return f"Reservation {self.id} — {self.content.title} x{self.quantity}"

class Ticket(models.Model):
    """Issued ticket linked to an order. Use UUID as public identifier."""
    T_STATUS = [("NEW", "New"), ("USED", "Used"), ("CANCELLED", "Cancelled")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.ForeignKey("Content", on_delete=models.CASCADE, related_name="tickets")
    order = models.ForeignKey("BookOrder", on_delete=models.CASCADE, related_name="tickets")
    ticket_type = models.ForeignKey("TicketType", on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey("User", on_delete=models.SET_NULL, null=True, blank=True)
    seat = models.CharField(max_length=50, blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=T_STATUS, default="NEW")
    issued_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user"]), models.Index(fields=["status"]), models.Index(fields=["-issued_at"])]

    def __str__(self):
        ttype = self.ticket_type.name if self.ticket_type else "--"
        return f"Ticket {self.id} — {self.content.title} ({ttype})"

class Receipt(models.Model):
    """Receipt model for transactions. Can be linked to an event (Content) or standalone."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    church = models.ForeignKey("Church", on_delete=models.CASCADE, related_name="receipts")
    
    # Optional links to specific transactions
    content = models.ForeignKey("Content", on_delete=models.SET_NULL, null=True, blank=True, related_name="receipts")    
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    description = models.TextField(blank=True)
    
    issued_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    

    class Meta:
        ordering = ["-issued_at"]
        indexes = [
            models.Index(fields=["church"]),
            models.Index(fields=["-issued_at"]),
        ]

    def __str__(self):
        who = self.user.phone_number if self.user else (self.church.title if self.church else "Unknown")
        return f"Receipt {self.receipt_number} — {who} — {self.amount} {self.currency}"

# =====================================================
# Chat Model
# =====================================================
class ChatRoom(models.Model):
    """Chat room for church, commission, roles, custom member selection, or programme"""
    
    ROOM_TYPES = (
        ('CHURCH', 'Tous les membres'),
        ('OWNER', 'Propriétaires'),
        ('PASTOR', 'Pasteurs'),
        ('COMMISSION', 'Commission'),
        ('PROGRAMME', 'Programme'),
        ('CUSTOM', 'Personnalisé'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey("Church", on_delete=models.CASCADE, related_name="chat_rooms")
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES, default='CHURCH')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    avatar_url = models.URLField(max_length=500, blank=True, null=True)
    only_admins_can_send = models.BooleanField(default=False)
    
    # Optional: for COMMISSION type
    commission = models.ForeignKey("Commission", on_delete=models.CASCADE, null=True, blank=True, related_name="chat_rooms")
    
    # Optional: for PROGRAMME type
    programme = models.ForeignKey("Programme", on_delete=models.CASCADE, null=True, blank=True, related_name="chat_rooms")
    
    # Custom members (for CUSTOM type)
    members = models.ManyToManyField("User", blank=True, related_name="custom_chat_rooms")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey("User", on_delete=models.SET_NULL, null=True, related_name="created_chat_rooms")

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["church", "room_type"]),
            models.Index(fields=["commission"]),
        ]

    def __str__(self):
        return f"{self.church.title} - {self.get_room_type_display()} - {self.name}"
    
    def user_has_access(self, user):
        """Check if a user has access to this room"""
        if not user.is_authenticated:
            return False

        if getattr(user, "role", None) == "SADMIN":
            return True

        is_admin = User.objects.filter(
            id=user.id,
            church_roles__church=self.church,
            church_roles__role__in=["OWNER", "ADMIN"],
        ).exists()
        if is_admin:
            return True
        
        # Check based on room type
        if self.room_type == 'CHURCH':
            return user.current_church_id == self.church_id
        
        elif self.room_type == 'OWNER':
            return User.objects.filter(
                id=user.id,
                church_roles__church=self.church,
                church_roles__role='OWNER'
            ).exists()
        
        elif self.room_type == 'PASTOR':
            return User.objects.filter(
                id=user.id,
                church_roles__church=self.church,
                church_roles__role='PASTOR'
            ).exists()
        
        elif self.room_type == 'COMMISSION':
            if self.commission:
                return User.objects.filter(
                    id=user.id,
                    church_commissions__church=self.church,
                    church_commissions__commission=self.commission,
                ).exists()
            return False

        elif self.room_type == 'PROGRAMME':
            if self.programme:
                return User.objects.filter(
                    id=user.id,
                    programmes__programme=self.programme,
                ).exists()
            return False
        
        elif self.room_type == 'CUSTOM':
            return self.created_by_id == user.id or self.members.filter(id=user.id).exists()
        
        return False

    def user_can_send_message(self, user):
        if not self.user_has_access(user):
            return False

        if not self.only_admins_can_send:
            return True

        if getattr(user, "role", None) == "SADMIN":
            return True

        is_admin = User.objects.filter(
            id=user.id,
            church_roles__church=self.church,
            church_roles__role__in=["OWNER", "ADMIN"],
        ).exists()
        if is_admin:
            return True

        return self.room_type == "CUSTOM" and self.created_by_id == user.id
    
    def get_members_queryset(self):
        """Get all members who have access to this room based on type"""
        from django.db.models import Q
        
        # Get owners
        owners_qs = User.objects.filter(
            church_roles__church=self.church,
            church_roles__role='OWNER'
        )
        
        if self.room_type == 'CHURCH':
            # All church members + owners
            return User.objects.filter(
                Q(current_church=self.church) | 
                Q(church_roles__church=self.church, church_roles__role='OWNER')
            ).distinct()
        
        elif self.room_type == 'OWNER':
            # All owners of the church
            return owners_qs.distinct()
        
        elif self.room_type == 'PASTOR':
            # All pastors + owners
            return User.objects.filter(
                Q(church_roles__church=self.church, church_roles__role='PASTOR') |
                Q(church_roles__church=self.church, church_roles__role='OWNER')
            ).distinct()
        
        elif self.room_type == 'COMMISSION':
            # All commission members + church admins
            if self.commission:
                return User.objects.filter(
                    Q(
                        church_commissions__church=self.church,
                        church_commissions__commission=self.commission,
                    ) |
                    Q(church_roles__church=self.church, church_roles__role__in=['OWNER', 'ADMIN'])
                ).distinct()
            return owners_qs.distinct()

        elif self.room_type == 'PROGRAMME':
            if self.programme:
                return User.objects.filter(
                    Q(programmes__programme=self.programme) |
                    Q(church_roles__church=self.church, church_roles__role__in=['OWNER', 'ADMIN'])
                ).distinct()
            return owners_qs.distinct()
        
        elif self.room_type == 'CUSTOM':
            # Custom members + creator + church admins
            custom_members = self.members.values_list('id', flat=True)
            return User.objects.filter(
                Q(id__in=custom_members) |
                Q(id=self.created_by_id) |
                Q(church_roles__church=self.church, church_roles__role__in=['OWNER', 'ADMIN'])
            ).distinct()
        
        return owners_qs.distinct()

class ChatMessage(models.Model):
    """Chat messages in a room"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey("ChatRoom", on_delete=models.CASCADE, related_name="messages")
    user = models.ForeignKey("User", on_delete=models.CASCADE, related_name="chat_messages")
    message = models.TextField(blank=True)
    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
    )
    
    # AWS URLs
    image_url = models.URLField(max_length=500, null=True, blank=True)
    audio_url = models.URLField(max_length=500, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["room", "-created_at"]),
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"{self.user.name} - {self.room.name}"


class ChatMessageRead(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        "ChatMessage",
        on_delete=models.CASCADE,
        related_name="reads",
    )
    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="chat_message_reads",
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("message", "user")
        indexes = [
            models.Index(fields=["message", "user"]),
            models.Index(fields=["user", "read_at"]),
        ]


# =====================================================
# Testimony Model - Témoignages textuels ou audio
# =====================================================

class Testimony(models.Model):
    """Testimonies (testimonials) in a church - text or audio"""
    
    TYPE_CHOICES = [
        ("TEXT", "Texte"),
        ("AUDIO", "Audio"),
    ]
    
    STATUS_CHOICES = [
        ("PENDING", "En attente d'approbation"),
        ("APPROVED", "Approuvé"),
        ("REJECTED", "Rejeté"),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relationships
    church = models.ForeignKey(
        "Church",
        on_delete=models.CASCADE,
        related_name="testimonies"
    )
    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="testimonies"
    )
    
    # Content
    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        db_index=True
    )
    title = models.CharField(
        max_length=200,
        blank=True,
        null=True
    )
    text_content = models.TextField(
        blank=True,
        null=True,
        help_text="Le contenu texte du témoignage"
    )
    audio_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL de l'audio du témoignage"
    )
    duration = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Durée en secondes pour les audios"
    )
    
    # Metadata
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING",
        db_index=True
    )
    is_public = models.BooleanField(
        default=True,
        help_text="Visible publiquement dans l'église"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Moderation
    approved_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_testimonies"
    )
    rejection_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Raison du rejet si applicable"
    )
    
    # Stats
    views_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["church", "-created_at"]),
            models.Index(fields=["user"]),
            models.Index(fields=["church", "status"]),
            models.Index(fields=["church", "is_public", "-created_at"]),
        ]
    
    def __str__(self):
        return f"{self.user.name} - {self.church.title} ({self.type})"
    
    def approve(self, approved_by_user):
        """Approuve le témoignage"""
        self.status = "APPROVED"
        self.approved_by = approved_by_user
        self.approved_at = timezone.now()
        self.save()
    
    def reject(self, reason):
        """Rejette le témoignage"""
        self.status = "REJECTED"
        self.rejection_reason = reason
        self.save()

# =====================================================
# Church Collaboration Model
# =====================================================

class ChurchCollaboration(models.Model):
    """Collaborations between churches"""
    
    STATUS_CHOICES = [
        ("PENDING", "En attente"),
        ("ACCEPTED", "Acceptée"),
        ("REJECTED", "Rejetée"),
    ]
    
    TYPE_CHOICES = [
        ("PARTNERSHIP", "Partenariat"),
        ("RESOURCE_SHARING", "Partage de ressources"),
        ("FATHER", "Ministère parternel"),
        ("OTHER", "Autre"),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relationships
    initiator_church = models.ForeignKey(
        "Church",
        on_delete=models.CASCADE,
        related_name="initiated_collaborations",
        help_text="L'église qui initie la collaboration"
    )
    target_church = models.ForeignKey(
        "Church",
        on_delete=models.CASCADE,
        related_name="received_collaborations",
        help_text="L'église avec laquelle collaborer"
    )
    created_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_collaborations"
    )
    
    # Details
  
    collaboration_type = models.CharField(
        max_length=50,
        choices=TYPE_CHOICES,
        default="PARTNERSHIP",
        db_index=True
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING",
        db_index=True
    )
    
    # Dates
    start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date de début de la collaboration"
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    
    # Moderation

    accepted_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_collaborations"
    )
    
    # Additional info


    class Meta:
        unique_together = [
            ['initiator_church', 'target_church'],
        ]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['initiator_church', 'status']),
            models.Index(fields=['target_church', 'status']),
            models.Index(fields=['collaboration_type']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.initiator_church.title} + {self.target_church.title} ({self.get_status_display()})"
    
    def accept(self, accepted_by_user):
        """Accepte la collaboration"""
        self.status = "ACCEPTED"
        self.accepted_by = accepted_by_user
        self.accepted_at = timezone.now()
        self.save()
    
    def reject(self):
        """Rejette la collaboration"""
        self.status = "REJECTED"
        self.rejected_at = timezone.now()
        self.save()

# =====================================================
# Testimony Like Model
# =====================================================

class TestimonyLike(models.Model):
    """Likes on testimonies"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relationships
    testimony = models.ForeignKey(
        "Testimony",
        on_delete=models.CASCADE,
        related_name="likes"
    )
    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="liked_testimonies"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = [['testimony', 'user']]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['testimony']),
            models.Index(fields=['user']),
        ]
    
    def __str__(self):
        return f"{self.user.name} likes {self.testimony.id}"


# =====================================================
# Programme Model
# =====================================================

class Programme(models.Model):
    """Programmes organisés par une église contenant plusieurs événements/enseignements"""
    
    STATUS_CHOICES = [
        ("DRAFT", "Brouillon"),
        ("PUBLISHED", "Publié"),
        ("ARCHIVED", "Archivé"),
        ("CANCELLED", "Annulé"),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relationships
    church = models.ForeignKey(
        "Church",
        on_delete=models.CASCADE,
        related_name="programmes",
        help_text="L'église qui organise le programme"
    )
    created_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_programmes"
    )
    
    # Details
    title = models.CharField(
        max_length=250,
        db_index=True,
        help_text="Titre du programme"
    )
    description = models.TextField(
        blank=True,
        help_text="Description détaillée du programme"
    )
    cover_image_url = models.URLField(
        blank=True,
        null=True,
        help_text="Image de couverture du programme"
    )
    
    # Dates
    start_date = models.DateField(
        db_index=True,
        help_text="Date de début du programme"
    )
    end_date = models.DateField(
        help_text="Date de fin du programme"
    )
    
    # Status & visibility
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT",
        db_index=True
    )
    is_public = models.BooleanField(
        default=False,
        help_text="Visible pour les églises collaboratrices"
    )
    
    # Introductory content (shown before programme starts)
    intro_video_url = models.URLField(
        blank=True,
        null=True,
        help_text="Vidéo introductive accessible avant le démarrage"
    )
    intro_document_url = models.URLField(
        blank=True,
        null=True,
        help_text="Document introductif (PDF, etc.) accessible avant le démarrage"
    )
    
    # Content references
    content_items = models.ManyToManyField(
        "Content",
        related_name="programmes",
        blank=True,
        help_text="Les événements, enseignements, etc. du programme"
    )
    
    # Metadata
    duration_in_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Durée en jours (calculé automatiquement)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['church', 'status']),
            models.Index(fields=['church', 'start_date']),
            models.Index(fields=['status', 'is_public']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.church.title}"
    
    def save(self, *args, **kwargs):
        """Calcul automatique de la durée"""
        if self.start_date and self.end_date:
            self.duration_in_days = (self.end_date - self.start_date).days + 1
        super().save(*args, **kwargs)
    
    def get_event_count(self):
        """Nombre d'événements/contenus du programme"""
        return self.content_items.count()
    
    def is_active(self):
        """Vérifier si le programme est actuellement actif"""
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date
    
    def get_member_count(self):
        """Nombre de membres dans le programme"""
        return self.members.count()
    
    def is_coming_soon(self):
        """Vérifier si le programme n'a pas encore commencé"""
        today = timezone.now().date()
        return self.status == "PUBLISHED" and today < self.start_date
    
    def get_status(self):
        """Retourner le statut du programme (COMING_SOON, ACTIVE, FINISHED)"""
        today = timezone.now().date()
        if today < self.start_date:
            return "COMING_SOON"
        elif self.start_date <= today <= self.end_date:
            return "ACTIVE"
        else:
            return "FINISHED"


# =====================================================
# Programme Member Model
# =====================================================

class ProgrammeMember(models.Model):
    """Membres d'un programme"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relationships
    programme = models.ForeignKey(
        "Programme",
        on_delete=models.CASCADE,
        related_name="members"
    )
    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="programmes"
    )
    
    # Timestamps
    joined_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        unique_together = [['programme', 'user']]
        ordering = ['-joined_at']
        indexes = [
            models.Index(fields=['programme', 'user']),
            models.Index(fields=['user']),
        ]
    
    def __str__(self):
        return f"{self.user.name} - {self.programme.title}"


# =====================================================
# Content Notification Model (Coming Soon)
# =====================================================

class ContentNotification(models.Model):
    """Notifications pour les contenus 'Coming Soon'"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relationships
    content = models.ForeignKey(
        "Content",
        on_delete=models.CASCADE,
        related_name="notifications"
    )
    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="content_notifications"
    )
    
    # Notification status
    is_notified = models.BooleanField(
        default=False,
        help_text="Si l'utilisateur a été notifié de la publication"
    )
    
    # Timestamps
    subscribed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = [['content', 'user']]
        ordering = ['-subscribed_at']
        indexes = [
            models.Index(fields=['content', 'is_notified']),
            models.Index(fields=['user', 'is_notified']),
        ]
    
    def __str__(self):
        return f"{self.user.name} → {self.content.title}"


# =====================================================
# Programme Notification Model
# =====================================================

class ProgrammeNotification(models.Model):
    """
    Subscription aux notifications pour les programmes Coming Soon
    Utilisé quand un utilisateur veut être notifié du début d'un programme auquel il a adhéré
    """
    
    programme = models.ForeignKey(
        "Programme",
        on_delete=models.CASCADE,
        related_name="notifications"
    )
    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="programme_notifications"
    )
    
    # Notification status
    is_notified = models.BooleanField(
        default=False,
        help_text="Si l'utilisateur a été notifié du démarrage"
    )
    
    # Timestamps
    subscribed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = [['programme', 'user']]
        ordering = ['-subscribed_at']
        indexes = [
            models.Index(fields=['programme', 'is_notified']),
            models.Index(fields=['user', 'is_notified']),
        ]
    
    def __str__(self):
        return f"{self.user.name} → {self.programme.title} (start: {self.programme.start_date})"


# =====================================================
# Programme Content Notification Model
# =====================================================

class ProgrammeContentNotification(models.Model):
    """
    Notifications quand du CONTENU est ajouté/modifié dans un programme
    Les membres du programme sont notifiés de chaque nouveau contenu
    Permet plusieurs notifications sur le même contenu (via différents contenus)
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relationships
    programme = models.ForeignKey(
        "Programme",
        on_delete=models.CASCADE,
        related_name="content_notifications"
    )
    content = models.ForeignKey(
        "Content",
        on_delete=models.CASCADE,
        related_name="programme_notifications"
    )
    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="programme_content_notifications"
    )
    
    # Notification status
    is_notified = models.BooleanField(
        default=False,
        help_text="Si l'utilisateur a été notifié"
    )
    is_read = models.BooleanField(
        default=False,
        help_text="Si l'utilisateur a lu la notification"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        # Allow multiple notifications for same content (added/modified at different times)
        unique_together = [['programme', 'content', 'user', 'created_at']]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['programme', 'user', 'is_notified']),
            models.Index(fields=['programme', 'is_notified']),
            models.Index(fields=['user', 'is_read']),
        ]
    
    def __str__(self):
        return f"{self.user.name} → {self.programme.title} - {self.content.title}"


# =====================================================
# Service Configuration Model
# =====================================================

class ServiceConfiguration(models.Model):
    """Configuration des services tiers (SMS, WhatsApp, FreeMoPay, etc.)"""

    SERVICE_TYPE_CHOICES = [
        ('maintenance', 'Mode Maintenance'),
        ('whatsapp', 'WhatsApp API'),
        ('nexaah_sms', 'Nexaah SMS'),
        ('freemopay', 'FreeMoPay Payment'),
        ('notification_preferences', 'Préférences de Notification'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Type de service
    service_type = models.CharField(
        max_length=50,
        choices=SERVICE_TYPE_CHOICES,
        unique=True,
        db_index=True,
        help_text="Type de service à configurer"
    )

    # Statut
    is_active = models.BooleanField(
        default=False,
        help_text="Activer/Désactiver le service"
    )

    # Configuration générique
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configuration additionnelle (JSON)"
    )

    # ============== Maintenance Mode ==============
    maintenance_message = models.TextField(
        blank=True,
        null=True,
        help_text="Message affiché en mode maintenance"
    )

    # ============== WhatsApp Configuration ==============
    whatsapp_api_token = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Token d'API Meta/Facebook"
    )
    whatsapp_phone_number_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="ID du numéro de téléphone WhatsApp"
    )
    whatsapp_api_version = models.CharField(
        max_length=20,
        default="v18.0",
        blank=True,
        null=True,
        help_text="Version de l'API WhatsApp"
    )
    whatsapp_template_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Nom du template WhatsApp"
    )
    whatsapp_language = models.CharField(
        max_length=10,
        default="fr",
        blank=True,
        null=True,
        help_text="Langue des messages WhatsApp"
    )

    # ============== Nexaah SMS Configuration ==============
    nexaah_base_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL de base de l'API Nexaah"
    )
    nexaah_send_endpoint = models.CharField(
        max_length=200,
        default="/send",
        blank=True,
        null=True,
        help_text="Endpoint pour envoyer les SMS"
    )
    nexaah_credits_endpoint = models.CharField(
        max_length=200,
        default="/credits",
        blank=True,
        null=True,
        help_text="Endpoint pour vérifier les crédits"
    )
    nexaah_user = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Nom d'utilisateur Nexaah"
    )
    nexaah_password = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Mot de passe Nexaah"
    )
    nexaah_sender_id = models.CharField(
        max_length=50,
        default="Christlumen",
        blank=True,
        null=True,
        help_text="ID de l'expéditeur SMS"
    )

    # ============== FreeMoPay Configuration ==============
    freemopay_base_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL de base de l'API FreeMoPay"
    )
    freemopay_app_key = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Clé d'application FreeMoPay"
    )
    freemopay_secret_key = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Clé secrète FreeMoPay"
    )
    freemopay_callback_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL de callback pour les paiements"
    )
    freemopay_init_payment_timeout = models.PositiveIntegerField(
        default=60,
        help_text="Timeout pour l'initialisation du paiement (secondes)"
    )
    freemopay_status_check_timeout = models.PositiveIntegerField(
        default=30,
        help_text="Timeout pour la vérification du statut (secondes)"
    )
    freemopay_token_timeout = models.PositiveIntegerField(
        default=60,
        help_text="Timeout pour l'obtention du token (secondes)"
    )
    freemopay_token_cache_duration = models.PositiveIntegerField(
        default=3600,
        help_text="Durée de cache du token (secondes)"
    )
    freemopay_max_retries = models.PositiveIntegerField(
        default=3,
        help_text="Nombre maximum de tentatives"
    )
    freemopay_retry_delay = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=1.0,
        help_text="Délai entre les tentatives (secondes)"
    )

    # ============== Notification Preferences ==============
    default_notification_channel = models.CharField(
        max_length=20,
        choices=[
            ('whatsapp', 'WhatsApp'),
            ('sms', 'SMS'),
            ('email', 'Email'),
        ],
        default='whatsapp',
        blank=True,
        null=True,
        help_text="Canal de notification par défaut"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['service_type']
        verbose_name = "Configuration de Service"
        verbose_name_plural = "Configurations"
        indexes = [
            models.Index(fields=['service_type']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.get_service_type_display()} ({'Actif' if self.is_active else 'Inactif'})"

    @classmethod
    def get_config(cls, service_type):
        """Récupère la configuration d'un service"""
        try:
            return cls.objects.get(service_type=service_type)
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_maintenance_config(cls):
        """Récupère la configuration du mode maintenance"""
        return cls.get_config('maintenance')

    @classmethod
    def get_whatsapp_config(cls):
        """Récupère la configuration WhatsApp"""
        return cls.get_config('whatsapp')

    @classmethod
    def get_nexaah_config(cls):
        """Récupère la configuration Nexaah SMS"""
        return cls.get_config('nexaah_sms')

    @classmethod
    def get_freemopay_config(cls):
        """Récupère la configuration FreeMoPay"""
        return cls.get_config('freemopay')

    @classmethod
    def is_maintenance_mode(cls):
        """Vérifie si le mode maintenance est activé"""
        config = cls.get_maintenance_config()
        return config.is_active if config else False

    def validate_whatsapp_config(self):
        """Valide la configuration WhatsApp"""
        errors = []
        if not self.whatsapp_api_token:
            errors.append("WhatsApp API Token est requis")
        if not self.whatsapp_phone_number_id:
            errors.append("WhatsApp Phone Number ID est requis")
        if not self.whatsapp_template_name:
            errors.append("WhatsApp Template Name est requis")
        return errors

    def validate_nexaah_config(self):
        """Valide la configuration Nexaah SMS"""
        errors = []
        if not self.nexaah_base_url:
            errors.append("Nexaah Base URL est requis")
        if not self.nexaah_user:
            errors.append("Nexaah User est requis")
        if not self.nexaah_password:
            errors.append("Nexaah Password est requis")
        if not self.nexaah_sender_id:
            errors.append("Nexaah Sender ID est requis")
        return errors

    def validate_freemopay_config(self):
        """Valide la configuration FreeMoPay"""
        errors = []
        if not self.freemopay_app_key:
            errors.append("FreeMoPay App Key est requis")
        if not self.freemopay_secret_key:
            errors.append("FreeMoPay Secret Key est requis")
        if not self.freemopay_callback_url:
            errors.append("FreeMoPay Callback URL est requis")
        return errors

    def is_configured(self):
        """Vérifie si le service est correctement configuré"""
        if not self.is_active:
            return False

        errors = []
        if self.service_type == 'whatsapp':
            errors = self.validate_whatsapp_config()
        elif self.service_type == 'nexaah_sms':
            errors = self.validate_nexaah_config()
        elif self.service_type == 'freemopay':
            errors = self.validate_freemopay_config()

        return len(errors) == 0
