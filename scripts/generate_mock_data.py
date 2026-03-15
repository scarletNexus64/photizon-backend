import os
import sys
from datetime import timedelta

import django
from django.utils import timezone


# Setup Django
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BACKEND_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "christlumen.settings")
django.setup()

from api.models import (  # noqa: E402
    Category,
    ChatMessage,
    ChatRoom,
    Church,
    ChurchAdmin,
    ChurchCommission,
    Comment,
    Content,
    ContentLike,
    ContentTag,
    ContentView,
    Donation,
    DonationCategory,
    Notification,
    OTP,
    Payment,
    Playlist,
    PlaylistItem,
    Commission,
    Tag,
    User,
)


def upsert_user(phone, name, role="USER", email=None, make_staff=False):
    user, _ = User.objects.get_or_create(
        phone_number=phone,
        defaults={
            "name": name,
            "role": role,
            "email": email,
            "is_staff": make_staff,
            "is_superuser": make_staff,
        },
    )
    changed = False
    if user.name != name:
        user.name = name
        changed = True
    if user.role != role:
        user.role = role
        changed = True
    if email and user.email != email:
        user.email = email
        changed = True
    if make_staff:
        if not user.is_staff:
            user.is_staff = True
            changed = True
        if not user.is_superuser:
            user.is_superuser = True
            changed = True
    if changed:
        user.save()
    return user


def create_or_update_content(church, created_by, title, ctype, slug, **extra):
    defaults = {"type": ctype, "slug": slug, "created_by": created_by, **extra}
    content, created = Content.objects.get_or_create(
        church=church,
        title=title,
        defaults=defaults,
    )
    if not created:
        changed = False
        for key, value in defaults.items():
            if getattr(content, key) != value:
                setattr(content, key, value)
                changed = True
        if changed:
            content.save()
    return content


def upsert_category(name, slug):
    category, _ = Category.objects.get_or_create(name=name, defaults={"slug": slug})
    if category.slug != slug:
        category.slug = slug
        category.save(update_fields=["slug"])
    return category


def upsert_tag(name, slug):
    tag, _ = Tag.objects.get_or_create(name=name, defaults={"slug": slug})
    if tag.slug != slug:
        tag.slug = slug
        tag.save(update_fields=["slug"])
    return tag


