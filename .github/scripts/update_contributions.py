"""
Uses the GitHub GraphQL contributionsCollection API to find all public repos
the user has contributed to (commits, PRs, issues), then deduplicates to
unique owners/orgs (excluding the user themselves) and renders them as
inline badges that wrap naturally.
"""

import os
import re
import requests

USERNAME = os.environ["GITHUB_USERNAME"]
TOKEN = os.environ["GITHUB_TOKEN"]

GRAPHQL_URL = "https://api.github.com/graphql"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

START_MARKER = "<!-- CONTRIBUTIONS:START -->"
END_MARKER   = "<!-- CONTRIBUTIONS:END -->"
README_PATH  = "README.md"

# Orgs: cool blues, greens, purples  |  Individual users: warm amber, orange, red
ORG_COLORS  = ["0EA5E9", "10B981", "16A34A", "8B5CF6", "6366F1", "06B6D4", "A78BFA", "34D399"]
USER_COLORS = ["F59E0B", "F97316", "EF4444", "FB923C", "FBBF24", "E11D48", "DC2626", "D97706"]

GRAPHQL_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      commitContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner isPrivate owner { login __typename } }
      }
      pullRequestContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner isPrivate owner { login __typename } }
      }
      issueContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner isPrivate owner { login __typename } }
      }
    }
  }
}
"""


def fetch_contributed_owners() -> dict[str, str]:
    """Return ordered dict of {owner_login: 'Organization'|'User'} the user
    contributed to on public repos, excluding their own account."""
    resp = requests.post(
        GRAPHQL_URL,
        json={"query": GRAPHQL_QUERY, "variables": {"login": USERNAME}},
        headers=HEADERS,
    )
    resp.raise_for_status()
    data = resp.json()

    collection = data["data"]["user"]["contributionsCollection"]
    buckets = [
        collection["commitContributionsByRepository"],
        collection["pullRequestContributionsByRepository"],
        collection["issueContributionsByRepository"],
    ]

    seen_owners: dict[str, str] = {}  # login -> __typename
    for bucket in buckets:
        for entry in bucket:
            repo = entry["repository"]
            if repo["isPrivate"]:
                continue
            owner_login = repo["owner"]["login"]
            owner_type  = repo["owner"]["__typename"]  # 'Organization' or 'User'
            if owner_login.lower() == USERNAME.lower():
                continue
            seen_owners.setdefault(owner_login, owner_type)

    return seen_owners


def build_markdown(owners: dict[str, str]) -> str:
    if not owners:
        return "_No external public contributions found yet._\n"

    # Sort: organizations first, then individual users
    orgs  = [(login, t) for login, t in owners.items() if t == "Organization"]
    users = [(login, t) for login, t in owners.items() if t != "Organization"]
    ordered = orgs + users

    badges = []
    org_idx  = 0
    user_idx = 0
    for login, owner_type in ordered:
        if owner_type == "Organization":
            color = ORG_COLORS[org_idx % len(ORG_COLORS)]
            org_idx += 1
        else:
            color = USER_COLORS[user_idx % len(USER_COLORS)]
            user_idx += 1
        label     = login.replace("-", "--").replace("_", "__")
        badge_url = (
            f"https://img.shields.io/badge/{label}-{color}"
            f"?style=for-the-badge&logo=github&logoColor=white"
        )
        owner_url = f"https://github.com/{login}"
        badges.append(
            f'<a href="{owner_url}"><img src="{badge_url}" alt="{login}"/></a>'
        )

    return "<p>\n" + "\n".join(badges) + "\n</p>\n"


def update_readme(new_block: str) -> None:
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        re.DOTALL,
    )
    if not pattern.search(content):
        raise RuntimeError(f"Markers not found in {README_PATH}")

    updated = pattern.sub(
        f"{START_MARKER}\n{new_block}{END_MARKER}", content
    )

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(updated)

    print(f"README updated — {len(owners)} unique owners written.")


if __name__ == "__main__":
    print(f"Fetching contributions for {USERNAME} ...")
    owners = fetch_contributed_owners()
    orgs  = [k for k, v in owners.items() if v == "Organization"]
    users = [k for k, v in owners.items() if v != "Organization"]
    print(f"Orgs ({len(orgs)}): {orgs}")
    print(f"Users ({len(users)}): {users}")
    markdown = build_markdown(owners)
    update_readme(markdown)
