# Blind-Review Anonymization Checklist

Follow before submitting to a venue that requires anonymized reviewers. This is a checklist,
not an automated tool — several items need a human decision.

## Paths and machine-specific strings

- [ ] The new experiment scripts use `Path(__file__)` / `Path.cwd()`, so no absolute
      `D:\...` or `C:\...` paths are hard-coded in code. (Verified: `rg "D:\\\\|C:\\\\Users"`
      returns only author-attribution lines in the docs, not code paths.)
- [ ] If embedding provenance, strip machine-specific `input_path` values from the JSON
      artifacts before submission, or replace them with relative paths.
- [ ] Committed data files carry no host-specific metadata in their headers.

## Author attribution

- [ ] `PAPER.md` and `REFERENCES.md` carry the author's name and affiliation in the
      authorship and AI-use notes. Decide whether the venue wants these kept (single-author
      portfolio) or removed for blind review.
- [ ] `README.md` badge links to `github.com/Farooq-Syed/...`; this leaks the identity.
      For a blind submission, either remove the badge or rewrite the README.

## Dependencies and reproducibility

- [ ] `requirements-lock.txt` pins exact versions for a clean reproduction.
- [ ] `reproducibility_config.json` records all seeds, split definitions, and dataset
      preparation parameters.
- [ ] Dataset download/checksum path is documented in `scripts/download_datasets.py` and
      `docs/real_dataset_guide.md`.

## Sensitive data

- [ ] The downloaded public benchmarks (UNSW-NB15, CIC-IDS2017/2018) are research datasets
      used only for evaluation; confirm the re-use terms of each source.
- [ ] No credentials, tokens, or private network identifiers appear in the committed data.
