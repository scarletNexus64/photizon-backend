from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Q
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from django.utils.dateparse import parse_date
from api.models import BookOrder, ChurchAdmin, Content, Donation, DonationCategory, Church, User, TicketType, Payment
from api.serializers import BookOrderSerializer, DonationSerializer, DonationCategorySerializer, TicketSerializer
from api.permissions import IsAuthenticatedUser, user_is_church_owner, IsSuperAdmin
from api.services.notification_preferences import create_in_app_notification

# ----------------------
# DonationCategory CRUD
# ----------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_categories_d(request):
    categories = DonationCategory.objects.all()
    serializer = DonationCategorySerializer(categories, many=True)
    return Response(serializer.data)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_category_d(request):
    serializer = DonationCategorySerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_category_d(request, category_id):
    category = get_object_or_404(DonationCategory, id=category_id)
    serializer = DonationCategorySerializer(category)
    return Response(serializer.data)

@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def update_category_d(request, category_id):
    category = get_object_or_404(DonationCategory, id=category_id)
    serializer = DonationCategorySerializer(category, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_category_d(request, category_id):
    category = get_object_or_404(DonationCategory, id=category_id)
    category.delete()
    return Response({"detail": "Category deleted"}, status=204)

# ----------------------
# Donations CRUD & Stats
# ----------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def make_donation(request, church_id):
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    category_id = request.data.get("category")
    category = None
    if category_id:
        category = get_object_or_404(DonationCategory, id=category_id)

    amount = request.data.get("amount")
    gateway = request.data.get("gateway", "CASH")
    message = request.data.get("message", "")

    if not amount:
        return Response({"error": "Amount is required"}, status=400)

    donation = Donation.objects.create(
        user=request.user,
        church=church,
        category=category,
        amount=amount,
        gateway=gateway,
        message=message
    )

    payment_status = "SUCCESS" if gateway == "CASH" else "PENDING"
    Payment.objects.create(
        user=request.user,
        church=church,
        donation=donation,
        amount=donation.amount,
        currency=donation.currency,
        gateway=gateway,
        status=payment_status,
        metadata={
            "source": "donation",
            "category_id": str(category.id) if category else None,
            "category_name": category.name if category else None,
            "message": message,
        },
    )

    if gateway == "CASH":
        donation.confirmed_at = timezone.now()
        donation.metadata = {
            **donation.metadata,
            "payment_status": "SUCCESS",
            "ready_for_gateway": False,
        }
        donation.save(update_fields=["confirmed_at", "metadata"])
    else:
        donation.metadata = {
            **donation.metadata,
            "payment_status": "PENDING",
            "ready_for_gateway": True,
        }
        donation.save(update_fields=["metadata"])

    category_label = category.name if category else "Don"
    create_in_app_notification(
        user=request.user,
        title="Don enregistré",
        message=(
            f"Votre don de {donation.amount} {donation.currency} pour {category_label} "
            f"a été enregistré avec le canal {gateway}."
        ),
        notif_type="SUCCESS",
        category="donation",
        meta={
            "donation_id": str(donation.id),
            "payment_gateway": gateway,
            "payment_status": payment_status,
        },
    )

    serializer = DonationSerializer(donation)
    return Response(serializer.data, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_user_donations(request):
    donations = Donation.objects.filter(user=request.user).order_by("-created_at")
    serializer = DonationSerializer(donations, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_church_donations(request, church_id, include_subchurches=False):
    """
    Liste des dons pour une église.
    Si include_subchurches=True, inclut les sous-églises
    """
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    qs = Donation.objects.filter(church__in=[church.id])

    if include_subchurches:
        sub_ids = church.sub_churches.all().values_list("id", flat=True)
        qs = Donation.objects.filter(church__id__in=[church.id, *sub_ids])

    serializer = DonationSerializer(qs.order_by("-created_at"), many=True)
    return Response(serializer.data)


# ----------------------
# Stats par église
# ----------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def church_donation_stats(request, church_id, include_subchurches=True):
    """
    Retourne les stats pour une église :
    - total général
    - total par mois
    - total par année
    """
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    qs = Donation.objects.filter(church=church)

    if include_subchurches:
        sub_ids = church.sub_churches.all().values_list("id", flat=True)
        qs = Donation.objects.filter(church__id__in=[church.id, *sub_ids])

    total_sum = qs.aggregate(total=Sum("amount"))["total"] or 0

    # Stats par mois
    monthly = {}
    for i in range(12):
        month_start = timezone.now() - relativedelta(months=i)
        month_qs = qs.filter(
            created_at__year=month_start.year,
            created_at__month=month_start.month
        )
        monthly[f"{month_start.year}-{month_start.month:02d}"] = month_qs.aggregate(sum=Sum("amount"))["sum"] or 0

    # Stats par année
    years = qs.dates("created_at", "year")
    yearly = {}
    for y in years:
        year_qs = qs.filter(created_at__year=y.year)
        yearly[str(y.year)] = year_qs.aggregate(sum=Sum("amount"))["sum"] or 0

    return Response({
        "church_id": church.id,
        "church_title": church.title,
        "total_sum": total_sum,
        "monthly": monthly,
        "yearly": yearly
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def church_order_stats(request, church_id, include_subchurches=True):
    """Return order stats for a given church: grand total, monthly (12 months), yearly, and breakdown by content type/is_ticket."""
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)

    # Base queryset: orders for this church
    if include_subchurches:
        sub_ids = list(church.sub_churches.all().values_list("id", flat=True))
        qs = BookOrder.objects.filter(content__church__id__in=[church.id, *sub_ids])
    else:
        qs = BookOrder.objects.filter(content__church=church)

    grand_total = qs.aggregate(total=Sum("total_price"))["total"] or 0

    # Monthly totals for last 12 months
    monthly = {}
    now = timezone.now()
    for i in range(12):
        d = now - relativedelta(months=i)
        month_sum = qs.filter(created_at__year=d.year, created_at__month=d.month).aggregate(sum=Sum("total_price"))["sum"] or 0
        monthly[f"{d.year}-{d.month:02d}"] = month_sum

    # Yearly totals
    yearly = {}
    years = qs.dates("created_at", "year")
    for y in years:
        year_sum = qs.filter(created_at__year=y.year).aggregate(sum=Sum("total_price"))["sum"] or 0
        yearly[str(y.year)] = year_sum

    # Breakdown by content type and by is_ticket
    by_type = (
        qs.values("content__type").annotate(total=Sum("total_price"), count=Sum("quantity"))
    )
    type_summary = {item["content__type"]: {"total": item["total"] or 0, "count": item["count"] or 0} for item in by_type}

    by_ticket = (
        qs.values("is_ticket").annotate(total=Sum("total_price"), count=Sum("quantity"))
    )
    ticket_summary = {str(item["is_ticket"]): {"total": item["total"] or 0, "count": item["count"] or 0} for item in by_ticket}

    # Top contents by revenue
    top_contents_qs = (
        qs.values("content__id", "content__title").annotate(revenue=Sum("total_price")).order_by("-revenue")[:10]
    )
    top_contents = [
        {"id": c["content__id"], "title": c["content__title"], "revenue": c["revenue"] or 0} for c in top_contents_qs
    ]

    return Response({
        "church_id": church.id,
        "church_title": church.title,
        "grand_total": grand_total,
        "monthly": monthly,
        "yearly": yearly,
        "by_type": type_summary,
        "by_ticket": ticket_summary,
        "top_contents": top_contents,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def church_payment_stats(request, church_id, include_subchurches=True):
    """Return payment stats for a church: daily, monthly (last 12 months), yearly and grand total."""
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)

    # Base queryset: payments for this church (optionally include subchurches)
    if include_subchurches:
        sub_ids = list(church.sub_churches.all().values_list("id", flat=True))
        qs = Payment.objects.filter(church__id__in=[church.id, *sub_ids])
    else:
        qs = Payment.objects.filter(church=church)

    grand_total = qs.aggregate(total=Sum("amount"))["total"] or 0

    # Daily total (today)
    today = timezone.now().date()
    daily_total = qs.filter(created_at__date=today).aggregate(total=Sum("amount"))["total"] or 0

    # Monthly totals for last 12 months
    monthly = {}
    now = timezone.now()
    for i in range(12):
        d = now - relativedelta(months=i)
        month_sum = qs.filter(created_at__year=d.year, created_at__month=d.month).aggregate(sum=Sum("amount"))["sum"] or 0
        monthly[f"{d.year}-{d.month:02d}"] = month_sum

    # Yearly totals
    yearly = {}
    years = qs.dates("created_at", "year")
    for y in years:
        year_sum = qs.filter(created_at__year=y.year).aggregate(sum=Sum("amount"))["sum"] or 0
        yearly[str(y.year)] = year_sum

    return Response({
        "church_id": church.id,
        "church_title": church.title,
        "grand_total": grand_total,
        "daily": daily_total,
        "monthly": monthly,
        "yearly": yearly,
    })


# ----------------------
# Admin stats : toutes les églises
# ----------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_all_churches_donation_stats(request):
    """
    Retourne stats pour toutes les églises :
    - somme totale par église
    - stats mensuelles / annuelles par église
    - somme générale
    - grand total mensuel et annuel toutes églises
    """
    all_churches = Church.objects.all()
    result = []
    grand_total = 0

    # Préparer les périodes pour les 12 derniers mois
    now = timezone.now()
    last_12_months = [(now - relativedelta(months=i)).replace(day=1) for i in range(12)]
    monthly_totals_all_churches = {d.strftime("%Y-%m"): 0 for d in last_12_months}

    # Préparer années existantes pour les dons
    all_years = Donation.objects.dates("created_at", "year")
    yearly_totals_all_churches = {y.year: 0 for y in all_years}

    for church in all_churches:
        # Inclure les sous-églises
        qs = Donation.objects.filter(
            church__in=[church.id, *church.sub_churches.all().values_list("id", flat=True)]
        )
        total_sum = qs.aggregate(total=Sum("amount"))["total"] or 0
        grand_total += total_sum

        # Stats mensuelles par église
        monthly = {}
        for d in last_12_months:
            month_qs = qs.filter(created_at__year=d.year, created_at__month=d.month)
            month_sum = month_qs.aggregate(sum=Sum("amount"))["sum"] or 0
            monthly[d.strftime("%Y-%m")] = month_sum
            monthly_totals_all_churches[d.strftime("%Y-%m")] += month_sum  # cumul global

        # Stats annuelles par église
        yearly = {}
        for y in all_years:
            year_qs = qs.filter(created_at__year=y.year)
            year_sum = year_qs.aggregate(sum=Sum("amount"))["sum"] or 0
            yearly[str(y.year)] = year_sum
            yearly_totals_all_churches[y.year] += year_sum  # cumul global

        result.append({
            "church_id": church.id,
            "church_title": church.title,
            "total_sum": total_sum,
            "monthly": monthly,
            "yearly": yearly
        })

    return Response({
        "grand_total": grand_total,
        "churches": result,
        "monthly_totals_all_churches": monthly_totals_all_churches,
        "yearly_totals_all_churches": yearly_totals_all_churches
    })


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def admin_all_churches_payment_stats(request):
    """Aggregate payment stats across all churches (per-church totals, monthly and yearly breakdowns, grand total)."""
    # Optional filters from query params
    gateway = request.query_params.get("gateway")
    status = request.query_params.get("status")
    start_date = request.query_params.get("start_date")
    end_date = request.query_params.get("end_date")

    all_churches = Church.objects.all()
    result = []
    grand_total = 0

    # Prepare last 12 months buckets
    now = timezone.now()
    last_12_months = [(now - relativedelta(months=i)).replace(day=1) for i in range(12)]
    monthly_totals_all_churches = {d.strftime("%Y-%m"): 0 for d in last_12_months}

    # Prepare years existing for payments
    all_years = Payment.objects.dates("created_at", "year")
    yearly_totals_all_churches = {y.year: 0 for y in all_years}

    for church in all_churches:
        qs = Payment.objects.filter(church__in=[church.id, *church.sub_churches.all().values_list("id", flat=True)])
        # apply filters
        if gateway:
            qs = qs.filter(gateway__iexact=gateway)
        if status:
            qs = qs.filter(status__iexact=status)
        if start_date:
            sd = parse_date(start_date)
            if sd:
                qs = qs.filter(created_at__date__gte=sd)
        if end_date:
            ed = parse_date(end_date)
            if ed:
                qs = qs.filter(created_at__date__lte=ed)
        total_sum = qs.aggregate(total=Sum("amount"))["total"] or 0
        grand_total += total_sum

        # Monthly per church
        monthly = {}
        for d in last_12_months:
            month_qs = qs.filter(created_at__year=d.year, created_at__month=d.month)
            month_sum = month_qs.aggregate(sum=Sum("amount"))["sum"] or 0
            monthly[d.strftime("%Y-%m")] = month_sum
            monthly_totals_all_churches[d.strftime("%Y-%m")] += month_sum

        # Yearly per church
        yearly = {}
        for y in all_years:
            year_qs = qs.filter(created_at__year=y.year)
            year_sum = year_qs.aggregate(sum=Sum("amount"))["sum"] or 0
            yearly[str(y.year)] = year_sum
            yearly_totals_all_churches[y.year] += year_sum

        result.append({
            "church_id": church.id,
            "church_title": church.title,
            "total_sum": total_sum,
            "monthly": monthly,
            "yearly": yearly,
        })

    return Response({
        "grand_total": grand_total,
        "churches": result,
        "monthly_totals_all_churches": monthly_totals_all_churches,
        "yearly_totals_all_churches": yearly_totals_all_churches,
    })


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def admin_payments_summary(request):
    """Return global payment sums: today, last 12 months (per month), per year, and grand total."""
    # filters
    gateway = request.query_params.get("gateway")
    status = request.query_params.get("status")
    start_date = request.query_params.get("start_date")
    end_date = request.query_params.get("end_date")

    qs = Payment.objects.all()
    if gateway:
        qs = qs.filter(gateway__iexact=gateway)
    if status:
        qs = qs.filter(status__iexact=status)
    if start_date:
        sd = parse_date(start_date)
        if sd:
            qs = qs.filter(created_at__date__gte=sd)
    if end_date:
        ed = parse_date(end_date)
        if ed:
            qs = qs.filter(created_at__date__lte=ed)

    grand_total = qs.aggregate(total=Sum("amount"))["total"] or 0

    # Daily total (today)
    today = timezone.now().date()
    daily_total = qs.filter(created_at__date=today).aggregate(total=Sum("amount"))["total"] or 0

    # Monthly totals for last 12 months
    monthly = {}
    now = timezone.now()
    for i in range(12):
        d = now - relativedelta(months=i)
        month_sum = qs.filter(created_at__year=d.year, created_at__month=d.month).aggregate(sum=Sum("amount"))["sum"] or 0
        monthly[f"{d.year}-{d.month:02d}"] = month_sum

    # Yearly totals
    yearly = {}
    years = qs.dates("created_at", "year")
    for y in years:
        year_sum = qs.filter(created_at__year=y.year).aggregate(sum=Sum("amount"))["sum"] or 0
        yearly[str(y.year)] = year_sum

    return Response({
        "grand_total": grand_total,
        "daily": daily_total,
        "monthly": monthly,
        "yearly": yearly,
    })

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def admin_book_order_stats(request):
    all_orders = BookOrder.objects.select_related("content", "user").order_by("-created_at")

    grand_total = all_orders.aggregate(total=Sum("total_price"))["total"] or 0

    # Total par mois (12 derniers mois)
    monthly_totals = {}
    for i in range(12):
        month_start = timezone.now() - relativedelta(months=i)
        month_sum = all_orders.filter(
            created_at__year=month_start.year,
            created_at__month=month_start.month
        ).aggregate(sum=Sum("total_price"))["sum"] or 0
        monthly_totals[f"{month_start.year}-{month_start.month:02d}"] = month_sum

    # Total par année
    years = all_orders.dates("created_at", "year")
    yearly_totals = {}
    for y in years:
        yearly_sum = all_orders.filter(created_at__year=y.year).aggregate(sum=Sum("total_price"))["sum"] or 0
        yearly_totals[str(y.year)] = yearly_sum

    # Stats par livre
    book_stats = []
    books = Content.objects.filter(type="BOOK")
    for book in books:
        book_orders = all_orders.filter(content=book)
        total_sum = book_orders.aggregate(total=Sum("total_price"))["total"] or 0
        book_stats.append({
            "book_id": book.id,
            "title": book.title,
            "total_sum": total_sum
        })

    return Response({
        "grand_total": grand_total,
        "monthly_totals": monthly_totals,
        "yearly_totals": yearly_totals,
        "book_stats": book_stats
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_book_order(request, book_id):
    content = get_object_or_404(Content, id=book_id)
    order_type = request.data.get("delivery_type", "DIGITAL")  # DIGITAL ou PHYSICAL
    quantity = int(request.data.get("quantity", 1))
    # Ticket-related params
    is_ticket = bool(request.data.get("is_ticket", False))
    ticket_type_id = request.data.get("ticket_type_id")
    ticket_tier = request.data.get("ticket_tier")  # CLASSIC | VIP | PREMIUM
    shipped = True if order_type.upper() == "DIGITAL" else False
    delivery_at = timezone.now() if shipped else None

    # Events must be ticket orders. Enforce and validate ticket_tier when applicable.
    if content.type == "EVENT":
        is_ticket = True
        # If the event uses ticket tiers, require ticket_tier in request
        if getattr(content, "has_ticket_tiers", False):
            if not ticket_tier:
                return Response({"error": "ticket_tier is required for this event (CLASSIC, VIP, PREMIUM)"}, status=400)
            tier = (ticket_tier or "").upper()
            if tier not in ["CLASSIC", "VIP", "PREMIUM"]:
                return Response({"error": "Invalid ticket_tier. Use CLASSIC, VIP or PREMIUM."}, status=400)
            # check availability immediately for friendlier error
            qty_field = {"CLASSIC": "classic_quantity", "VIP": "vip_quantity", "PREMIUM": "premium_quantity"}.get(tier)
            avail = getattr(content, qty_field, None)
            if avail is not None and int(quantity) > int(avail):
                return Response({"error": f"Not enough tickets available for tier {tier}. Available: {avail}"}, status=400)
        else:
            # If no tiers, check overall capacity
            if content.capacity is not None and (content.capacity - (content.tickets_sold or 0)) < int(quantity):
                return Response({"error": "Not enough tickets available for this event."}, status=400)

    order_kwargs = dict(
        user=request.user,
        content=content,
        quantity=quantity,
        delivery_type=order_type.upper(),
        shipped=shipped,
        delivered_at=delivery_at,
    )
    # Optional delivery info (useful for PHYSICAL delivery_type)
    delivery_fields = [
        "delivery_recipient_name",
        "delivery_address_line1",
        "delivery_address_line2",
        "delivery_city",
        "delivery_postal_code",
        "delivery_country",
        "delivery_phone",
        "shipping_method",
        "shipping_cost",
    ]
    for f in delivery_fields:
        if f in request.data:
            order_kwargs[f] = request.data.get(f)
    if is_ticket:
        order_kwargs["is_ticket"] = True
        if ticket_type_id:
            tt = get_object_or_404(TicketType, id=ticket_type_id)
            order_kwargs["ticket_type"] = tt
        if ticket_tier:
            order_kwargs["ticket_tier"] = ticket_tier.upper()

    with transaction.atomic():
        # Verrouillage et vérification finale de la disponibilité
        if is_ticket:
            from api.models import TicketReservation
            expires_at = timezone.now() + timedelta(minutes=15)
            
            if ticket_type_id:
                # On utilise TicketType.available() qui doit inclure les réservations (on vérifiera ça après)
                tt = TicketType.objects.select_for_update().get(id=ticket_type_id)
                if tt.available() < quantity:
                    return Response({"error": "Tickets no longer available for this type."}, status=400)
                
                TicketReservation.objects.create(
                    user=request.user,
                    content=content,
                    ticket_type=tt,
                    quantity=quantity,
                    expires_at=expires_at
                )
            elif ticket_tier:
                # Pour les tiers sur Content, on verrouille le Content
                c = Content.objects.select_for_update().get(id=content.id)
                tier = ticket_tier.upper()
                qty_field = {"CLASSIC": "classic_quantity", "VIP": "vip_quantity", "PREMIUM": "premium_quantity"}.get(tier)
                avail = getattr(c, qty_field, 0)
                
                # Calculer les réservations actives pour ce tier sur ce contenu
                # Note: Le modèle TicketReservation actuel ne semble pas avoir de champ 'ticket_tier' string, 
                # seulement une FK vers TicketType. On va devoir adapter le modèle ou la logique.
                # Pour l'instant, on se base sur la capacité simple si pas de TicketType.
                
                if avail is not None and avail < quantity:
                    return Response({"error": f"Not enough tickets available for tier {tier}."}, status=400)
                
                # On crée la réservation (on aura peut-être besoin d'ajouter ticket_tier au modèle Reservation)
                TicketReservation.objects.create(
                    user=request.user,
                    content=c,
                    quantity=quantity,
                    expires_at=expires_at,
                    metadata={"ticket_tier": tier}
                )

        order = BookOrder.objects.create(**order_kwargs)

    serializer = BookOrderSerializer(order)
    return Response(serializer.data, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_book_order(request, order_id):
    """Finalize a book/ticket order after payment confirmation.
    Expects `payment_transaction_id` in body. For ticket orders, this will call `issue_tickets()`.
    """
    order = get_object_or_404(BookOrder, id=order_id)
    payment_tx = request.data.get("payment_transaction_id")

    if not payment_tx:
        return Response({"error": "payment_transaction_id required"}, status=400)

    # Attach payment tx and if ticket order, issue tickets
    if order.is_ticket:
        try:
            tickets = order.issue_tickets(payment_transaction_id=payment_tx, buyer=request.user)
        except Exception as e:
            return Response({"error": str(e)}, status=400)
        # serialize tickets
        ticket_serializer = TicketSerializer(tickets, many=True)
        return Response({"order": BookOrderSerializer(order).data, "tickets": ticket_serializer.data})

    # non-ticket orders: just attach payment id
    order.payment_transaction_id = payment_tx
    order.save()
    return Response(BookOrderSerializer(order).data)

# -----------------------------------------
# Lister les commandes d’un utilisateur
# -----------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_book_orders(request):
    orders = BookOrder.objects.filter(user=request.user).order_by("-created_at")
    serializer = BookOrderSerializer(orders, many=True)
    return Response(serializer.data)


# -----------------------------------------
# Détails / mise à jour d’une commande
# -----------------------------------------
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def book_order_detail(request, order_id):
    order = get_object_or_404(BookOrder, id=order_id)

    if request.method == "GET":
        serializer = BookOrderSerializer(order)
        return Response(serializer.data)

@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def update_book_order(request, order_id):
    """Update an order partially or fully. Same validation as PATCH in detail view."""
    order = get_object_or_404(BookOrder, id=order_id)
    serializer = BookOrderSerializer(order, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)
    if request.method == "PATCH":
        serializer = BookOrderSerializer(order, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)
    
@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def church_financial_overview(request, church_id):
    from django.db.models import Sum
    from django.utils.timezone import now

    # Vérifier que l'église existe
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response({"error": "Cette église n'existe pas."}, status=404)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)

    # 📌 Membres = Users dont current_church = church
    # inclut aussi le owner et les users présents dans ChurchAdmin
    member_users = User.objects.filter(
        Q(current_church=church) |
        Q(id=getattr(church, "owner_id", None)) |
        Q(church_roles__church=church)
    ).distinct()

    # ==========================
    #   1. ORDERS DES MEMBRES
    # ==========================

    member_orders = BookOrder.objects.filter(
        user__in=member_users,
        content__church=church
    ).select_related("user", "content")

    # ==========================
    #   2. DONATIONS DES MEMBRES
    # ==========================

    member_donations = Donation.objects.filter(
        user__in=member_users,
        church=church
    ).select_related("user", "category")

    # ==========================
    #   3. ORDERS NON MEMBRES
    # ==========================

    external_orders = BookOrder.objects.filter(
        content__church=church
    ).exclude(user__in=member_users)

    # ==========================
    #   4. DONATIONS NON MEMBRES
    # ==========================

    external_donations = Donation.objects.filter(
        church=church
    ).exclude(user__in=member_users)

    # ==============================================
    #   CALCUL DES TOTAUX (MENSUELS / ANNUELS / GLOBAL)
    # ==============================================

    current_month = now().month
    current_year = now().year

    def summarize(qs):
        return {
            "month": qs.filter(created_at__month=current_month).aggregate(total=Sum("amount"))["total"] or 0,
            "year": qs.filter(created_at__year=current_year).aggregate(total=Sum("amount"))["total"] or 0,
            "total": qs.aggregate(total=Sum("amount"))["total"] or 0,
            "withdrawed": qs.filter(withdrawed=True).aggregate(total=Sum("amount"))["total"] or 0,
            "pending_withdrawal": qs.filter(withdrawed=False).aggregate(total=Sum("amount"))["total"] or 0,
        }

    def summarize_orders(qs):
        return {
            "month": qs.filter(created_at__month=current_month).aggregate(total=Sum("total_price"))["total"] or 0,
            "year": qs.filter(created_at__year=current_year).aggregate(total=Sum("total_price"))["total"] or 0,
            "total": qs.aggregate(total=Sum("total_price"))["total"] or 0,
            "withdrawed": qs.filter(withdrawed=True).aggregate(total=Sum("total_price"))["total"] or 0,
            "pending_withdrawal": qs.filter(withdrawed=False).aggregate(total=Sum("total_price"))["total"] or 0,
        }

    # =============================
    #   SÉRIALISATION SIMPLE
    # =============================

    def serialize_order(o):
        return {
            "id": o.id,
            "user": o.user.phone_number,
            "content": o.content.title,
            "delivery_type": o.delivery_type,
            "total_price": o.total_price,
            "quantity": o.quantity,
            "withdrawed": o.withdrawed,
            "shipped": o.shipped,
            "delivered_at": o.delivered_at,
            "created_at": o.created_at,
        }

    def serialize_donation(d):
        return {
            "id": d.id,
            "user": d.user.phone_number,
            "amount": d.amount,
            "withdrawed": d.withdrawed,
            "category": d.category.name if d.category else None,
            "gateway": d.gateway,
            "created_at": d.created_at,
        }

    # =============================
    #   REPONSE FINALE
    # =============================

    return Response({
        "members": {
            "orders": {
                "items": [serialize_order(o) for o in member_orders],
                "summary": summarize_orders(member_orders)
            },
            "donations": {
                "items": [serialize_donation(d) for d in member_donations],
                "summary": summarize(member_donations)
            }
        },
        "non_members": {
            "orders": {
                "items": [serialize_order(o) for o in external_orders],
                "summary": summarize_orders(external_orders)
            },
            "donations": {
                "items": [serialize_donation(d) for d in external_donations],
                "summary": summarize(external_donations)
            }
        }
    })

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def withdraw_all_donations_view(request, church_id):
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response({"detail": "Church not found"}, status=404)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)

    # Vérifier que l’utilisateur est admin de cette église ou le owner
    if not (ChurchAdmin.objects.filter(church=church, user=request.user).exists() or request.user == getattr(church, "owner", None)):
        return Response({"detail": "Not authorized"}, status=403)

    donations = Donation.objects.filter(church=church, withdrawed=False)

    # Mise à jour en masse
    donations.update(withdrawed=True)

    return Response({
        "message": "Toutes les donations ont été retirées avec succès",
        "count": donations.count(),
    })

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def withdraw_all_orders_view(request, church_id):
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response({"detail": "Church not found"}, status=404)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)

    # Vérifier que l’utilisateur est admin de cette église ou le owner
    if not (ChurchAdmin.objects.filter(church=church, user=request.user).exists() or request.user == getattr(church, "owner", None)):
        return Response({"detail": "Not authorized"}, status=403)

    orders = BookOrder.objects.filter(content__church=church, withdrawed=False)

    # Mise à jour en masse
    orders.update(withdrawed=True)

    return Response({
        "message": "Tous les orders ont été retirés avec succès",
        "count": orders.count(),
    })
