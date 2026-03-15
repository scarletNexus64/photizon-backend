import os
import sys
import django
from django.utils import timezone

sys.path.append('/home/rochinel/churchlumen/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'christlumen.settings')
django.setup()

from api.models import User, Church, ChatRoom, ChatMessage

def run():
    print("Populating chat for existing churches...")
    churches = Church.objects.all()
    
    if not churches:
        print("No churches found.")
        return

    users = list(User.objects.all()[:2])
    if not users:
        print("No users found to construct messages.")
        return

    admin_user = users[0]
    member_user = users[1] if len(users) > 1 else admin_user

    for church in churches:
        print(f"Checking chat and content for church {church.title}")
        
        # General chat
        room, created = ChatRoom.objects.get_or_create(
            church=church,
            room_type="CHURCH",
            name=f"Discussion Générale",
            defaults={"created_by": admin_user},
        )
        
        if room.messages.count() < 2:
            print("Adding chat messages...")
            for idx in range(1, 5):
                sender = admin_user if idx % 2 == 0 else member_user
                ChatMessage.objects.create(
                    room=room,
                    user=sender,
                    message=f"Bonjour ! Ceci est le message auto #{idx} dans la salle de prière et discussion de l'église.",
                )
        else:
            print("Chat already populated.")

    print("Chat data successfully ensured!")

if __name__ == "__main__":
    run()
