import os
import subprocess

import pytest

from app.core import private_files


def test_private_file_is_owner_only_and_exclusive(tmp_path, assert_private_file):
    path = tmp_path / 'private snapshot.json'
    with private_files.open_private_text(path) as handle:
        handle.write('synthetic sensitive data')
    assert_private_file(path)
    with pytest.raises(FileExistsError):
        private_files.open_private_text(path)
    assert path.read_text() == 'synthetic sensitive data'


@pytest.mark.skipif(os.name != 'nt', reason='Windows DACL setup')
def test_permission_failure_removes_empty_file_before_data_can_be_written(tmp_path, monkeypatch):
    path = tmp_path / 'snapshot.json'

    def deny_access(_path):
        assert path.read_bytes() == b''
        raise subprocess.CalledProcessError(1, 'icacls')

    monkeypatch.setattr(private_files, '_restrict_windows_access', deny_access)
    with pytest.raises(subprocess.CalledProcessError):
        with private_files.open_private_text(path) as handle:
            handle.write('must never be written')
    assert not path.exists()
