from django.db import migrations


FORWARD_SQL = """
ALTER TABLE "subject_representatives"
    DROP CONSTRAINT
    "subject_representati_data_subject_id_f148cb71_fk_data_subj";

ALTER TABLE "subject_representatives"
    ADD CONSTRAINT "fk_representatives_subject"
    FOREIGN KEY ("data_subject_id")
    REFERENCES "data_subjects" ("id")
    ON DELETE CASCADE;


ALTER TABLE "subject_representatives"
    DROP CONSTRAINT
    "subject_representatives_verified_by_id_789df5dd_fk_users_id";

ALTER TABLE "subject_representatives"
    ADD CONSTRAINT "fk_representatives_verified_by"
    FOREIGN KEY ("verified_by_id")
    REFERENCES "users" ("id")
    ON DELETE SET NULL;
"""


REVERSE_SQL = """
ALTER TABLE "subject_representatives"
    DROP CONSTRAINT "fk_representatives_subject";

ALTER TABLE "subject_representatives"
    ADD CONSTRAINT
    "subject_representati_data_subject_id_f148cb71_fk_data_subj"
    FOREIGN KEY ("data_subject_id")
    REFERENCES "data_subjects" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "subject_representatives"
    DROP CONSTRAINT "fk_representatives_verified_by";

ALTER TABLE "subject_representatives"
    ADD CONSTRAINT
    "subject_representatives_verified_by_id_789df5dd_fk_users_id"
    FOREIGN KEY ("verified_by_id")
    REFERENCES "users" ("id")
    DEFERRABLE INITIALLY DEFERRED;
"""


class Migration(migrations.Migration):

    dependencies = [
        (
            "subjects",
            "0001_initial",
        ),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]