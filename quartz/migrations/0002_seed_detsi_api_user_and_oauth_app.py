from django.conf import settings
from django.db import migrations

USERNAME = "dynamics_user"
APPLICATION_NAME = "Dynamics API OAuth Application"


class Migration(migrations.Migration):

    dependencies = [
        ("quartz", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("oauth2_provider", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    def forwards(apps, schema_editor):
        db_alias = schema_editor.connection.alias

        Application = apps.get_model("oauth2_provider", "Application")

        user_app_label, user_model_name = settings.AUTH_USER_MODEL.split(".")
        UserModel = apps.get_model(user_app_label, user_model_name)

        user, created = UserModel.objects.using(db_alias).get_or_create(
            username=USERNAME,
            defaults={"is_active": True},
        )
        if created:
            user.save(using=db_alias, update_fields=["password"])

        Application.objects.using(db_alias).get_or_create(
            name=APPLICATION_NAME,
            user=user,
            defaults={
                "client_type": "confidential",
                "authorization_grant_type": "client-credentials",
                "hash_client_secret": False,
            },
        )

    def backwards(apps, schema_editor):
        db_alias = schema_editor.connection.alias

        Application = apps.get_model("oauth2_provider", "Application")

        user_app_label, user_model_name = settings.AUTH_USER_MODEL.split(".")
        UserModel = apps.get_model(user_app_label, user_model_name)

        try:
            user = UserModel.objects.using(db_alias).get(username=USERNAME)
        except UserModel.DoesNotExist:
            user = None

        if user is not None:
            Application.objects.using(db_alias).filter(
                name=APPLICATION_NAME,
                user=user,
            ).delete()
            user.delete()

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
