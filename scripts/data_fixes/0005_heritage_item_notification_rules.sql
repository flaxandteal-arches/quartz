-- Heritage Item notification rules for Heritage Hub (use case 1): new application
-- received, and new draft version created. Mirrors quartz-graphs
-- "01_structure - 09_heritage_item_functions.csv", which covers fresh builds.
-- Notification types are upserted here because only the graph designer's save
-- (NotifyFunction.after_function_save) creates them otherwise.

\set ON_ERROR_STOP on

BEGIN;

UPDATE functions_x_graphs
SET config = $config${
  "nodegroups": [
    {
      "users_to_notify": [],
      "groups_to_notify": [
        "Heritage Officer"
      ],
      "email": true,
      "email_recipients": "extra_only",
      "email_addresses": [
        "set-per-environment@example.invalid"
      ],
      "emailtemplate": "email/arches_notifications/notification.htm",
      "button_text": "Open record",
      "link_path": "",
      "node_alias": null,
      "saved_by": "system",
      "resource_name": {
        "require_prefix": null,
        "strip_prefix": null,
        "strip_suffix": null
      },
      "notiftype_id": "17ae3efe-5e32-45fa-b4cd-6baaa873b70d",
      "notification_name": "Heritage Hub: new application received",
      "nodegroup_alias": "system_reference_numbers",
      "fire_on": "created",
      "message": "A new application has been received from Heritage Hub: {name} (Heritage ID {value:primary_reference_number}). Please review it and commence assessment in the Asset Register."
    },
    {
      "users_to_notify": [],
      "groups_to_notify": [
        "Heritage Officer"
      ],
      "email": true,
      "email_recipients": "extra_only",
      "email_addresses": [
        "set-per-environment@example.invalid"
      ],
      "emailtemplate": "email/arches_notifications/notification.htm",
      "button_text": "Open record",
      "link_path": "",
      "node_alias": null,
      "saved_by": "anyone",
      "resource_name": {
        "require_prefix": null,
        "strip_prefix": null,
        "strip_suffix": null
      },
      "notiftype_id": "c3a4f1d2-6b7e-4f80-9a1c-2d3e4f5a6b70",
      "notification_name": "New draft version created",
      "nodegroup_alias": "versioning",
      "fire_on": "copied",
      "message": "A new draft version for {name} has been created."
    }
  ],
  "triggering_nodegroups": []
}$config$::jsonb
WHERE graphid = '076f9381-7b00-11e9-8d6b-80000b44d1d9'
  AND functionid = 'f5a0e2b0-1c3e-4a8f-9d2c-1a2b3c4d5e6f';

INSERT INTO notification_types (typeid, name, emailtemplate, emailnotify, webnotify)
VALUES
  ('17ae3efe-5e32-45fa-b4cd-6baaa873b70d', 'Heritage Hub: new application received',
   'email/arches_notifications/notification.htm', true, true),
  ('c3a4f1d2-6b7e-4f80-9a1c-2d3e4f5a6b70', 'New draft version created',
   'email/arches_notifications/notification.htm', true, true)
ON CONFLICT (typeid) DO UPDATE
SET name = EXCLUDED.name,
    emailtemplate = EXCLUDED.emailtemplate,
    emailnotify = EXCLUDED.emailnotify,
    webnotify = EXCLUDED.webnotify;

COMMIT;
