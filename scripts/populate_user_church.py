import os
import sys
import django
import random
from datetime import timedelta
from django.utils import timezone

sys.path.append('/home/rochinel/churchlumen/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'christlumen.settings')
django.setup()

from api.models import User, Church, Content, Category, Tag

def run():
    u = User.objects.filter(phone_number='+237600000000').first()
    if not u or not u.current_church:
        print("User or current church not found.")
        return
    
    church = u.current_church
    print(f"Populating data for church: {church.title} ({church.id})")
    
    # Ensure categories exist
    music_cat, _ = Category.objects.get_or_create(name="Musique", slug="music")
    vid_cat, _ = Category.objects.get_or_create(name="Prédications", slug="predication")
    event_cat, _ = Category.objects.get_or_create(name="Événements", slug="evenements")
    
    # Add dummy contents (Audio)
    for i in range(3):
        Content.objects.create(
            church=church,
            title=f"Chant de Louange - {i+1}",
            description="Un moment puissant d'adoration.",
            type="AUDIO",
            audio_url="https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
            cover_image_url="https://images.unsplash.com/photo-1501281668745-f7f57925c3b4",
            category=music_cat,
            published=True
        )
        
    # Add dummy contents (Videos)
    for i in range(2):
        Content.objects.create(
            church=church,
            title=f"Culte du Dimanche - {i+1}",
            description="Rejoignez-nous pour la parole.",
            type="VIDEO",
            video_url="https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4",
            cover_image_url="https://images.unsplash.com/photo-1438232992991-995b7058bbb3",
            category=vid_cat,
            published=True
        )

    # Add dummy contents (Events)
    for i in range(2):
        Content.objects.create(
            church=church,
            title=f"Soirée de prière - {i+1}",
            description="Rejoignez-nous pour la parole.",
            type="EVENT",
            cover_image_url="https://images.unsplash.com/photo-1511895426328-dc8714191300",
            category=event_cat,
            start_at=timezone.now() + timedelta(days=2+i),
            end_at=timezone.now() + timedelta(days=2+i, hours=2),
            location="Chapelle Principale",
            published=True
        )

    print("Content successfully populated!")

run()
