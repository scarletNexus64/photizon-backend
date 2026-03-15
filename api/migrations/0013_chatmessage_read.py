from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0012_chatmessage_reply_and_edit"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatMessageRead",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("read_at", models.DateTimeField(auto_now_add=True)),
                ("message", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reads", to="api.chatmessage")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chat_message_reads", to="api.user")),
            ],
            options={
                "unique_together": {("message", "user")},
            },
        ),
        migrations.AddIndex(
            model_name="chatmessageread",
            index=models.Index(fields=["message", "user"], name="api_chatmes_message_40db4f_idx"),
        ),
        migrations.AddIndex(
            model_name="chatmessageread",
            index=models.Index(fields=["user", "read_at"], name="api_chatmes_user_id_739eab_idx"),
        ),
    ]
