# (C) Copyright 2024 European Centre for Medium-Range Weather Forecasts.
# This software is licensed under the terms of the Apache Licence Version 2.0
# which can be obtained at http://www.apache.org/licenses/LICENSE-2.0.
# In applying this licence, ECMWF does not waive the privileges and immunities
# granted to it by virtue of its status as an intergovernmental organisation
# nor does it submit to any jurisdiction.

import logging
import os
import random
import subprocess

from ..humanize import bytes_to_human
from . import BaseUpload

LOGGER = logging.getLogger(__name__)


def call_process(*args):

    proc = subprocess.Popen(
        " ".join(args),  # this is because of the && in the rsync command
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
    )
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        msg = f"{' '.join(args)} failed: {stderr}"
        raise RuntimeError(msg)

    return stdout.decode("utf-8").strip()


class RsyncUpload(BaseUpload):

    def _transfer_file(self, source, target, overwrite, resume, verbosity, config=None):

        assert target.startswith("ssh://")

        target = target[6:]
        hostname, path = target.split(":")

        if "+" in hostname:
            hostnames = hostname.split("+")
            hostname = hostnames[random.randint(0, len(hostnames) - 1)]

        size = os.path.getsize(source)

        if verbosity > 0:
            LOGGER.info(f"{self.action} {source} to {target} ({bytes_to_human(size)})")

        call_process(
            "rsync",
            "-av",
            "--partial",
            f"--rsync-path='mkdir -p {os.path.dirname(path)} && rsync'",
            source,
            f"{hostname}:{path}",
        )
        return size


class SshUpload(BaseUpload):
    """This class is not used in the current implementation, but it is left here for reference."""

    def _transfer_file(self, source, target, overwrite, resume, verbosity, config=None):

        assert target.startswith("ssh://")
        target = target[6:]

        hostname, path = target.split(":")

        size = os.path.getsize(source)

        if verbosity > 0:
            LOGGER.info(f"{self.action} {source} to {target} ({bytes_to_human(size)})")

        remote_size = None
        try:
            out = call_process("ssh", hostname, "stat", "-c", "%s", path)
            remote_size = int(out)
        except RuntimeError:
            remote_size = None

        if remote_size is not None:
            if remote_size != size:
                LOGGER.warning(
                    f"{target} already exists, but with different size, re-uploading (remote={remote_size}, local={size})"
                )
            elif resume:
                # LOGGER.info(f"{target} already exists, skipping")
                return size

        if remote_size is not None and not overwrite and not resume:
            raise ValueError(f"{target} already exists, use 'overwrite' to replace or 'resume' to skip")

        call_process("ssh", hostname, "mkdir", "-p", os.path.dirname(path))
        call_process("scp", source, f"{hostname}:{path}")

        return size


def upload(source, target, *, overwrite=False, resume=False, verbosity=1, progress=None, threads=1) -> None:
    # uploader = SshUpload()
    uploader = RsyncUpload()

    if os.path.isdir(source):
        uploader.transfer_folder(
            source=source,
            target=target,
            overwrite=overwrite,
            resume=resume,
            verbosity=verbosity,
            progress=progress,
            threads=threads,
        )
    else:
        uploader.transfer_file(
            source=source,
            target=target,
            overwrite=overwrite,
            resume=resume,
            verbosity=verbosity,
            progress=progress,
        )