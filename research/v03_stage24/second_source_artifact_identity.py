"""Select exact immutable second-source GitHub artifact metadata from API listing.

No network in this module. Caller retrieves authentic GitHub Actions artifact list.
Fail closed on duplicates, expired artifacts, or wrong source run association.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from second_trial_artifact_bridge import verify_second_run


def select_source_artifact(run_meta, listing):
    rid=verify_second_run(run_meta)
    if type(listing) is not dict or type(listing.get("artifacts")) is not list:
        raise ValueError("INVALID_GITHUB_ARTIFACT_LIST")
    name=f"luca-v03-second-prospective-{rid}"
    matches=[a for a in listing["artifacts"] if type(a) is dict and a.get("name")==name]
    if len(matches)!=1:
        raise ValueError("MISSING_OR_DUPLICATE_SOURCE_ARTIFACT")
    artifact=matches[0]
    verify_second_run(run_meta,artifact)
    aid=artifact.get("id")
    if type(aid) is not int or aid<=0 or artifact.get("size_in_bytes",0)<=0:
        raise ValueError("EMPTY_OR_INVALID_SOURCE_ARTIFACT")
    return artifact


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--run-metadata",required=True)
    p.add_argument("--artifacts-list",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    def load(path):
        f=Path(path)
        if not f.is_file() or f.stat().st_size>2_000_000:
            raise ValueError("MISSING_OR_OVERSIZE_METADATA")
        return json.loads(f.read_text(encoding="utf8"))
    meta=select_source_artifact(load(a.run_metadata),load(a.artifacts_list))
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf8") as f:
        json.dump(meta,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print("SECOND_SOURCE_ARTIFACT_ID_VERIFIED; NOT_VALIDATED; NO_ORDERS")


if __name__=="__main__":
    main()
