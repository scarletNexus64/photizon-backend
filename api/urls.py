from django.urls import path
from api.views.commissions.commissions_view import add_member_to_commission, church_commissions_summary, create_commission, delete_commission, list_church_commission_members, list_church_commissions, list_church_commissions_with_members, list_commissions, remove_member_from_commission, update_commission, update_member_role_in_commission
from api.views.commissions.commissions_view import join_commission
from api.views.contents.contents_view import add_comment, report_content, add_to_playlist, content_stats_for_church, content_stats_global, create_category, create_content, create_playlist, create_tag, delete_category, delete_comment, delete_content, delete_tag, feed_for_church, get_category, get_playlist_with_items,list_all_playlists, list_categories, list_comments, list_content, list_tags, recommend_for_user, reorder_playlist_item, retrieve_content, toggle_like_content, trending_content, update_category, update_content, update_tag, view_content, church_feed, list_coming_soon, subscribe_to_content, unsubscribe_from_content, get_my_subscriptions, get_content_subscribers
from api.views.contents.contents_view import list_ticket_types, create_ticket_type, update_ticket_type, delete_ticket_type
from api.views.programmes.programmes_view import (
    create_programme, retrieve_programme, update_programme, delete_programme,
    list_church_programmes, add_content_to_programme, remove_content_from_programme,
    get_programme_content, programme_stats_for_church, join_programme, leave_programme,
    get_programme_members, get_programme_content_notifications, mark_programme_notification_as_read
)
from .views.auth.auth_views import change_subscription_plan, check_subscription_status, delete_subscription, get_church_subscription, get_subscription_plan, list_subscription_plans, list_subscriptions, renew_subscription, send_otp_view, toggle_subscription_status, update_subscription, verify_otp_view
from .views.crud.crud_views import churches_metrics,create_subchurch_view, deny_user,filter_church_members,get_current_user, get_user_by_id, join_church, leave_church, leave_commission, unban_user,update_church_by_owner,list_owners,list_users,delete_church,update_church,delete_self,update_self,delete_self,list_churches,create_church_view,list_my_churches,verify_church_view,add_church_admin,list_sub_churches,retrieve_church
from .views.crud.receipt_views import ReceiptViewSet, create_receipt, get_receipt, update_receipt, delete_receipt, list_all_receipts
from .views.chat.chat_views import (
    list_create_chat_rooms, room_detail, list_create_messages, message_detail,
    add_member_to_custom_room, remove_member_from_custom_room, mark_room_messages_read,
    create_programme_chat, get_programme_chat, send_programme_message, get_programme_messages
)
from .views.testimonies.testimonies_view import (
    create_testimony, list_church_testimonies, list_user_testimonies, retrieve_testimony,
    update_testimony, delete_testimony, my_testimonies,
    approve_testimony, reject_testimony, list_pending_testimonies,
    increment_testimony_views, testimony_stats_for_church,
    toggle_like_testimony, get_testimony_likes
)
from .views.collaborations.collaborations_view import (
    create_collaboration, list_church_collaborations, list_pending_collaborations,
    approve_collaboration, reject_collaboration, end_collaboration,
    update_collaboration, delete_collaboration, retrieve_collaboration,
    collaboration_stats_for_church
)
from .views.gifts.gifts_view import (
    admin_book_order_stats, book_order_detail,church_financial_overview, church_order_stats, create_book_order, list_categories_d, create_category_d, retrieve_category_d, update_book_order, update_category_d, delete_category_d,
    make_donation, list_user_donations, list_church_donations,
    church_donation_stats, admin_all_churches_donation_stats, user_book_orders, withdraw_all_donations_view, withdraw_all_orders_view, complete_book_order, church_payment_stats, admin_all_churches_payment_stats, admin_payments_summary
)
from .views.notifications.notifications_view import (
    list_notifications, mark_all_notifications_as_read, mark_notification_as_read,
    notification_preferences
)
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

