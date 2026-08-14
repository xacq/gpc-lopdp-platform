from django.db import models


class CIEmailField(models.EmailField):
    """
    EmailField backed by PostgreSQL CITEXT.

    VINESA PostgreSQL Blueprint v1.4 requires users.email
    to use the CITEXT data type.
    """

    def db_type(self, connection):
        if connection.vendor == "postgresql":
            return "citext"

        return super().db_type(connection)