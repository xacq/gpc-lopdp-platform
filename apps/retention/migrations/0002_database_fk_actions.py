from django.db import migrations


FORWARD_SQL = """
-- ============================================================
-- DATA DISPOSAL EVENTS
-- ============================================================

ALTER TABLE "data_disposal_events"
    DROP CONSTRAINT
    "data_disposal_events_approved_by_id_e7b6cbae_fk_users_id";

ALTER TABLE "data_disposal_events"
    ADD CONSTRAINT "fk_disposal_approved_by"
    FOREIGN KEY ("approved_by_id")
    REFERENCES "users" ("id")
    ON DELETE SET NULL;


ALTER TABLE "data_disposal_events"
    DROP CONSTRAINT
    "data_disposal_events_executed_by_id_14c2d090_fk_users_id";

ALTER TABLE "data_disposal_events"
    ADD CONSTRAINT "fk_disposal_executed_by"
    FOREIGN KEY ("executed_by_id")
    REFERENCES "users" ("id")
    ON DELETE SET NULL;


ALTER TABLE "data_disposal_events"
    DROP CONSTRAINT
    "data_disposal_events_retention_rule_id_001b1aea_fk_retention";

ALTER TABLE "data_disposal_events"
    ADD CONSTRAINT "fk_disposal_retention_rule"
    FOREIGN KEY ("retention_rule_id")
    REFERENCES "retention_rules" ("id")
    ON DELETE SET NULL;
"""


REVERSE_SQL = """
ALTER TABLE "data_disposal_events"
    DROP CONSTRAINT "fk_disposal_retention_rule";

ALTER TABLE "data_disposal_events"
    ADD CONSTRAINT
    "data_disposal_events_retention_rule_id_001b1aea_fk_retention"
    FOREIGN KEY ("retention_rule_id")
    REFERENCES "retention_rules" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "data_disposal_events"
    DROP CONSTRAINT "fk_disposal_executed_by";

ALTER TABLE "data_disposal_events"
    ADD CONSTRAINT
    "data_disposal_events_executed_by_id_14c2d090_fk_users_id"
    FOREIGN KEY ("executed_by_id")
    REFERENCES "users" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "data_disposal_events"
    DROP CONSTRAINT "fk_disposal_approved_by";

ALTER TABLE "data_disposal_events"
    ADD CONSTRAINT
    "data_disposal_events_approved_by_id_e7b6cbae_fk_users_id"
    FOREIGN KEY ("approved_by_id")
    REFERENCES "users" ("id")
    DEFERRABLE INITIALLY DEFERRED;
"""


class Migration(migrations.Migration):

    dependencies = [
        (
            "retention",
            "0001_initial",
        ),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]