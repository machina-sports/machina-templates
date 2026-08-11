"""Build the release artefacts so that building them twice gives the same bytes.

Run it, never import it as ``packaging.…`` — for the same reason ``build.py``
beside it is loaded by path: a regular ``packaging`` package at a repository root
would shadow the ``packaging`` distribution setuptools itself resolves.

    SOURCE_DATE_EPOCH=<epoch> python packaging/machina_sports_canonical/release.py . dist

**Why this exists.** The release checklist in ``docs/iptc/RELEASING.md`` says to
compare the digest PyPI serves with the digest that was reviewed. That step is
unperformable unless one commit builds to one set of bytes, and it did not:

- The **wheel** stores an mtime per zip entry. ``SOURCE_DATE_EPOCH`` alone fixes
  this — ``wheel`` reads it and stamps every entry with it — which is why nothing
  below touches the wheel.
- The **sdist** ignores ``SOURCE_DATE_EPOCH`` completely on this backend. Its tar
  members carry the source files' own mtimes, the generated ``PKG-INFO``,
  ``setup.cfg`` and ``egg-info`` members carry the time the build ran, and every
  member carries the uid, gid and user name of whoever ran it. So two builds of
  one commit differed, and a build on CI could never match a build on a reviewer's
  machine.

**What it does to the sdist, and what it refuses to do.** It rewrites the archive
with each member's *machine* facts replaced by fixed values: the release epoch for
every mtime, uid and gid 0 with empty owner names, and one mode for files and one
for directories. Nothing else changes — the member list, the member order and
every payload byte are carried across unaltered, and
``tests/test_iptc_canonical_package.py`` asserts exactly that. It does not touch
the canonical source, it does not rewrite a single payload, and it does not add,
drop or reorder a member. A release artefact must be the same bytes wherever it is
built, and mtime, ownership and umask are properties of the builder, not of the
release.

**Fail closed.** ``SOURCE_DATE_EPOCH`` is required rather than defaulted: a
release built without it is silently irreproducible, which is the exact failure
this file exists to remove. A member that is neither a regular file nor a
directory is refused rather than normalized, because an sdist for this
distribution has no reason to contain one and guessing what to do with it is how a
release grows a surprise.
"""

from __future__ import annotations

import gzip
import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path

#: The permissions every member of the released sdist carries, whatever the
#: builder's umask happened to be.
NORMALIZED_FILE_MODE = 0o644
NORMALIZED_DIRECTORY_MODE = 0o755

#: The archive dialect the release is written in, chosen here rather than
#: inherited from whatever the backend and the reader negotiated. Sub-second
#: mtimes make the backend emit pax headers; the members below are rebuilt with
#: integer fields and no pax headers at all, so the two builds cannot differ in
#: their header dialect either.
ARCHIVE_FORMAT = tarfile.PAX_FORMAT

#: Compression level. Fixed because the digest depends on it.
COMPRESSION_LEVEL = 9


def source_date_epoch(environment: dict = None) -> int:
    """The release epoch, from the environment, required.

    Not defaulted to "now" and not defaulted to the epoch of the commit being
    built: both would produce an artefact that looks fine and cannot be compared
    with anything.
    """
    raw = (os.environ if environment is None else environment).get(
        "SOURCE_DATE_EPOCH", "")
    if not raw.isdigit():
        raise ValueError(
            "SOURCE_DATE_EPOCH must be set to the release epoch (an integer); "
            "got {0!r}. A release built without it cannot be reproduced.".format(
                raw))
    return int(raw)


def normalized_member(member: tarfile.TarInfo, epoch: int) -> tarfile.TarInfo:
    """``member`` with the builder's facts replaced by the release's.

    Built fresh rather than mutated so that nothing the reader attached — pax
    headers holding a float mtime, in particular — survives into the release.
    """
    if not (member.isfile() or member.isdir()):
        raise ValueError(
            "the sdist for this distribution contains only files and "
            "directories; refusing to normalize {0!r} (type {1!r})".format(
                member.name, member.type))
    rewritten = tarfile.TarInfo(member.name)
    rewritten.type = member.type
    rewritten.size = member.size
    rewritten.mtime = epoch
    rewritten.uid = 0
    rewritten.gid = 0
    rewritten.uname = ""
    rewritten.gname = ""
    rewritten.mode = (NORMALIZED_DIRECTORY_MODE if member.isdir()
                      else NORMALIZED_FILE_MODE)
    return rewritten


def normalize_sdist(path: Path, epoch: int) -> Path:
    """Rewrite the sdist at ``path`` in place, payloads and order untouched.

    The gzip header carries an mtime and a stored filename of its own, so the
    container is written explicitly instead of through ``tarfile``'s ``w:gz``,
    which would stamp it with the current time.
    """
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        payloads = [archive.extractfile(member).read() if member.isfile() else None
                    for member in members]
    temporary = path.with_name(path.name + ".reproducible")
    with open(temporary, "wb") as raw:
        with gzip.GzipFile(filename=path.stem, mode="wb", fileobj=raw,
                           mtime=epoch,
                           compresslevel=COMPRESSION_LEVEL) as compressed:
            with tarfile.open(fileobj=compressed, mode="w",
                              format=ARCHIVE_FORMAT) as rewritten:
                for member, payload in zip(members, payloads):
                    entry = normalized_member(member, epoch)
                    rewritten.addfile(
                        entry, None if payload is None else io.BytesIO(payload))
    os.replace(temporary, path)
    return path


def build(source: Path, outdir: Path, epoch: int,
          python: str = None) -> subprocess.CompletedProcess:
    """One ``python -m build``, then the sdist made reproducible.

    ``--no-isolation`` for the reason the proof suite uses it: the frontend and
    the backend are the exactly pinned ones already installed from
    ``requirements-iptc-build.txt``, so the build is offline and the tooling is
    the tooling this repository recorded.
    """
    result = subprocess.run(
        [python or sys.executable, "-m", "build", "--no-isolation",
         "--outdir", str(outdir), str(source)],
        env=dict(os.environ, SOURCE_DATE_EPOCH=str(epoch)))
    if result.returncode != 0:
        return result
    for sdist in sorted(Path(outdir).glob("*.tar.gz")):
        normalize_sdist(sdist, epoch)
    return result


def main(argv: list) -> int:
    if len(argv) != 2:
        sys.stderr.write(
            "usage: SOURCE_DATE_EPOCH=<epoch> python {0} SOURCE OUTDIR\n".format(
                Path(__file__).name))
        return 2
    return build(Path(argv[0]), Path(argv[1]), source_date_epoch()).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
