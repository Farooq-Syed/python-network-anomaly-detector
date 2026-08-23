import hashlib
from pathlib import Path

from benchmark_compare import sha256_file


def test_sha256_file_matches_standard_library(tmp_path: Path) -> None:
    sample = tmp_path / "sample.csv"
    payload = b"feature,label\n1,0\n2,1\n"
    sample.write_bytes(payload)

    assert sha256_file(sample) == hashlib.sha256(payload).hexdigest()
