from django.db import migrations


FORWARD_SQL = """
-- ============================================================
-- REQUEST ATTACHMENTS
-- ============================================================

ALTER TABLE "request_attachments"
    DROP CONSTRAINT
    "request_attachments_representative_id_2d4c4e8f_fk_subject_r";

ALTER TABLE "request_attachments"
    ADD CONSTRAINT "fk_attachments_representative"
    FOREIGN KEY ("representative_id")
    REFERENCES "subject_representatives" ("id")
    ON DELETE SET NULL;


ALTER TABLE "request_attachments"
    DROP CONSTRAINT
    "request_attachments_request_id_8ccb01fd_fk_rights_requests_id";

ALTER TABLE "request_attachments"
    ADD CONSTRAINT "fk_attachments_request"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    ON DELETE CASCADE;


ALTER TABLE "request_attachments"
    DROP CONSTRAINT
    "request_attachments_uploaded_by_id_4e9a50eb_fk_users_id";

ALTER TABLE "request_attachments"
    ADD CONSTRAINT "fk_attachments_uploaded_by"
    FOREIGN KEY ("uploaded_by_id")
    REFERENCES "users" ("id")
    ON DELETE SET NULL;


-- ============================================================
-- TEMPORARY UPLOADS
-- ============================================================

ALTER TABLE "temporary_uploads"
    DROP CONSTRAINT
    "temporary_uploads_promoted_attachment__4a61d341_fk_request_a";

ALTER TABLE "temporary_uploads"
    ADD CONSTRAINT "fk_tmp_promoted_attachment"
    FOREIGN KEY ("promoted_attachment_id")
    REFERENCES "request_attachments" ("id")
    ON DELETE SET NULL;


ALTER TABLE "temporary_uploads"
    DROP CONSTRAINT
    "temporary_uploads_promoted_request_id_1cc2d68a_fk_rights_re";

ALTER TABLE "temporary_uploads"
    ADD CONSTRAINT "fk_tmp_promoted_request"
    FOREIGN KEY ("promoted_request_id")
    REFERENCES "rights_requests" ("id")
    ON DELETE SET NULL;


-- ============================================================
-- IDENTITY VERIFICATIONS
-- ============================================================

ALTER TABLE "identity_verifications"
    DROP CONSTRAINT
    "identity_verificatio_request_id_f00e341d_fk_rights_re";

ALTER TABLE "identity_verifications"
    ADD CONSTRAINT "fk_idv_request"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    ON DELETE CASCADE;


ALTER TABLE "identity_verifications"
    DROP CONSTRAINT
    "identity_verifications_verified_by_id_566ffd46_fk_users_id";

ALTER TABLE "identity_verifications"
    ADD CONSTRAINT "fk_idv_verified_by"
    FOREIGN KEY ("verified_by_id")
    REFERENCES "users" ("id")
    ON DELETE SET NULL;


-- ============================================================
-- NOTICE DELIVERIES
-- ============================================================

ALTER TABLE "notice_deliveries"
    DROP CONSTRAINT
    "notice_deliveries_legal_document_id_91b8051f_fk_legal_doc";

ALTER TABLE "notice_deliveries"
    ADD CONSTRAINT "fk_notice_legal_document"
    FOREIGN KEY ("legal_document_id")
    REFERENCES "legal_documents" ("id")
    ON DELETE RESTRICT;


ALTER TABLE "notice_deliveries"
    DROP CONSTRAINT
    "notice_deliveries_request_id_d308a2dd_fk_rights_requests_id";

ALTER TABLE "notice_deliveries"
    ADD CONSTRAINT "fk_notice_request"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    ON DELETE CASCADE;
"""


REVERSE_SQL = """
-- ============================================================
-- NOTICE DELIVERIES
-- ============================================================

ALTER TABLE "notice_deliveries"
    DROP CONSTRAINT "fk_notice_request";

ALTER TABLE "notice_deliveries"
    ADD CONSTRAINT
    "notice_deliveries_request_id_d308a2dd_fk_rights_requests_id"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "notice_deliveries"
    DROP CONSTRAINT "fk_notice_legal_document";

ALTER TABLE "notice_deliveries"
    ADD CONSTRAINT
    "notice_deliveries_legal_document_id_91b8051f_fk_legal_doc"
    FOREIGN KEY ("legal_document_id")
    REFERENCES "legal_documents" ("id")
    DEFERRABLE INITIALLY DEFERRED;


-- ============================================================
-- IDENTITY VERIFICATIONS
-- ============================================================

ALTER TABLE "identity_verifications"
    DROP CONSTRAINT "fk_idv_verified_by";

ALTER TABLE "identity_verifications"
    ADD CONSTRAINT
    "identity_verifications_verified_by_id_566ffd46_fk_users_id"
    FOREIGN KEY ("verified_by_id")
    REFERENCES "users" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "identity_verifications"
    DROP CONSTRAINT "fk_idv_request";

ALTER TABLE "identity_verifications"
    ADD CONSTRAINT
    "identity_verificatio_request_id_f00e341d_fk_rights_re"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    DEFERRABLE INITIALLY DEFERRED;


-- ============================================================
-- TEMPORARY UPLOADS
-- ============================================================

ALTER TABLE "temporary_uploads"
    DROP CONSTRAINT "fk_tmp_promoted_request";

ALTER TABLE "temporary_uploads"
    ADD CONSTRAINT
    "temporary_uploads_promoted_request_id_1cc2d68a_fk_rights_re"
    FOREIGN KEY ("promoted_request_id")
    REFERENCES "rights_requests" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "temporary_uploads"
    DROP CONSTRAINT "fk_tmp_promoted_attachment";

ALTER TABLE "temporary_uploads"
    ADD CONSTRAINT
    "temporary_uploads_promoted_attachment__4a61d341_fk_request_a"
    FOREIGN KEY ("promoted_attachment_id")
    REFERENCES "request_attachments" ("id")
    DEFERRABLE INITIALLY DEFERRED;


-- ============================================================
-- REQUEST ATTACHMENTS
-- ============================================================

ALTER TABLE "request_attachments"
    DROP CONSTRAINT "fk_attachments_uploaded_by";

ALTER TABLE "request_attachments"
    ADD CONSTRAINT
    "request_attachments_uploaded_by_id_4e9a50eb_fk_users_id"
    FOREIGN KEY ("uploaded_by_id")
    REFERENCES "users" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "request_attachments"
    DROP CONSTRAINT "fk_attachments_request";

ALTER TABLE "request_attachments"
    ADD CONSTRAINT
    "request_attachments_request_id_8ccb01fd_fk_rights_requests_id"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "request_attachments"
    DROP CONSTRAINT "fk_attachments_representative";

ALTER TABLE "request_attachments"
    ADD CONSTRAINT
    "request_attachments_representative_id_2d4c4e8f_fk_subject_r"
    FOREIGN KEY ("representative_id")
    REFERENCES "subject_representatives" ("id")
    DEFERRABLE INITIALLY DEFERRED;
"""


class Migration(migrations.Migration):

    dependencies = [
        (
            "evidence",
            "0001_initial",
        ),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]
