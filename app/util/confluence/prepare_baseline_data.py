import argparse
import csv
import json
from collections import OrderedDict

from util.api.confluence_clients import ConfluenceRestClient
from util.common_util import print_timing
from util.conf import CONFLUENCE_SETTINGS
from util.project_paths import CONFLUENCE_PAGES

# Seeds baselines for the "Baselines for Confluence" (OBSS) app so that the
# JMeter standalone_extension actions (view / compare / export) have real data
# to work against. Runs automatically in confluence.yml -> services -> prepare,
# right after confluence_prepare_data.py (it depends on pages.csv).

BASELINES_CSV = CONFLUENCE_PAGES.parent / "baselines.csv"
CREATE_BASELINE_PATH = "/rest/baseline/1.0/baselineService/createBaseline"
SPACE_API_PATH = "/rest/api/space/{space_key}"

# Two fixed baseline names per space. Compare needs two baselines; re-runs that
# hit an existing name are treated as already-seeded.
BASELINE_NAME_1 = "perf-seed-1"
BASELINE_NAME_2 = "perf-seed-2"

DEFAULT_SPACES_LIMIT = 40
DEFAULT_PAGES_PER_BASELINE = 3


def __parse_args():
    parser = argparse.ArgumentParser(description="Seed Baselines-for-Confluence data for perf tests.")
    parser.add_argument("--spaces-limit", type=int, default=DEFAULT_SPACES_LIMIT,
                        help="Max number of distinct spaces to seed.")
    parser.add_argument("--pages-per-baseline", type=int, default=DEFAULT_PAGES_PER_BASELINE,
                        help="How many pages from each space to include in a baseline.")
    return parser.parse_args()


def __read_spaces_from_pages(spaces_limit):
    """Return OrderedDict[space_key] -> list[page_id] from pages.csv (id,space_key,template_id)."""
    if not CONFLUENCE_PAGES.exists():
        raise SystemExit(f"{CONFLUENCE_PAGES} not found - run confluence_prepare_data.py first.")
    spaces = OrderedDict()
    with open(CONFLUENCE_PAGES, newline="", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if len(row) < 2:
                continue
            page_id, space_key = row[0].strip(), row[1].strip()
            if not page_id.isdigit():
                continue
            if space_key not in spaces and len(spaces) >= spaces_limit:
                continue
            spaces.setdefault(space_key, [])
            if page_id not in spaces[space_key]:
                spaces[space_key].append(page_id)
    return spaces


def __get_space_id(client, space_key):
    url = f"{client.host}{SPACE_API_PATH.format(space_key=space_key)}"
    resp = client.session.get(url, auth=client.base_auth, headers=client.headers,
                              verify=client.verify, timeout=client.requests_timeout)
    if resp.status_code != 200:
        print(f"  ! could not resolve space id for {space_key} (HTTP {resp.status_code})")
        return None
    try:
        return str(resp.json()["id"])
    except (ValueError, KeyError):
        print(f"  ! unexpected space payload for {space_key}: {resp.text[:200]}")
        return None


def __create_baseline(client, space_key, baseline_name, page_ids):
    """Create one version-based baseline over the given page ids. True on success or existing."""
    url = f"{client.host}{CREATE_BASELINE_PATH}"
    headers = dict(client.headers)
    headers["X-Atlassian-Token"] = "no-check"
    # Server gson lowercases field names that lack @SerializedName, so these two
    # keys MUST be all-lowercase ("selectallpages"/"fullyselectedpages") or the
    # page selection is dropped and the API returns "You must select at least one page".
    body = {
        "baselineName": baseline_name,
        "spaceKey": space_key,
        "creationType": "version-based",
        "baselineKeyword": "",
        "selectallpages": "false",
        "fullyselectedpages": [{"id": str(pid), "version": "latest"} for pid in page_ids],
    }
    resp = client.session.post(url, data=json.dumps(body), auth=client.base_auth, headers=headers,
                               verify=client.verify, timeout=client.requests_timeout)
    if resp.status_code == 200:
        return True
    body_text = (resp.text or "").lower()
    if resp.status_code == 400 and ("already" in body_text or "exist" in body_text):
        print(f"  = baseline '{baseline_name}' already exists in {space_key}, reusing")
        return True
    print(f"  ! createBaseline '{baseline_name}' in {space_key} failed: "
          f"HTTP {resp.status_code} {resp.text[:200]}")
    return False


def __write_baselines_csv(rows):
    BASELINES_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(BASELINES_CSV, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)


def __standalone_extension_enabled():
    try:
        return int(CONFLUENCE_SETTINGS.get_property("standalone_extension") or 0) > 0
    except Exception:
        return False


@print_timing('Baseline data preparation')
def main():
    if not __standalone_extension_enabled():
        print("standalone_extension weight is 0 (disabled) - skipping baseline seeding.")
        return

    args = __parse_args()
    url = CONFLUENCE_SETTINGS.server_url
    print("Server url: ", url)
    client = ConfluenceRestClient(url, CONFLUENCE_SETTINGS.admin_login, CONFLUENCE_SETTINGS.admin_password,
                                  verify=CONFLUENCE_SETTINGS.secure)

    spaces = __read_spaces_from_pages(args.spaces_limit)
    if not spaces:
        raise SystemExit("No spaces found in pages.csv.")

    print(f"Seeding baselines into {len(spaces)} space(s) ...")
    rows = []
    for space_key, page_ids in spaces.items():
        selected = page_ids[: args.pages_per_baseline]
        if not selected:
            continue
        space_id = __get_space_id(client, space_key)
        if space_id is None:
            continue
        ok1 = __create_baseline(client, space_key, BASELINE_NAME_1, selected)
        ok2 = __create_baseline(client, space_key, BASELINE_NAME_2, selected)
        if ok1 and ok2:
            rows.append([space_key, space_id, selected[0], BASELINE_NAME_1, BASELINE_NAME_2])
        else:
            print(f"  - {space_key}: not fully seeded, excluded from baselines.csv")

    if not rows:
        raise SystemExit("No spaces were fully seeded - check license, read-only mode, and admin permissions.")

    __write_baselines_csv(rows)
    print(f"Finished. Wrote {len(rows)} row(s) to {BASELINES_CSV}")


if __name__ == "__main__":
    main()
