import click
import os
import math
from random import Random

from .schemas.user import UserCreate
from .ops.user import create_user

from .tools import ffmpeg
from .db.database import init_db, connect_db
from .db.models import AudioFile, Sample, Base, Role
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError


DATASETS_DIR = "datasets"


@click.group()
def cli():
    pass


@cli.command()
@click.option("--create-test-user", is_flag=True, default=False)
def initdb(create_test_user):
    click.echo("Initialized the database")
    init_db()
    if create_test_user:
        from .service import get_db

        session = next(get_db())
        try:
            create_user(session, UserCreate(name="testuser", password="pass"))
            print("Created user 'testuser' with password 'pass'")
            create_user(
                session,
                UserCreate(name="testadmin", password="pass"),
                role=Role.admin,
            )
            print("Created user 'testadmin' with password 'pass'")
        except IntegrityError:
            click.echo("'testuser' already exists")


@cli.command("sync-datasets")
def sync_datasets():
    click.echo(f"Scanninng {DATASETS_DIR}")
    filenames = []
    for root, dir_names, file_names in os.walk(DATASETS_DIR):
        for name in file_names:
            if name.endswith((".wav", ".m4a")):
                filenames.append(os.path.join(root, name))
    click.echo(f"Found {len(filenames)} files")
    # filenames = filenames[-10:]

    session = Session(db.connect())

    with session.begin():
        existing = set(af.name for af in session.query(AudioFile).all())
    audio_files = []
    skipped = 0
    for filename in filenames:
        name = os.path.relpath(filename, DATASETS_DIR)
        if name in existing:
            skipped += 1
            continue
        duration = ffmpeg.get_duration(filename)
        audio_files.append(AudioFile(name=name, duration=duration))

    with session.begin():
        session.bulk_save_objects(audio_files)

    click.echo(f"{len(audio_files)} new files; {skipped} skipped")


@cli.command("create-samples")
@click.argument("name", type=str)
@click.argument("count", type=int)
@click.argument("duration", type=float)
@click.option("--seed", type=str, default="Ax389a684067za5e1c2172c686958565e8m")
def create_samples(name: str, count: int, duration: float, seed: str):
    engine = db.connect()
    Base.metadata.create_all(engine)
    session = Session(engine)
    rnd = Random(seed)
    with session.begin():
        audio_files = (
            session.query(AudioFile).where(AudioFile.duration >= duration).all()
        )

        sample_set = SampleSet(name=name)
        session.add(sample_set)

        samples = []
        weights = [math.sqrt(af.duration / duration) for af in audio_files]
        for af in rnd.choices(audio_files, weights=weights, k=count):
            start = rnd.random() * (af.duration - duration)
            sample = Sample(
                sample_set_id=sample_set.id,
                audio_file=af.name,
                start=start,
                duration=duration,
            )
            samples.append(sample)
        session.add_all(samples)


if __name__ == "__main__":
    cli()
