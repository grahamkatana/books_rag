from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# SQLite's batch-alter mode (used for ALTER TABLE support, since SQLite
# doesn't support most ALTER TABLE forms natively) needs every constraint
# to have an explicit name to recreate tables correctly. Without this,
# autogenerate produces unnamed foreign keys that crash with
# "Constraint must have a name" the moment a migration needs to add one
# to an existing table. This naming convention is the standard fix --
# every constraint gets a deterministic name from here on, automatically.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
