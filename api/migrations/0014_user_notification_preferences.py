from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0013_chatmessage_read"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="notification_preferences",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
