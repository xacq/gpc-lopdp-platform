from django.db import migrations


FORWARD_SQL = """
ALTER TABLE "legal_documents"
    DROP CONSTRAINT
    "legal_documents_created_by_id_4d93a174_fk_users_id";

ALTER TABLE "legal_documents"
    ADD CONSTRAINT "fk_legal_documents_created_by"
    FOREIGN KEY ("created_by_id")
    REFERENCES "users" ("id")
    ON DELETE SET NULL;


ALTER TABLE "right_rules"
    DROP CONSTRAINT
    "right_rules_right_id_8fec5f33_fk_rights_catalog_id";

ALTER TABLE "right_rules"
    ADD CONSTRAINT "fk_right_rules_right"
    FOREIGN KEY ("right_id")
    REFERENCES "rights_catalog" ("id")
    ON DELETE RESTRICT;
"""


REVERSE_SQL = """
ALTER TABLE "legal_documents"
    DROP CONSTRAINT "fk_legal_documents_created_by";

ALTER TABLE "legal_documents"
    ADD CONSTRAINT
    "legal_documents_created_by_id_4d93a174_fk_users_id"
    FOREIGN KEY ("created_by_id")
    REFERENCES "users" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "right_rules"
    DROP CONSTRAINT "fk_right_rules_right";

ALTER TABLE "right_rules"
    ADD CONSTRAINT
    "right_rules_right_id_8fec5f33_fk_rights_catalog_id"
    FOREIGN KEY ("right_id")
    REFERENCES "rights_catalog" ("id")
    DEFERRABLE INITIALLY DEFERRED;
"""


class Migration(migrations.Migration):

    dependencies = [
        (
            "legal_content",
            "0001_initial",
        ),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]