from peewee import CharField, DateTimeField, IntegerField, Model, SqliteDatabase

from src.config import DB_PATH

db = SqliteDatabase(DB_PATH)


class Person(Model):
    uniqueId = CharField(primary_key=True)
    name = CharField(null=False)
    admissionNumber = CharField(null=True)
    roomId = CharField(null=True)
    pictureFileName = CharField(null=False)
    personType = CharField(null=False)  # Cadet, Employee
    syncedAt = DateTimeField(null=True)

    class Meta:
        database = db


class Room(Model):
    roomId = CharField(primary_key=True)
    roomName = CharField()
    syncedAt = DateTimeField()

    class Meta:
        database = db


class CadetAttendance(Model):
    personId = CharField()
    attendanceTimeStamp = DateTimeField()
    sessionId = CharField()
    syncedAt = DateTimeField()

    class Meta:
        database = db


class Session(Model):
    id = CharField(primary_key=True)
    name = CharField()
    startTimestamp = DateTimeField()
    plannedEndTimestamp = DateTimeField()
    plannedDurationInMinutes = IntegerField()
    actualEndTimestamp = DateTimeField(null=True)
    syncedAt = DateTimeField(null=True)

    class Meta:
        database = db


class FaceIdentityMap(Model):
    """Mapping between InspireFace FeatureHub identity IDs and our Person.uniqueId.

    Embeddings persist inside InspireFace FeatureHub tables in the same SQLite DB.
    We store only the mapping so we can resolve recognitions to people.
    """

    hubId = IntegerField(primary_key=True)
    personId = CharField(unique=True)

    class Meta:
        database = db


def ensure_db_schema() -> None:
    """Create tables if they do not already exist."""
    db.connect(reuse_if_open=True)
    db.create_tables(
        [Person, Room, CadetAttendance, Session, FaceIdentityMap], safe=True
    )
    db.close()


if __name__ == "__main__":
    ensure_db_schema()
