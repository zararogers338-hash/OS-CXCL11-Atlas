# Shared helpers for all rule files.

SEED = config["project"]["seed"]
BULK = config["datasets"]["bulk"]
GEO_BULK = [k for k, v in BULK.items() if v["source"] == "GEO"]

# Each analysis rule that records statistics appends its fragment path here;
# collect_stats merges them into results/stats.json.
STAT_FRAGMENTS = []


def stat_fragment(name):
    path = f"results/stats/{name}.json"
    STAT_FRAGMENTS.append(path)
    return path
