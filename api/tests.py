from types import SimpleNamespace
from datetime import date
from unittest.mock import Mock, patch

from django.core import mail
from django.test import TestCase
from django.test.utils import override_settings
from rest_framework.test import APITestCase

from api.models import (
    Category,
    ChatRoom,
    Church,
    ChurchAdmin,
    Commission,
    Content,
    Notification,
    OTP,
    Playlist,
    Programme,
    ProgrammeMember,
    User,
)
from api.permissions import IsChurchAdmin, IsChurchOwnerOrAdmin


class PermissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number="+237690000001", name="User")
        self.owner = User.objects.create_user(phone_number="+237690000002", name="Owner")
        self.church = Church.objects.create(title="Eglise Test")
        self.other_church = Church.objects.create(title="Autre Eglise")
        ChurchAdmin.objects.create(church=self.church, user=self.owner, role="OWNER")

    def _build_request(self, user):
        return SimpleNamespace(user=user)

    def _build_view(self, church_id=None):
        kwargs = {}
        if church_id is not None:
            kwargs["church_id"] = str(church_id)
        return SimpleNamespace(kwargs=kwargs)

    def test_is_church_admin_rejects_plain_authenticated_user(self):
        permission = IsChurchAdmin()

        allowed = permission.has_permission(
            self._build_request(self.user),
            self._build_view(self.church.id),
        )

        self.assertFalse(allowed)

    def test_is_church_admin_accepts_owner_for_matching_church(self):
        permission = IsChurchAdmin()

        allowed = permission.has_permission(
            self._build_request(self.owner),
            self._build_view(self.church.id),
        )

        self.assertTrue(allowed)

    def test_is_church_owner_or_admin_rejects_non_admin_user(self):
        permission = IsChurchOwnerOrAdmin()

        allowed = permission.has_permission(
            self._build_request(self.user),
            self._build_view(self.church.id),
        )

        self.assertFalse(allowed)

    def test_is_church_owner_or_admin_rejects_admin_for_other_church(self):
        permission = IsChurchOwnerOrAdmin()

        allowed = permission.has_permission(
            self._build_request(self.owner),
            self._build_view(self.other_church.id),
        )

        self.assertFalse(allowed)

    def test_programme_room_allows_programme_member(self):
        programme = Programme.objects.create(
            church=self.church,
            created_by=self.owner,
            title="Programme Test",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
        )
        ProgrammeMember.objects.create(programme=programme, user=self.user)
        room = ChatRoom.objects.create(
            church=self.church,
            room_type="PROGRAMME",
            name="Chat programme",
            programme=programme,
            created_by=self.owner,
        )

        self.assertTrue(room.user_has_access(self.user))

    def test_programme_room_allows_admin_even_without_membership(self):
        admin = User.objects.create_user(phone_number="+237690000003", name="Admin")
        ChurchAdmin.objects.create(church=self.church, user=admin, role="ADMIN")
        programme = Programme.objects.create(
            church=self.church,
            created_by=self.owner,
            title="Programme Admin",
            start_date=date(2026, 1, 3),
            end_date=date(2026, 1, 4),
        )
        room = ChatRoom.objects.create(
            church=self.church,
            room_type="PROGRAMME",
            name="Chat admin",
            programme=programme,
            created_by=self.owner,
        )

        self.assertTrue(room.user_has_access(admin))


class NotificationApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number="+237690000010", name="Notif")
        self.client.force_authenticate(self.user)
        self.notification = Notification.objects.create(
            user=self.user,
            title="Bienvenue",
            message="Hello",
            type="INFO",
        )

    def test_list_notifications_returns_current_user_notifications(self):
        response = self.client.get("/api/notifications/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.notification.id))

    def test_mark_notification_as_read_updates_state(self):
        response = self.client.post(f"/api/notifications/{self.notification.id}/read/")

        self.assertEqual(response.status_code, 200)
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="no-reply@test.local",
)
class AuthOtpApiTests(APITestCase):
    @override_settings(
        WHATSAPP_ENABLED=True,
        WHATSAPP_PHONE_NUMBER_ID="123456",
        WHATSAPP_API_TOKEN="token-test",
        WHATSAPP_OTP_TEMPLATE_NAME="otp_test_template",
    )
    @patch("api.services.whatsapp.requests.post")
    def test_send_otp_sends_whatsapp_and_email(self, mock_post):
        mock_post.return_value = Mock(status_code=200, text="ok")

        response = self.client.post(
            "/api/auth/send-otp/",
            {
                "phone": "+237690000060",
                "email": "user@test.local",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data["channels"]), {"whatsapp", "email"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["user@test.local"])

        otp = OTP.objects.get(phone="+237690000060")
        self.assertIn(otp.otp, mail.outbox[0].body)

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["type"], "template")
        self.assertEqual(
            payload["template"]["components"][0]["parameters"][0]["text"],
            otp.otp,
        )

    @override_settings(
        WHATSAPP_ENABLED=True,
        WHATSAPP_PHONE_NUMBER_ID="123456",
        WHATSAPP_API_TOKEN="token-test",
        WHATSAPP_OTP_TEMPLATE_NAME="otp_test_template",
    )
    @patch("api.services.whatsapp.requests.post")
    def test_send_otp_returns_success_when_email_works_but_whatsapp_fails(self, mock_post):
        mock_post.return_value = Mock(status_code=500, text="boom")

        response = self.client.post(
            "/api/auth/send-otp/",
            {
                "phone": "+237690000061",
                "email": "fallback@test.local",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["channels"], ["email"])
        self.assertIn("whatsapp", response.data["failed_channels"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["fallback@test.local"])

    def test_verify_otp_updates_user_email_when_code_is_valid(self):
        OTP.objects.create(phone="+237690000062", otp="123456")

        response = self.client.post(
            "/api/auth/verify-otp/",
            {
                "phone": "+237690000062",
                "code": "123456",
                "email": "verified@test.local",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(phone_number="+237690000062")
        self.assertEqual(user.email, "verified@test.local")
        self.assertTrue(response.data["success"])


class ContentApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+237690000020",
            name="Member Story",
        )
        self.church = Church.objects.create(
            title="Eglise Stories",
            is_verified=True,
        )
        self.user.current_church = self.church
        self.user.save(update_fields=["current_church"])
        self.client.force_authenticate(self.user)

    def test_member_can_create_story_for_current_church(self):
        response = self.client.post(
            f"/api/contents/{self.church.id}/add/",
            {
                "title": "Ma story",
                "description": "Story de test",
                "type": "STORY",
                "delivery_type": "DIGITAL",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["type"], "STORY")
        self.assertEqual(str(response.data["created_by"]["id"]), str(self.user.id))

    def test_toggle_like_returns_exact_count(self):
        content = Content.objects.create(
            church=self.church,
            created_by=self.user,
            title="Annonce",
            slug="annonce",
            type="POST",
            delivery_type="DIGITAL",
        )

        first_response = self.client.post(
            f"/api/contents/{content.id}/toggle_like/",
        )
        second_response = self.client.post(
            f"/api/contents/{content.id}/toggle_like/",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertTrue(first_response.data["liked"])
        self.assertEqual(first_response.data["likes_count"], 1)

        self.assertEqual(second_response.status_code, 200)
        self.assertFalse(second_response.data["liked"])
        self.assertEqual(second_response.data["likes_count"], 0)

    def test_creator_can_delete_own_content(self):
        content = Content.objects.create(
            church=self.church,
            created_by=self.user,
            title="Publication à supprimer",
            slug="publication-a-supprimer",
            type="POST",
            delivery_type="DIGITAL",
        )

        response = self.client.delete(f"/api/contents/{content.id}/delete/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Content.objects.filter(id=content.id).exists())


class ChurchApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+237690000030",
            name="Member Church",
        )
        self.church = Church.objects.create(
            title="Eglise Active",
            is_verified=True,
            is_public=False,
        )
        self.user.current_church = self.church
        self.user.save(update_fields=["current_church"])
        self.client.force_authenticate(self.user)

    def test_member_can_retrieve_current_church_detail(self):
        response = self.client.get(f"/api/church/{self.church.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(response.data["id"]), str(self.church.id))

    def test_member_cannot_self_promote_via_profile_update(self):
        response = self.client.patch(
            "/api/user/me/update/",
            {"role": "SADMIN", "is_staff": True, "is_superuser": True},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, "USER")
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)


class ChurchOwnerUpdateApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            phone_number="+237690000031",
            name="Church Owner",
        )
        self.other_user = User.objects.create_user(
            phone_number="+237690000032",
            name="Other User",
        )
        self.church = Church.objects.create(
            title="Eglise Owner Update",
            is_verified=True,
        )
        ChurchAdmin.objects.create(church=self.church, user=self.owner, role="OWNER")
        self.client.force_authenticate(self.owner)

    def test_owner_cannot_update_protected_church_fields(self):
        response = self.client.patch(
            f"/api/owner/church/{self.church.id}/update/",
            {
                "is_active_subscription": False,
                "owner": str(self.other_user.id),
                "members_count": 999,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.church.refresh_from_db()
        self.assertTrue(self.church.is_active_subscription)
        self.assertNotEqual(self.church.owner_id, self.other_user.id)
        self.assertEqual(self.church.members_count, 0)


class CategoryApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+237690000033",
            name="Simple User",
        )
        self.sadmin = User.objects.create_user(
            phone_number="+237690000034",
            name="Sadmin Category",
            role="SADMIN",
        )

    def test_anonymous_user_cannot_create_category(self):
        response = self.client.post(
            "/api/categories/create/",
            {"name": "Unauthorized"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_non_sadmin_cannot_delete_category(self):
        category = Category.objects.create(name="Protected", slug="protected")
        self.client.force_authenticate(self.user)

        response = self.client.delete(f"/api/categories/{category.id}/delete/")

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Category.objects.filter(id=category.id).exists())

    def test_sadmin_can_create_category(self):
        self.client.force_authenticate(self.sadmin)

        response = self.client.post(
            "/api/categories/create/",
            {"name": "Authorized"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "Authorized")


class PlaylistApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            phone_number="+237690000035",
            name="Playlist Owner",
        )
        self.member = User.objects.create_user(
            phone_number="+237690000036",
            name="Playlist Member",
        )
        self.foreign_author = User.objects.create_user(
            phone_number="+237690000037",
            name="Foreign Author",
        )
        self.church = Church.objects.create(
            title="Eglise Playlist",
            is_verified=True,
        )
        self.other_church = Church.objects.create(
            title="Autre Eglise Playlist",
            is_verified=True,
        )
        ChurchAdmin.objects.create(church=self.church, user=self.owner, role="OWNER")
        self.member.current_church = self.church
        self.member.save(update_fields=["current_church"])
        self.content = Content.objects.create(
            church=self.church,
            created_by=self.owner,
            title="Audio interne",
            slug="audio-interne",
            type="AUDIO",
            delivery_type="DIGITAL",
            audio_url="https://example.com/audio.mp3",
        )
        self.foreign_content = Content.objects.create(
            church=self.other_church,
            created_by=self.foreign_author,
            title="Audio externe",
            slug="audio-externe",
            type="AUDIO",
            delivery_type="DIGITAL",
            audio_url="https://example.com/foreign.mp3",
        )

    def test_member_cannot_create_playlist_for_church(self):
        self.client.force_authenticate(self.member)

        response = self.client.post(
            "/api/playlists/create/",
            {"church_id": str(self.church.id), "title": "Playlist membre"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_owner_cannot_add_foreign_content_to_playlist(self):
        playlist = Playlist.objects.create(church=self.church, title="Playlist owner")
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            f"/api/playlists/{playlist.id}/add/",
            {"content_id": str(self.foreign_content.id)},
            format="json",
        )

        self.assertEqual(response.status_code, 400)


class CommissionApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+237690000040",
            name="Commission Member",
        )
        self.church = Church.objects.create(
            title="Eglise Commission",
            is_verified=True,
        )
        self.user.current_church = self.church
        self.user.save(update_fields=["current_church"])
        self.commission = Commission.objects.create(name="Chorale")
        self.client.force_authenticate(self.user)

    def test_member_can_join_commission(self):
        response = self.client.post(
            f"/api/church/{self.church.id}/commissions/{self.commission.id}/join/",
        )

        self.assertIn(response.status_code, (200, 201))
        self.assertEqual(response.data["commission"]["name"], "Chorale")
        self.assertEqual(str(response.data["user"]["id"]), str(self.user.id))


class MetricsApiTests(APITestCase):
    def setUp(self):
        self.sadmin = User.objects.create_user(
            phone_number="+237690000050",
            name="Sadmin",
            role="SADMIN",
        )
        self.client.force_authenticate(self.sadmin)

    def test_sadmin_can_access_church_metrics(self):
        response = self.client.get("/api/sadmin/churches/metrics/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("stats", response.data)
