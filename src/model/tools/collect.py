# Collects random active rated Codeforces users for datasets.

import json
import random

import requests


RATED_LIST_URL = "https://codeforces.com/api/user.ratedList"
USER_COUNT = 50


def get_rated_users(active_only=True):
    response = requests.get(
        RATED_LIST_URL,
        params={"activeOnly": str(active_only).lower()},
        timeout=20,
    )
    response.raise_for_status()

    data = response.json()
    if data.get("status") != "OK":
        raise RuntimeError(data.get("comment", "Codeforces API Error"))

    return data["result"]


def main():
    users = get_rated_users(active_only=True)
    sample = random.sample(users, k=min(USER_COUNT, len(users)))

    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(sample)} users to users.json")


if __name__ == "__main__":
    main()