# Router for Receipt ViewSet
router = DefaultRouter()
router.register(r'receipts', ReceiptViewSet, basename='receipt')
urlpatterns = [
    path("auth/send-otp/", send_otp_view),
    path("auth/verify-otp/", verify_otp_view),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("church/create/", create_church_view),
    path("subchurch/create/<str:church_id>/", create_subchurch_view),
    path("church/my/", list_my_churches),
    path("church/<str:church_id>/", retrieve_church),
    path("church/verify/<str:church_id>/", verify_church_view),
    path("church/<str:church_id>/admins/add/", add_church_admin),
    path("church/<str:church_id>/sub_churches/", list_sub_churches),
    path("church/<int:church_code>/join/", join_church, name="join_church"),
    path("church/<str:church_id>/leave/", leave_church, name="leave_church"),
    path(
    "church/<str:church_id>/members/<str:user_id>/deny/",
    deny_user,
    name="deny_member"
    ),
    path(
    "church/<str:church_id>/members/<str:user_id>/undeny/",
    unban_user,
    name="deny_member"
    ),
    path("sadmin/users/", list_users),
    path("sadmin/owners/", list_owners),
    path("sadmin/church/<str:church_id>/update/", update_church),
    path("owner/church/<str:church_id>/update/", update_church_by_owner),
    path("sadmin/church/<str:church_id>/delete/", delete_church),
    path("owner/church/<str:church_id>/delete/", delete_church),
    path("user/me/update/", update_self),
    path("user/me/delete/", delete_self),
    path("sadmin/churches/", list_churches),
    path("sadmin/churches/metrics/", churches_metrics),
    path("user/me/",get_current_user ),
    path("user/<str:user_id>/", get_user_by_id, name="get_user_by_id"),
    path("commissions/", list_commissions, name="list_commissions"),
    path("commissions/create/", create_commission, name="create_commission"),
    path("commissions/<str:commission_id>/update/",update_commission, name="update_commission"),
    path("commissions/<str:commission_id>/delete/",delete_commission, name="delete_commission"),
    path("church/<str:church_id>/commissions/",list_church_commissions, name="list_church_commissions"),
    path("church/<str:church_id>/commissions/summary/",church_commissions_summary, name="church_commissions_summary"),
    path("church/<str:church_id>/commissions/<str:commission_id>/members/",list_church_commission_members, name="list_commission_members"),
    path("church/<str:church_id>/commissions/<str:commission_id>/members/add/",add_member_to_commission, name="add_member_to_commission"),
    path("church/<str:church_id>/commissions/<str:commission_id>/join/", join_commission, name="join_commission"),
    path("church/<str:church_id>/commissions/<str:commission_id>/members/<str:user_id>/remove/",remove_member_from_commission, name="remove_member_from_commission"),
    path(
    "church/<str:church_id>/commissions/<str:commission_id>/members/<str:user_id>/role/",
    update_member_role_in_commission,
    name="update_member_role_in_commission", 
    ),
    path(
    "church/<str:church_id>/commissions/<str:commission_id>/leave/",
    leave_commission,
    name="leave_commission", 
    ),
    path(
    "church/<str:church_id>/commissions-with-members/",
    list_church_commissions_with_members,
    name="list_church_commissions_with_members"
    ),
    path("church/<str:church_id>/members/", filter_church_members),
    path("categories/", list_categories),
    path("categories/create/", create_category),
    path("categories/<str:category_id>/", get_category),
    path("categories/<str:category_id>/update/", update_category),
    path("categories/<str:category_id>/delete/", delete_category),
    path("contents/", list_content),
    path("contents/<str:content_id>/", retrieve_content),
    path("contents/<str:church_id>/add/", create_content,name="create_content"),
    path("contents/<str:content_id>/update/", update_content),
    path("contents/<str:content_id>/delete/", delete_content),
    path("contents/<str:content_id>/toggle_like/", toggle_like_content),
    path("contents/<str:content_id>/view/", view_content),
    path("contents/<str:content_id>/comments/", list_comments),
    path("contents/<str:content_id>/comments/add/", add_comment),
    path("contents/<str:content_id>/report/", report_content),
    path("comments/<str:comment_id>/delete/", delete_comment),
    path("tags/<str:tag_id>/update/", update_tag),
    path("tags/", list_tags),
    path("tags/<str:tag_id>/delete/", delete_tag),
    path("tags/create/", create_tag),
    path("playlists/create/", create_playlist),
    path("playlists/<str:playlist_id>/", get_playlist_with_items),
    path("playlists/<str:playlist_id>/add/", add_to_playlist),
    path("playlist-items/<str:item_id>/reorder/", reorder_playlist_item),
    path("playlist/", list_all_playlists, name="playlist-list"),
    path("trending/<str:church_id>/", trending_content),#plus populaire
    path("contents/<str:content_id>/ticket-types/", list_ticket_types),
    path("contents/<str:content_id>/ticket-types/create/", create_ticket_type),
    path("ticket-types/<str:ticket_type_id>/update/", update_ticket_type),
    path("ticket-types/<str:ticket_type_id>/delete/", delete_ticket_type),
    path("recommend/<str:church_id>/", recommend_for_user),#
    path("church/<str:church_id>/public-feed/", feed_for_church),
    path("church/<str:church_id>/feed/", church_feed, name="church-feed"),
    path("stats/contents/", content_stats_global),
    path("stats/contents/church/<str:church_id>/", content_stats_for_church),
    path("subscription/<str:church_id>/", get_church_subscription),
    path("subscription/<str:church_id>/update/", update_subscription),
    path("subscription/<str:church_id>/delete/", delete_subscription),
    path("subscription/<str:church_id>/status/", check_subscription_status),
    path("subscription/<str:church_id>/change-plan/", change_subscription_plan),
    path("subscription/<str:church_id>/toggle/", toggle_subscription_status),
    path("subscription/<str:church_id>/renew/", renew_subscription),
    path("subscriptions/", list_subscriptions),
    path("subscription-plans/", list_subscription_plans),
    path("subscription-plans/<str:plan_id>/", get_subscription_plan),
    path("donation-categories/list/", list_categories_d),
    path("donation-categories/create/", create_category_d),
    path("donation-categories/<str:category_id>/", retrieve_category_d),
    path("donation-categories/<str:category_id>/update/", update_category_d),
    path("donation-categories/<str:category_id>/delete/", delete_category_d),
    path("church/<str:church_id>/donate/", make_donation),
    path("my-donations/", list_user_donations),
    path("church/<str:church_id>/donations/", list_church_donations),
    path("church/<str:church_id>/donation-stats/", church_donation_stats),
    path("church/<str:church_id>/payment-stats/", church_payment_stats),
    path("church/<str:church_id>/order-stats/", church_order_stats),
    path("admin/donations-stats/", admin_all_churches_donation_stats),
    path("admin/payments-stats/", admin_all_churches_payment_stats),
    path("admin/payments-summary/", admin_payments_summary),
    path("notifications/", list_notifications, name="list-notifications"),
    path(
        "notifications/read-all/",
        mark_all_notifications_as_read,
        name="mark-all-notifications-as-read",
    ),
    path(
        "notifications/<str:notification_id>/read/",
        mark_notification_as_read,
        name="mark-notification-as-read",
    ),
    path(
        "notifications/preferences/",
        notification_preferences,
        name="notification-preferences",
    ),
    path("books/<str:book_id>/order/", create_book_order, name="create-book-order"),
    path("books/orders/", user_book_orders, name="user-book-orders"),
    path("books/orders/<str:order_id>/", book_order_detail, name="book-order-detail"),
    path("books/orders/<str:order_id>/update/", update_book_order, name="update-book-order"),
    path("books/orders/<str:order_id>/complete/", complete_book_order, name="complete-book-order"),
    path("admin/book-orders/stats/", admin_book_order_stats, name="admin-book-order-stats"),
    path("church/<str:church_id>/withdrawed/",church_financial_overview, name="church_gift"),
    path("church/<int:church_id>/withdraw-all-donations/", withdraw_all_donations_view),
    path("church/<int:church_id>/withdraw-all-orders/", withdraw_all_orders_view),
    
    # Receipt endpoints
    path("receipts/all/", list_all_receipts, name="list-all-receipts"),
    path("receipts/create/<str:church_id>/", create_receipt, name="create-receipt"),
    path("receipts/<str:receipt_id>/", get_receipt, name="get-receipt"),
    path("receipts/<str:receipt_id>/update/", update_receipt, name="update-receipt"),
    path("receipts/<str:receipt_id>/delete/", delete_receipt, name="delete-receipt"),
    # Chat endpoints
    path("chat/church/<str:church_id>/rooms/", list_create_chat_rooms, name="list-create-chat-rooms"),
    path("chat/church/<str:church_id>/rooms/create/", list_create_chat_rooms, name="create-chat-room"),
    path("chat/room/<str:room_id>/", room_detail, name="room-detail"),
    path("chat/room/<str:room_id>/messages/", list_create_messages, name="list-create-messages"),
    path("chat/room/<str:room_id>/messages/create/", list_create_messages, name="create-message"),
    path("chat/room/<str:room_id>/messages/<str:message_id>/", message_detail, name="message-detail"),
    path("chat/room/<str:room_id>/messages/read/", mark_room_messages_read, name="mark-room-messages-read"),
    path("chat/room/<str:room_id>/members/add/", add_member_to_custom_room, name="add-member-to-room"),
    path("chat/room/<str:room_id>/members/remove/", remove_member_from_custom_room, name="remove-member-from-room"),
    
    # Testimony endpoints
    path("church/<str:church_id>/testimonies/", list_church_testimonies, name="list-church-testimonies"),
    path("church/<str:church_id>/testimonies/pending/", list_pending_testimonies, name="list-pending-testimonies"),
    path("church/<str:church_id>/testimonies/stats/", testimony_stats_for_church, name="testimony-stats"),
    path("church/<str:church_id>/testimonies/create/", create_testimony, name="create-testimony"),
    path("church/<str:church_id>/testimonies/<str:testimony_id>/", retrieve_testimony, name="retrieve-testimony"),
    path("church/<str:church_id>/testimonies/<str:testimony_id>/update/", update_testimony, name="update-testimony"),
    path("church/<str:church_id>/testimonies/<str:testimony_id>/delete/", delete_testimony, name="delete-testimony"),
    path("church/<str:church_id>/testimonies/<str:testimony_id>/approve/", approve_testimony, name="approve-testimony"),
    path("church/<str:church_id>/testimonies/<str:testimony_id>/reject/", reject_testimony, name="reject-testimony"),
    path("church/<str:church_id>/testimonies/<str:testimony_id>/view/", increment_testimony_views, name="increment-testimony-views"),
    path("church/<str:church_id>/testimonies/<str:testimony_id>/toggle-like/", toggle_like_testimony, name="toggle-like-testimony"),
    path("church/<str:church_id>/testimonies/<str:testimony_id>/likes/", get_testimony_likes, name="get-testimony-likes"),
    path("user/me/testimonies/", my_testimonies, name="my-testimonies"),
    path("user/<str:user_id>/testimonies/", list_user_testimonies, name="list-user-testimonies"),
    
    # Church Collaboration endpoints
    path("church/<str:church_id>/collaborations/", list_church_collaborations, name="list-church-collaborations"),
    path("church/<str:church_id>/collaborations/pending/", list_pending_collaborations, name="list-pending-collaborations"),
    path("church/<str:church_id>/collaborations/stats/", collaboration_stats_for_church, name="collaboration-stats"),
    path("church/<str:church_id>/collaborations/create/", create_collaboration, name="create-collaboration"),
    path("church/<str:church_id>/collaborations/<str:collaboration_id>/", retrieve_collaboration, name="retrieve-collaboration"),
    path("church/<str:church_id>/collaborations/<str:collaboration_id>/update/", update_collaboration, name="update-collaboration"),
    path("church/<str:church_id>/collaborations/<str:collaboration_id>/delete/", delete_collaboration, name="delete-collaboration"),
    path("church/<str:church_id>/collaborations/<str:collaboration_id>/approve/", approve_collaboration, name="approve-collaboration"),
    path("church/<str:church_id>/collaborations/<str:collaboration_id>/reject/", reject_collaboration, name="reject-collaboration"),
    path("church/<str:church_id>/collaborations/<str:collaboration_id>/end/", end_collaboration, name="end-collaboration"),
    # Programme endpoints
    path("church/<str:church_id>/programmes/", list_church_programmes, name="list-church-programmes"),
    path("church/<str:church_id>/programmes/stats/", programme_stats_for_church, name="programme-stats"),
    path("church/<str:church_id>/programmes/create/", create_programme, name="create-programme"),
    path("church/<str:church_id>/programmes/<str:programme_id>/", retrieve_programme, name="retrieve-programme"),
    path("church/<str:church_id>/programmes/<str:programme_id>/update/", update_programme, name="update-programme"),
    path("church/<str:church_id>/programmes/<str:programme_id>/delete/", delete_programme, name="delete-programme"),
    path("church/<str:church_id>/programmes/<str:programme_id>/content/", get_programme_content, name="get-programme-content"),
    path("church/<str:church_id>/programmes/<str:programme_id>/content/add/", add_content_to_programme, name="add-content-to-programme"),
    path("church/<str:church_id>/programmes/<str:programme_id>/content/remove/", remove_content_from_programme, name="remove-content-from-programme"),
    path("church/<str:church_id>/programmes/<str:programme_id>/join/", join_programme, name="join-programme"),
    path("church/<str:church_id>/programmes/<str:programme_id>/leave/", leave_programme, name="leave-programme"),
    path("church/<str:church_id>/programmes/<str:programme_id>/members/", get_programme_members, name="get-programme-members"),
    path("church/<str:church_id>/programmes/<str:programme_id>/notifications/", get_programme_content_notifications, name="get-programme-content-notifications"),
    path("church/<str:church_id>/programmes/<str:programme_id>/notifications/<str:notification_id>/read/", mark_programme_notification_as_read, name="mark-programme-notification-as-read"),
    
    # Programme Chat endpoints
    path("church/<str:church_id>/programmes/<str:programme_id>/chat/create/", create_programme_chat, name="create-programme-chat"),
    path("church/<str:church_id>/programmes/<str:programme_id>/chat/", get_programme_chat, name="get-programme-chat"),
    path("church/<str:church_id>/programmes/<str:programme_id>/chat/messages/", get_programme_messages, name="get-programme-messages"),
    path("church/<str:church_id>/programmes/<str:programme_id>/chat/messages/send/", send_programme_message, name="send-programme-message"),
    
    # Content Coming Soon endpoints
    path("church/<str:church_id>/coming-soon/", list_coming_soon, name="list-coming-soon"),
    path("contents/<str:content_id>/coming-soon/subscribe/", subscribe_to_content, name="subscribe-to-content"),
    path("contents/<str:content_id>/coming-soon/unsubscribe/", unsubscribe_from_content, name="unsubscribe-from-content"),
    path("contents/<str:content_id>/coming-soon/subscribers/", get_content_subscribers, name="get-content-subscribers"),
    path("user/me/coming-soon-subscriptions/", get_my_subscriptions, name="get-my-subscriptions"),
]

urlpatterns += router.urls
