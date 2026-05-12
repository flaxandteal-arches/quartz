from django.db import models

from arches.app.models.models import ResourceInstance


class HeritageItemState(models.Model):
    DRAFT = "draft"
    FINAL = "final"
    ARCHIVED = "archived"
    STATE_CHOICES = {
        DRAFT: "draft",
        FINAL: "final",
        ARCHIVED: "archived",
    }
    id = models.AutoField(primary_key=True)
    heritageitem_id = models.UUIDField(blank=True, null=True)
    heritage_id_number = models.CharField(max_length=255)
    resourceinstanceid = models.ForeignKey(
        ResourceInstance,
        on_delete=models.CASCADE,
    )
    state = models.CharField(choices=STATE_CHOICES, default=DRAFT, max_length=50)
    version = models.CharField(max_length=255, blank=True, null=True)
    payload = models.JSONField(blank=True, null=True)
    archived_resourceinstance = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    editable = models.BooleanField(default=False)

    class Meta:
        managed = True
        db_table = "heritage_item_state"