def run():
    print("== Seed data ChristLumen ==")

    admin = upsert_user(
        phone="+237600000000",
        name="Super Admin Test",
        role="SADMIN",
        email="admin@test.local",
        make_staff=True,
    )
    member = upsert_user(
        phone="+237600000111",
        name="Membre Test",
        role="USER",
        email="membre@test.local",
        make_staff=False,
    )
    worship_member = upsert_user(
        phone="+237699111222",
        name="Sarah Louange",
        role="USER",
        email="sarah@test.local",
    )
    youth_member = upsert_user(
        phone="+237699111223",
        name="Marc Jeunesse",
        role="USER",
        email="marc@test.local",
    )
    prayer_member = upsert_user(
        phone="+237699111224",
        name="Esther Intercession",
        role="USER",
        email="esther@test.local",
    )

    church, _ = Church.objects.get_or_create(
        title="Église ChristLumen Principale",
        defaults={
            "description": "Église principale pour tests manuels mobile",
            "logo_url": "https://images.unsplash.com/photo-1438232992991-995b7058bbb3?w=800&q=80",
            "status": "APPROVED",
            "is_verified": True,
            "is_public": True,
            "owner": admin,
            "phone_number_1": "+237690000001",
            "city": "Douala",
            "country": "CM",
        },
    )
    church.status = "APPROVED"
    church.is_verified = True
    church.is_public = True
    church.owner = admin
    church.save()

    admin.current_church = church
    admin.save(update_fields=["current_church"])
    member.current_church = church
    member.save(update_fields=["current_church"])
    worship_member.current_church = church
    worship_member.save(update_fields=["current_church"])
    youth_member.current_church = church
    youth_member.save(update_fields=["current_church"])
    prayer_member.current_church = church
    prayer_member.save(update_fields=["current_church"])

    ChurchAdmin.objects.get_or_create(church=church, user=admin, defaults={"role": "OWNER"})
    ChurchAdmin.objects.get_or_create(church=church, user=member, defaults={"role": "PASTOR"})

    commission_specs = [
        (
            "Intercession",
            "Intercession",
            "Groupe de prière et d'accompagnement spirituel.",
            [admin, prayer_member, member],
        ),
        (
            "Louange",
            "Worship",
            "Equipe musicale et de louange.",
            [admin, worship_member],
        ),
        (
            "Jeunesse",
            "Youth",
            "Animation de la jeunesse et activités communautaires.",
            [admin, youth_member, member],
        ),
    ]
    for name, eng_name, description, users in commission_specs:
      commission, _ = Commission.objects.get_or_create(
          name=name,
          defaults={"eng_name": eng_name, "description": description},
      )
      if commission.eng_name != eng_name or commission.description != description:
          commission.eng_name = eng_name
          commission.description = description
          commission.save(update_fields=["eng_name", "description"])
      for user in users:
          role = "LEADER" if user == admin else "MEMBER"
          ChurchCommission.objects.get_or_create(
              church=church,
              commission=commission,
              user=user,
              defaults={"role": role},
          )

    cat_news = upsert_category("Actualités", "actualites")
    cat_music = upsert_category("Musique", "musique")
    cat_events = upsert_category("Événements", "evenements")
    cat_teach = upsert_category("Enseignements", "enseignements")

    tag_priere = upsert_tag("Prière", "priere")
    tag_jeunesse = upsert_tag("Jeunesse", "jeunesse")
    tag_louange = upsert_tag("Louange", "louange")

    now = timezone.now()
    posts = []
    for i in range(1, 16):
        post = create_or_update_content(
            church=church,
            created_by=admin,
            title=f"Annonce test #{i}",
            ctype="POST",
            slug=f"annonce-test-{i}",
            description=f"Ceci est l'annonce de test numéro {i} pour valider la pagination 10/10.",
            cover_image_url=f"https://picsum.photos/seed/church-post-{i}/900/500",
            category=cat_news,
            published=True,
            is_public=True,
        )
        Content.objects.filter(pk=post.pk).update(created_at=now - timedelta(hours=i))
        posts.append(post)

    audio_items = []
    for i in range(1, 6):
        audio = create_or_update_content(
            church=church,
            created_by=admin,
            title=f"Chant de louange #{i}",
            ctype="AUDIO",
            slug=f"chant-louange-{i}",
            description="Audio de test pour l'onglet Musique.",
            cover_image_url=f"https://picsum.photos/seed/church-audio-{i}/600/600",
            audio_url="https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
            category=cat_music,
            published=True,
            is_public=True,
        )
        audio_items.append(audio)
        ContentTag.objects.get_or_create(content=audio, tag=tag_louange)

    for i in range(1, 4):
        create_or_update_content(
            church=church,
            created_by=admin,
            title=f"Culte spécial #{i}",
            ctype="EVENT",
            slug=f"culte-special-{i}",
            description="Événement de test.",
            cover_image_url=f"https://picsum.photos/seed/church-event-{i}/900/500",
            start_at=now + timedelta(days=i),
            end_at=now + timedelta(days=i, hours=2),
            location="Chapelle Principale",
            category=cat_events,
            published=True,
            is_public=True,
        )

    create_or_update_content(
        church=church,
        created_by=admin,
        title="Prédication audio à venir",
        ctype="AUDIO",
        slug="predication-a-venir",
        description="Contenu coming soon pour valider la section dédiée.",
        cover_image_url="https://picsum.photos/seed/church-coming-soon/600/600",
        audio_url="https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
        category=cat_teach,
        published=True,
        is_public=True,
        planned_release_date=now + timedelta(days=4),
    )

    for p in posts[:5]:
        ContentLike.objects.get_or_create(user=member, content=p)
        Comment.objects.get_or_create(
            user=member,
            content=p,
            text=f"Commentaire de test sur {p.title}",
        )
        ContentView.objects.create(user=member, content=p)
        ContentView.objects.create(user=admin, content=p)
        ContentTag.objects.get_or_create(content=p, tag=tag_priere)
        ContentTag.objects.get_or_create(content=p, tag=tag_jeunesse)

    playlist, _ = Playlist.objects.get_or_create(
        church=church,
        title="Top Louange Test",
        defaults={
            "description": "Playlist générée automatiquement pour tests",
            "cover_image_url": "https://picsum.photos/seed/church-playlist/700/700",
        },
    )
    for idx, content in enumerate(audio_items[:4], start=1):
        PlaylistItem.objects.get_or_create(
            playlist=playlist,
            content=content,
            defaults={"position": idx},
        )

    room, _ = ChatRoom.objects.get_or_create(
        church=church,
        room_type="CHURCH",
        name="Discussion Générale",
        defaults={"created_by": admin},
    )
    if room.messages.count() == 0:
        for idx in range(1, 9):
            sender = admin if idx % 2 == 0 else member
            ChatMessage.objects.create(
                room=room,
                user=sender,
                message=f"Message de test #{idx} dans le chat général.",
            )

    custom_specs = [
        ("Equipe Louange", [admin, worship_member, member]),
        ("Cellule Jeunesse", [admin, youth_member, prayer_member]),
        ("Intercession Nuit", [admin, prayer_member, member]),
    ]
    for room_name, users in custom_specs:
        custom_room, _ = ChatRoom.objects.get_or_create(
            church=church,
            room_type="CUSTOM",
            name=room_name,
            defaults={"created_by": admin},
        )
        if custom_room.created_by_id != admin.id:
            custom_room.created_by = admin
            custom_room.save(update_fields=["created_by"])
        custom_room.members.set(users)
        if custom_room.messages.count() == 0:
            for idx, sender in enumerate(users, start=1):
                ChatMessage.objects.create(
                    room=custom_room,
                    user=sender,
                    message=f"{room_name}: message test #{idx}",
                )

    donation_specs = [
        ("Dîme", "Dîme mensuelle"),
        ("Offrande", "Offrande de culte"),
        ("Action de grâce", "Remerciement et reconnaissance"),
        ("Projet", "Contribution à un projet spécial"),
        ("Aide sociale", "Soutien social et entraide"),
    ]
    donation_categories = {}
    for name, description in donation_specs:
        category, _ = DonationCategory.objects.get_or_create(
            name=name,
            defaults={"description": description},
        )
        if category.description != description:
            category.description = description
            category.save(update_fields=["description"])
        donation_categories[name] = category

    donation_rows = [
        (admin, "Dîme", 25000, "CASH", "Dîme du mois", True),
        (member, "Offrande", 5000, "OM", "Offrande culte dimanche", False),
        (worship_member, "Projet", 10000, "MOMO", "Projet sonorisation", False),
        (youth_member, "Action de grâce", 7000, "CASH", "Reconnaissance", True),
        (prayer_member, "Aide sociale", 3000, "CASH", "Soutien fraternel", True),
    ]
    for donor, category_name, amount, gateway, message, confirmed in donation_rows:
        donation, created = Donation.objects.get_or_create(
            user=donor,
            church=church,
            category=donation_categories[category_name],
            amount=amount,
            gateway=gateway,
            message=message,
            defaults={
                "confirmed_at": timezone.now() if confirmed else None,
                "metadata": {
                    "payment_status": "SUCCESS" if confirmed else "PENDING",
                    "ready_for_gateway": not confirmed,
                },
            },
        )
        if created:
            Payment.objects.create(
                user=donor,
                church=church,
                donation=donation,
                amount=donation.amount,
                currency=donation.currency,
                gateway=gateway,
                status="SUCCESS" if confirmed else "PENDING",
                metadata={
                    "source": "seed",
                    "category_name": category_name,
                },
            )

    notification_specs = [
        (
            member,
            "Nouvel événement publié",
            "Le programme de la semaine a été publié.",
            {"scope": "events"},
        ),
        (
            worship_member,
            "Don en attente",
            "Votre contribution Mobile Money est prête pour l'intégration passerelle.",
            {"scope": "donations"},
        ),
        (
            prayer_member,
            "Groupe mis à jour",
            "Vous avez été ajouté au groupe Intercession Nuit.",
            {"scope": "chat"},
        ),
    ]
    for user, title, message, meta in notification_specs:
        Notification.objects.get_or_create(
            user=user,
            title=title,
            defaults={
                "eng_title": title,
                "message": message,
                "eng_message": message,
                "type": "SUCCESS",
                "channel": "IN_APP",
                "sent": True,
                "sent_at": timezone.now(),
                "meta": meta,
            },
        )

    # OTP de test pour login mobile rapide (valide selon la config actuelle)
    for phone in (
        admin.phone_number,
        member.phone_number,
        worship_member.phone_number,
        youth_member.phone_number,
        prayer_member.phone_number,
    ):
        otp, _ = OTP.objects.get_or_create(phone=phone)
        otp.otp = "123456"
        otp.last_sent_at = timezone.now()
        otp.save()

    print("Seed terminé.")
    print(f"- Église: {church.title} ({church.id})")
    print(f"- Utilisateur admin: {admin.phone_number} / code OTP 123456")
    print(f"- Utilisateur membre: {member.phone_number} / code OTP 123456")
    print(
        "- Membres additionnels: +237699111222 / +237699111223 / +237699111224 "
        "(code OTP 123456)"
    )
    print("- Contenus: 15 annonces POST + 5 AUDIO + 3 EVENT + 1 COMING_SOON")
    print("- Dons: catégories + dons récents + paiements de démonstration")
    print("- Groupes: commissions Intercession, Louange, Jeunesse")
    print("- Chat: room générale + 3 groupes CUSTOM avec messages de test")
    print("- Notifications: exemples IN_APP créés pour plusieurs membres")
    print("- Playlist: 'Top Louange Test'")


if __name__ == "__main__":
    run()
