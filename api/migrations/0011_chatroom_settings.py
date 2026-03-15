from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0010_alter_serviceconfiguration_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatroom",
            name="avatar_url",
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name="chatroom",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="chatroom",
            name="only_admins_can_send",
            field=models.BooleanField(default=False),
        ),
    ]
