from django.db import models


class CITextField(models.TextField):
    """
    PostgreSQL CITEXT-backed text field.
    """

    def db_type(self, connection):
        if connection.vendor == "postgresql":
            return "citext"

        return super().db_type(connection)


class CIEmailField(models.EmailField):
    """
    EmailField backed by PostgreSQL CITEXT.
    """

    def db_type(self, connection):
        if connection.vendor == "postgresql":
            return "citext"

        return super().db_type(connection)


class FixedCharField(models.CharField):
    """
    Fixed-length CHAR field for PostgreSQL.

    Used primarily for SHA-256/HMAC-SHA-256 hexadecimal
    representations defined as CHAR(64) in the VINESA
    PostgreSQL 18 Blueprint v1.5.
    """

    def db_type(self, connection):
        if connection.vendor == "postgresql":
            return f"char({self.max_length})"

        return super().db_type(connection)